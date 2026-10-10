"""Fault-input durability tests, not fabricated model runs or acceptance records."""
import json

import pytest

from vinsoc_text2sql.accounting import RunJournal


def journal_for_fault_input(tmp_path):
    journal = RunJournal()
    journal.path = tmp_path/'journal.json'
    journal.release = {'contracts': {'r2': {'model': 'gpt-5-mini-2025-08-07'}}, 'gate_inputs': {'pricing': {}}}
    journal.data = {'attempted': 1, 'received': 0, 'valid_usage': 0, 'known_usd': 0,
                    'pending_exposure_usd': .01, 'cost_unknown': True, 'terminal': False,
                    'events': [{'role': 'r2', 'received': False, 'reserved_usd': .01,
                                'cost_usd': None, 'case_id': 'invalid-input-only', 'condition': 'E0'}]}
    return journal


def test_malformed_response_is_saved_before_usage_validation(tmp_path):
    journal = journal_for_fault_input(tmp_path)
    # Deliberately malformed input: never exported as a model prediction.
    raw = {'usage': None}
    with pytest.raises(ValueError, match='MISSING_OR_INVALID_USAGE'):
        journal.record_response(0, raw)
    saved = json.loads(journal.path.read_text())
    assert saved['events'][0]['response'] == raw
    assert saved['received'] == 1
    assert saved['terminal'] and saved['cost_unknown']
    assert saved['pending_exposure_usd'] == .01
    assert saved['events'][0]['cost_usd'] is None


def test_crash_after_reserve_never_reopens_claim(tmp_path, monkeypatch):
    from evaluation.finalization.query_runtime_validation import verify_scope_unused
    monkeypatch.setattr('pathlib.Path.home', lambda: tmp_path)
    window = tmp_path/'.vinsoc/live-windows/text2sql-integration-20261008-pipeline'
    window.mkdir(parents=True)
    (window/'claim.json').write_text('{}')
    # No ledger exists: an interrupted atomic claim is still consumed.
    with pytest.raises(ValueError, match='RELEASE_WINDOW_CONSUMED'):
        verify_scope_unused('pipeline')


def test_unknown_exposure_blocks_further_transmission(tmp_path):
    journal = journal_for_fault_input(tmp_path)
    with pytest.raises(ValueError, match='TERMINAL_OR_UNKNOWN_COST'):
        journal.reserve('r2', {})
    assert journal.data['attempted'] == 1


def test_remote_claim_precedes_local_demo_claim(tmp_path, monkeypatch):
    import vinsoc_text2sql.accounting as accounting

    monkeypatch.setattr(accounting, 'validate_release', lambda release: release)
    monkeypatch.setattr('pathlib.Path.home', lambda: tmp_path)
    release = {'window_id':'text2sql-integration-20261008-demo-case',
               'release_sha256':'abc',
               'gate_inputs':{'account':{'known_prior_cost_usd':0}}}
    ledger = tmp_path/'.vinsoc/live-windows'/release['window_id']/'ledger.json'
    calls = []
    class Store:
        def claim(self, window_id, release_sha256):
            assert not ledger.parent.exists()
            calls.append((window_id, release_sha256))
    journal = RunJournal.claim(release, ledger_path=ledger, remote_store=Store())
    assert calls == [(release['window_id'], 'abc')]
    assert journal.remote_store is not None


def test_remote_begin_checkpoint_is_durable_before_transport(tmp_path, monkeypatch):
    import vinsoc_text2sql.accounting as accounting

    journal = RunJournal()
    journal.path = tmp_path/'ledger.json'
    checkpoints = []
    class Store:
        def checkpoint(self, request_number, phase, event):
            checkpoints.append((request_number, phase, event))
    journal.remote_store = Store()
    journal.release = {
        'role_caps':{'r2':1}, 'reserves_usd':{'r2':.102},
        'contracts':{'r2':{'model':'gpt-5-mini-2025-08-07','reasoning_effort':'low',
            'max_completion_tokens':1000,'service_tier':'default','max_request_bytes':32768,
            'max_messages':20}},
        'gate_inputs':{'budget':{'limit_usd':3},'identities':{},
            'pricing':{'gpt-5-mini-2025-08-07':{}}}}
    journal.data = {'attempted':0,'received':0,'valid_usage':0,'known_usd':0,
                    'pending_exposure_usd':0,'cost_unknown':False,'terminal':False,'events':[]}
    journal.case_id, journal.condition = 'case', 'E3'
    monkeypatch.setattr('evaluation.finalization.query_runtime_validation.verify_transmission_files', lambda _: None)
    monkeypatch.setattr('evaluation.finalization.query_token_bound.verified_input_bound', lambda *_: 400000)
    payload = {'model':'gpt-5-mini-2025-08-07','reasoning_effort':'low',
               'max_completion_tokens':1000,'service_tier':'default','messages':[]}
    assert journal.reserve('r2', payload) == 0
    assert checkpoints[0][0:2] == (1, 'begin')
    assert 'request' not in checkpoints[0][2]
    assert json.loads(journal.path.read_text())['attempted'] == 1
