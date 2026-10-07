"""Manual-only cloud entrypoint for the existing network E2E paid window.

Secrets: existing OPENAI_API_KEY; fresh NETWORK_E2E_GATES_JSON; attested sealed
NETWORK_E2E_WINDOW_STATE_JSON; signed NETWORK_E2E_SNAPSHOT_URL. Never creates a
new budget/window from missing state. Preflight never constructs a model client.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re

from evaluation.finalization.cloud_window import (CloudError,GitHubAPI,GitHubWindowStore,
    CloudCheckpointClient,REPOSITORY,atomic_json,digest,validate_migration,download_bundle,extract_snapshot_bundle)
from evaluation.finalization.live_window import WINDOW_ID,canonical_window_root,_validate_gates
from evaluation.finalization.network_contract import LOCK_PATH,validate_lock

REQUIRED=('OPENAI_API_KEY','GITHUB_TOKEN','NETWORK_E2E_GATES_JSON','NETWORK_E2E_WINDOW_STATE_JSON','NETWORK_E2E_SNAPSHOT_URL')


def verify_cloud_ci(api,gates,env):
    sha=env.get('GITHUB_SHA','')
    if (env.get('GITHUB_REPOSITORY')!=REPOSITORY or env.get('GITHUB_REF')!='refs/heads/master'
        or env.get('GITHUB_EVENT_NAME')!='workflow_dispatch' or gates['implementation_sha']!=sha):
        raise CloudError('CLOUD_GIT_CONTEXT_INVALID')
    prefix='/repos/'+REPOSITORY
    head=api.request('GET',prefix+'/git/ref/heads/master')
    if not isinstance(head,dict) or head.get('object',{}).get('sha')!=sha:raise CloudError('REMOTE_MASTER_CHANGED')
    url=gates['ci']['run_url']
    match=re.fullmatch(r'https://github\.com/Whats-up-pro/VinSOC/actions/runs/([0-9]+)',url)
    if not match:raise CloudError('CLOUD_CI_URL_INVALID')
    run=api.request('GET',prefix+'/actions/runs/'+match[1])
    jobs=api.request('GET',prefix+'/actions/runs/'+match[1]+'/jobs?per_page=100')
    names=[j.get('name','') for j in (jobs or {}).get('jobs',[]) if j.get('conclusion')=='success']
    if (not run or run.get('head_sha')!=sha or run.get('conclusion')!='success'
        or run.get('path')!='.github/workflows/ci.yml' or run.get('head_branch')!='master'
        or run.get('event')!='push' or not {'test (3.11)','test (3.12)'}.issubset(names)):
        raise CloudError('CLOUD_EXACT_SHA_CI_UNVERIFIED')


def merge_transport_accounting(report,wrapper):
    report['transport_accounting']={k:v for k,v in wrapper.data.items() if k!='events'}
    report['openai_transmissions']=wrapper.data['attempted_calls']
    report['cost_unknown']=bool(report.get('cost_unknown') or (report.get('cost_summary') or {}).get('cost_unknown')
                                or wrapper.data['cost_unknown'])
    report['known_new_inference_cost_usd']=wrapper.data['known_cost_usd']
    report['new_inference_cost_usd']=None if report['cost_unknown'] else wrapper.data['known_cost_usd']
    report.setdefault('lifecycle_counts',{k:report.get(k,0) for k in ('attempted_calls','responses_received')})
    for key in ('attempted_calls','responses_received'):
        report[key]=wrapper.data[key]


def run(mode,output_dir,env,*,api_factory=GitHubAPI):
    output_dir=Path(output_dir)
    if output_dir.exists():raise CloudError('CLOUD_OUTPUT_ALREADY_EXISTS')
    output_dir.mkdir(parents=True,exist_ok=False)
    report={'scope':'network_only_public_lifecycle_demo','mode':mode,'status':'blocked',
            'client_created':False,'attempted_calls':0,'responses_received':0,'new_inference_cost_usd':0,
            'cost_unknown':False,'human_approval':False}
    store=wrapper=None
    try:
        missing=[k for k in REQUIRED if not env.get(k)]
        if missing:
            report['missing_inputs']=missing
            raise CloudError('CLOUD_PRIVATE_INPUTS_MISSING')
        if env.get('OPENAI_BASE_URL'):raise CloudError('CUSTOM_BASE_URL_REJECTED')
        gates=_validate_gates(json.loads(env['NETWORK_E2E_GATES_JSON']),WINDOW_ID)
        migration=json.loads(env['NETWORK_E2E_WINDOW_STATE_JSON']);ledger=validate_migration(migration)
        if ledger['known_cost_usd']>gates['reconciliation']['known_prior_cost_usd']:
            raise CloudError('MIGRATION_RECONCILIATION_UNDERSTATES_COST')
        api=api_factory(env['GITHUB_TOKEN']);verify_cloud_ci(api,gates,env)
        store=GitHubWindowStore(api,env['GITHUB_SHA'],env['GITHUB_RUN_ID'])
        if store.exists():raise CloudError('WINDOW_ALREADY_USED')
        bundle=output_dir/'snapshot.zip'
        download_bundle(env['NETWORK_E2E_SNAPSHOT_URL'],bundle)
        snapshot=extract_snapshot_bundle(bundle,output_dir/'snapshot')
        locked=validate_lock(snapshot,json.loads(LOCK_PATH.read_text(encoding='utf-8')))
        if locked.get('valid') is not True:raise CloudError('NETWORK_CONTRACT_INVALID')
        root=canonical_window_root();root.mkdir(parents=True,exist_ok=True)
        ledger_path=root/'ledger.json';gates_path=root/'gates.json'
        if (root/'claim.json').exists():raise CloudError('WINDOW_ALREADY_USED')
        if ledger_path.exists():
            if digest(json.loads(ledger_path.read_text()))!=digest(ledger):raise CloudError('EXISTING_LOCAL_STATE_MISMATCH')
        else:
            with ledger_path.open('x',encoding='utf-8') as out:json.dump(ledger,out)
        if gates_path.exists():
            if digest(json.loads(gates_path.read_text()))!=digest(gates):raise CloudError('EXISTING_GATES_MISMATCH')
        else:
            with gates_path.open('x',encoding='utf-8') as out:json.dump(gates,out)
        from scripts.demo_ctu_network_public_model_driven import run_e2e_preflight,run_e2e_live,_create_openai_client
        preflight=run_e2e_preflight(snapshot,output_dir/'cloud-check.json',budget_usd=gates['task_budget_usd'],
                                  ledger_path=ledger_path,gates_path=gates_path,env_file=Path('/nonexistent-cloud-dotenv'))
        report.update(preflight_status=preflight['status'],implementation_sha=env['GITHUB_SHA'],
                      snapshot_binary_sha256=hashlib.sha256(snapshot.read_bytes()).hexdigest(),
                      migration_ledger_sha256=migration['ledger_sha256'])
        if preflight['status']!='preflight_pass':raise CloudError('NETWORK_PREFLIGHT_FAILED')
        if mode=='preflight':
            report['status']='preflight_pass';return report
        if mode!='live':raise CloudError('CLOUD_MODE_INVALID')
        # Re-read remote identity immediately before claim, after slow snapshot validation.
        verify_cloud_ci(api,gates,env)
        def factory(key):
            nonlocal wrapper
            store.claim(migration['ledger_sha256'])  # CAS: immutable ref BEFORE client/request
            report['window_claimed']=True
            atomic_json(output_dir/'cloud_run.json',report)
            sdk=_create_openai_client(key)
            report['client_created']=True
            wrapper=CloudCheckpointClient(sdk,store,output_dir/'cloud_transport.json')
            return wrapper
        result=run_e2e_live(snapshot,output_dir/'technical-live.json',budget_usd=gates['task_budget_usd'],
            ledger_path=ledger_path,gates_path=gates_path,env_file=Path('/nonexistent-cloud-dotenv'),
            review_mode='deferred',client_factory=factory)
        from scripts.render_network_e2e_report import render_report
        render_report(output_dir/'technical-live.json',output_dir/'technical-live.html')
        report.update(status=result['status'],attempted_calls=result['attempted_calls'],responses_received=result['responses_received'],
            valid_usage_records=result.get('valid_usage_records',0),cost_summary=result.get('cost_summary'),
            technical_receipt_sha256=hashlib.sha256((output_dir/'technical-live.json').read_bytes()).hexdigest())
        if wrapper:
            merge_transport_accounting(report,wrapper)
        if store.claimed:
            store.checkpoint('terminal',{'status':report['status'],'attempted_calls':report['attempted_calls'],
                'responses_received':report['responses_received'],'technical_receipt_sha256':report['technical_receipt_sha256']})
        return report
    except Exception as error:
        # Safe controlled CloudError codes only. All other text/path/body discarded.
        reason=error.args[0] if isinstance(error,CloudError) and len(error.args)==1 else type(error).__name__
        if not isinstance(reason,str) or not re.fullmatch('[A-Z_]{1,100}',reason):reason=type(error).__name__
        report['failure_category']=reason
        if wrapper:
            report.update(status='partial',attempted_calls=wrapper.data['attempted_calls'],
                responses_received=wrapper.data['responses_received'],new_inference_cost_usd=wrapper.data['known_cost_usd'],
                cost_unknown=wrapper.data['cost_unknown'],transport_checkpoint_retained=True)
        elif store and store.claimed:
            report.update(status='partial',window_claimed=True)
        return report
    finally:
        if wrapper:
            merge_transport_accounting(report,wrapper)
            try:wrapper.close()
            except Exception:pass
        atomic_json(output_dir/'cloud_run.json',report)


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--mode',choices=['preflight','live'],required=True)
    parser.add_argument('--output-dir',type=Path,required=True)
    args=parser.parse_args(argv)
    try:result=run(args.mode,args.output_dir,os.environ)
    except CloudError as error:
        parser.error(error.args[0])
    print(json.dumps({k:result.get(k) for k in ('status','failure_category','missing_inputs','attempted_calls','responses_received','client_created','cost_unknown')}))
    return 0 if result['status'] in ('preflight_pass','technical_complete_awaiting_human') else 1


if __name__=='__main__':raise SystemExit(main())
