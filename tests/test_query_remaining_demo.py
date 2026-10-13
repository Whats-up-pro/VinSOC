"""Remaining demo gates use pinned inventory and authentic prior receipts."""
from datetime import datetime, timezone
import json
from pathlib import Path

import pytest


def authorization():
    selection = json.loads(Path('results/evaluation_v1/text2sql_integration_v1/demo_selection.json').read_text())
    return {'scope': 'remaining_demo3', 'condition': 'E3',
            'allocation_id': 'mentor-remaining3-20261013',
            'execution_id': 'mentor-remaining3-20261013',
            'case_ids': [r['case_id'] for r in selection['cases'][1:]],
            'limit_usd': 3.0, 'known_prior_cost_usd': 0.061155,
            'remaining_allocation_usd': 2.938845, 'unknown_exposure_usd': 0.0,
            'confirmed_utc': datetime.now(timezone.utc).isoformat()}


def test_remaining_authorization_binds_exact_three_unrun_ids_and_all_prior_cost():
    from scripts.run_query_remaining_demo_cloud import validate_remaining_authorization, remaining_selection, verified_prior_receipts
    auth = authorization()
    assert validate_remaining_authorization(auth) == auth
    assert [r['case_id'] for r in remaining_selection()] == auth['case_ids']
    prior = verified_prior_receipts()
    assert len(prior) == 10
    assert prior[-1]['workflow_run_id'] == 38338493466
    assert sum(r['known_cost_usd'] for r in prior) == pytest.approx(0.061155)


@pytest.mark.parametrize('mutation', ['first_case', 'reordered', 'missing', 'larger_budget', 'zero_prior', 'unknown', 'stale'])
def test_remaining_authorization_cannot_expand_or_reset_scope(mutation):
    from scripts.run_query_remaining_demo_cloud import validate_remaining_authorization
    auth = authorization()
    if mutation == 'first_case':
        auth['case_ids'][0] = 'ctu_cross_708b66575657429a'
    elif mutation == 'reordered':
        auth['case_ids'].reverse()
    elif mutation == 'missing':
        auth['case_ids'].pop()
    elif mutation == 'larger_budget':
        auth['limit_usd'] = 3.01
    elif mutation == 'zero_prior':
        auth['known_prior_cost_usd'] = 0.0
    elif mutation == 'unknown':
        auth['unknown_exposure_usd'] = 0.1
    else:
        auth['confirmed_utc'] = '2020-01-01T00:00:00Z'
    with pytest.raises(ValueError, match='REMAINING_DEMO_AUTHORIZATION_INVALID'):
        validate_remaining_authorization(auth)


def test_remaining_cloud_missing_inputs_never_creates_client_or_claim(tmp_path):
    from scripts.run_query_demo_cloud import run
    result = run('live', tmp_path/'output', {}, selection_mode='remaining3')
    assert result['status'] == 'blocked'
    assert result['attempted'] == result['received'] == 0
    assert result['client_created'] is False
    assert result['window_claimed'] is False


@pytest.mark.parametrize('mutation', ['unknown', 'unreceived', 'duplicate_response', 'missing_cost', 'other_case', 'terminal'])
def test_sequential_case_cost_reconciliation_rejects_unknown_or_unreceived(mutation):
    from scripts.run_query_remaining_demo_cloud import reconcile_case_report
    saved = json.loads(Path('results/evaluation_v1/text2sql_integration_v1/single_demo_full_e2e_10_20261013/runner_report.json').read_text())
    assert reconcile_case_report(saved, expected_case_id=saved['case_records'][0]['case_id']) == pytest.approx(0.00739705)
    if mutation == 'unknown':
        saved['cost_unknown'] = True
    elif mutation == 'unreceived':
        saved['cost_events'][0]['received'] = False
    elif mutation == 'duplicate_response':
        saved['cost_events'][1]['response_id'] = saved['cost_events'][0]['response_id']
    elif mutation == 'missing_cost':
        saved['cost_events'][0]['cost_usd'] = None
    elif mutation == 'other_case':
        saved['cost_events'][0]['case_id'] = 'outside-the-authorized-case'
    else:
        saved['terminal'] = True
    with pytest.raises(ValueError, match='REMAINING_DEMO_COST_UNRECONCILED'):
        reconcile_case_report(saved, expected_case_id=saved['case_records'][0]['case_id'])


def test_remaining_runner_is_bound_into_runtime_identity():
    from evaluation.finalization.query_runtime_validation import source_hashes
    assert 'scripts/run_query_remaining_demo_cloud.py' in source_hashes()


def test_workflow_requires_explicit_remaining_selection_mode():
    workflow = Path('.github/workflows/query-demo-once.yml').read_text(encoding='utf-8')
    assert 'selection_mode:' in workflow
    assert '- remaining3' in workflow
    assert '--selection-mode "${{ inputs.selection_mode }}"' in workflow
    assert 'Preserve canonical journals after failure or cancellation' in workflow


def test_remaining_guards_are_required_in_both_python_ci_jobs():
    ci = Path('.github/workflows/ci.yml').read_text(encoding='utf-8')
    assert 'tests/test_query_remaining_demo.py' in ci
    assert 'REQUIRED_OFFLINE_GUARD_SKIP_FORBIDDEN' in ci
