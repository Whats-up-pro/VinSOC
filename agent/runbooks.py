"""Runbook/persona normalization for analyst-facing investigations."""
from dataclasses import dataclass, field
from typing import Dict, List


@dataclass
class InvestigationPersona:
    """Standard persona profile used during review stage."""
    name: str
    role: str
    priorities: List[str] = field(default_factory=list)


@dataclass
class InvestigationRunbook:
    """Standardized runbook sections inspired by SOC workflows."""
    title: str
    trigger: str
    triage_checks: List[str]
    investigation_steps: List[str]
    verification_checks: List[str]
    review_questions: List[str]

    def to_dict(self) -> Dict[str, object]:
        return {
            "title": self.title,
            "trigger": self.trigger,
            "triage_checks": self.triage_checks,
            "investigation_steps": self.investigation_steps,
            "verification_checks": self.verification_checks,
            "review_questions": self.review_questions,
        }


def default_soc_runbook() -> InvestigationRunbook:
    """Default runbook aligned to triage->investigate->verify->review."""
    return InvestigationRunbook(
        title="SOC IOC Investigation",
        trigger="Suspicious indicator alert",
        triage_checks=[
            "Validate alert context and source fidelity",
            "Classify indicator type and trust level",
            "Decide close vs continue",
        ],
        investigation_steps=[
            "Collect CTI evidence for the indicator",
            "Pivot to network telemetry when communication evidence is needed",
            "Pivot to endpoint telemetry when process execution evidence is needed",
        ],
        verification_checks=[
            "Ensure every hypothesis cites evidence IDs",
            "Validate result schema and trace integrity",
        ],
        review_questions=[
            "What evidence supports or contradicts the assessment?",
            "What data gaps remain before action by human analyst?",
        ],
    )
