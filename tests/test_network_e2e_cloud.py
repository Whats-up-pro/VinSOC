"""Cloud boundaries use fake external GitHub/SDK only; no paid inference."""
import hashlib
import json
import threading
from pathlib import Path
from types import SimpleNamespace
from datetime import datetime, timezone
import pytest


def migration(**changes):
    ledger = {"window_id": "network-finalization-20261006", "condition": "NETWORK_DEMO",
              "consumed": False, "active_claim": False, "cost_unknown": False,
              "attempted_requests": 0, "responses_received": 0, "valid_usage_records": 0,
              "attempts": [], "reservations": [], "known_cost_usd": 0.0}
    value = {"window_id": "network-finalization-20261006", "confirmed_utc": datetime.now(timezone.utc).isoformat(),
             "previous_hosts_sealed": True, "ledger": ledger,
             "ledger_sha256": hashlib.sha256(json.dumps(ledger,sort_keys=True,separators=(',',':')).encode()).hexdigest()}
    value.update(changes)
    return value


class FakeGitAPI:
    """External CAS service with shared durable state across runner instances."""
    def __init__(self):
        self.refs, self.objects, self.lock = {}, {}, threading.Lock()
    def request(self, method, route, payload=None):
        from evaluation.finalization.cloud_window import CloudError
        with self.lock:
            if method == 'GET':
                name=route.split('/git/ref/tags/',1)[1]
                return self.refs.get(name)
            if route.endswith('/git/tags'):
                sha=hashlib.sha256(json.dumps(payload,sort_keys=True).encode()).hexdigest()
                self.objects[sha]=payload
                return {'sha':sha}
            if route.endswith('/git/refs'):
                name=payload['ref'].split('refs/tags/',1)[1]
                if name in self.refs: raise CloudError('REMOTE_CLAIM_CONFLICT')
                self.refs[name]={'object':{'sha':payload['sha']}}
                return self.refs[name]
            pytest.fail('Unexpected API operation')


def sdk(response=None, failure=None):
    def create(**payload):
        if failure: raise failure
        return response
    return SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)))


def response():
    return SimpleNamespace(model='gpt-4.1-mini-2025-04-14', id='chatcmpl-synthetic', _request_id='req_synthetic',
        usage=SimpleNamespace(prompt_tokens=400,completion_tokens=56,total_tokens=456,
            prompt_tokens_details=SimpleNamespace(cached_tokens=0)),
        choices=[SimpleNamespace(finish_reason='stop',message=SimpleNamespace(content='PRIVATE RAW RESPONSE'))])


def test_missing_cloud_inputs_block_before_any_sdk(tmp_path,monkeypatch):
    from scripts.run_network_e2e_cloud import main
    import openai
    monkeypatch.setattr(openai,'OpenAI',lambda **kwargs:pytest.fail('SDK constructed'))
    for name in ('OPENAI_API_KEY','GITHUB_TOKEN','NETWORK_E2E_GATES_JSON','NETWORK_E2E_WINDOW_STATE_JSON','NETWORK_E2E_SNAPSHOT_URL'):
        monkeypatch.delenv(name,raising=False)
    out=tmp_path/'new'
    assert main(['--mode','preflight','--output-dir',str(out)])==1
    result=json.loads((out/'cloud_run.json').read_text())
    assert result['status']=='blocked' and result['client_created'] is False
    assert result['attempted_calls']==0 and 'NETWORK_E2E_WINDOW_STATE_JSON' in result['missing_inputs']


@pytest.mark.parametrize('changes,reason',[
    ({'previous_hosts_sealed':False},'PREVIOUS_HOST_NOT_SEALED'),
    ({'confirmed_utc':'2000-01-01T00:00:00Z'},'MIGRATION_STATE_STALE'),
    ({'ledger_sha256':'a'*64},'MIGRATION_LEDGER_HASH_MISMATCH'),
])
def test_migration_never_invents_previous_state(changes,reason):
    from evaluation.finalization.cloud_window import validate_migration,CloudError
    with pytest.raises(CloudError,match=reason): validate_migration(migration(**changes))


