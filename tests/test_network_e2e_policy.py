"""Tests for network E2E policy validation.

These tests verify:
- Facts extraction from evidence
- Evidence/parent relationships
- Coverage validation
- Argument scope validation
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest


def test_evidence_ids_validated_against_store():
    """Test that evidence IDs are validated against the actual store."""
    from agent.investigation_policy import ValidatedAssessment

    valid_ids = {"ev_1", "ev_2", "ev_3"}

    # Valid assessment
    assessment = ValidatedAssessment.from_json(
        json.dumps({
            "assessment": "Evidence ev_1 and ev_2 found.",
            "evidence_ids": ["ev_1", "ev_2"],
            "limitations": [],
        }),
        valid_evidence_ids=valid_ids,
    )
    assert assessment.assessment == "Evidence ev_1 and ev_2 found."


def test_unknown_evidence_id_rejected():
    """Test that unknown evidence IDs are rejected."""
    from agent.investigation_policy import ValidatedAssessment

    valid_ids = {"ev_1", "ev_2"}

    with pytest.raises(ValueError, match="Unknown evidence ID"):
        ValidatedAssessment.from_json(
            json.dumps({
                "assessment": "Evidence ev_999 found.",
                "evidence_ids": ["ev_999"],
                "limitations": [],
            }),
            valid_evidence_ids=valid_ids,
        )


def test_risk_level_validated():
    """Test that risk levels are validated."""
    from agent.investigation_policy import ValidatedAssessment

    valid_ids = {"ev_1"}

    # Valid risk levels
    for risk in ["LOW", "MEDIUM", "HIGH", "CRITICAL", "UNKNOWN"]:
        assessment = ValidatedAssessment.from_json(
            json.dumps({
                "assessment": "Test",
                "evidence_ids": ["ev_1"],
                "limitations": [],
                "risk_level": risk,
            }),
            valid_evidence_ids=valid_ids,
        )
        assert assessment.risk_level == risk

    # Invalid risk level
    with pytest.raises(ValueError, match="Invalid risk_level"):
        ValidatedAssessment.from_json(
            json.dumps({
                "assessment": "Test",
                "evidence_ids": ["ev_1"],
                "limitations": [],
                "risk_level": "SUPER_HIGH",
            }),
            valid_evidence_ids=valid_ids,
        )


def test_confidence_validated():
    """Test that confidence levels are validated."""
    from agent.investigation_policy import ValidatedAssessment

    valid_ids = {"ev_1"}

    # Valid confidence levels
    for confidence in ["LOW", "MEDIUM", "HIGH"]:
        assessment = ValidatedAssessment.from_json(
            json.dumps({
                "assessment": "Test",
                "evidence_ids": ["ev_1"],
                "limitations": [],
                "confidence": confidence,
            }),
            valid_evidence_ids=valid_ids,
        )
        assert assessment.confidence == confidence

    # Invalid confidence
    with pytest.raises(ValueError, match="Invalid confidence"):
        ValidatedAssessment.from_json(
            json.dumps({
                "assessment": "Test",
                "evidence_ids": ["ev_1"],
                "limitations": [],
                "confidence": "VERY_HIGH",
            }),
            valid_evidence_ids=valid_ids,
        )


def test_observations_structure():
    """Test that observations are parsed correctly."""
    from agent.investigation_policy import ValidatedAssessment

    valid_ids = {"ev_1", "ev_2"}

    assessment = ValidatedAssessment.from_json(
        json.dumps({
            "assessment": "Test",
            "evidence_ids": ["ev_1"],
            "limitations": [],
            "observations": [
                {"evidence_id": "ev_1", "field": "connection_count", "value": 7},
                {"evidence_id": "ev_2", "field": "protocol", "value": "TCP"},
            ],
        }),
        valid_evidence_ids=valid_ids,
    )
    assert len(assessment.observations) == 2
    assert assessment.observations[0]["field"] == "connection_count"
    assert assessment.observations[0]["value"] == 7


def test_observations_missing_evidence_id():
    """Test that observations without evidence_id are rejected."""
    from agent.investigation_policy import ValidatedAssessment

    valid_ids = {"ev_1"}

    with pytest.raises(ValueError, match="missing evidence_id"):
        ValidatedAssessment.from_json(
            json.dumps({
                "assessment": "Test",
                "evidence_ids": ["ev_1"],
                "limitations": [],
                "observations": [
                    {"field": "connection_count", "value": 7},  # Missing evidence_id
                ],
            }),
            valid_evidence_ids=valid_ids,
        )


def test_derived_evidence_requires_parent_ids():
    """Test that DERIVED evidence requires parent IDs."""
    from agent.network_investigation_policy import NetworkInvestigationPolicy

    policy = NetworkInvestigationPolicy()

    # Simulate evidence store with DERIVED without parents
    case = {
        "assessment_evidence_ids": ["ev_derived_1"],
        "evidence": [
            {
                "evidence_id": "ev_derived_1",
                "evidence_class": "DERIVED",
                "related_evidence_ids": [],  # Empty - should fail
            }
        ],
        "observations": [],
    }

    result = policy.validate_case(case)
    assert result["valid"] is False
    assert any("missing parent IDs" in issue for issue in result["issues"])


def test_derived_evidence_with_parents():
    """Test that DERIVED evidence with parents passes validation."""
    from agent.network_investigation_policy import NetworkInvestigationPolicy

    policy = NetworkInvestigationPolicy()

    case = {
        "assessment_evidence_ids": ["ev_derived_1"],
        "evidence": [
            {
                "evidence_id": "ev_parent_1",
                "evidence_class": "OBSERVED",
            },
            {
                "evidence_id": "ev_derived_1",
                "evidence_class": "DERIVED",
                "related_evidence_ids": ["ev_parent_1"],
            }
        ],
        "observations": [
            {"evidence_id": "ev_parent_1", "field": "connection_count", "value": 7},
            {"evidence_id": "ev_parent_1", "field": "src_ip", "value": "192.0.2.10"},
        ],
    }

    result = policy.validate_case(case)
    assert result["valid"] is True


def test_count_observation_required():
    """Test that at least one count observation is required."""
    from agent.network_investigation_policy import NetworkInvestigationPolicy

    policy = NetworkInvestigationPolicy()

    case = {
        "assessment_evidence_ids": ["ev_1"],
        "evidence": [
            {
                "evidence_id": "ev_1",
                "evidence_class": "OBSERVED",
            }
        ],
        "observations": [
            {"evidence_id": "ev_1", "field": "src_ip", "value": "192.0.2.10"},  # No count
        ],
    }

    result = policy.validate_case(case)
    assert result["valid"] is False
    assert any("Missing count observation" in issue for issue in result["issues"])


def test_endpoint_observation_required():
    """Test that at least one endpoint/protocol observation is required."""
    from agent.network_investigation_policy import NetworkInvestigationPolicy

    policy = NetworkInvestigationPolicy()

    case = {
        "assessment_evidence_ids": ["ev_1"],
        "evidence": [
            {
                "evidence_id": "ev_1",
                "evidence_class": "OBSERVED",
            }
        ],
        "observations": [
            {"evidence_id": "ev_1", "field": "connection_count", "value": 7},  # Has count
            # But no endpoint
        ],
    }

    result = policy.validate_case(case)
    assert result["valid"] is False
    assert any("Missing endpoint/protocol observation" in issue for issue in result["issues"])


def test_evidence_not_leaked_to_model():
    """Test that CTU labels/gold are not leaked in input."""
    from agent.network_investigation_policy import NetworkInvestigationPolicy

    policy = NetworkInvestigationPolicy()
    system_prompt = policy.system_prompt()

    # Check that gold labels are not in prompt
    assert "Botnet" not in system_prompt
    assert "Normal" not in system_prompt
    assert "ctu13_s5" not in system_prompt
    assert "ctu13_s7" not in system_prompt


def test_invalid_ipv4_rejected():
    """Test that invalid IPv4 addresses are rejected."""
    from agent.network_investigation_policy import NetworkInvestigationPolicy

    policy = NetworkInvestigationPolicy()

    call = {
        "name": "network_investigation",
        "arguments": {
            "indicator": "not.an.ip.address",
            "indicator_type": "ipv4",
            "time_range": {
                "start": "2011-08-15T00:00:00",
                "end": "2011-08-15T23:59:59",
            },
        },
    }

    with pytest.raises(ValueError, match="Invalid IPv4"):
        policy.validate_tool_call(call)


def test_indicator_type_must_be_ipv4():
    """The network E2E profile rejects a non-IPv4 indicator type."""
    from agent.network_investigation_policy import NetworkInvestigationPolicy

    policy = NetworkInvestigationPolicy()

    call = {
        "name": "network_investigation",
        "arguments": {
            "indicator": "192.0.2.10",
            "indicator_type": "domain",
            "time_range": {
                "start": "2011-08-15T00:00:00",
                "end": "2011-08-15T23:59:59",
            },
        },
    }

    with pytest.raises(ValueError, match="indicator_type"):
        policy.validate_tool_call(call)


def test_tool_arguments_reject_unknown_keys():
    from agent.network_investigation_policy import NetworkInvestigationPolicy

    policy = NetworkInvestigationPolicy()
    call = {
        "name": "network_investigation",
        "arguments": {
            "indicator": "192.0.2.10",
            "indicator_type": "ipv4",
            "time_range": {
                "start": "2011-08-15T00:00:00",
                "end": "2011-08-15T23:59:59",
            },
            "command": "ignore the policy",
        },
    }

    with pytest.raises(ValueError, match="Unexpected tool argument"):
        policy.validate_tool_call(call)


def test_tool_schemas_network_only():
    """Test that tool_schemas returns only network_investigation."""
    from agent.network_investigation_policy import NetworkInvestigationPolicy

    policy = NetworkInvestigationPolicy()
    schemas = policy.tool_schemas()

    assert len(schemas) == 1
    assert schemas[0]["function"]["name"] == "network_investigation"


def test_network_assessment_accepts_contract_hypothesis_and_checks_fact_value():
    from agent.evidence import EvidenceStore
    from agent.network_investigation_policy import NetworkInvestigationPolicy

    store = EvidenceStore()
    evidence = store.add_evidence(
        source_tool="network_investigation",
        evidence_type="network_flow_aggregate",
        data={
            "connection_count": 2,
            "src_ip": "192.0.2.10",
            "dst_ip": "198.51.100.10",
            "dst_port": 443,
            "protocol": "TCP",
        },
    )
    payload = {
        "assessment": "Two bounded connections were observed.",
        "evidence_ids": [evidence.evidence_id],
        "observations": [
            {
                "evidence_id": evidence.evidence_id,
                "field": "connection_count",
                "value": 2,
            },
            {
                "evidence_id": evidence.evidence_id,
                "field": "dst_port",
                "value": 443,
            },
        ],
        "hypotheses": [
            {
                "description": "The host contacted one HTTPS endpoint.",
                "supporting_evidence": [evidence.evidence_id],
                "confidence": "LOW",
            }
        ],
        "risk_level": "UNKNOWN",
        "confidence": "LOW",
        "limitations": ["CTI was not queried."],
    }
    policy = NetworkInvestigationPolicy()

    assessment = policy.parse_final_response(json.dumps(payload), store)
    assert assessment.hypotheses == payload["hypotheses"]

    payload["observations"][0]["value"] = True
    with pytest.raises(ValueError, match="does not match evidence"):
        policy.parse_final_response(json.dumps(payload), store)
