"""One-shot GitHub runner for the fixed, three-dollar E3 query demo."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
from datetime import datetime, timezone
from pathlib import Path

from evaluation.finalization.cloud_window import GitHubAPI, REPOSITORY
from evaluation.finalization.query_cloud import QueryDemoGitHubStore
from evaluation.finalization.query_runtime_validation import source_hashes
from evaluation.finalization.query_token_bound import MODEL_DOCS, read_model_document
from evaluation.r2_cross_domain_v1.release import fresh
from scripts.run_vinsoc_query_acceptance import ROOT, run_live, run_preflight

CASE_ID = 'ctu_cross_708b66575657429a'
REQUIRED = ('OPENAI_API_KEY','GITHUB_TOKEN','GITHUB_SHA','GITHUB_RUN_ID','GITHUB_CI_RUN_ID',
            'VINSOC_QUERY_DEMO_AUTH_JSON','VINSOC_GPT5_DOC','VINSOC_GPT41_DOC')


def write_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix+'.tmp')
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
    os.replace(temporary, path)


def validate_authorization(value):
    numbers = ('limit_usd','known_prior_cost_usd','remaining_allocation_usd','unknown_exposure_usd')
    if (not isinstance(value, dict) or not isinstance(value.get('allocation_id'), str)
            or not value['allocation_id'] or value.get('scope') != 'demo'
            or value.get('condition') != 'E3' or value.get('case_id') != CASE_ID
            or value.get('limit_usd') != 3.0 or value.get('known_prior_cost_usd') != 0.0
            or value.get('remaining_allocation_usd') != 3.0
            or value.get('unknown_exposure_usd') != 0.0
            or any(type(value.get(k)) not in (int,float) for k in numbers)
            or not fresh(value.get('confirmed_utc'))):
        raise ValueError('DEMO_AUTHORIZATION_INVALID')
    return value


def verify_cloud_ci(api, env):
    sha = env.get('GITHUB_SHA','')
    if (env.get('GITHUB_REPOSITORY') != REPOSITORY or env.get('GITHUB_REF') != 'refs/heads/master'
            or env.get('GITHUB_EVENT_NAME') != 'workflow_dispatch'
            or not re.fullmatch(r'[0-9a-f]{40}', sha)):
        raise ValueError('CLOUD_GIT_CONTEXT_INVALID')
    prefix = '/repos/'+REPOSITORY
    head = api.request('GET', prefix+'/git/ref/heads/master')
    if not isinstance(head,dict) or head.get('object',{}).get('sha') != sha:
        raise ValueError('REMOTE_MASTER_CHANGED')
    run_id = env.get('GITHUB_CI_RUN_ID','')
    if not re.fullmatch(r'[0-9]{1,24}', run_id):
        raise ValueError('CLOUD_CI_ID_INVALID')
    run = api.request('GET', prefix+'/actions/runs/'+run_id)
    jobs = api.request('GET', prefix+'/actions/runs/'+run_id+'/jobs?per_page=100')
    passed = {j.get('name') for j in (jobs or {}).get('jobs',[]) if j.get('conclusion') == 'success'}
    required = {'test (3.11)','test (3.12)','query-real-data (3.11)','query-real-data (3.12)'}
    if (not isinstance(run,dict) or run.get('head_sha') != sha or run.get('conclusion') != 'success'
            or run.get('path') != '.github/workflows/ci.yml' or run.get('head_branch') != 'master'
            or run.get('event') != 'push' or not required.issubset(passed)):
        raise ValueError('CLOUD_EXACT_SHA_CI_UNVERIFIED')
    return int(run_id)


def fixed_selection():
    selection = json.loads((ROOT/'results/evaluation_v1/text2sql_integration_v1/demo_selection.json').read_text(encoding='utf-8'))
    chosen = next((case for case in selection.get('cases',[]) if case.get('case_id') == CASE_ID), None)
    if not chosen:
        raise ValueError('FIXED_DEMO_SELECTION_REQUIRED')
    return chosen


def prepare_private_inputs(auth, env, ci_run_id):
    stamp = datetime.now(timezone.utc).isoformat()
    canonical = Path.home()/'.vinsoc/live-windows'
    allocation_dir = canonical/'allocations'/auth['allocation_id']
    allocation_dir.mkdir(parents=True, exist_ok=False)
    ledger_path = allocation_dir/'allocation_ledger.json'
    allocation = {'schema_version':1, 'allocation_id':auth['allocation_id'], 'currency':'USD',
                  'authorized_limit_usd':3.0, 'known_prior_cost_usd':0.0,
                  'remaining_allocation_usd':3.0, 'unknown_exposure_usd':0.0,
                  'events':[], 'authorization':{k:auth[k] for k in ('scope','condition','case_id','confirmed_utc')}}
    write_json(ledger_path, allocation)
    ledger_sha = hashlib.sha256(ledger_path.read_bytes()).hexdigest()
    receipt_path = allocation_dir/'reconciliation.json'
    receipt = {'schema_version':1, 'verified_utc':stamp, 'allocation_id':auth['allocation_id'],
               'authoritative_host_verified':True, 'prior_hosts_sealed':True,
               'unknown_exposure_usd':0, 'known_prior_cost_usd':0.0,
               'remaining_allocation_usd':3.0,
               'scope_states':{'calibration':'outside_demo_allocation','evaluation':'outside_demo_allocation',
                               'pipeline':'outside_demo_allocation','demo':'unused'},
               'ledger_artifacts':[{'path':ledger_path.relative_to(canonical).as_posix(),'sha256':ledger_sha}],
               'basis':'dedicated_new_3_usd_allocation_authorized_for_one_fixed_E3_demo'}
    write_json(receipt_path, receipt)
    receipt_sha = hashlib.sha256(receipt_path.read_bytes()).hexdigest()
    pricing = {}
    paths = {'gpt-5-mini-2025-08-07':Path(env['VINSOC_GPT5_DOC']),
             'gpt-4.1-mini-2025-04-14':Path(env['VINSOC_GPT41_DOC'])}
    for model,path in paths.items():
        observed = read_model_document(path, model)
        pricing[model] = {**observed, 'checked_utc':stamp,
            'source_url':'https://developers.openai.com/api/docs/pricing',
            'token_bound_method':'documented_context_window',
            'model_document':{'source_url':MODEL_DOCS[model], 'path':str(path.resolve()),
                              'sha256':hashlib.sha256(path.read_bytes()).hexdigest()}}
    return {
        'pricing':pricing,
        'account':{'confirmed_utc':stamp,'project_verified':True,'allocation_id':auth['allocation_id'],
                   'known_prior_cost_usd':0.0,'remaining_allocation_usd':3.0,
                   'unresolved_cost_unknown':False,
                   'reconciliation_reference':{'path':str(receipt_path.resolve()),'sha256':receipt_sha}},
        'budget':{'paid_authorized':True,'authorization_scope':'demo','limit_usd':3.0,
                  'decision_reference':'explicit-user-approval-one-fixed-E3-demo-hard-cap-3-USD-2026-10-10'},
        'identities':{'implementation_sha':env['GITHUB_SHA'],'ci_run_id':ci_run_id,
                      'runtime_source_sha256':source_hashes()},
    }


def run(mode, output_dir, env, *, api_factory=GitHubAPI):
    output_dir = Path(output_dir)
    if output_dir.exists():
        raise ValueError('CLOUD_OUTPUT_ALREADY_EXISTS')
    public = output_dir/'public'
    private = output_dir/'private'
    public.mkdir(parents=True)
    private.mkdir(parents=True)
    control = {'scope':'single_fixed_query_demo','condition':'E3','case_id':CASE_ID,
               'status':'blocked','client_created':False,'attempted':0,'received':0,
               'known_usd':0.0,'cost_unknown':False,'window_claimed':False}
    store = None
    try:
        missing = [name for name in REQUIRED if not env.get(name)]
        if missing:
            control['missing_inputs'] = missing
            raise ValueError('CLOUD_PRIVATE_INPUTS_MISSING')
        if env.get('OPENAI_BASE_URL'):
            raise ValueError('CUSTOM_BASE_URL_REJECTED')
        auth = validate_authorization(json.loads(env['VINSOC_QUERY_DEMO_AUTH_JSON']))
        api = api_factory(env['GITHUB_TOKEN'])
        ci_run_id = verify_cloud_ci(api, env)
        selected = fixed_selection()
        inputs = prepare_private_inputs(auth, env, ci_run_id)
        preflight = run_preflight('demo','E3',inputs,selected_input=selected)
        write_json(private/'release.json', preflight)
        public_preflight = json.loads(json.dumps(preflight))
        public_preflight['release'].pop('gate_inputs',None)
        write_json(public/'preflight.json', public_preflight)
        release = preflight['release']
        control.update(preflight_status=release['status'], new_cost_ceiling_usd=release['new_cost_ceiling_usd'],
                       window_id=release['window_id'], implementation_sha=env['GITHUB_SHA'], ci_run_id=ci_run_id)
        if not release['authorized']:
            raise ValueError('QUERY_DEMO_PREFLIGHT_BLOCKED')
        if mode == 'preflight':
            control['status'] = 'preflight_pass'
            return control
        if mode != 'live':
            raise ValueError('CLOUD_MODE_INVALID')
        verify_cloud_ci(api, env)
        store = QueryDemoGitHubStore(api, implementation_sha=env['GITHUB_SHA'], run_id=env['GITHUB_RUN_ID'])
        report = run_live(release, public/'live', selected_input=selected, remote_store=store)
        control.update(status=report['status'], client_created=report.get('client_created',False),
                       attempted=report.get('attempted',0), received=report.get('received',0),
                       known_usd=report.get('known_usd',0), cost_unknown=report.get('cost_unknown',False),
                       completed=report.get('completed',0), official_eligible=False,
                       window_claimed=store.claimed)
        window = Path.home()/'.vinsoc/live-windows'/release['window_id']
        for name in ('claim.json','ledger.json'):
            if (window/name).is_file():
                shutil.copy2(window/name, private/name)
        return control
    except Exception as error:
        reason = error.args[0] if isinstance(error,ValueError) and len(error.args)==1 else type(error).__name__
        control['failure_category'] = reason if isinstance(reason,str) and re.fullmatch(r'[A-Z0-9_]{1,100}',reason) else type(error).__name__
        if store is not None:
            control['window_claimed'] = store.claimed
        return control
    finally:
        write_json(public/'cloud_run.json', control)


def enter_delegated_cgroup():
    if os.environ.get('VINSOC_QUERY_CLOUD_REQUIRED') != '1':
        return
    if os.name != 'posix':
        raise ValueError('LINUX_DELEGATED_CGROUP_REQUIRED')
    groups = dict(line.split('::',1) for line in Path('/proc/self/cgroup').read_text().splitlines())
    root = Path('/sys/fs/cgroup')/groups.get('0','').lstrip('/')
    manager = root/'supervisor'
    manager.mkdir()
    (manager/'cgroup.procs').write_text(str(os.getpid()))
    (root/'cgroup.subtree_control').write_text('+memory +cpu +pids')
    os.environ['VINSOC_QUERY_CGROUP_ROOT'] = str(root)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--mode', choices=['preflight','live'], required=True)
    parser.add_argument('--output-dir', type=Path, required=True)
    args = parser.parse_args(argv)
    enter_delegated_cgroup()
    result = run(args.mode, args.output_dir, os.environ)
    print(json.dumps(result, ensure_ascii=False))
    return 0 if result['status'] in ('preflight_pass','technical_complete_awaiting_human') else 1


if __name__ == '__main__':
    raise SystemExit(main())
