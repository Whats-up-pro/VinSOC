"""Remote one-shot boundaries for the paid single-case query demo."""
import pytest


class FakeAPI:
    def __init__(self, existing=False):
        self.existing = existing
        self.calls = []

    def request(self, method, route, payload=None):
        self.calls.append((method, route, payload))
        if method == 'GET' and '/git/ref/tags/' in route:
            return {'object': {'sha': 'a'*40}} if self.existing else None
        if route.endswith('/git/tags'):
            return {'sha': 'b'*40}
        return {'ok': True}


def test_demo_remote_store_claims_unique_tag_before_checkpoints():
    from evaluation.finalization.query_cloud import QueryDemoGitHubStore

    api = FakeAPI()
    store = QueryDemoGitHubStore(api, implementation_sha='a'*40, run_id='123')
    window = 'text2sql-integration-20261008-demo-ctu_cross_708b66575657429a'
    store.claim(window, 'c'*64)
    store.checkpoint(1, 'begin', {'role':'routing','request_sha256':'request-hash'})
    refs = [call[2]['ref'] for call in api.calls if call[1].endswith('/git/refs')]
    assert refs[0].startswith('refs/tags/vinsoc-query-demo-')
    assert refs[1].endswith('-request-1-begin')
    assert store.claimed is True


def test_existing_demo_remote_tag_blocks_without_new_ref():
    from evaluation.finalization.query_cloud import QueryDemoGitHubStore, QueryCloudError

    api = FakeAPI(existing=True)
    store = QueryDemoGitHubStore(api, implementation_sha='a'*40, run_id='123')
    with pytest.raises(QueryCloudError, match='WINDOW_ALREADY_USED'):
        store.claim('text2sql-integration-20261008-demo-case', 'c'*64)
    assert not any(call[1].endswith('/git/refs') for call in api.calls)


def test_cloud_runner_missing_inputs_stops_before_client_or_claim(tmp_path):
    from scripts.run_query_demo_cloud import run
    result = run('live', tmp_path/'output', {})
    assert result['status'] == 'blocked'
    assert result['attempted'] == result['received'] == 0
    assert result['client_created'] is False
    assert result['window_claimed'] is False
    assert 'OPENAI_API_KEY' in result['missing_inputs']


def test_cloud_authorization_is_exactly_three_dollars_for_fixed_case():
    from datetime import datetime, timezone
    from scripts.run_query_demo_cloud import validate_authorization
    valid = {'allocation_id':'demo-allocation','limit_usd':3.0,'known_prior_cost_usd':0.0,
             'remaining_allocation_usd':3.0,'unknown_exposure_usd':0.0,
             'scope':'demo','condition':'E3','case_id':'ctu_cross_708b66575657429a',
             'confirmed_utc':datetime.now(timezone.utc).isoformat()}
    assert validate_authorization(valid) == valid
    with pytest.raises(ValueError, match='DEMO_AUTHORIZATION_INVALID'):
        validate_authorization({**valid, 'limit_usd':3.01})


def test_demo_workflow_is_bound_into_runtime_identity():
    from evaluation.finalization.query_runtime_validation import source_hashes
    assert '.github/workflows/query-demo-once.yml' in source_hashes()
