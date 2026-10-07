"""Hand-checked offline report fixtures, never model-run evidence."""
import pytest


def inventory():
    return {"cases": [
        {"case_id": "a", "database_id": "db1", "domain": "music", "family_id": "fa", "difficulty": "basic", "features": []},
        {"case_id": "b", "database_id": "db2", "domain": "school", "family_id": "fb", "difficulty": "medium", "features": ["join"]},
    ], "conditions": ["E3"]}


def record(case_id="a", **changes):
    result = {"case_id": case_id, "condition": "E3", "final_sql": "SELECT 1", "syntax_valid": True,
              "execution_success": True, "execution_accurate": True, "semantic_test_accuracy": True,
              "semantic_instances_correct": 3, "semantic_instances_total": 3, "safety_rejected": False,
              "error_category": "OK", "scoring_error_category": "OK", "attempted_calls": 1,
              "response_count": 1, "db_calls": 0, "wall_seconds": .5, "evidence_kind": "synthetic_transport",
              "modules": {"schema_linker": None, "value_grounding": None},
              "responses": [{"response": {"model": "pinned", "usage": {"input_tokens": 10, "output_tokens": 5}, "cost_usd": .01}}]}
    result.update(changes)
    return result


def test_missing_case_and_no_final_sql_stay_in_planned_denominator():
    from evaluation.r2_cross_domain_v1.reporting import build_evaluation_report
    report = build_evaluation_report([record(final_sql=None, error_category="TOOL_LIMIT", execution_accurate=False,
        syntax_valid=False, execution_success=False, semantic_test_accuracy=False)], inventory())
    e3 = report["conditions"]["E3"]
    assert e3["execution_accuracy"] == {"correct": 0, "total": 2, "rate": 0.0}
    assert e3["coverage"] == {"received": 1, "planned": 2, "missing_case_ids": ["b"]}
    assert e3["cases"][0]["primary_error"] == "NO_FINAL_SQL"
    assert e3["cases"][1]["primary_error"] == "MISSING_CASE"
    assert report["status"] == "incomplete"


def test_boolean_execution_mismatch_never_overridden_by_perfect_modules():
    from evaluation.r2_cross_domain_v1.reporting import build_evaluation_report
    metrics = {"correct": 1, "predicted": 1, "required": 1, "precision": 1, "recall": 1, "f1": 1}
    modules = {"schema_linker": {"case_success": True, "valid_relationship_path": True,
        "tables": metrics, "columns": metrics, "relationships": metrics},
        "value_grounding": {"case_success": True, "predicates": metrics, "witness_precision": None,
            "unsupported_literal_rate": None, "provenance_status": "CONTEXT_UNAVAILABLE"}}
    out = build_evaluation_report([record(modules=modules, execution_accurate=False,
        scoring_error_category="RESULT_MISMATCH", semantic_test_accuracy=False), record("b")], inventory())["conditions"]["E3"]
    assert out["execution_accuracy"]["correct"] == 1
    assert out["module_metrics"]["schema_linker"]["coverage"] == {"available": 1, "total": 2}
    assert out["module_metrics"]["schema_linker"]["columns"]["tp"] == 1
    assert out["module_metrics"]["schema_linker"]["columns"]["fp"] == 0
    assert out["sql_generation"]["final_sql_coverage"] == {"correct": 2, "total": 2, "rate": 1.0}
    assert out["cases"][0]["primary_error"] == "SEMANTIC_MISMATCH"
    assert out["witness_precision"]["rate"] is None


def test_missing_usage_is_unknown_cost_and_safety_rejection_is_not_accuracy():
    from evaluation.r2_cross_domain_v1.reporting import build_evaluation_report
    r = record(responses=[{"response": {"model": "pinned"}}], safety_rejected=True,
        execution_accurate=False, execution_success=False, scoring_error_category="SAFETY_REJECTION")
    out = build_evaluation_report([r, record("b")], inventory())["conditions"]["E3"]
    assert out["cost"]["complete"] is False
    assert out["cost"]["known_usd"] == .01
    assert out["cost"]["total_usd"] is None
    assert out["safety_rejection_rate"] == {"correct": 1, "total": 2, "rate": .5}
    assert out["execution_accuracy"]["rate"] == .5
    assert out["cases"][0]["primary_error"] == "SAFETY_REJECTION"


@pytest.mark.parametrize("records", [[record(), record()], [record("unknown")]])
def test_duplicate_or_foreign_case_is_rejected(records):
    from evaluation.r2_cross_domain_v1.reporting import build_evaluation_report
    with pytest.raises(ValueError):
        build_evaluation_report(records, inventory())


def test_missing_linker_is_na_with_coverage_and_false_reject_uses_benign_fixture_denominator():
    from evaluation.r2_cross_domain_v1.reporting import build_evaluation_report
    out = build_evaluation_report([record(safety_checks=[{"benign": True, "rejected": True},
        {"benign": False, "rejected": True}]), record("b")], inventory())["conditions"]["E3"]
    assert out["module_metrics"]["schema_linker"]["coverage"] == {"available": 0, "total": 2}
    assert out["cases"][0]["missing_stages"]["schema_linker"] == "STAGE_NOT_RECORDED"
    assert out["safety_false_rejection_rate"] == {"correct": 1, "total": 1, "rate": 1.0}
    assert out["witness_precision"] == {"correct": 0, "total": 0, "rate": None, "unavailable_cases": 2}
    assert out["synthetic_records"] == 2


def test_rejected_sql_probe_is_reported_even_when_final_sql_scoring_has_no_rejection(tmp_path):
    from evaluation.r2_cross_domain_v1.reporting import build_evaluation_report
    from evaluation.r2_cross_domain_v1.tools import DatabaseTools
    from evaluation.r2_cross_domain_v1.semantic_instances import build_fixture
    from evaluation.r2_cross_domain_v1.safety import SafetyError
    spec = {"database_id": "fixture", "fixture_only": True, "seed": 1,
        "schema": [{"name": "items", "columns": [{"name": "id", "duckdb_type": "BIGINT"}]}],
        "relationships": [], "rows": {"items": [[1]]}}
    tools = DatabaseTools(build_fixture(spec, tmp_path/"fixture.duckdb")["context"])
    with pytest.raises(SafetyError): tools.call("sql_probe", {"sql": "DELETE FROM items"})
    rejected = record(final_sql=None, error_category="SAFETY_REJECTION", execution_accurate=False,
        syntax_valid=False, execution_success=False, safety_rejected=False, trajectory=tools.trajectory)
    out = build_evaluation_report([rejected, record("b")], inventory())["conditions"]["E3"]
    assert out["safety_rejection_rate"] == {"correct": 1, "total": 2, "rate": .5}
    assert out["tool_safety"] == {"sql_attempts": 1, "rejected_attempts": 1, "cases_rejected": 1}
    assert out["final_sql_safety_rejection_rate"]["correct"] == 0


def test_provider_error_with_missing_sql_is_counted_without_changing_primary_reason():
    from evaluation.r2_cross_domain_v1.reporting import build_evaluation_report
    out = build_evaluation_report([record(final_sql=None, error_category="PROVIDER_ERROR",
        execution_accurate=False), record("b")], inventory())["conditions"]["E3"]
    assert out["cases"][0]["primary_error"] == "PROVIDER_ERROR"
    assert out["sql_generation"]["no_final_sql"] == 1
