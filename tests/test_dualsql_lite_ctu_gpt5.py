"""Tests for CTU-only DualSQL-Lite v1 framework."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from evaluation.dualsql_lite_ctu_gpt5.agents import (
    DualSQLCaseRunner, InvalidEvidenceRun, _RoleResult,
    cost_usd, validate_linked_schema,
)
from evaluation.dualsql_lite_ctu_gpt5.tools import (
    DatabaseTools, SnapshotOnlyDuckDBSnapshot, TOOL_SCHEMAS,
    validate_snapshot_only_sql,
)
from evaluation.text_to_sql import SQLBenchmarkCase


FIXTURE_DIR = Path("evaluation/ctu_network_frozen")
SNAPSHOT_PATH = Path("data/ctu_network_frozen/snapshots/frozen_v1.duckdb")


class TestTools:
    """Test database tools for CTU-only snapshot."""

    @pytest.fixture
    def tools(self) -> DatabaseTools:
        return DatabaseTools(SNAPSHOT_PATH)

    def test_loads_snapshot(self, tools: DatabaseTools) -> None:
        assert "network_flows" in tools.schema
        assert "dataset_provenance" in tools.schema

    def test_schema_context_typed(self, tools: DatabaseTools) -> None:
        ctx = tools.schema_context()
        assert "source_dataset" in ctx
        assert "label" in ctx
        assert "VARCHAR" in ctx or "INTEGER" in ctx or "BIGINT" in ctx

    def test_value_search_ctu_values(self, tools: DatabaseTools) -> None:
        result = tools.value_search({"query": "ctu13_s1"})
        assert result["ok"]
        matches = result["matches"]
        assert any(m["table"] == "network_flows" and m["column"] == "source_dataset" and m["value"] == "ctu13_s1"
                   for m in matches)

    def test_value_search_label_format(self, tools: DatabaseTools) -> None:
        result = tools.value_search({"query": "Botnet"})
        assert result["ok"]
        matches = result["matches"]
        labels = [m["value"] for m in matches if m["table"] == "network_flows" and m["column"] == "label"]
        assert any("flow=" in l for l in labels)

    def test_profiler_returns_typed_columns(self, tools: DatabaseTools) -> None:
        result = tools.profiler({"table": "network_flows"})
        assert result["ok"]
        cols = result["tables"][0]["columns"]
        for col in cols:
            assert "type" in col
            assert "name" in col

    def test_sql_probe_valid(self, tools: DatabaseTools) -> None:
        result = tools.sql_probe({"sql": "SELECT COUNT(*) FROM network_flows LIMIT 1"})
        assert result["ok"]
        assert "rows" in result

    def test_sql_probe_blocked_external(self, tools: DatabaseTools) -> None:
        result = tools.sql_probe({"sql": "SELECT * FROM information_schema.tables"})
        assert not result["ok"]
        assert result["error_type"] == "SAFETY_REJECTION"


class TestSchemaValidation:
    """Test schema validation logic."""

    @pytest.fixture
    def tools(self) -> DatabaseTools:
        return DatabaseTools(SNAPSHOT_PATH)

    def test_validate_linked_schema_valid(self, tools: DatabaseTools) -> None:
        """Valid linked schema with grounded values from tool output."""
        trajectory = [{
            "tool_call_id": "call_1",
            "result": {
                "ok": True,
                "matches": [
                    {"table": "network_flows", "column": "source_dataset", "value": "ctu13_s1"}
                ]
            }
        }]
        raw = '{"tables":[{"table":"network_flows","columns":["source_dataset"]}],"grounded_values":[{"table":"network_flows","column":"source_dataset","value":"ctu13_s1"}]}'
        result = validate_linked_schema(raw, tools, trajectory)
        assert result["tables"][0]["table"] == "network_flows"

    def test_validate_linked_schema_question_literals_allowed(self, tools: DatabaseTools) -> None:
        """Question literals (like 'botnet') don't need DB verification."""
        trajectory = []
        raw = '{"tables":[{"table":"network_flows","columns":["label"]}],"grounded_values":[]}'
        result = validate_linked_schema(raw, tools, trajectory)
        assert "label" in result["tables"][0]["columns"]

    def test_validate_linked_schema_stored_values_require_provenance(self, tools: DatabaseTools) -> None:
        """Stored values (like ctu13_s1) MUST come from tool output."""
        trajectory = []
        raw = '{"tables":[{"table":"network_flows","columns":["source_dataset"]}],"grounded_values":[{"table":"network_flows","column":"source_dataset","value":"ctu13_s1"}]}'
        with pytest.raises(ValueError, match="Invented"):
            validate_linked_schema(raw, tools, trajectory)


