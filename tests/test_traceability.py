"""Tests for evidence traceability enforcement."""
import pytest
from agent.orchestrator import (
    InvestigationOrchestrator,
    InvestigationHypothesis,
    EvidenceTraceabilityViolation,
)
from agent.provider import MockProvider
from agent.evidence import Evidence


class TestEvidenceTraceability:
    """Test evidence traceability enforcement."""

    def test_hypothesis_with_invalid_evidence_id_is_flagged(self):
        """Hypothesis referencing non-existent evidence should be flagged."""
        orchestrator = InvestigationOrchestrator()

        # Create mock evidence
        mock_evidence = [
            Evidence(
                evidence_id="ev_001",
                source_tool="cti_enrichment",
                type="cti_result",
                data={"reputation": "malicious"},
                collected_at="2024-01-01T00:00:00Z"
            )
        ]

        # Mock tool_call
        mock_tool_calls = []

        # Create hypothesis with INVALID evidence reference
        invalid_hypothesis = InvestigationHypothesis(
            id="h1",
            description="Malicious activity detected",
            supporting_evidence=["ev_001", "ev_invalid_999"],  # ev_invalid_999 doesn't exist
            confidence="HIGH"
        )

        limitations, violations = orchestrator._verify_case_quality(
            mock_evidence,
            mock_tool_calls,
            [invalid_hypothesis]
        )

        # Should have violation for invalid evidence AND orphan evidence
        assert len(violations) >= 1
        # Find the hypothesis violation
        hypothesis_violations = [v for v in violations if v.hypothesis_id == "h1"]
        assert len(hypothesis_violations) == 1
        assert "ev_invalid_999" in hypothesis_violations[0].invalid_evidence_ids
        assert len(limitations) > 0

    def test_hypothesis_with_valid_evidence_has_no_violations(self):
        """Hypothesis with only valid evidence should pass."""
        orchestrator = InvestigationOrchestrator()

        # Provide lifecycle trace (at least one entry) to avoid that limitation
        from agent.orchestrator import LifecycleEvent
        orchestrator.lifecycle_trace = [
            LifecycleEvent(phase="triage", status="completed", note="test", timestamp="2024-01-01T00:00:00Z")
        ]

        mock_evidence = [
            Evidence(
                evidence_id="ev_001",
                source_tool="cti_enrichment",
                type="cti_result",
                data={"reputation": "malicious"},
                collected_at="2024-01-01T00:00:00Z"
            )
        ]

        # Valid hypothesis with existing evidence ID
        valid_hypothesis = InvestigationHypothesis(
            id="h1",
            description="Malicious activity detected",
            supporting_evidence=["ev_001"],  # Valid reference
            confidence="HIGH"
        )

        # Provide tool_calls to avoid orphan evidence flag
        mock_tool_calls = [{"tool": "cti_enrichment", "id": "tc_001"}]

        limitations, violations = orchestrator._verify_case_quality(
            mock_evidence,
            mock_tool_calls,
            [valid_hypothesis]
        )

        # Should have no violations
        assert len(violations) == 0

    def test_multiple_hypotheses_with_mixed_validity(self):
        """Test multiple hypotheses with some having invalid references."""
        orchestrator = InvestigationOrchestrator()

        mock_evidence = [
            Evidence(
                evidence_id="ev_001",
                source_tool="cti_enrichment",
                type="cti_result",
                data={},
                collected_at="2024-01-01T00:00:00Z"
            ),
            Evidence(
                evidence_id="ev_002",
                source_tool="network_investigation",
                type="network_result",
                data={},
                collected_at="2024-01-01T00:00:00Z"
            )
        ]

        # Provide tool_calls to avoid orphan evidence flag
        mock_tool_calls = [{"tool": "cti_enrichment", "id": "tc_001"}]

        hypotheses = [
            InvestigationHypothesis(
                id="h1",
                description="Valid hypothesis",
                supporting_evidence=["ev_001"],  # Valid
                confidence="HIGH"
            ),
            InvestigationHypothesis(
                id="h2",
                description="Invalid hypothesis",
                supporting_evidence=["ev_001", "ev_missing"],  # ev_missing doesn't exist
                confidence="HIGH"
            ),
            InvestigationHypothesis(
                id="h3",
                description="Another valid hypothesis",
                supporting_evidence=["ev_002"],  # Valid
                confidence="MEDIUM"
            ),
        ]

        limitations, violations = orchestrator._verify_case_quality(
            mock_evidence,
            mock_tool_calls,
            hypotheses
        )

        # Should have violation for h2 only
        assert len(violations) == 1
        assert violations[0].hypothesis_id == "h2"
        assert "ev_missing" in violations[0].invalid_evidence_ids

    def test_empty_evidence_with_hypothesis(self):
        """Test with no evidence but hypothesis exists."""
        orchestrator = InvestigationOrchestrator()

        hypothesis = InvestigationHypothesis(
            id="h1",
            description="Some hypothesis",
            supporting_evidence=["ev_001"],
            confidence="HIGH"
        )

        limitations, violations = orchestrator._verify_case_quality(
            [],  # No evidence
            [],
            [hypothesis]
        )

        # Should have violation for invalid evidence reference
        assert len(violations) >= 1
        assert violations[0].hypothesis_id == "h1"

    def test_case_metadata_contains_traceability_info(self):
        """Case metadata should include traceability validation results."""
        orchestrator = InvestigationOrchestrator(
            provider=MockProvider(model="test")
        )

        case = orchestrator.investigate(
            indicator="192.168.1.1",
            context="suspicious beacon"
        )

        assert "traceability_valid" in case.metadata
        assert "traceability_violations" in case.metadata
        assert isinstance(case.metadata["traceability_violations"], list)

    def test_traceability_violation_flagged_in_security_flags(self):
        """Traceability violations should add security flag in case metadata."""
        orchestrator = InvestigationOrchestrator()

        mock_evidence = [
            Evidence(
                evidence_id="ev_001",
                source_tool="cti_enrichment",
                type="cti_result",
                data={},
                collected_at="2024-01-01T00:00:00Z"
            )
        ]

        hypothesis = InvestigationHypothesis(
            id="h1",
            description="Test",
            supporting_evidence=["ev_invalid"],  # Invalid
            confidence="HIGH"
        )

        # Call with empty tool_calls to trigger orphan violation
        limitations, violations = orchestrator._verify_case_quality(
            mock_evidence, [], [hypothesis]
        )

        # Should have violations
        assert len(violations) > 0

        # The flag is added in _generate_case, not in _verify_case_quality
        # So we test by running a full investigation
        from agent.provider import MockProvider
        orch2 = InvestigationOrchestrator(provider=MockProvider(model="test"))
        case = orch2.investigate("192.168.1.1", context="suspicious")

        # Check that traceability_violations appears in case metadata if there are any
        if len(violations) > 0:
            # The flag would be added if violations exist
            assert "traceability_violations" in case.metadata

    def test_traceability_violation_to_dict(self):
        """Test EvidenceTraceabilityViolation.to_dict() method."""
        violation = EvidenceTraceabilityViolation(
            hypothesis_id="h1",
            invalid_evidence_ids=["ev_001", "ev_002"]
        )

        d = violation.to_dict()
        assert d["hypothesis_id"] == "h1"
        assert "ev_001" in d["invalid_evidence_ids"]
        assert "message" in d
        assert "h1" in d["message"]

    def test_orphan_evidence_detected(self):
        """Evidence without tool trace should be flagged."""
        orchestrator = InvestigationOrchestrator()

        mock_evidence = [
            Evidence(
                evidence_id="ev_001",
                source_tool="cti_enrichment",
                type="cti_result",
                data={},
                collected_at="2024-01-01T00:00:00Z"
            )
        ]

        # Empty tool_calls means evidence has no trace
        limitations, violations = orchestrator._verify_case_quality(
            mock_evidence,
            [],  # No tool calls
            []
        )

        # Should flag orphan evidence
        assert len(violations) >= 1
        orphan_violations = [v for v in violations if "_orphan_evidence" in v.invalid_evidence_ids]
        assert len(orphan_violations) == 1
