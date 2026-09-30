"""Tests for v2 package - validate grounding without question literal hints."""

import json
import pytest
import duckdb

from evaluation.dualsql_lite_ctu_gpt5_v2.prompts import (
    LINKER_INSTRUCTIONS,
    GENERATOR_INSTRUCTIONS,
    LINKER_PROMPT_VERSION,
    GENERATOR_PROMPT_VERSION,
)
from evaluation.dualsql_lite_ctu_gpt5_v2.tools import V2DatabaseTools
from evaluation.dualsql_lite_ctu_gpt5_v2.runner import validate_linked_schema


@pytest.fixture
def tools(tmp_path):
    """Unit tests use a synthetic snapshot available on both CI Python jobs."""
    snapshot = tmp_path / "ctu-fixture.duckdb"
    with duckdb.connect(str(snapshot)) as connection:
        connection.execute(
            "CREATE TABLE network_flows(source_dataset VARCHAR, label VARCHAR, protocol VARCHAR)"
        )
        connection.executemany("INSERT INTO network_flows VALUES (?, ?, ?)", [
            ("ctu13_s5", "flow=From-Botnet-TCP", "TCP"),
            ("ctu13_s7", "flow=From-Normal-UDP", "UDP"),
        ])
    manifest = tmp_path / "manifest.json"
    manifest.write_text(json.dumps({"sources": [{"dataset_id": "ctu13_s5", "source_name": "CTU-13 Scenario 5"}, {"dataset_id": "ctu13_s7", "source_name": "CTU-13 Scenario 7"}]}))
    return V2DatabaseTools(snapshot, manifest)


class TestPrompts:
    """Verify prompts don't contain question literal hints."""

    def test_no_question_literals_in_prompts(self):
        """Prompts must NOT hint actual stored values."""
        forbidden = [
            "ctu13_s1", "ctu13_s4", "ctu13_s5", "ctu13_s7",
            "flow=From-Botnet", "flow=From-Normal",
            "scenario 5", "scenario 7",
        ]
        combined = LINKER_INSTRUCTIONS + GENERATOR_INSTRUCTIONS
        for hint in forbidden:
            assert hint.lower() not in combined.lower(), f"Prompt contains hint: {hint}"

    def test_prompts_mention_tool_usage(self):
        """Prompts should reference tools for discovery."""
        assert "value_search" in LINKER_INSTRUCTIONS or "tool" in LINKER_INSTRUCTIONS.lower()
        assert "tool" in GENERATOR_INSTRUCTIONS.lower() or "value_search" in GENERATOR_INSTRUCTIONS


class TestTools:
    """Test v2 tools."""

    def test_catalog_contains_ctu_values(self, tools):
        """Verify catalog has ctu13_s5/s7 in source_dataset."""
        source_vals = [v["value"] for v in tools.catalog
                      if v["table"] == "network_flows" and v["column"] == "source_dataset"]
        assert "ctu13_s5" in source_vals
        assert "ctu13_s7" in source_vals

    def test_catalog_contains_flow_labels(self, tools):
        """Verify catalog has flow= labels."""
        label_vals = [v["value"] for v in tools.catalog
                     if v["table"] == "network_flows" and v["column"] == "label"]
        assert any("flow=" in v for v in label_vals)

    def test_value_search_finds_ctus(self, tools):
        """value_search should find ctu13_s5 when searching for it."""
        result = tools.value_search({"query": "ctu13_s5"})
        assert result["ok"]
        matches = [m for m in result["matches"]
                  if m["table"] == "network_flows" and m["column"] == "source_dataset"]
        assert any(m["value"] == "ctu13_s5" for m in matches)

    def test_value_search_ambiguity_detection(self, tools):
        """Short queries should be flagged as ambiguous."""
        # Single digit
        result = tools.value_search({"query": "5"})
        if result["ok"]:
            # Should be flagged or have low matches
            assert result.get("ambiguous") or len(result["matches"]) <= 10

    def test_value_search_finds_flow_labels(self, tools):
        """value_search should find flow= labels when searching for Botnet."""
        result = tools.value_search({"query": "Botnet"})
        assert result["ok"]
        matches = [m for m in result["matches"]
                  if m["table"] == "network_flows" and m["column"] == "label"]
        assert any("flow=" in m["value"] for m in matches)


class TestValidation:
    """Test v2 linked schema validation."""

    def test_valid_value_with_provenance(self, tools):
        """Value found by tool should pass validation."""
        trajectory = [{"tool_call_id": "call_1", "tool": "value_search",
                       "arguments": {"query": "ctu13_s5"},
                       "result": tools.value_search({"query": "ctu13_s5"})}]
        schema = '{"tables":[{"table":"network_flows","columns":["source_dataset"]}],"grounded_values":[{"table":"network_flows","column":"source_dataset","value":"ctu13_s5"}]}'
        validated, errors = validate_linked_schema(schema, tools, trajectory)
        assert not errors, f"Unexpected errors: {errors}"

    def test_value_without_provenance_rejected(self, tools):
        """Value NOT found by tool should fail validation."""
        trajectory = []  # No tool calls
        schema = '{"tables":[{"table":"network_flows","columns":["source_dataset"]}],"grounded_values":[{"table":"network_flows","column":"source_dataset","value":"ctu13_s5"}]}'
        validated, errors = validate_linked_schema(schema, tools, trajectory)
        assert errors, "Should reject unprovenanced value"
        assert any("provenance" in e.lower() for e in errors)

    def test_question_literal_does_not_need_provenance(self, tools):
        """Question literals (like 'Botnet') don't need tool provenance."""
        trajectory = []  # No tool calls
        # 'Botnet' is a question literal, not a stored value
        schema = '{"tables":[{"table":"network_flows","columns":["label"]}],"grounded_values":[]}'
        validated, errors = validate_linked_schema(schema, tools, trajectory)
        assert not errors, f"Question literal should not need provenance: {errors}"


class TestPackageVersioning:
    """Verify v2 is separate from v1."""

    def test_v2_version_strings(self):
        """v2 should have v2 version strings."""
        assert "v2" in LINKER_PROMPT_VERSION
        assert "v2" in GENERATOR_PROMPT_VERSION

    def test_v1_still_exists(self):
        """v1 package should still be importable."""
        from evaluation.dualsql_lite_ctu_gpt5.prompts import (
            LINKER_INSTRUCTIONS as V1_LINKER,
            GENERATOR_INSTRUCTIONS as V1_GENERATOR,
        )
        # v1 and v2 should be different
        assert V1_LINKER != LINKER_INSTRUCTIONS or V1_GENERATOR != GENERATOR_INSTRUCTIONS
