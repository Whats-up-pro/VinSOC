"""Actual phase-2 controller with SDK offline transport; no network/model calls."""
import json
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path

import pytest

from tests.r2_remediation_fixtures import case, make_tools
from tests.test_r2_v2_dev_live import sdk_factory, reply


@pytest.fixture
def live(tmp_path,monkeypatch):
    from scripts import run_r2_phase2_dev_live as module
    from scripts import run_r2_v2_dev_live as guard_module
    from evaluation.r2_phase2.tool_schemas_v4 import TOOL_SCHEMAS
    # Synthetic transport only: exercise telemetry with the new evaluation schema.
    # The historical production guard/lock remain unchanged and reject v4.
    monkeypatch.setattr(guard_module, 'TOOL_SCHEMAS', TOOL_SCHEMAS)
    from evaluation.r2_phase2.grounding import Phase2Tools
    old,manifest=make_tools(tmp_path)
    tools=Phase2Tools(old.snapshot_path,manifest)
    cases=[replace(case('Count Capture Group 5 flows',gold='SELECT 3 AS GOLD_SENTINEL'),case_id=f'ctu_sql_{i:03d}') for i in range(1,9)]
    identity={'git_sha':'f'*40,'dirty_state':False,'contract_sha256':'locked','schema_sha256':'typed'}
    if hasattr(module,'verified_environment'):
        monkeypatch.setattr(module,'verified_environment',lambda p:(cases,tools,identity))
        monkeypatch.setattr(module,'git_state',lambda:{'sha':'f'*40,'origin':'f'*40,'branch':'master','dirty':False})
        monkeypatch.setattr(module,'ATTEMPTS_ROOT',tmp_path/'claims')
        monkeypatch.setattr(module,'key_configuration',lambda:('fixture-key',{'source':'fixture','project':None,'organization':None}))
    now=datetime.now(timezone.utc).isoformat()
    gates={'implementation_sha':'f'*40,'ci':{'headSha':'f'*40,'conclusion':'success','jobs':[{'name':'test (3.11)','conclusion':'success'},{'name':'test (3.12)','conclusion':'success'}]},'account':{'source':'owner_confirmation','confirmed_utc':now,'project_verified':True,'credit_at_least_usd':.75,'hard_limit_at_least_usd':.75},'pricing':{'url':'https://developers.openai.com/api/docs/models/gpt-5-mini.md','checked_utc':now,'source_sha256':'a'*64,'input':.25,'cached_input':.025,'output':2.0},'new_live_budget_usd':.75,'total_authorized_usd':2.0,'historical_recorded_lower_bound_usd':.08693465}
    if hasattr(module,'load_gates'):
        monkeypatch.setattr(module,'load_gates',lambda:gates)
    return module,gates,tmp_path


def test_v4_schema_cannot_bypass_historical_request_guard():
    from scripts.run_r2_v2_dev_live import validate_request, GateError, MODEL
    from evaluation.r2_phase2.tool_schemas_v4 import TOOL_SCHEMAS
    with pytest.raises(GateError, match='REQUEST_CONTRACT_ERROR'):
        validate_request({'model':MODEL,'reasoning_effort':'low',
                          'max_completion_tokens':1000,'messages':[],
                          'tools':TOOL_SCHEMAS})


def pipeline():
    return [reply(json.dumps({'tables':[{'table':'network_flows','columns':['source_dataset']}],'grounded_values':[]})),reply('SELECT\n9;')]


def test_one_suite_no_smoke_and_no_retry_of_wrong_cases(live):
    module,_,root=live; requests=[]
    result=module.run_suite(Path('fixture'),root/'output',sdk_factory(pipeline()*8,requests))
    assert result['case_count']==result['completed_case_count']==8 and result['status']=='complete'
    assert result['counts']['execution_accurate']==0 and result['counts']['execution_success']==8
    assert result['attempted_calls']==result['response_count']==16 and result['db_calls']==0
    assert result['cost_complete'] and result['observed_cost_usd']==pytest.approx(16*.000056)
    assert not result['official_eligible'] and len(requests)==16
    assert all('GOLD_SENTINEL' not in json.dumps(r) and 'temperature' not in r and r['service_tier']=='default' for r in requests)
    with pytest.raises(module.GateError,match='CONSUMED'):
        module.run_suite(Path('fixture'),root/'different',sdk_factory(pipeline(),requests))
    assert len(requests)==16


