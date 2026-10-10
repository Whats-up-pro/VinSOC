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
