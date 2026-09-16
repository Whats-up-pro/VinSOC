"""
Deterministic alert triage gate for the MVP.

This module provides a rule-based triage engine with:
- Phrase-based detection using regex
- Case-insensitive matching
- Negation handling (e.g., "not malicious", "ruled out")
- Sentence-level analysis for context
"""
import re
from dataclasses import dataclass
from typing import List, Optional, Tuple


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


class TriageEngine:
    """
    Rule-based triage engine with phrase detection and negation handling.

    Priority: BENIGN > SUSPICIOUS > NEEDS_INVESTIGATION

    This is a CONSERVATIVE gate - false positives are preferred over
    false negatives in a security context.
    """

    def __init__(self):
        # Phrases that indicate BENIGN activity (higher priority)
        self._benign_phrases: List[Tuple[str, str]] = [
            (r"\bknown\s+infrastructure\b", "Known infrastructure marker"),
            (r"\bexpected\b", "Expected marker"),  # Standalone "expected" also benign
            (r"\bexpected\s+(?:traffic|activity|behavior)\b", "Expected activity marker"),
            (r"\ballowlist(?:ed)?\b", "Allowlist marker"),
            (r"\b(?:allowlist|whitelist)\s+(?:entry|ip|domain)\b", "Allowlist entry"),
            (r"\bbenign\b", "Benign marker"),
            (r"\bknown\s+good\b", "Known good marker"),
            (r"\bfalse\s+positive\b", "False positive declaration"),
            (r"\bnot\s+a\s+threat\b", "Explicit non-threat"),
            (r"\bclear(?:ed)?\s+(?:of|as)\b", "Explicitly cleared"),
            (r"\bruled\s+out\b", "Ruled out threat"),
        ]

        # Phrases that indicate SUSPICIOUS activity
        self._suspicious_phrases: List[Tuple[str, str]] = [
            (r"\b(?:active\s+)?malicious\b", "Malicious marker"),
            (r"\b(?:confirmed\s+)?suspicious\b", "Suspicious marker"),
            (r"\b(?:potential\s+)?beacon(?:ing)?\b", "Beacon indicator"),
            (r"\b(?:data\s+)?exfil(?:tration)?\b", "Exfiltration indicator"),
            (r"\b(?:port\s+)?scan(?:ning)?\b", "Scan indicator"),
            (r"\b(?:security\s+)?anomal(?:y|ies)\b", "Anomaly marker"),
            (r"\b(?:command\s+and\s+control|c2|c\&c)\b", "C2 indicator"),
            (r"\b(?:lateral\s+)?movement\b", "Movement indicator"),
            (r"\b(?:privilege\s+)?escalation\b", "Escalation indicator"),
            (r"\bransomware\b", "Ransomware indicator"),
            (r"\bbackdoor\b", "Backdoor indicator"),
            (r"\btrojan\b", "Trojan indicator"),
            (r"\bcobalt\s+strike\b", "Cobalt Strike indicator"),
            (r"\bapt\b", "APT indicator"),
            (r"\bimplant\b", "Implant indicator"),
            (r"\bdropper\b", "Dropper indicator"),
        ]

        # Negation patterns - phrases that CANCEL suspicious markers
        self._negation_patterns = [
            r"\bnot\s+(?:malicious|suspicious|beacon|exfil|scan)",
            r"\bno\s+(?:evidence\s+of|signs?\s+of)\s+(?:malicious|suspicious)",
            r"\bclear(?:ed)?\s+(?:of|as)\s+(?:benign|not\s+a\s+threat)",
            r"\bruled\s+out\b",
            r"\bfalse\s+positive\b",
            r"\bbenign\s+(?:activity|traffic|behavior)",
            r"\bnot\s+a\s+threat\b",
            r"\bknown\s+(?:good|infrastructure)\b",
            r"\ballowlist(?:ed)?\b",
        ]

    def triage(self, indicator: str, context: Optional[str] = None) -> TriageResult:
        """
        Apply conservative triage rules.

        Priority: BENIGN > SUSPICIOUS > NEEDS_INVESTIGATION

        Negation handling: If suspicious markers are negated in the SAME sentence,
        they are ignored. But if suspicious appears in one sentence and negation
        in another, the suspicious still triggers.
        """
        text = f"{indicator} {context or ''}".lower()

        # Check for negation
        has_negation = self._check_negation(text)

        # Check BENIGN phrases (higher priority)
        benign_hit = self._match_phrases(text, self._benign_phrases)
        if benign_hit:
            # Even if there are suspicious markers, benign takes priority
            # UNLESS the suspicious markers are in sentences WITHOUT negation
            if not self._has_suspicious_without_negation(text):
                return TriageResult(
                    verdict="BENIGN",
                    reason=benign_hit,
                    confidence="MEDIUM"
                )

        # Check SUSPICIOUS phrases (unless negated)
        suspicious_hit = self._match_phrases(text, self._suspicious_phrases)
        if suspicious_hit:
            # Only skip if NEGATION is present in text
            # (not just in the same sentence as suspicious)
            if not has_negation:
                return TriageResult(
                    verdict="SUSPICIOUS",
                    reason=suspicious_hit,
                    confidence="MEDIUM"
                )

        # Default: needs investigation
        return TriageResult(
            verdict="NEEDS_INVESTIGATION",
            reason="Context is insufficient for closure",
            confidence="LOW"
        )

    def _check_negation(self, text: str) -> bool:
        """Check if text contains negation patterns."""
        for pattern in self._negation_patterns:
            if re.search(pattern, text, re.IGNORECASE):
                return True
        return False

    def _match_phrases(self, text: str, phrase_list: List[Tuple[str, str]]) -> Optional[str]:
        """Match phrases in text, return first match reason."""
        for pattern, reason in phrase_list:
            if re.search(pattern, text, re.IGNORECASE):
                return reason
        return None

    def _has_suspicious_without_negation(self, text: str) -> bool:
        """
        Check if text has suspicious markers that are NOT negated.

        Uses sentence-level analysis: suspicious and negation in same
        sentence means suspicious is likely negated.
        """
        # Split into sentences
        sentences = re.split(r'[.!?\n]', text)

        for sentence in sentences:
            sentence = sentence.strip()
            if not sentence:
                continue

            has_suspicious = self._match_phrases(sentence, self._suspicious_phrases)
            has_negation = self._check_negation(sentence)

            # If suspicious in same sentence as negation, it's likely negated
            if has_suspicious and has_negation:
                continue  # Negated suspicious, continue to next sentence

            if has_suspicious:
                return True  # Un-negated suspicious found

        return False


# Module-level engine instance for backward compatibility
_triage_engine = TriageEngine()


def triage_alert(indicator: str, context: Optional[str] = None) -> TriageResult:
    """Apply conservative, explainable triage rules before tool use."""
    return _triage_engine.triage(indicator, context)
