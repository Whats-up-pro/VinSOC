"""One authorized sequential attempt for each of the three missing fixed demos."""
from __future__ import annotations

import hashlib
import json
import math
import re
from pathlib import Path

from evaluation.finalization.cloud_window import REPOSITORY
from evaluation.finalization.query_cloud import QueryDemoGitHubStore
from evaluation.finalization.query_runtime_validation import window_id_for
from evaluation.r2_cross_domain_v1.release import canonical_hash, fresh
from scripts.run_query_demo_cloud import (
    CASE_ID, REQUIRED, ROOT, prepare_private_inputs, prior_demo_receipt,
    verify_cloud_ci, write_json,
)
from scripts.run_vinsoc_query_acceptance import run_live, run_preflight, verify_selected_question

EXECUTION_ID = 'mentor-remaining3-20261013'
BASE_PRIOR_USD = 0.061155
LIMIT_USD = 3.0
REMAINING_IDS = ('ctu_cross_66b8e92a76c3359b', 'ctu_cross_3f659571f998adb0',
                 'ctu_cross_bce6d3679ade4cd6')


def remaining_selection():
    selection = json.loads((ROOT/'results/evaluation_v1/text2sql_integration_v1/demo_selection.json').read_text(encoding='utf-8'))
    if tuple(r['case_id'] for r in selection['cases']) != (CASE_ID, *REMAINING_IDS):
        raise ValueError('FIXED_DEMO_SELECTION_REQUIRED')
    return [verify_selected_question(r['case_id'], r['question'], require_demo=True)
            for r in selection['cases'][1:]]


def validate_remaining_authorization(value):
    numeric = ('limit_usd', 'known_prior_cost_usd', 'remaining_allocation_usd', 'unknown_exposure_usd')
    if (not isinstance(value, dict) or value.get('scope') != 'remaining_demo3'
            or value.get('condition') != 'E3' or value.get('case_ids') != list(REMAINING_IDS)
            or value.get('execution_id') != EXECUTION_ID or value.get('allocation_id') != EXECUTION_ID
            or any(type(value.get(k)) not in (int, float) or not math.isfinite(value[k]) for k in numeric)
            or value['limit_usd'] != LIMIT_USD or value['known_prior_cost_usd'] != BASE_PRIOR_USD
            or value['remaining_allocation_usd'] != LIMIT_USD-BASE_PRIOR_USD
            or value['unknown_exposure_usd'] != 0.0 or not fresh(value.get('confirmed_utc'))):
        raise ValueError('REMAINING_DEMO_AUTHORIZATION_INVALID')
    return value


def verified_prior_receipts():
    prior = prior_demo_receipt({'execution_id':'full-e2e-10', 'known_prior_cost_usd':0.05375795})
    path = ROOT/'results/evaluation_v1/text2sql_integration_v1/single_demo_full_e2e_10_20261013/outcome_audit.json'
    audit = json.loads(path.read_text(encoding='utf-8'))
    actual, workflow = audit['actual'], audit['workflow']
    expected_digest = 'sha256:ed290e86e1342bc0c9bb5d45d1319094c90d477597015d75480fa92f97c52540'
    if (audit.get('case_id') != CASE_ID or workflow.get('run_id') != 38338493466
            or workflow.get('artifact_digest') != expected_digest or actual.get('cost_unknown') is not False
            or actual.get('provider_transmitted_calls') != 7 or actual.get('received_responses') != 7
            or actual.get('current_run_cost_usd') != 0.00739705):
        raise ValueError('PRIOR_DEMO_RECEIPT_INVALID')
    prior.append({'workflow_run_id':38338493466, 'known_cost_usd':0.00739705,
                  'artifact_digest':expected_digest, 'audit_sha256':hashlib.sha256(path.read_bytes()).hexdigest()})
    if not math.isclose(sum(r['known_cost_usd'] for r in prior), BASE_PRIOR_USD, rel_tol=0, abs_tol=1e-12):
        raise ValueError('PRIOR_DEMO_RECEIPT_INVALID')
    return prior


