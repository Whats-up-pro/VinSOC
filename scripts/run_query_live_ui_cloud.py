"""Guarded Linux execution requested from the local mentor UI."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
from pathlib import Path

from evaluation.finalization.cloud_window import GitHubAPI
from evaluation.finalization.query_cloud import QueryDemoGitHubStore
from scripts.run_query_demo_cloud import (
    enter_delegated_cgroup,
    prepare_private_inputs,
    verify_cloud_ci,
    write_json,
)
from scripts.run_vinsoc_query_acceptance import run_live, run_preflight
from scripts.vinsoc_live_protocol import (
    ROOT,
    AllocationRegistry,
    catalog,
    reconcile_allocation,
    request_limit,
    validate_request,
)


class LiveUiStore(QueryDemoGitHubStore):
    def __init__(self, *args, cap, **kwargs):
        super().__init__(*args,**kwargs)
        self.cap = cap

    @staticmethod
    def _tag_component(window_id):
        if not re.fullmatch(
                r'text2sql-integration-(?:20261008-demo-[A-Za-z0-9_-]+|20261014-protocol2-(?:calibration|evaluation|pipeline))',
                window_id):
            raise ValueError('CLOUD_WINDOW_ID_INVALID')
        return 'vinsoc-query-ui-'+window_id

    def checkpoint(self, request_number, phase, event):
        if not self.claimed or type(request_number) is not int or not 1 <= request_number <= self.cap:
            raise ValueError('REMOTE_CHECKPOINT_INVALID')
        if phase not in ('begin','end') or not isinstance(event,dict) or 'request' in event or 'response' in event:
            raise ValueError('REMOTE_CHECKPOINT_INVALID')
        self._tag(f'{self.tag_prefix}-request-{request_number}-{phase}',
                  {'run_id':self.run_id,'request_number':request_number,'phase':phase,'event':event})


def private_inputs(request, env, ci_id, allocation):
    case_id = request['case_id'] or catalog('demo')[0]['case_id']
    auth = {**request,'scope':request['scope'],'case_id':case_id,
            'allocation_id':request['execution_id'], 'known_prior_cost_usd':allocation['known_usd'],
            'remaining_allocation_usd':allocation['remaining_usd'],'unknown_exposure_usd':0}
    inputs = prepare_private_inputs(
        auth, env, ci_id, verified_prior=allocation['receipts'],
        authorized_limit_usd=request['limit_usd'])
    inputs['budget'].update(authorization_scope=request['scope'],
        decision_reference=(
            'explicit-user-all-official-scopes-20261014-cumulative-cap-'+str(request['limit_usd'])+'-USD'))
    if request['scope'] != 'demo':
        account = inputs['account']
        reference = Path(account['reconciliation_reference']['path'])
        data = json.loads(reference.read_text())
        data['scope_states'] = {s:'unconsumed_or_gate_pending' for s in ('calibration','evaluation','pipeline')}
        write_json(reference,data)
        account['reconciliation_reference']['sha256'] = hashlib.sha256(reference.read_bytes()).hexdigest()
        lock = ROOT/'results/evaluation_v1/text2sql_integration_v1/selection_lock.json'
        if lock.is_file():
            selection_sha256 = json.loads(lock.read_text(encoding='utf-8')).get('selection_sha256')
            if not isinstance(selection_sha256, str) or not re.fullmatch(r'[a-f0-9]{64}', selection_sha256):
                raise ValueError('CALIBRATION_SELECTION_LOCK_REQUIRED')
            inputs['identities']['selection_lock_path'] = str(lock)
            inputs['identities']['selection_sha256'] = selection_sha256
    return inputs


def run(mode, output_dir, env, *, api_factory=GitHubAPI):
    output = Path(output_dir)
    if output.exists():
        raise ValueError('CLOUD_OUTPUT_ALREADY_EXISTS')
    public,private = output/'public',output/'private'
    public.mkdir(parents=True)
    private.mkdir(parents=True)
    control = {'status':'blocked','attempted':0,'received':0,'client_created':False,
               'cost_unknown':False,'window_claimed':False,'new_run':True}
    registry = request = store = release = None
    allocation_claimed = False
    try:
        required = ('GITHUB_TOKEN','GITHUB_SHA','GITHUB_RUN_ID','GITHUB_CI_RUN_ID',
                    'VINSOC_LIVE_UI_REQUEST','VINSOC_LIVE_UI_EXECUTION_ID','VINSOC_GPT5_DOC','VINSOC_GPT41_DOC')
        if any(not env.get(k) for k in required):
            raise ValueError('CLOUD_PRIVATE_INPUTS_MISSING')
        request = validate_request(json.loads(env['VINSOC_LIVE_UI_REQUEST']),mode=mode)
        control.update(request=request,implementation_sha=env['GITHUB_SHA'],ci_run_id=request['ci_run_id'])
        if (request['head_sha'] != env['GITHUB_SHA'] or str(request['ci_run_id']) != env['GITHUB_CI_RUN_ID']
                or request['execution_id'] != env['VINSOC_LIVE_UI_EXECUTION_ID']
                or env.get('OPENAI_BASE_URL')):
            raise ValueError('UI_REQUEST_IDENTITY_MISMATCH')
        api = api_factory(env['GITHUB_TOKEN'])
        ci_id = verify_cloud_ci(api,env)
        registry = AllocationRegistry(api,sha=env['GITHUB_SHA'],run_id=env['GITHUB_RUN_ID'])
        allocation = reconcile_allocation(registry.entries(), limit_usd=request['limit_usd'])
        control.update(request=request,implementation_sha=env['GITHUB_SHA'],ci_run_id=ci_id,
                       prior_cost_usd=allocation['known_usd'],known_usd=allocation['known_usd'],
                       remaining_cap_usd=allocation['remaining_usd'],current_run_cost_usd=0.0)
        selected = {'case_id':request['case_id'],'question':request['question']} if request['scope'] == 'demo' else None
        inputs = private_inputs(request,env,ci_id,allocation)
        execution = request['execution_id'] if request['scope'] == 'demo' else None
        checked = run_preflight(request['scope'],request['condition'],inputs,selected_input=selected,execution_id=execution)
        release = checked['release']
        write_json(private/'release.json',checked)
        safe = json.loads(json.dumps(checked))
        safe['release'].pop('gate_inputs',None)
        write_json(public/'preflight.json',safe)
        control.update(preflight_status=release['status'],gate_reasons=release['reasons'],
                       cost_ceiling_usd=release['new_cost_ceiling_usd'],role_caps=release['role_caps'],
                       window_id=release['window_id'])
        if not release['authorized']:
            raise ValueError('LIVE_UI_PREFLIGHT_BLOCKED')
        store = LiveUiStore(api,implementation_sha=env['GITHUB_SHA'],run_id=env['GITHUB_RUN_ID'],cap=request_limit(request))
        if store._exists(store._tag_component(release['window_id'])):
            raise ValueError('WINDOW_ALREADY_USED')
        if mode == 'preflight':
            control['status'] = 'preflight_pass'
            return control
        if not env.get('OPENAI_API_KEY'):
            raise ValueError('OFFICIAL_KEY_REQUIRED')
        verify_cloud_ci(api,env)
        registry.append(request,'begin',{'prior_cost_usd':allocation['known_usd'],
                        'reserved_ceiling_usd':release['new_cost_ceiling_usd']})
        allocation_claimed = True
        control['status'] = 'running'
        write_json(public/'cloud_run.json',control)
        report = run_live(release,public/'live',selected_input=selected,remote_store=store)
        known = report.get('known_usd',allocation['known_usd'])
        control.update(status=report['status'],attempted=report.get('attempted',0),
                       received=report.get('received',0),client_created=report.get('client_created',False),
                       window_claimed=store.claimed,cost_unknown=report.get('cost_unknown',False),
                       known_usd=known,current_run_cost_usd=known-allocation['known_usd'],
                       remaining_cap_usd=request['limit_usd']-known,official_eligible=False)
        if report.get('failure_category'):
            control['failure_category'] = report['failure_category']
        return control
    except Exception as error:
        value = str(error) if isinstance(error,ValueError) else type(error).__name__
        control['failure_category'] = value if re.fullmatch(r'[A-Z0-9_]{1,100}',value) else type(error).__name__
        if allocation_claimed:
            control['cost_unknown'] = True
        return control
    finally:
        if release is not None:
            window = Path.home()/'.vinsoc/live-windows'/release['window_id']
            for name in ('claim.json','ledger.json'):
                if (window/name).is_file():
                    shutil.copy2(window/name,private/name)
            if (window/'ledger.json').is_file():
                ledger = json.loads((window/'ledger.json').read_text())
                prior = control['prior_cost_usd']
                control.update(known_usd=ledger['known_usd'],current_run_cost_usd=ledger['known_usd']-prior,
                               remaining_cap_usd=request['limit_usd']-ledger['known_usd'],
                               cost_unknown=ledger['cost_unknown'],
                               attempted=ledger['attempted'],received=ledger['received'])
        write_json(public/'cloud_run.json',control)
        if allocation_claimed:
            try:
                registry.append(request,'end',{k:control[k] for k in
                    ('attempted','received','cost_unknown','current_run_cost_usd')} |
                    {'report_sha256':hashlib.sha256((public/'cloud_run.json').read_bytes()).hexdigest()})
            except Exception:
                control['allocation_checkpoint_error'] = 'REMOTE_ALLOCATION_END_UNCONFIRMED'
                write_json(public/'cloud_run.json',control)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--mode',choices=['preflight','live'],required=True)
    parser.add_argument('--output-dir',type=Path,required=True)
    args = parser.parse_args(argv)
    enter_delegated_cgroup()
    result = run(args.mode,args.output_dir,os.environ)
    print(json.dumps(result,ensure_ascii=False))
    return 0 if result['status'] in ('preflight_pass','technical_complete_awaiting_human','completed') else 1


if __name__ == '__main__':
    raise SystemExit(main())
