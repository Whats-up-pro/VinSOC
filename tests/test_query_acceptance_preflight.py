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


def test_demo_reconciliation_requires_demo_scope_state(tmp_path, monkeypatch):
    import json
    from datetime import datetime, timezone
    from evaluation.r2_cross_domain_v1.benchmark_lock import file_hash
    from evaluation.finalization.query_runtime_validation import verify_canonical_reconciliation

    monkeypatch.setattr('pathlib.Path.home', lambda: tmp_path)
    canonical = tmp_path/'.vinsoc/live-windows'
    canonical.mkdir(parents=True)
    ledger = canonical/'allocation-ledger.json'
    ledger.write_text('{}')
    receipt_path = canonical/'reconciliation.json'
    receipt = {'verified_utc':datetime.now(timezone.utc).isoformat(),
               'authoritative_host_verified':True, 'prior_hosts_sealed':True,
               'unknown_exposure_usd':0, 'allocation_id':'demo-$3',
               'known_prior_cost_usd':0, 'remaining_allocation_usd':3,
               'scope_states':{'calibration':'outside_allocation','evaluation':'outside_allocation',
                               'pipeline':'outside_allocation'},
               'ledger_artifacts':[{'path':ledger.name,'sha256':file_hash(ledger)}]}
    receipt_path.write_text(json.dumps(receipt))
    account = {'allocation_id':'demo-$3','known_prior_cost_usd':0,'remaining_allocation_usd':3,
               'reconciliation_reference':{'path':str(receipt_path),'sha256':file_hash(receipt_path)}}
    with pytest.raises(ValueError, match='CANONICAL_RECONCILIATION_UNVERIFIED'):
        verify_canonical_reconciliation(account, required_scope='demo')
    receipt['scope_states']['demo'] = 'unused'
    receipt_path.write_text(json.dumps(receipt))
    account['reconciliation_reference']['sha256'] = file_hash(receipt_path)
    assert verify_canonical_reconciliation(account, required_scope='demo') == receipt


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
