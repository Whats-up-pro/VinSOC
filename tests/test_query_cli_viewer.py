"""CLI selection and viewer consume locked inventory and real existing receipts."""
import json
from pathlib import Path

import pytest

from scripts.run_vinsoc_query_acceptance import inventory_for


def test_exact_original_question_is_required_before_any_action():
    from scripts.run_vinsoc_query_acceptance import verify_selected_question
    row = inventory_for('pipeline')[0]
    assert verify_selected_question(row['case_id'], row['question']) == row
    with pytest.raises(ValueError, match='EXACT_ORIGINAL_QUESTION_REQUIRED'):
        verify_selected_question(row['case_id'], row['question']+' ')


def test_default_viewer_keeps_four_fixed_ids_and_32_missing_cases(tmp_path):
    from scripts.render_query_pipeline_report import render_report
    source = Path('results/evaluation_v1/text2sql_integration_v1/preflight_pipeline.json')
    output = tmp_path/'viewer.html'
    result = render_report(source, output)
    selection = json.loads(Path('results/evaluation_v1/text2sql_integration_v1/demo_selection.json').read_text())
    assert result['planned'] == 32
    assert result['cases'] == 0
    assert result['missing'] == 32
    assert result['api_calls'] == 0
    page = output.read_text(encoding='utf-8')
    for row in selection['cases']:
        assert row['case_id'] in page and row['question'] in page
    assert page.count('data-case-id=') == 32
    assert '<script' not in page


def test_saved_artifact_text_is_escaped():
    from scripts.render_query_pipeline_report import escaped_json
    saved = json.loads(Path('results/evaluation_v1/ctu_network_public/r2_phase2_live/20261001_3f9d72d/suite/report.json').read_text())
    sql = next(r['final_sql'] for r in saved['case_results'] if r['final_sql'] and '<' in r['final_sql'])
    encoded = escaped_json(sql)
    assert '<' not in encoded
    assert '&lt;' in encoded


def test_human_review_hash_mismatch_does_not_join():
    from evaluation.finalization.query_pipeline_reporting import validate_review
    real = json.loads(Path('results/evaluation_v1/text2sql_integration_v1/original_data_20261010/ci_verification.json').read_text())
    assert validate_review(real, real) is False


@pytest.mark.parametrize('value', ['', '2026-10-10T12:00:00', '2026-10-10T12:00:00+07:00'])
def test_review_requires_analyst_entered_utc(value):
    from scripts.review_vinsoc_query_case import validate_review_utc
    with pytest.raises(ValueError, match='ACTUAL_UTC_REQUIRED'):
        validate_review_utc(value)


def test_duplicate_real_inventory_is_rejected():
    from evaluation.finalization.query_pipeline_reporting import build_pipeline_report
    inventory = inventory_for('pipeline')
    with pytest.raises(ValueError, match='DUPLICATE_PLANNED_CASE'):
        build_pipeline_report([], inventory+[inventory[0]], reviews=[], identities={}, journal={})