@pytest.mark.parametrize('gate,category',[('ci','EXACT_SHA_CI_REQUIRED'),('credit','ACCOUNT_GATE_FAILED'),
    ('pricing','PRICING_GATE_FAILED'),('budget','BUDGET_GATE_FAILED'),('dirty','IMPLEMENTATION_STATE_MISMATCH'),
    ('snapshot','DEV_IDENTITY_VERIFICATION_FAILED'),('output','OUTPUT_EXISTS')])
def test_all_preflight_failures_block_client_creation(live,monkeypatch,gate,category):
    module,gates,root=live
    if gate=='ci': gates['ci']['headSha']='wrong'
    if gate=='credit': gates['account']['credit_at_least_usd']=0
    if gate=='pricing': gates['pricing']['input']=99
    if gate=='budget': gates['new_live_budget_usd']=99
    if hasattr(module,'git_state') and gate=='dirty': monkeypatch.setattr(module,'git_state',lambda:{'sha':'f'*40,'origin':'f'*40,'branch':'master','dirty':True})
    if hasattr(module,'verified_environment') and gate=='snapshot': monkeypatch.setattr(module,'verified_environment',lambda p:(_ for _ in ()).throw(ValueError('private-path')))
    if gate=='output': (root/'output').mkdir()
    def forbidden(): pytest.fail('client created before a failed gate')
    with pytest.raises(module.GateError,match=category): module.run_suite(Path('fixture'),root/'output',forbidden)


def test_parse_failure_is_charged_and_remaining_cases_still_measured(live):
    module,_,root=live; requests=[]
    bad=reply(calls=[{'id':'bad','type':'function','function':{'name':'value_search','arguments':'{'}}])
    result=module.run_suite(Path('fixture'),root/'output',sdk_factory([bad]+pipeline()*7,requests))
    assert result['status']=='complete' and result['case_count']==8
    assert result['case_results'][0]['error_category']=='MALFORMED_TOOL_ARGUMENTS'
    assert result['attempted_calls']==result['response_count']==15
    assert result['cost_complete'] and result['observed_cost_usd']==pytest.approx(15*.000056)
    assert 'sdk_response' in (root/'output'/'partial.jsonl').read_text()


def test_provider_failure_consumes_suite_and_never_retries(live):
    module,_,root=live; requests=[]
    result=module.run_suite(Path('fixture'),root/'output',sdk_factory([429],requests))
    assert result['status']=='partial' and result['attempted_calls']==1 and result['response_count']==0
    assert result['case_results'][0]['error_category']=='RATE_LIMIT' and not result['cost_complete']
    assert result['case_count']==8 and len(result['missing_case_ids'])==7
    assert len(requests)==1


def test_contract_tamper_blocks_before_provider(live,monkeypatch):
    module,_,root=live
    if hasattr(module,'verify_contract'):
        monkeypatch.setattr(module,'verified_environment',lambda p:module.verify_contract(root/'missing-lock'))
    with pytest.raises(module.GateError):
        module.run_suite(Path('fixture'),root/'output',lambda:pytest.fail('client created'))


def test_contract_entries_cannot_be_removed_to_bypass_source_hashes(tmp_path):
    from scripts.run_r2_phase2_dev_live import verify_contract,GateError
    contract=json.loads(Path('evaluation/r2_phase2/CONTRACT.lock.json').read_text())
    contract['files_portable_sha256']={}
    forged=tmp_path/'forged-lock.json'
    forged.write_text(json.dumps(contract))
    with pytest.raises(GateError,match='CONTRACT'):
        verify_contract(forged)


def test_cleanup_failure_still_finalizes_charged_report(live):
    module,_,root=live; requests=[]
    base=sdk_factory(pipeline()*8,requests)
    def factory():
        client=base(); close=client.close
        def broken_close():
            close()
            raise OSError('credential-sentinel')
        client.close=broken_close
        return client
    result=module.run_suite(Path('fixture'),root/'output',factory)
    assert (root/'output'/'report.json').is_file()
    assert result['response_count']==16 and result['cost_complete']
    assert result['infrastructure_error']=='CLIENT_CLEANUP_ERROR'
    assert result['status']=='partial' and not result['official_eligible']
    assert 'credential-sentinel' not in (root/'output'/'report.json').read_text()
