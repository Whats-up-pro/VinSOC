"""Deterministic alert triage gate for the MVP."""
from dataclasses import dataclass
from typing import Optional


@dataclass
class TriageResult:
    """Initial alert decision before deeper investigation."""

    verdict: str
    reason: str
    confidence: str

    def to_dict(self):
        return {
            "verdict": self.verdict,
            "reason": self.reason,
            "confidence": self.confidence,
        }


def triage_alert(indicator: str, context: Optional[str] = None) -> TriageResult:
    """Apply conservative, explainable triage rules before tool use."""
    text = f"{indicator} {context or ''}".lower()
    benign_markers = ("known infrastructure", "expected", "allowlisted", "benign")
    suspicious_markers = ("malicious", "suspicious", "beacon", "exfil", "scan", "anomaly")

    if any(marker in text for marker in suspicious_markers):
        return TriageResult("SUSPICIOUS", "Alert context contains suspicious activity markers", "MEDIUM")
    if any(marker in text for marker in benign_markers):
        return TriageResult("BENIGN", "Alert context identifies expected or known activity", "MEDIUM")
    return TriageResult("NEEDS_INVESTIGATION", "Context is insufficient for closure", "LOW")