def test_consumed_migration_is_rejected_even_with_valid_digest():
    from evaluation.finalization.cloud_window import validate_migration,CloudError
    data=migration();data['ledger']['consumed']=True
    data['ledger_sha256']=hashlib.sha256(json.dumps(data['ledger'],sort_keys=True,separators=(',',':')).encode()).hexdigest()
    with pytest.raises(CloudError,match='WINDOW_ALREADY_USED'):validate_migration(data)


def test_remote_claim_survives_new_store_and_has_one_winner():
    from evaluation.finalization.cloud_window import GitHubWindowStore,CloudError
    api=FakeGitAPI();winners=[]
    def claim():
        try:GitHubWindowStore(api,'a'*40,'123').claim('b'*64);winners.append(True)
        except CloudError:pass
    threads=[threading.Thread(target=claim) for _ in range(2)]
    for t in threads:t.start()
    for t in threads:t.join()
    assert len(winners)==1
    with pytest.raises(CloudError,match='WINDOW_ALREADY_USED'):
        GitHubWindowStore(api,'a'*40,'124').claim('b'*64)
    persisted=list(api.objects.values())
    assert all(p['object']=='a'*40 and p['type']=='commit' for p in persisted)
    assert 'consumed' in json.loads(persisted[0]['message'])


def test_checkpoint_failure_before_transport_sends_zero_model_requests(tmp_path):
    from evaluation.finalization.cloud_window import CloudCheckpointClient,CloudError
    class RejectStore:
        def checkpoint(self,*args):raise CloudError('REMOTE_STATE_UNAVAILABLE')
    client=CloudCheckpointClient(sdk(failure=AssertionError('API reached')),RejectStore(),tmp_path/'transport.json')
    with pytest.raises(CloudError):client.chat.completions.create(model='gpt-4.1-mini-2025-04-14',messages=[])
    record=json.loads((tmp_path/'transport.json').read_text())
    assert record['attempted_calls']==0 and record['events'][0]['status']=='reserved_before_transmission'


def test_real_response_usage_is_persisted_without_raw_model_text(tmp_path):
    from evaluation.finalization.cloud_window import CloudCheckpointClient,GitHubWindowStore
    store=GitHubWindowStore(FakeGitAPI(),'a'*40,'123');store.claim('b'*64)
    client=CloudCheckpointClient(sdk(response()),store,tmp_path/'transport.json')
    returned=client.chat.completions.create(model='gpt-4.1-mini-2025-04-14',messages=[])
    record=json.loads((tmp_path/'transport.json').read_text())
    assert returned.model=='gpt-4.1-mini-2025-04-14'
    assert record['attempted_calls']==record['responses_received']==1
    assert record['known_cost_usd']==pytest.approx(.0002496)
    assert record['cost_unknown'] is False and 'PRIVATE RAW RESPONSE' not in (tmp_path/'transport.json').read_text()


def test_provider_failure_is_unknown_exposure_and_never_retains_body(tmp_path):
    from evaluation.finalization.cloud_window import CloudCheckpointClient,GitHubWindowStore,CloudError
    store=GitHubWindowStore(FakeGitAPI(),'a'*40,'123');store.claim('b'*64)
    client=CloudCheckpointClient(sdk(failure=RuntimeError('sk-sensitive PRIVATE BODY')),store,tmp_path/'transport.json')
    with pytest.raises(CloudError,match='PROVIDER_ERROR'):client.chat.completions.create(model='gpt-4.1-mini-2025-04-14',messages=[])
    record=json.loads((tmp_path/'transport.json').read_text())
    assert record['attempted_calls']==1 and record['responses_received']==0 and record['cost_unknown'] is True
    assert 'sk-sensitive' not in (tmp_path/'transport.json').read_text()
    with pytest.raises(CloudError,match='TERMINAL'):client.chat.completions.create(model='gpt-4.1-mini-2025-04-14',messages=[])
    assert json.loads((tmp_path/'transport.json').read_text())['attempted_calls']==1


