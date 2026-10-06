"""Pre-inference exclusion evidence must distinguish source and fixture errors."""
import json

import pytest


def receipt(path, records):
    path.write_text(json.dumps({"scope": "candidate_semantic_validation_not_benchmark_or_model_score",
        "external_model_calls": 0, "benchmark_locked": False, "blocked": records}), encoding="utf-8")
    return path


def test_only_proved_source_tie_or_dialect_failure_is_excluded(tmp_path):
    from evaluation.r2_cross_domain_v1.case_preparation import read_semantic_exclusions
    path = receipt(tmp_path / "audit.json", [
        {"case_id": "source_tie", "fixture_sqlite_duckdb_parity": [{"parity": True, "ordering_validation": "AMBIGUOUS_LIMIT_TIE"}]},
        {"case_id": "generator_unresolved", "fixture_sqlite_duckdb_parity": [{"parity": True, "ordering_validation": "PASS"}], "semantic": {"semantic_mutants_killed": 0}},
    ])
    result = read_semantic_exclusions([path])
    assert [item["case_id"] for item in result] == ["source_tie"]
    assert result[0]["evidence_sha256"]


def test_exclusion_cannot_use_model_failure_to_remove_a_case(tmp_path):
    from evaluation.r2_cross_domain_v1.case_preparation import read_semantic_exclusions
    path = receipt(tmp_path / "audit.json", [])
    value = json.loads(path.read_text(encoding="utf-8"))
    value["external_model_calls"] = 1
    path.write_text(json.dumps(value), encoding="utf-8")
    with pytest.raises(ValueError, match="PRE_INFERENCE"):
        read_semantic_exclusions([path])