class TestSnapshotOnly:
    """Test snapshot-only SQL enforcement."""

    def test_blocks_information_schema(self) -> None:
        with pytest.raises(Exception):
            validate_snapshot_only_sql("SELECT * FROM information_schema.tables")

    def test_blocks_system_tables(self) -> None:
        with pytest.raises(Exception):
            validate_snapshot_only_sql("SELECT * FROM pg_catalog.pg_tables")

    def test_blocks_external_access(self) -> None:
        with pytest.raises(Exception):
            validate_snapshot_only_sql("SELECT * FROM read_csv('http://evil.com/data.csv')")


class TestPricing:
    """Test GPT-5 Mini pricing."""

    def test_cost_calculation(self) -> None:
        cost = cost_usd(1000, 100)
        assert cost == pytest.approx(0.00021)


class TestFramework:
    """Test framework-level behaviors."""

    def test_tools_schemas_match_agent(self) -> None:
        tool_names = {s["function"]["name"] for s in TOOL_SCHEMAS}
        assert tool_names == {"database_profiler", "value_search", "sql_probe"}

    def test_tools_version_set(self) -> None:
        from evaluation.dualsql_lite_ctu_gpt5 import tools as tools_module
        assert tools_module.TOOL_VERSION == "dualsql_lite_ctu_gpt5_tools_v1"

    def test_linker_prompt_mentions_ctu_format(self) -> None:
        from evaluation.dualsql_lite_ctu_gpt5.agents import LINKER_INSTRUCTIONS
        assert "ctu13_s1" in LINKER_INSTRUCTIONS
        assert "flow=" in LINKER_INSTRUCTIONS

    def test_generator_prompt_mentions_ctu_format(self) -> None:
        from evaluation.dualsql_lite_ctu_gpt5.agents import GENERATOR_INSTRUCTIONS
        assert "ctu13_s1" in GENERATOR_INSTRUCTIONS
        assert "flow=" in GENERATOR_INSTRUCTIONS


class TestSelection:
    """Test E0-E3 selection logic."""

    def test_select_winner_requires_all_four(self) -> None:
        from evaluation.dualsql_lite_ctu_gpt5.selection import select_winner
        partial = [
            {"experiment_id": "E0", "eligible": True, "metrics": {"execution_accuracy": "3/8"},
             "total_cost_usd": 0.01, "model_calls": 10, "latency_ms": 1000},
            {"experiment_id": "E1", "eligible": True, "metrics": {"execution_accuracy": "4/8"},
             "total_cost_usd": 0.02, "model_calls": 20, "latency_ms": 2000},
            {"experiment_id": "E2", "eligible": True, "metrics": {"execution_accuracy": "5/8"},
             "total_cost_usd": 0.03, "model_calls": 30, "latency_ms": 3000},
        ]
        with pytest.raises(ValueError, match="requires all four"):
            select_winner(partial)

    def test_select_winner_highest_accuracy_first(self) -> None:
        from evaluation.dualsql_lite_ctu_gpt5.selection import select_winner
        reports = [
            {"experiment_id": "E0", "eligible": True, "metrics": {"execution_accuracy": "3/8"},
             "total_cost_usd": 0.01, "model_calls": 10, "latency_ms": 1000},
            {"experiment_id": "E1", "eligible": True, "metrics": {"execution_accuracy": "5/8"},
             "total_cost_usd": 0.02, "model_calls": 20, "latency_ms": 2000},
            {"experiment_id": "E2", "eligible": True, "metrics": {"execution_accuracy": "4/8"},
             "total_cost_usd": 0.01, "model_calls": 30, "latency_ms": 3000},
            {"experiment_id": "E3", "eligible": True, "metrics": {"execution_accuracy": "2/8"},
             "total_cost_usd": 0.04, "model_calls": 40, "latency_ms": 4000},
        ]
        winner = select_winner(reports)
        assert winner["experiment_id"] == "E1"

    def test_select_winner_lowest_cost_tiebreak(self) -> None:
        from evaluation.dualsql_lite_ctu_gpt5.selection import select_winner
        reports = [
            {"experiment_id": "E0", "eligible": True, "metrics": {"execution_accuracy": "4/8"},
             "total_cost_usd": 0.02, "model_calls": 10, "latency_ms": 1000},
            {"experiment_id": "E1", "eligible": True, "metrics": {"execution_accuracy": "4/8"},
             "total_cost_usd": 0.01, "model_calls": 20, "latency_ms": 2000},
            {"experiment_id": "E2", "eligible": True, "metrics": {"execution_accuracy": "4/8"},
             "total_cost_usd": 0.03, "model_calls": 30, "latency_ms": 3000},
            {"experiment_id": "E3", "eligible": True, "metrics": {"execution_accuracy": "4/8"},
             "total_cost_usd": 0.04, "model_calls": 40, "latency_ms": 4000},
        ]
        winner = select_winner(reports)
        assert winner["experiment_id"] == "E1"

    def test_select_winner_simplicity_tiebreak(self) -> None:
        from evaluation.dualsql_lite_ctu_gpt5.selection import select_winner
        reports = [
            {"experiment_id": "E0", "eligible": True, "metrics": {"execution_accuracy": "4/8"},
             "total_cost_usd": 0.01, "model_calls": 10, "latency_ms": 1000},
            {"experiment_id": "E1", "eligible": True, "metrics": {"execution_accuracy": "4/8"},
             "total_cost_usd": 0.01, "model_calls": 10, "latency_ms": 1000},
            {"experiment_id": "E2", "eligible": True, "metrics": {"execution_accuracy": "4/8"},
             "total_cost_usd": 0.01, "model_calls": 10, "latency_ms": 1000},
            {"experiment_id": "E3", "eligible": True, "metrics": {"execution_accuracy": "4/8"},
             "total_cost_usd": 0.01, "model_calls": 10, "latency_ms": 1000},
        ]
        winner = select_winner(reports)
        assert winner["experiment_id"] == "E0"

    def test_ineligible_report_rejected(self) -> None:
        from evaluation.dualsql_lite_ctu_gpt5.selection import select_winner
        reports = [
            {"experiment_id": "E0", "eligible": False, "metrics": {"execution_accuracy": "3/8"},
             "total_cost_usd": 0.01, "model_calls": 10, "latency_ms": 1000},
            {"experiment_id": "E1", "eligible": True, "metrics": {"execution_accuracy": "5/8"},
             "total_cost_usd": 0.02, "model_calls": 20, "latency_ms": 2000},
            {"experiment_id": "E2", "eligible": True, "metrics": {"execution_accuracy": "4/8"},
             "total_cost_usd": 0.03, "model_calls": 30, "latency_ms": 3000},
            {"experiment_id": "E3", "eligible": True, "metrics": {"execution_accuracy": "2/8"},
             "total_cost_usd": 0.04, "model_calls": 40, "latency_ms": 4000},
        ]
        with pytest.raises(ValueError, match="ineligible"):
            select_winner(reports)


