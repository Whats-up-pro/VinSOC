"""Current CTU GPT-5 contract tests; historical v1 assumptions live in artifacts."""

from __future__ import annotations

import json

import duckdb
import pytest

from evaluation.dualsql_lite_ctu_gpt5.agents import cost_usd
from evaluation.dualsql_lite_ctu_gpt5.contract import verify_e0_baseline
from evaluation.dualsql_lite_ctu_gpt5.prompts import (
    GENERATOR_INSTRUCTIONS, LINKER_INSTRUCTIONS,
)
from evaluation.dualsql_lite_ctu_gpt5.runner import conservative_preflight
from evaluation.dualsql_lite_ctu_gpt5.tools import (
    CTUDatabaseTools, TOOL_SCHEMAS, TOOL_VERSION,
    validate_snapshot_only_sql,
)
from vinsoc_data.duckdb_store import QuerySafetyError


@pytest.fixture
def tools(tmp_path):
    path = tmp_path / "ctu-fixture.duckdb"
    with duckdb.connect(str(path)) as connection:
        connection.execute(
            "CREATE TABLE network_flows(source_dataset VARCHAR, label VARCHAR, protocol VARCHAR)"
        )
        connection.execute("CREATE TABLE dataset_provenance(secret VARCHAR)")
        connection.execute("INSERT INTO dataset_provenance VALUES ('GOLD_ONLY_SENTINEL')")
        connection.execute("INSERT INTO network_flows VALUES "
                           "('ctu13_s5', 'flow=From-Botnet-TCP', 'TCP'), "
                           "('ctu13_s7', 'flow=Normal-UDP', 'UDP')")
    return CTUDatabaseTools(path)


def test_only_network_flows_is_visible_and_schema_is_typed(tools):
    assert list(tools.schema) == ["network_flows"]
    profile = tools.database_profiler({})
    assert profile["ok"] and [table["name"] for table in profile["tables"]] == ["network_flows"]
    assert all("type" in column for column in profile["tables"][0]["columns"])
    assert "dataset_provenance" not in tools.schema_context()


@pytest.mark.parametrize("column,query,expected", [
    ("source_dataset", "ctu13_s5", "ctu13_s5"),
    ("source_dataset", "ctu13_s7", "ctu13_s7"),
    ("label", "From-Botnet", "flow=From-Botnet-TCP"),
    ("protocol", "UDP", "UDP"),
])
def test_fixture_values_are_grounded_with_evidence_id(tools, column, query, expected):
    result = tools.value_search({"column": column, "query": query})
    assert result["ok"]
    assert any(match["value"] == expected and
               match["evidence_id"] == result["evidence_id"] for match in result["matches"])


def test_probe_is_read_only_bounded_and_suppresses_internal_errors(tools):
    assert tools.sql_probe({"sql": "SELECT count(*) FROM network_flows"})["ok"]
    assert tools.sql_probe({"sql": "SELECT * FROM dataset_provenance"}) == {
        "ok": False, "error_type": "SAFETY_REJECTION"}
    assert tools.sql_probe({"sql": "SELECT nonexistent_column FROM network_flows"}) == {
        "ok": False, "error_type": "EXECUTION_ERROR"}


@pytest.mark.parametrize("sql", [
    "DELETE FROM network_flows",
    "SELECT * FROM information_schema.tables",
    "SELECT * FROM read_csv('https://example.invalid/data.csv')",
])
def test_sql_validator_rejects_external_or_internal_access(sql):
    with pytest.raises(QuerySafetyError):
        validate_snapshot_only_sql(sql)


def test_pinned_price_and_tool_version_match_new_protocol():
    assert cost_usd(1000, 100) == pytest.approx(0.00045)
    assert TOOL_VERSION == "dualsql_lite_ctu_gpt5_tools_v2"
    assert {schema["function"]["name"] for schema in TOOL_SCHEMAS} == {
        "database_profiler", "value_search", "sql_probe"}


def test_dev_prompts_have_no_frozen_source_or_gold_hints():
    prompts = LINKER_INSTRUCTIONS + GENERATOR_INSTRUCTIONS
    assert all(value not in prompts for value in
               ("ctu13_s1", "ctu13_s4", "GOLD_ONLY_SENTINEL", "gold_sql"))


def test_preflight_caps_all_three_paid_conditions():
    bounds = conservative_preflight("network_flows(source_dataset VARCHAR, label VARCHAR)")
    assert {name: bound["max_calls"] for name, bound in bounds.items()} == {
        "E1": 48, "E2": 40, "E3": 80}
    assert sum(bound["ceiling_usd"] for bound in bounds.values()) < 0.75


def test_e0_is_verified_from_immutable_report_without_provider():
    report = verify_e0_baseline(
        "results/evaluation_v1/ctu_network_public/gpt5_e0/36520685612/ctu-r2-result.json"
    )
    assert report.run_id == "36520685612"
    assert report.execution_accurate == 0 and report.model_calls == 8
    assert report.known_cost_usd == pytest.approx(0.00384725)
