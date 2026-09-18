"""Runtime human-in-the-loop behavior tests."""
from agent.hitl import (
    HumanDecision,
    ScriptedHumanReviewGate,
    TRIAGE_CLOSE,
    TRIAGE_CONTINUE,
    REVIEW_APPROVE,
    REVIEW_REQUEST_MORE_EVIDENCE,
    REVIEW_ESCALATE,
)
from agent.orchestrator import InvestigationOrchestrator
from agent.provider import MockProvider


def _benign_cti(indicator):
    return {
        indicator: {
            "indicator": indicator,
            "indicator_type": "ipv4",
            "reputation": "benign",
            "confidence": "high",
            "related_actors": [],
            "related_malware": [],
            "mitre_techniques": [],
            "sources": [],
            "observed_evidence": [],
        }
    }


def _unknown_cti(indicator):
    return {
        indicator: {
            "indicator": indicator,
            "indicator_type": "ipv4",
            "reputation": "unknown",
            "confidence": "low",
            "related_actors": [],
            "related_malware": [],
            "mitre_techniques": [],
            "sources": [],
            "observed_evidence": [],
        }
    }


def test_benign_triage_requires_human_close_when_gate_enabled():
    indicator = "8.8.8.8"
    gate = ScriptedHumanReviewGate(
        triage_decision=TRIAGE_CLOSE,
        final_decisions=[REVIEW_APPROVE],
    )
    orch = InvestigationOrchestrator(
        provider=MockProvider(model="hitl-test"),
        human_review_gate=gate,
        cti_mock_data=_benign_cti(indicator),
    )

    case = orch.investigate(indicator)

    assert case.metadata["hitl_enabled"] is True
    assert case.metadata["review_status"] == "approved"
    assert any(
        d["phase"] == "triage" and d["decision"] == TRIAGE_CLOSE
        for d in case.metadata["human_decisions"]
    )
    statuses = [
        (event["phase"], event["status"])
        for event in case.metadata["lifecycle_trace"]
    ]
    assert ("triage_review", "awaiting_human") in statuses


def test_human_can_override_benign_triage_and_continue():
    indicator = "8.8.4.4"
    gate = ScriptedHumanReviewGate(
        triage_decision=TRIAGE_CONTINUE,
        final_decisions=[REVIEW_APPROVE],
    )
    orch = InvestigationOrchestrator(
        provider=MockProvider(model="hitl-test"),
        human_review_gate=gate,
        cti_mock_data=_benign_cti(indicator),
    )

    case = orch.investigate(indicator)

    assert any(
        d["phase"] == "triage" and d["decision"] == TRIAGE_CONTINUE
        for d in case.metadata["human_decisions"]
    )
    assert any(
        event["phase"] == "investigate"
        for event in case.metadata["lifecycle_trace"]
    )


def test_final_review_can_approve_case():
    indicator = "192.0.2.10"
    gate = ScriptedHumanReviewGate(
        final_decisions=[REVIEW_APPROVE],
    )
    orch = InvestigationOrchestrator(
        provider=MockProvider(model="hitl-test"),
        human_review_gate=gate,
        cti_mock_data=_unknown_cti(indicator),
    )

    case = orch.investigate(indicator)

    assert case.metadata["review_status"] == "approved"
    assert any(
        d["phase"] == "final_review" and d["decision"] == REVIEW_APPROVE
        for d in case.metadata["human_decisions"]
    )


def test_final_review_can_escalate_case():
    indicator = "192.0.2.11"
    gate = ScriptedHumanReviewGate(
        final_decisions=[REVIEW_ESCALATE],
    )
    orch = InvestigationOrchestrator(
        provider=MockProvider(model="hitl-test"),
        human_review_gate=gate,
        cti_mock_data=_unknown_cti(indicator),
    )

    case = orch.investigate(indicator)

    assert case.metadata["review_status"] == "escalated"


class FeedbackGate:
    """Request one evidence pass, then approve the revised case."""

    def __init__(self):
        self.calls = 0

    def review_triage(self, indicator, indicator_type, context, triage):
        return HumanDecision(decision=TRIAGE_CONTINUE, analyst="test-analyst")

    def review_final(self, case):
        self.calls += 1
        if self.calls == 1:
            return HumanDecision(
                decision=REVIEW_REQUEST_MORE_EVIDENCE,
                feedback="Check whether another read-only telemetry source can corroborate this assessment.",
                analyst="test-analyst",
            )
        return HumanDecision(
            decision=REVIEW_APPROVE,
            rationale="Reviewed revised evidence set",
            analyst="test-analyst",
        )


def test_analyst_feedback_resumes_investigation():
    indicator = "192.0.2.12"
    gate = FeedbackGate()
    orch = InvestigationOrchestrator(
        provider=MockProvider(model="hitl-test"),
        human_review_gate=gate,
        max_review_cycles=1,
        cti_mock_data=_unknown_cti(indicator),
    )

    case = orch.investigate(indicator)

    assert case.metadata["review_status"] == "approved"
    decisions = [d["decision"] for d in case.metadata["human_decisions"]]
    assert REVIEW_REQUEST_MORE_EVIDENCE in decisions
    assert REVIEW_APPROVE in decisions
    assert any(
        event["phase"] == "investigate" and event["status"] == "resumed"
        for event in case.metadata["lifecycle_trace"]
    )