def test_response_checkpoint_failure_keeps_paid_usage_before_raising(tmp_path):
    from evaluation.finalization.cloud_window import CloudCheckpointClient,CloudError
    class Store:
        def checkpoint(self,name,data):
            if name.endswith('end'):raise CloudError('REMOTE_STATE_UNAVAILABLE')
    client=CloudCheckpointClient(sdk(response()),Store(),tmp_path/'transport.json')
    with pytest.raises(CloudError):client.chat.completions.create(model='gpt-4.1-mini-2025-04-14',messages=[])
    record=json.loads((tmp_path/'transport.json').read_text())
    assert record['responses_received']==1 and record['known_cost_usd']==pytest.approx(.0002496)
    assert record['events'][0]['usage']['input_tokens']==400


def test_wrong_snapshot_archive_checksum_rejected_before_extract(tmp_path):
    from evaluation.finalization.cloud_window import extract_snapshot_bundle,CloudError
    source=tmp_path/'wrong.zip';source.write_bytes(b'not ZIP')
    with pytest.raises(CloudError,match='SNAPSHOT_BUNDLE_HASH_MISMATCH'):extract_snapshot_bundle(source,tmp_path/'out')
    assert not (tmp_path/'out').exists()


def test_cloud_workflow_is_manual_only_and_uses_guarded_e2e_adapter():
    path=Path('.github/workflows/network-e2e-once.yml')
    assert path.exists(),'Missing guarded cloud workflow'
    flow=json.loads(path.read_text(encoding='utf-8'))
    assert list(flow['on'])==['workflow_dispatch']
    assert flow['on']['workflow_dispatch']['inputs']['mode']['default']=='preflight'
    assert flow['concurrency']['cancel-in-progress'] is False
    jobs=flow['jobs'];assert 'master' in jobs['e2e']['if']
    assert flow['permissions']['contents']=='write'
    commands='\n'.join(step.get('run','') for step in jobs['e2e']['steps'])
    assert 'scripts.run_network_e2e_cloud' in commands
    assert 'scripts.demo_ctu_network_public --' not in commands
    uploads=[s for s in jobs['e2e']['steps'] if s.get('uses','').startswith('actions/upload-artifact')]
    assert uploads and all(s['if']=='always()' for s in uploads)


def test_outer_report_never_keeps_zero_cost_after_authentic_usage(tmp_path):
    from scripts.run_network_e2e_cloud import merge_transport_accounting
    from evaluation.finalization.cloud_window import CloudCheckpointClient,GitHubWindowStore
    store=GitHubWindowStore(FakeGitAPI(),'a'*40,'123');store.claim('b'*64)
    client=CloudCheckpointClient(sdk(response()),store,tmp_path/'transport.json')
    client.chat.completions.create(model='gpt-4.1-mini-2025-04-14',messages=[])
    report={'new_inference_cost_usd':0,'cost_unknown':False,'cost_summary':{'cost_unknown':True}}
    merge_transport_accounting(report,client)
    assert report['new_inference_cost_usd'] is None
    assert report['known_new_inference_cost_usd']==pytest.approx(.0002496)
    assert report['cost_unknown'] is True  # outer partial uncertainty is never erased
    assert report['openai_transmissions']==1


def test_cloud_ci_uses_actual_remote_jobs_not_supplied_verified_flag():
    from scripts.run_network_e2e_cloud import verify_cloud_ci
    from evaluation.finalization.cloud_window import CloudError
    env={'GITHUB_SHA':'a'*40,'GITHUB_REPOSITORY':'Whats-up-pro/VinSOC','GITHUB_REF':'refs/heads/master','GITHUB_EVENT_NAME':'workflow_dispatch'}
    gates={'implementation_sha':'a'*40,'ci':{'run_url':'https://github.com/Whats-up-pro/VinSOC/actions/runs/123','conclusion':'success'}}
    class API:
        def request(self,method,route,payload=None):
            if route.endswith('/master'):return {'object':{'sha':'a'*40}}
            if '/jobs?' in route:return {'jobs':[{'name':'test (3.11)','conclusion':'success'},{'name':'test (3.12)','conclusion':'failure'}]}
            return {'head_sha':'a'*40,'conclusion':'success'}
    with pytest.raises(CloudError,match='EXACT_SHA_CI_UNVERIFIED'):verify_cloud_ci(API(),gates,env)