def reconcile_case_report(report, *, expected_case_id):
    events = report.get('cost_events', [])
    if report.get('cost_unknown') is not False or report.get('terminal') is True or not events:
        raise ValueError('REMAINING_DEMO_COST_UNRECONCILED')
    responses = set()
    for event in events:
        usage = event.get('usage') or {}
        if (event.get('case_id') != expected_case_id or event.get('condition') != 'E3'
                or event.get('received') is not True or not event.get('response_id')
                or event['response_id'] in responses or not event.get('request_id')
                or event.get('role') not in ('routing','r2','assessment')
                or any(type(usage.get(k)) is not int or usage[k] < 0 for k in ('input_tokens','output_tokens','cached_tokens'))
                or type(event.get('cost_usd')) not in (int,float) or not math.isfinite(event['cost_usd'])
                or event['cost_usd'] < 0):
            raise ValueError('REMAINING_DEMO_COST_UNRECONCILED')
        responses.add(event['response_id'])
    if report.get('attempted') != len(events) or report.get('received') != len(events):
        raise ValueError('REMAINING_DEMO_COST_UNRECONCILED')
    return sum(event['cost_usd'] for event in events)


def verify_remote_cases_unused(api):
    for case_id in REMAINING_IDS:
        prefix = 'vinsoc-query-demo-text2sql-integration-20261008-demo-'+case_id
        refs = api.request('GET', '/repos/'+REPOSITORY+'/git/matching-refs/tags/'+prefix)
        if not isinstance(refs, list):
            raise ValueError('REMOTE_SCOPE_STATE_UNVERIFIED')
        if refs:
            raise ValueError('WINDOW_ALREADY_USED')