class TestBudgetGate:
    """Test budget gate preflight logic."""

    def test_budget_gate_accepts_valid_budget(self) -> None:
        from evaluation.dualsql_lite_ctu_gpt5.experiment import BudgetGate
        case = SQLBenchmarkCase.from_dict({
            "case_id": "test_001", "question": "Test?", "gold_sql": "SELECT 1",
            "database_snapshot": "dummy.duckdb", "category": "filter", "difficulty": "basic",
        })
        schema = "network_flows(source_dataset VARCHAR)"
        gate = BudgetGate([case], schema, budget_usd=0.50)
        assert gate.ceiling_usd < 0.50

    def test_budget_gate_rejects_excessive_budget(self) -> None:
        from evaluation.dualsql_lite_ctu_gpt5.experiment import BudgetGate
        case = SQLBenchmarkCase.from_dict({
            "case_id": "test_001", "question": "Test?", "gold_sql": "SELECT 1",
            "database_snapshot": "dummy.duckdb", "category": "filter", "difficulty": "basic",
        })
        schema = "network_flows(source_dataset VARCHAR)"
        with pytest.raises(ValueError, match="exceeds budget"):
            BudgetGate([case], schema, budget_usd=0.001)


class TestExperimentConditions:
    """Test E0-E3 experiment condition logic."""

    def test_e0_has_no_linker_calls(self) -> None:
        from evaluation.dualsql_lite_ctu_gpt5.experiment import BudgetGate
        case = SQLBenchmarkCase.from_dict({
            "case_id": "test_001", "question": "Test?", "gold_sql": "SELECT 1",
            "database_snapshot": "dummy.duckdb", "category": "filter", "difficulty": "basic",
        })
        schema = "network_flows(source_dataset VARCHAR)"
        gate = BudgetGate([case], schema, budget_usd=0.50)
        e0_slots = gate.slots[("E0", "test_001")]
        roles = [slot[0] for slot in e0_slots]
        assert "linker" not in roles
        assert roles.count("generator") == 1

    def test_e1_has_linker_and_generator(self) -> None:
        from evaluation.dualsql_lite_ctu_gpt5.experiment import BudgetGate
        case = SQLBenchmarkCase.from_dict({
            "case_id": "test_001", "question": "Test?", "gold_sql": "SELECT 1",
            "database_snapshot": "dummy.duckdb", "category": "filter", "difficulty": "basic",
        })
        schema = "network_flows(source_dataset VARCHAR)"
        gate = BudgetGate([case], schema, budget_usd=0.50)
        e1_slots = gate.slots[("E1", "test_001")]
        roles = [slot[0] for slot in e1_slots]
        assert "linker" in roles
        assert "generator" in roles
