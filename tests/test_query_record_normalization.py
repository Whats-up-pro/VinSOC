"""Actual inventory and missing outputs; never manufacture calibration predictions."""
from scripts.run_vinsoc_query_acceptance import inventory_for
import json
from pathlib import Path
import pytest


def test_missing_records_keep_192_slots_and_no_scores():
    from evaluation.finalization.query_record_normalization import normalize_query_records
    result = normalize_query_records([], inventory_for('evaluation'), identities={}, journal={})
    assert len(result) == 192
    assert all(r['present'] is False and r['execution_accurate'] is None for r in result)
    assert all(r['usage_valid'] is False and r['provenance_valid'] is False for r in result)
    assert {r['planned_case_count'] for r in result} == {96}


def test_statistics_and_modules_do_not_turn_missing_into_accuracy():
    from evaluation.finalization.query_reporting import build_query_report
    report = build_query_report([], inventory_for('evaluation'), identities={}, journal={})
    assert report['statistics']['paired']['complete'] is False
    assert report['statistics']['paired']['delta'] is None
    for condition in ('E0','E3'):
        assert report['statistics']['conditions'][condition]['micro']['rate'] is None
        assert report['modules']['conditions'][condition]['execution_accuracy']['rate'] is None
        assert report['conditions'][condition]['difficulty']['basic']['planned'] == 24
        assert report['conditions'][condition]['difficulty']['medium']['planned'] == 48
        assert report['conditions'][condition]['difficulty']['advanced']['planned'] == 24


def test_archived_sql_cannot_be_relabelled_as_new_evaluation():
    from evaluation.finalization.query_record_normalization import normalize_query_records
    saved = json.loads(Path('results/evaluation_v1/ctu_network_public/r2_phase2_live/20261001_3f9d72d/suite/report.json').read_text())
    with pytest.raises(ValueError, match='FOREIGN_CASE_RECORD'):
        normalize_query_records(saved['case_results'], inventory_for('evaluation'), identities={}, journal={})
