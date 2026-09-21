"""Schema contract tests for Evidence V2 enforcement.

Tests that JSON schema correctly enforces Evidence V2 fields.
"""
import json
import pytest
from pathlib import Path
from jsonschema import Draft7Validator, ValidationError


def get_schema(name: str) -> dict:
    """Load JSON schema from schemas directory."""
    schema_path = Path(__file__).parent.parent / "schemas" / name
    with open(schema_path) as f:
        return json.load(f)


def get_case_schema() -> dict:
    return get_schema("investigation_case.json")


class TestInvestigationCaseSchema:
    """Tests for InvestigationCase schema enforcement."""

    def test_evidence_missing_evidence_class_fails(self):
        """Evidence without evidence_class should fail validation."""
        schema = get_case_schema()
        validator = Draft7Validator(schema)

        invalid_case = {
            "case_id": "test_case",
            "created_at": "2026-09-18T00:00:00Z",
            "initial_indicator": {"type": "ipv4", "value": "1.2.3.4"},
            "tool_trace": [],
            "evidence": [
                {
                    "evidence_id": "EV1",
                    "source_tool": "network_investigation",
                    "type": "network_result",
                    "data": {},
                    "collected_at": "2026-09-18T00:00:00Z",
                    "linked_from": None,
                    # Missing: evidence_class, provenance, references, related_evidence_ids
                }
            ],
            "hypotheses": [],
            "risk_level": "UNKNOWN",
            "confidence": "LOW",
            "limitations": [],
            "final_assessment": "Test",
            "supporting_evidence": [],
            "contradicting_evidence": [],
            "metadata": {},
        }

        errors = list(validator.iter_errors(invalid_case))
        assert len(errors) > 0, "Missing evidence_class should cause validation error"

    def test_valid_observed_evidence_passes(self):
        """Valid OBSERVED evidence should pass validation."""
        schema = get_case_schema()
        validator = Draft7Validator(schema)

        valid_case = {
            "case_id": "test_case",
            "created_at": "2026-09-18T00:00:00Z",
            "initial_indicator": {"type": "ipv4", "value": "1.2.3.4"},
            "tool_trace": [],
            "evidence": [
                {
                    "evidence_id": "EV1",
                    "source_tool": "network_investigation",
                    "evidence_class": "OBSERVED",
                    "type": "network_result",
                    "data": {"connections": 10},
                    "collected_at": "2026-09-18T00:00:00Z",
                    "linked_from": None,
                    "provenance": {"collector": "network_skill_v2"},
                    "references": [],
                    "related_evidence_ids": [],
                }
            ],
            "hypotheses": [],
            "risk_level": "UNKNOWN",
            "confidence": "LOW",
            "limitations": [],
            "final_assessment": "Test",
            "supporting_evidence": [],
            "contradicting_evidence": [],
            "metadata": {},
        }

        errors = list(validator.iter_errors(valid_case))
        assert len(errors) == 0, f"Valid case should pass: {errors}"

    def test_valid_derived_evidence_passes(self):
        """Valid DERIVED evidence should pass validation."""
        schema = get_case_schema()
        validator = Draft7Validator(schema)

        valid_case = {
            "case_id": "test_case",
            "created_at": "2026-09-18T00:00:00Z",
            "initial_indicator": {"type": "ipv4", "value": "1.2.3.4"},
            "tool_trace": [],
            "evidence": [
                {
                    "evidence_id": "EV1",
                    "source_tool": "network_investigation",
                    "evidence_class": "DERIVED",
                    "type": "periodic_beaconing",
                    "data": {"interval_mean": 60.0},
                    "collected_at": "2026-09-18T00:00:00Z",
                    "linked_from": None,
                    "provenance": {"algorithm": "periodicity_rule", "sources": ["EV_raw"]},
                    "references": [],
                    "related_evidence_ids": ["EV_raw"],
                }
            ],
            "hypotheses": [],
            "risk_level": "UNKNOWN",
            "confidence": "LOW",
            "limitations": [],
            "final_assessment": "Test",
            "supporting_evidence": [],
            "contradicting_evidence": [],
            "metadata": {},
        }

        errors = list(validator.iter_errors(valid_case))
        assert len(errors) == 0, f"Valid DERIVED should pass: {errors}"

    def test_valid_external_intel_evidence_passes(self):
        """Valid EXTERNAL_INTEL evidence should pass validation."""
        schema = get_case_schema()
        validator = Draft7Validator(schema)

        valid_case = {
            "case_id": "test_case",
            "created_at": "2026-09-18T00:00:00Z",
            "initial_indicator": {"type": "ipv4", "value": "1.2.3.4"},
            "tool_trace": [],
            "evidence": [
                {
                    "evidence_id": "EV1",
                    "source_tool": "cti_enrichment",
                    "evidence_class": "EXTERNAL_INTEL",
                    "type": "threat_intel",
                    "data": {"reputation": "malicious"},
                    "collected_at": "2026-09-18T00:00:00Z",
                    "linked_from": None,
                    "provenance": {"provider": "threatfox", "query": "1.2.3.4"},
                    "references": ["https://threatfox.abuse.ch/ioc/123/"],
                    "related_evidence_ids": [],
                }
            ],
            "hypotheses": [],
            "risk_level": "UNKNOWN",
            "confidence": "LOW",
            "limitations": [],
            "final_assessment": "Test",
            "supporting_evidence": [],
            "contradicting_evidence": [],
            "metadata": {},
        }

        errors = list(validator.iter_errors(valid_case))
        assert len(errors) == 0, f"Valid EXTERNAL_INTEL should pass: {errors}"

    def test_invalid_evidence_class_fails(self):
        """Invalid evidence_class should fail validation."""
        schema = get_case_schema()
        validator = Draft7Validator(schema)

        invalid_case = {
            "case_id": "test_case",
            "created_at": "2026-09-18T00:00:00Z",
            "initial_indicator": {"type": "ipv4", "value": "1.2.3.4"},
            "tool_trace": [],
            "evidence": [
                {
                    "evidence_id": "EV1",
                    "source_tool": "network_investigation",
                    "evidence_class": "INVALID_CLASS",
                    "type": "network_result",
                    "data": {},
                    "collected_at": "2026-09-18T00:00:00Z",
                    "linked_from": None,
                    "provenance": {},
                    "references": [],
                    "related_evidence_ids": [],
                }
            ],
            "hypotheses": [],
            "risk_level": "UNKNOWN",
            "confidence": "LOW",
            "limitations": [],
            "final_assessment": "Test",
            "supporting_evidence": [],
            "contradicting_evidence": [],
            "metadata": {},
        }

        errors = list(validator.iter_errors(invalid_case))
        assert len(errors) > 0, "Invalid evidence_class should fail"
