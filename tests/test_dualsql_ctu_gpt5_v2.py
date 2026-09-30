"""Offline regressions for the source-grounded CTU v2 controller."""

import json

import duckdb
import pytest

from evaluation.dualsql_lite_ctu_gpt5_v2.tools import V2DatabaseTools
from evaluation.dualsql_lite_ctu_gpt5_v2.agents import (
    extract_question_references,
    validate_link,
)
from evaluation.dualsql_lite_ctu_gpt5_v2.metrics import (
    inspect_sql_literals,
    linker_column_precision,
)
from evaluation.dualsql_lite_ctu_gpt5_v2.offline_gate import evaluate_offline


@pytest.fixture
def tools(tmp_path):
    snapshot = tmp_path / "ctu.duckdb"
    with duckdb.connect(str(snapshot)) as connection:
        connection.execute(
            "CREATE TABLE network_flows(source_dataset VARCHAR, source_row_id VARCHAR, "
            "label VARCHAR, protocol VARCHAR)"
        )
        connection.executemany(
            "INSERT INTO network_flows VALUES (?, ?, ?, ?)",
            [("ctu13_s5", f"line:{10000 + index}", "flow=From-Botnet-TCP", "TCP")
             for index in range(60)]
            + [("ctu13_s7", "line:10007", "flow=Normal-UDP", "UDP")],
        )
    manifest = tmp_path / "manifest.json"
    manifest.write_text(json.dumps({"sources": [
        {"dataset_id": "ctu13_s5", "source_name": "CTU-13 Scenario 5"},
        {"dataset_id": "ctu13_s7", "source_name": "CTU-13 Scenario 7"},
    ]}), encoding="utf-8")
    return V2DatabaseTools(snapshot, manifest)


def test_value_search_resolves_source_alias_from_verified_manifest(tools):
    result = tools.value_search({"query": "scenario 5", "column": "source_dataset"})
    assert result["ok"]
    assert [(match["column"], match["value"], match["match_basis"])
            for match in result["matches"]] == [
                ("source_dataset", "ctu13_s5", "source_metadata")]


def test_value_search_reports_low_cardinality_domain_on_miss(tools):
    result = tools.value_search({"query": "unknown", "column": "source_dataset"})
    assert result["ok"] and result["matches"] == []
    assert result["resolution"] == "unresolved"
    assert [item["value"] for item in result["domain"]] == ["ctu13_s5", "ctu13_s7"]


def test_profiler_exposes_source_domain_without_catalog_overflow(tools):
    result = tools.database_profiler({})
    assert result["ok"]
    assert [item["value"] for item in result["domains"]["source_dataset"]] == [
        "ctu13_s5", "ctu13_s7"]


def test_numeric_query_cannot_ground_high_cardinality_row_id(tools):
    result = tools.value_search({"query": "7", "column": "source_row_id"})
    assert result["matches"] == []
    assert result["resolution"] == "unresolved"


def test_bare_source_reference_is_recorded_but_grouping_question_has_none(tools):
    references = extract_question_references("Count scenario 5 flows", tools)
    assert references == [{"surface": "scenario 5", "column": "source_dataset",
                           "value": "ctu13_s5", "evidence_class": "source_metadata"}]
    assert extract_question_references(
        "Return scenario flow totals ordered by source dataset.", tools) == []


def test_linker_rejects_wrong_column_for_source_reference(tools):
    selected = [{"table": "network_flows", "columns": ["source_row_id", "label"]}]
    event = {"tool": "value_search", "arguments": {"query": "7", "column": "source_row_id"},
             "result": {"ok": True, "matches": [{"table": "network_flows",
                        "column": "source_row_id", "value": "line:10007",
                        "evidence_id": "ev-1"}]}}
    result = validate_link("Count scenario 7 flows labeled Normal", selected, [event], tools)
    assert result["error"] == "WRONG_COLUMN_FOR_INTENT"
    assert result["grounded_values"] == []


def test_linker_flags_unresolved_source_reference(tools):
    selected = [{"table": "network_flows", "columns": ["source_dataset", "label"]}]
    result = validate_link("Count scenario 5 flows", selected, [], tools)
    assert result["error"] == "UNRESOLVED_LITERAL"
    assert result["unresolved_literals"] == ["scenario 5"]


