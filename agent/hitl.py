"""Human-in-the-loop review primitives for VinSOC.

The core orchestrator depends on this interface instead of terminal/UI code so
interactive CLI, web UI, and deterministic tests can provide their own review
implementation.
"""
from dataclasses import dataclass
from typing import Optional, Protocol, TYPE_CHECKING

if TYPE_CHECKING:
    from agent.orchestrator import InvestigationCase
    from agent.triage import TriageResult


TRIAGE_CLOSE = "CLOSE"
TRIAGE_CONTINUE = "CONTINUE"

REVIEW_APPROVE = "APPROVE"
REVIEW_REQUEST_MORE_EVIDENCE = "REQUEST_MORE_EVIDENCE"
REVIEW_ESCALATE = "ESCALATE"
REVIEW_REJECT = "REJECT"


@dataclass
class HumanDecision:
    """A traceable analyst decision returned by a HITL gate."""
    decision: str
    rationale: str = ""
    feedback: str = ""
    analyst: str = "human"

    def to_dict(self):
        return {
            "decision": self.decision,
            "rationale": self.rationale,
            "feedback": self.feedback,
            "analyst": self.analyst,
        }


class HumanReviewGate(Protocol):
    """UI-agnostic contract for runtime analyst intervention."""

    def review_triage(
        self,
        indicator: str,
        indicator_type: str,
        context: Optional[str],
        triage: "TriageResult",
    ) -> HumanDecision:
        ...

    def review_final(self, case: "InvestigationCase") -> HumanDecision:
        ...


class ScriptedHumanReviewGate:
    """Deterministic gate for tests, benchmarks, and non-interactive evaluation."""

    def __init__(
        self,
        triage_decision: str = TRIAGE_CLOSE,
        final_decisions=None,
        analyst: str = "scripted-reviewer",
    ):
        self.triage_decision = triage_decision
        self.final_decisions = list(final_decisions or [REVIEW_APPROVE])
        self.analyst = analyst
        self._final_index = 0

    def review_triage(self, indicator, indicator_type, context, triage):
        return HumanDecision(
            decision=self.triage_decision,
            rationale="Deterministic scripted triage decision",
            analyst=self.analyst,
        )

    def review_final(self, case):
        idx = min(self._final_index, len(self.final_decisions) - 1)
        decision = self.final_decisions[idx]
        self._final_index += 1
        if isinstance(decision, HumanDecision):
            return decision
        return HumanDecision(
            decision=decision,
            rationale="Deterministic scripted final review",
            analyst=self.analyst,
        )