def run_remaining(mode, output_dir, env, *, api_factory):
    output = Path(output_dir)
    if output.exists():
        raise ValueError('CLOUD_OUTPUT_ALREADY_EXISTS')
    public, private = output/'public', output/'private'
    public.mkdir(parents=True)
    private.mkdir(parents=True)
    control = {'scope':'three_fixed_missing_query_demos_not_pipeline32', 'execution_id':EXECUTION_ID,
               'case_ids':list(REMAINING_IDS), 'planned':3, 'status':'blocked', 'attempted':0,
               'received':0, 'client_created':False, 'window_claimed':False,
               'current_run_cost_usd':0.0, 'prior_cost_usd':BASE_PRIOR_USD,
               'known_usd':BASE_PRIOR_USD, 'remaining_cap_usd':LIMIT_USD-BASE_PRIOR_USD,
               'cost_unknown':False, 'official_eligible':False, 'cases':[]}
    batch_store = None
    active_window = None
    try:
        missing = [name for name in REQUIRED if not env.get(name)]
        if missing:
            control['missing_inputs'] = missing
            raise ValueError('CLOUD_PRIVATE_INPUTS_MISSING')
        if mode not in ('preflight','live') or env.get('OPENAI_BASE_URL'):
            raise ValueError('CLOUD_MODE_OR_ENDPOINT_INVALID')
        auth = validate_remaining_authorization(json.loads(env['VINSOC_QUERY_DEMO_AUTH_JSON']))
        prior = verified_prior_receipts()
        api = api_factory(env['GITHUB_TOKEN'])
        ci_id = verify_cloud_ci(api, env)
        control.update(implementation_sha=env['GITHUB_SHA'], ci_run_id=ci_id)
        verify_remote_cases_unused(api)
        batch_store = QueryDemoGitHubStore(api, implementation_sha=env['GITHUB_SHA'], run_id=env['GITHUB_RUN_ID'])
        batch_window = window_id_for('demo', 'remaining3', EXECUTION_ID)
        if batch_store._exists(batch_store._tag_component(batch_window)):
            raise ValueError('WINDOW_ALREADY_USED')
        for selected in remaining_selection():
            case_id = selected['case_id']
            known = BASE_PRIOR_USD+control['current_run_cost_usd']
            case_auth = {**auth, 'scope':'demo', 'case_id':case_id,
                         'known_prior_cost_usd':known, 'remaining_allocation_usd':LIMIT_USD-known}
            inputs = prepare_private_inputs(case_auth, env, ci_id, verified_prior=prior)
            checked = run_preflight('demo','E3',inputs,selected_input=selected,execution_id=EXECUTION_ID)
            release = checked['release']
            write_json(private/case_id/'release.json', checked)
            safe = json.loads(json.dumps(checked))
            safe['release'].pop('gate_inputs',None)
            write_json(public/case_id/'preflight.json', safe)
            row = {'case_id':case_id, 'question':selected['question'], 'preflight_status':release['status'],
                   'cost_ceiling_usd':release['new_cost_ceiling_usd'], 'window_id':release['window_id'],
                   'status':'not_run', 'attempted':0, 'received':0}
            control['cases'].append(row)
            if not release['authorized']:
                row.update(status='blocked', reasons=release['reasons'])
                raise ValueError('REMAINING_DEMO_PREFLIGHT_BLOCKED')
            if mode == 'preflight':
                row['status'] = 'preflight_pass'
                continue
            verify_cloud_ci(api, env)
            if not batch_store.claimed:
                batch_store.claim(batch_window, canonical_hash(auth))
                control['window_claimed'] = True
                write_json(public/'cloud_run.json', control)
            store = QueryDemoGitHubStore(api, implementation_sha=env['GITHUB_SHA'], run_id=env['GITHUB_RUN_ID'])
            active_window = Path.home()/'.vinsoc/live-windows'/release['window_id']
            report = run_live(release, public/case_id/'live', selected_input=selected, remote_store=store)
            row.update(status=report['status'], attempted=report.get('attempted',0), received=report.get('received',0),
                       window_claimed=store.claimed, cost_unknown=report.get('cost_unknown',False))
            control.update(attempted=control['attempted']+row['attempted'],
                           received=control['received']+row['received'],
                           client_created=control['client_created'] or report.get('client_created',False))
            for name in ('claim.json','ledger.json'):
                if (active_window/name).is_file():
                    import shutil
                    target = private/case_id/name
                    target.parent.mkdir(parents=True,exist_ok=True)
                    shutil.copy2(active_window/name,target)
            cost = reconcile_case_report(report, expected_case_id=case_id)
            row['current_run_cost_usd'] = cost
            control['current_run_cost_usd'] += cost
            control.update(known_usd=BASE_PRIOR_USD+control['current_run_cost_usd'],
                           remaining_cap_usd=LIMIT_USD-BASE_PRIOR_USD-control['current_run_cost_usd'])
            journal_path = active_window/'ledger.json'
            prior.append({'workflow_run_id':int(env['GITHUB_RUN_ID']), 'case_id':case_id,
                          'known_cost_usd':cost, 'journal_sha256':hashlib.sha256(journal_path.read_bytes()).hexdigest()})
            batch_store.checkpoint(len(control['cases']),'end',
                {'case_id':case_id,'known_usd':control['known_usd'],'cost_unknown':False,
                 'report_sha256':hashlib.sha256((public/case_id/'live/report.json').read_bytes()).hexdigest()})
            write_json(public/'cloud_run.json',control)
            active_window = None
        control['status'] = ('preflight_pass' if mode == 'preflight' else
            'technical_complete_awaiting_human' if all(r['status']=='technical_complete_awaiting_human' for r in control['cases'])
            else 'technical_incomplete')
        return control
    except Exception as error:
        reason = error.args[0] if isinstance(error,ValueError) and len(error.args)==1 else type(error).__name__
        control['failure_category'] = reason if isinstance(reason,str) and re.fullmatch(r'[A-Z0-9_]{1,100}',reason) else type(error).__name__
        if active_window is not None:
            ledger = active_window/'ledger.json'
            if ledger.is_file():
                saved = json.loads(ledger.read_text())
                control.update(cost_unknown=saved.get('cost_unknown',True), known_usd=saved['known_usd'],
                               current_run_cost_usd=saved['known_usd']-BASE_PRIOR_USD,
                               remaining_cap_usd=LIMIT_USD-saved['known_usd'],
                               pending_exposure_usd=saved.get('pending_exposure_usd'))
            else:
                control['cost_unknown'] = True
        return control
    finally:
        write_json(public/'cloud_run.json', control)