def test_linker_accepts_no_reference_grouping_without_grounded_values(tools):
    selected = [{"table": "network_flows", "columns": ["source_dataset"]}]
    result = validate_link(
        "Return scenario flow totals ordered by source dataset.", selected, [], tools)
    assert result["error"] is None
    assert result["grounded_values"] == []


def test_literal_metric_handles_equality_and_substring_like(tools):
    sql = ("SELECT count(*) FROM network_flows WHERE "
           "source_dataset = 'ctu13_s5' AND label LIKE '%Normal%' "
           "AND source_row_id = 'line:10007' AND protocol = 'UDP'")
    inspected = inspect_sql_literals(sql, tools)
    assert [(item["column"], item["status"]) for item in inspected] == [
        ("source_dataset", "grounded"), ("label", "grounded"),
        ("source_row_id", "grounded"), ("protocol", "grounded")]


def test_literal_metric_flags_invented_dataset_but_ignores_time_and_numbers(tools):
    sql = ("SELECT count(*) FROM network_flows WHERE source_dataset = 'scenario-5' "
           "AND bytes_out > 0 AND event_time >= TIMESTAMP '2011-08-15 00:00:00'")
    assert [(item["column"], item["status"]) for item in inspect_sql_literals(sql, tools)] == [
        ("source_dataset", "ungrounded")]


def test_column_precision_uses_intersection_over_selected_columns():
    assert linker_column_precision(["source_dataset", "source_row_id", "label"],
                                   ["source_dataset", "label"]) == pytest.approx(2 / 3)


def test_offline_gate_resolves_references_and_keeps_wrong_lookup_unresolved(tools):
    cases = [
        {"case_id": "one", "question": "Count scenario 5 flows"},
        {"case_id": "two", "question": "Count scenario 7 flows"},
        {"case_id": "three", "question": "Return scenario flow totals ordered by source dataset"},
    ]
    replay = [
        {"case_id": "one", "arguments": {"query": "scenario 5"}},
        {"case_id": "two", "arguments": {"query": "7", "column": "source_row_id"}},
    ]
    report = evaluate_offline(tools, cases, replay)
    assert report["gate_passed"]
    assert report["referenced_cases_resolved"] == 2
    assert report["no_reference_cases"] == ["three"]
    assert report["negative_controls_passed"] == 2
    assert report["replay"][1]["resolution"] == "unresolved"


def test_unknown_source_reference_fails_closed(tools):
    result = validate_link("Count scenario 999 flows", [{"table": "network_flows", "columns": ["source_dataset"]}], [], tools)
    assert result["error"] == "UNKNOWN_SOURCE_REFERENCE"


def test_forged_or_mismatched_evidence_rejected(tools):
    result = tools.value_search({"query": "scenario 5"})
    result["matches"][0]["evidence_id"] = "forged"
    linked = validate_link("Count scenario 5 flows", [{"table": "network_flows", "columns": ["source_dataset"]}], [{"result": result}], tools)
    assert linked["error"] == "INVALID_TOOL_PROVENANCE"


def test_manifest_mismatch_and_ambiguous_alias_fail_closed(tools, tmp_path):
    manifest = tmp_path / "bad.json"
    manifest.write_text(json.dumps({"sources": [{"dataset_id": "missing", "source_name": "Scenario 5"}]}))
    with pytest.raises(ValueError, match="metadata"):
        V2DatabaseTools(tools.snapshot_path, manifest)
    manifest.write_text(json.dumps({"sources": [{"dataset_id": s, "source_name": "Dataset Group 5"} for s in ("ctu13_s5", "ctu13_s7")]}))
    ambiguous = V2DatabaseTools(tools.snapshot_path, manifest)
    linked = validate_link("Count Group 5 flows", [{"table": "network_flows", "columns": ["source_dataset"]}], [], ambiguous)
    assert linked["error"] == "AMBIGUOUS_SOURCE_REFERENCE"


def test_probe_error_does_not_serialize_exception(tools, monkeypatch):
    def broken():
        raise RuntimeError("sensitive-secret-sentinel")
    monkeypatch.setattr(tools, "_connect", broken)
    result = tools.sql_probe({"sql": "SELECT * FROM network_flows"})
    assert result["error_type"] == "EXECUTION_ERROR"
    assert "sensitive-secret-sentinel" not in json.dumps(result)
