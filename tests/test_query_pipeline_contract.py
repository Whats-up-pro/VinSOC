"""No SDK/transport stand-ins; release gates are checked without paid calls."""
import pytest

from evaluation.finalization.query_pipeline_contract import preflight, role_caps
from vinsoc_text2sql.accounting import RunJournal


def test_release_denies_missing_inputs_without_client():
    receipt = preflight('pipeline', 'E3', inventory=[], identities={}, account={}, pricing={}, budget={})
    assert receipt['authorized'] is False
    assert receipt['attempted'] == receipt['received'] == 0
    assert receipt['client_created'] is False
    assert 'FULL_LOCKED_INVENTORY_UNVERIFIED' in receipt['reasons']
    assert 'PAID_RELEASE_NOT_AUTHORIZED' in receipt['reasons']


def test_all_layers_counted_in_upper_bound():
    assert role_caps('calibration', 'E3') == {'routing': 0, 'r2': 168, 'assessment': 0}
    assert role_caps('evaluation', 'E3') == {'routing': 0, 'r2': 672, 'assessment': 0}
    assert role_caps('pipeline', 'E3') == {'routing': 32, 'r2': 192, 'assessment': 32}
    assert role_caps('pipeline', 'E0') == {'routing': 32, 'r2': 32, 'assessment': 32}


def test_single_demo_reserves_one_complete_e3_case_without_selection_gate():
    from scripts.run_vinsoc_query_acceptance import inventory_for

    selected = inventory_for('demo')
    assert len(selected) == 1
    assert role_caps('demo', 'E3') == {'routing': 1, 'r2': 6, 'assessment': 1}
    receipt = preflight('demo', 'E3', inventory=selected, identities={},
                        account={}, pricing={}, budget={})
    assert receipt['planned'] == 1
    assert receipt['case_ids'] == [selected[0]['case_id']]
    assert receipt['window_id'] == 'text2sql-integration-20261008-demo-'+selected[0]['case_id']
    assert 'CALIBRATION_SELECTION_LOCK_REQUIRED' not in receipt['reasons']


def test_single_demo_rejects_non_e3_condition():
    with pytest.raises(ValueError, match='DEMO_REQUIRES_E3'):
        role_caps('demo', 'E0')


def test_second_demo_uses_a_distinct_immutable_window():
    from scripts.run_vinsoc_query_acceptance import inventory_for
    selected = inventory_for('demo')
    receipt = preflight('demo', 'E3', inventory=selected, identities={},
                        account={}, pricing={}, budget={}, execution_id='full-e2e-2')
    assert receipt['execution_id'] == 'full-e2e-2'
    assert receipt['window_id'].endswith('-full-e2e-2')


def test_denied_release_cannot_claim_window(tmp_path):
    release = preflight('pipeline', 'E3', inventory=[], identities={}, account={}, pricing={}, budget={})
    with pytest.raises(ValueError, match='RELEASE_NOT_AUTHORIZED'):
        RunJournal.claim(release, ledger_path=tmp_path/'ledger.json')
    assert not list(tmp_path.iterdir())


def test_self_declared_framing_flag_cannot_reserve_paid_exposure():
    from datetime import datetime, timezone
    from scripts.run_vinsoc_query_acceptance import inventory_for
    pricing = {'gpt-5-mini-2025-08-07': {
        'checked_utc': datetime.now(timezone.utc).isoformat(),
        'input_bound_verified': True, 'source_url': 'https://developers.openai.com/api/docs/pricing',
        'input_usd_per_million': .25, 'output_usd_per_million': 2,
    }}
    receipt = preflight('calibration', 'E3', inventory=inventory_for('calibration'),
                        identities={}, account={}, pricing=pricing, budget={})
    assert receipt['reserves_usd'] == {}
    assert 'PRICING_OR_TOKEN_BOUND_UNVERIFIED_R2' in receipt['reasons']


def test_missing_canonical_ledger_is_unknown_not_zero(tmp_path):
    from scripts.prepare_query_budget import inspect_canonical
    observed = inspect_canonical(tmp_path/'absent-canonical-ledger')
    assert observed['known_prior_cost_usd'] is None
    assert observed['unknown_exposure_usd'] is None
    assert observed['verified_remaining_allocation_usd'] is None
    assert observed['authoritative_host_verified'] is False


def test_changed_document_hash_cannot_authorize_input_bound():
    from datetime import datetime, timezone
    from pathlib import Path
    from evaluation.finalization.query_token_bound import verified_input_bound, MODEL_DOCS
    model = 'gpt-5-mini-2025-08-07'
    actual = Path('results/evaluation_v1/text2sql_integration_v1/demo_selection.json')
    assert actual.is_file()
    pricing = {'checked_utc':datetime.now(timezone.utc).isoformat(),
               'token_bound_method':'documented_context_window',
               'model_document':{'source_url':MODEL_DOCS[model], 'path':str(actual), 'sha256':'0'*64}}
    with pytest.raises(ValueError, match='MODEL_DOCUMENT_HASH_MISMATCH'):
        verified_input_bound(pricing, model)


def test_budget_package_includes_single_demo_e3_ceiling(monkeypatch):
    import scripts.prepare_query_budget as budgeter
    monkeypatch.setattr(budgeter, 'verified_input_bound',
                        lambda pricing, model: pricing['input_token_ceiling'])
    pricing = {
        'gpt-5-mini-2025-08-07': {'input_token_ceiling':400000,
            'input_usd_per_million':.25,'output_usd_per_million':2},
        'gpt-4.1-mini-2025-04-14': {'input_token_ceiling':1047576,
            'input_usd_per_million':.4,'output_usd_per_million':1.6},
    }
    result = budgeter.cost_bound(pricing, 'documented_context_window')
    demo = result['scopes']['demo_E3']
    assert demo['request_caps_by_role'] == {'routing':1,'r2':6,'assessment':1}
    assert demo['max_requests'] == 8
    assert float(demo['new_cost_ceiling_usd']) == pytest.approx(1.4532608)
