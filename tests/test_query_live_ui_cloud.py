import importlib
import importlib.util
import json

import openai


def test_missing_inputs_cannot_create_sdk_client(tmp_path, monkeypatch):
    assert importlib.util.find_spec('scripts.run_query_live_ui_cloud'), 'Live UI cloud runner missing'
    m = importlib.import_module('scripts.run_query_live_ui_cloud')
    def forbidden(*args, **kwargs):
        raise AssertionError('Missing release must not create SDK client')
    monkeypatch.setattr(openai, 'OpenAI', forbidden)
    result = m.run('preflight', tmp_path/'out', {})
    assert result['status'] == 'blocked'
    assert result['attempted'] == result['received'] == 0
    assert result['client_created'] is False


def test_evaluation_private_inputs_bind_canonical_selection_hash(tmp_path, monkeypatch):
    m = importlib.import_module('scripts.run_query_live_ui_cloud')
    lock = tmp_path/'results/evaluation_v1/text2sql_integration_v1/selection_lock.json'
    lock.parent.mkdir(parents=True)
    lock.write_text(json.dumps({'selection_sha256': 'a'*64}), encoding='utf-8')
    reconciliation = tmp_path/'reconciliation.json'
    reconciliation.write_text(json.dumps({'scope_states': {}}), encoding='utf-8')
    prepared = {
        'budget': {},
        'account': {'reconciliation_reference': {
            'path': str(reconciliation),
            'sha256': 'unused-before-rewrite',
        }},
        'identities': {},
    }
    monkeypatch.setattr(m, 'ROOT', tmp_path)
    monkeypatch.setattr(m, 'catalog', lambda scope: [{'case_id': 'ctu_cross_708b66575657429a'}])
    monkeypatch.setattr(m, 'prepare_private_inputs', lambda *args, **kwargs: prepared)

    result = m.private_inputs(
        {'scope': 'evaluation', 'case_id': None,
         'execution_id': 'liveui-'+'1'*24, 'limit_usd': 100.0},
        {},
        123,
        {'known_usd': 1.0, 'remaining_usd': 99.0, 'receipts': []},
    )

    assert result['identities']['selection_lock_path'] == str(lock)
    assert result['identities']['selection_sha256'] == 'a'*64
