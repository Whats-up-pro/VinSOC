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


def test_demo_inventory_is_one_fixed_selection_with_exact_original_question():
    from scripts.run_vinsoc_query_acceptance import verify_selected_question

    selection = json.loads(Path('results/evaluation_v1/text2sql_integration_v1/demo_selection.json').read_text())
    chosen = selection['cases'][0]
    row = verify_selected_question(chosen['case_id'], chosen['question'], require_demo=True)
    assert inventory_for('demo', case_id=chosen['case_id'], question=chosen['question']) == [row]
    with pytest.raises(ValueError, match='FIXED_DEMO_SELECTION_REQUIRED'):
        verify_selected_question(inventory_for('pipeline')[0]['case_id'],
                                 inventory_for('pipeline')[0]['question'], require_demo=True)
    with pytest.raises(ValueError, match='EXACT_ORIGINAL_QUESTION_REQUIRED'):
        inventory_for('demo', case_id=chosen['case_id'], question=chosen['question']+' ')


def test_demo_cli_passes_one_locked_case_to_preflight(monkeypatch, tmp_path):
    import scripts.run_vinsoc_query_acceptance as runner

    chosen = json.loads(Path('results/evaluation_v1/text2sql_integration_v1/demo_selection.json').read_text())['cases'][0]
    captured = {}
    def fake_preflight(scope, condition, private, *, selected_input=None):
        captured.update(scope=scope, condition=condition, selected_input=selected_input)
        return {'release': {'status': 'preflight_pass', 'planned': 1, 'attempted': 0,
                            'received': 0, 'client_created': False, 'gate_inputs': {}},
                'diagnostics': [], 'client_created': False, 'attempted': 0, 'received': 0}
    monkeypatch.setattr(runner, 'run_preflight', fake_preflight)
    output = tmp_path/'preflight.json'
    assert runner.main(['--scope','demo','--condition','E3','--preflight-only',
                        '--case-id',chosen['case_id'],'--question',chosen['question'],
                        '--output',str(output)]) == 0
    assert captured == {'scope':'demo', 'condition':'E3', 'selected_input':chosen}
    saved = json.loads(output.read_text())
    assert saved['release']['attempted'] == saved['release']['received'] == 0
    assert saved['release']['client_created'] is False


def test_live_entrypoint_accepts_remote_store_for_ephemeral_runner():
    import inspect
    from scripts.run_vinsoc_query_acceptance import run_live
    assert 'remote_store' in inspect.signature(run_live).parameters


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


@pytest.mark.parametrize('utc', ['2026-10-10T00:00:00Z', None])
def test_null_analyst_and_rationale_are_missing_review_fields(utc):
    import hashlib
    from evaluation.finalization.query_pipeline_reporting import validate_review
    actual_receipt = Path('results/evaluation_v1/text2sql_integration_v1/original_data_20261010/ci_verification.json')
    record = {'case_id':inventory_for('pipeline')[0]['case_id'],
              'case_receipt_sha256':hashlib.sha256(actual_receipt.read_bytes()).hexdigest()}
    # Malformed review metadata only: no human decision or prediction is created/exported.
    invalid = {'scope':'actual_human_review','case_id':record['case_id'],
               'case_receipt_sha256':record['case_receipt_sha256'], 'decision':'escalated',
               'analyst':None,'rationale':None,'utc':utc}
    assert validate_review(invalid, record) is False
