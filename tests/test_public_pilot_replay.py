"""Offline scoring of stored public R2 predictions; never instantiate a provider."""

import pytest

from evaluation.text_to_sql import SQLBenchmarkCase
from scripts.replay_r2_public_pilot import replay_saved_predictions
from vinsoc_data.duckdb_store import DuckDBSnapshot, SocSnapshotBuilder


def test_replay_scores_saved_sql_without_model_and_preserves_original_verdict(tmp_path):
    path = tmp_path / "replay.duckdb"
    SocSnapshotBuilder(path).create_empty_snapshot()
    case = SQLBenchmarkCase(
        "sample_001", "Count one", str(path), ("SELECT 1 AS value",),
        "aggregation", "basic", "scalar",
    )
    original = [{"case_id": case.case_id, "generated_sql": "SELECT 1 AS value;",
                 "error_category": "SAFETY_REJECTION", "execution_accurate": False,
                 "safety_rejected": True}]
    results, metrics = replay_saved_predictions(original, [case], DuckDBSnapshot(path))
    assert original[0]["error_category"] == "SAFETY_REJECTION"
    assert results[0]["v1"]["error_category"] == "SAFETY_REJECTION"
    assert results[0]["v2"] == {
        "error_category": "OK", "syntax_valid": True, "execution_success": True,
        "execution_accurate": True, "safety_rejected": False, "error": None,
    }
    assert metrics == {"syntax_validity_rate": 1.0, "execution_success_rate": 1.0,
                       "execution_accuracy": 1.0, "safety_rejection_rate": 0.0}


def test_replay_rejects_missing_or_duplicated_saved_predictions(tmp_path):
    path = tmp_path / "empty.duckdb"
    SocSnapshotBuilder(path).create_empty_snapshot()
    case = SQLBenchmarkCase("sample_001", "Count one", str(path),
                            ("SELECT 1",), "aggregation", "basic", "scalar")
    result = {"case_id": "sample_001", "generated_sql": "SELECT 1",
              "error_category": "OK", "execution_accurate": True}
    snapshot = DuckDBSnapshot(path)
    with pytest.raises(ValueError, match="case IDs"):
        replay_saved_predictions([], [case], snapshot)
    with pytest.raises(ValueError, match="case IDs"):
        replay_saved_predictions([result, result], [case], snapshot)
