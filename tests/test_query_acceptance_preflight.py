"""Only offline rejection paths; no SDK stand-ins or paid authorization."""
import pytest

from evaluation.finalization.query_pipeline_contract import preflight
from scripts.run_vinsoc_query_acceptance import inventory_for


@pytest.mark.parametrize('scope', ['evaluation', 'pipeline'])
def test_missing_selection_denied_before_client(scope):
    result = preflight(scope, 'E3', inventory=inventory_for(scope), identities={},
                       account={}, pricing={}, budget={})
    assert 'CALIBRATION_SELECTION_LOCK_REQUIRED' in result['reasons']
    assert result['attempted'] == result['received'] == 0
    assert result['client_created'] is False


def test_consumed_scope_blocks_without_account_or_sdk(tmp_path, monkeypatch):
    from evaluation.finalization.query_runtime_validation import verify_scope_unused
    monkeypatch.setattr('pathlib.Path.home', lambda: tmp_path)
    window = tmp_path/'.vinsoc/live-windows/text2sql-integration-20261008-calibration'
    window.mkdir(parents=True)
    (window/'claim.json').write_text('{}')
    with pytest.raises(ValueError, match='RELEASE_WINDOW_CONSUMED'):
        verify_scope_unused('calibration')


def test_source_mutation_is_rejected_at_transmission_boundary():
    from evaluation.finalization.query_runtime_validation import verify_transmission_files
    with pytest.raises(ValueError, match='RUNTIME_SOURCE_IDENTITY_MISMATCH'):
        verify_transmission_files({'runtime_source_sha256': {}, 'transmission_files_sha256': {}})


def test_missing_ledger_is_not_zero_prior_cost():
    from evaluation.finalization.query_runtime_validation import verify_canonical_reconciliation
    with pytest.raises(ValueError, match='CANONICAL_RECONCILIATION_REQUIRED'):
        verify_canonical_reconciliation({'known_prior_cost_usd': 0, 'remaining_allocation_usd': 100})


def test_unfinished_checkpoint_is_retained_in_partial_report():
    from scripts.run_vinsoc_query_acceptance import retain_active_checkpoint
    row = inventory_for('pipeline')[0]
    # Real inventory metadata only; no SQL, model output, score or review is supplied.
    active = {'case_id':row['case_id'],'condition':'E3','question':row['question'],'status':'partial'}
    report = {'case_records':[],'completed':0}
    retain_active_checkpoint(report, active)
    assert report['case_records'] == [active]
    assert report['completed'] == 0
    retain_active_checkpoint(report, active)
    assert len(report['case_records']) == 1