@pytest.mark.parametrize('change',[
    {'path':'.github/workflows/unrelated.yml'}, {'head_branch':'other'}, {'event':'pull_request'},
])
def test_cloud_ci_rejects_wrong_workflow_branch_or_event(change):
    from scripts.run_network_e2e_cloud import verify_cloud_ci
    from evaluation.finalization.cloud_window import CloudError
    env={'GITHUB_SHA':'a'*40,'GITHUB_REPOSITORY':'Whats-up-pro/VinSOC','GITHUB_REF':'refs/heads/master','GITHUB_EVENT_NAME':'workflow_dispatch'}
    gates={'implementation_sha':'a'*40,'ci':{'run_url':'https://github.com/Whats-up-pro/VinSOC/actions/runs/123'}}
    class API:
        def request(self,method,route,payload=None):
            if route.endswith('/master'):return {'object':{'sha':'a'*40}}
            if '/jobs?' in route:return {'jobs':[{'name':'test (3.11)','conclusion':'success'},{'name':'test (3.12)','conclusion':'success'}]}
            return dict({'head_sha':'a'*40,'conclusion':'success','path':'.github/workflows/ci.yml','head_branch':'master','event':'push'},**change)
    with pytest.raises(CloudError,match='EXACT_SHA_CI_UNVERIFIED'):verify_cloud_ci(API(),gates,env)


def test_cloud_ci_requires_exact_matrix_jobs_and_accepts_valid_ci():
    from scripts.run_network_e2e_cloud import verify_cloud_ci
    from evaluation.finalization.cloud_window import CloudError
    env={'GITHUB_SHA':'a'*40,'GITHUB_REPOSITORY':'Whats-up-pro/VinSOC','GITHUB_REF':'refs/heads/master','GITHUB_EVENT_NAME':'workflow_dispatch'}
    gates={'implementation_sha':'a'*40,'ci':{'run_url':'https://github.com/Whats-up-pro/VinSOC/actions/runs/123'}}
    class API:
        names=['noop (3.11)','noop (3.12)']
        def request(self,method,route,payload=None):
            if route.endswith('/master'):return {'object':{'sha':'a'*40}}
            if '/jobs?' in route:return {'jobs':[{'name':n,'conclusion':'success'} for n in self.names]}
            return {'head_sha':'a'*40,'conclusion':'success','path':'.github/workflows/ci.yml','head_branch':'master','event':'push'}
    api=API()
    with pytest.raises(CloudError,match='EXACT_SHA_CI_UNVERIFIED'):verify_cloud_ci(api,gates,env)
    api.names=['test (3.11)','test (3.12)'];verify_cloud_ci(api,gates,env)


def test_unknown_total_and_received_response_survive_outer_failure(tmp_path):
    from scripts.run_network_e2e_cloud import merge_transport_accounting
    wrapper=SimpleNamespace(data={'attempted_calls':1,'responses_received':1,'known_cost_usd':0,'cost_unknown':True,'events':[]})
    report={'attempted_calls':1,'responses_received':0,'new_inference_cost_usd':0}
    merge_transport_accounting(report,wrapper)
    assert report['new_inference_cost_usd'] is None
    assert report['known_new_inference_cost_usd']==0
    assert report['responses_received']==1
    assert report['lifecycle_counts']['responses_received']==0
    merge_transport_accounting(report,wrapper)
    assert report['lifecycle_counts']['responses_received']==0
