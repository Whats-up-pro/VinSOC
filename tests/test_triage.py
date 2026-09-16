"""Comprehensive tests for the strengthened TriageEngine."""
import pytest
from agent.triage import triage_alert, TriageEngine, TriageResult


class TestTriageEngine:
    """Test cases for strengthened triage."""

    # ============ Case Sensitivity Tests ============

    def test_case_insensitive_suspicious_uppercase(self):
        """Test uppercase MALICIOUS is detected."""
        result = triage_alert("1.1.1.1", "MALICIOUS BEACON")
        assert result.verdict == "SUSPICIOUS"

    def test_case_insensitive_suspicious_mixed_case(self):
        """Test mixed case Suspicious is detected."""
        result = triage_alert("1.1.1.1", "Suspicious Activity")
        assert result.verdict == "SUSPICIOUS"

    def test_case_insensitive_benign(self):
        """Test case-insensitive benign detection."""
        result = triage_alert("10.0.0.1", "Known Infrastructure")
        assert result.verdict == "BENIGN"

    # ============ Phrase Detection Tests ============

    def test_phrase_suspicious_beaconing(self):
        """Test beaconing phrase detection."""
        result = triage_alert("1.1.1.1", "Active beaconing detected")
        assert result.verdict == "SUSPICIOUS"
        assert "beacon" in result.reason.lower()

    def test_phrase_suspicious_data_exfil(self):
        """Test data exfiltration phrase detection."""
        result = triage_alert("1.1.1.1", "Data exfiltration attempt")
        assert result.verdict == "SUSPICIOUS"

    def test_phrase_suspicious_lateral_movement(self):
        """Test lateral movement phrase detection."""
        result = triage_alert("10.0.0.5", "Lateral movement detected")
        assert result.verdict == "SUSPICIOUS"

    def test_phrase_benign_known_infrastructure(self):
        """Test known infrastructure phrase detection."""
        result = triage_alert("10.0.0.1", "known infrastructure")
        assert result.verdict == "BENIGN"

    def test_phrase_benign_expected_traffic(self):
        """Test expected traffic phrase detection."""
        result = triage_alert("8.8.8.8", "Expected traffic pattern")
        assert result.verdict == "BENIGN"

    def test_phrase_benign_allowlist(self):
        """Test allowlist phrase detection."""
        result = triage_alert("10.0.0.10", "IP is allowlisted")
        assert result.verdict == "BENIGN"

    # ============ Negation Tests ============

    def test_negation_not_malicious(self):
        """Test negation: 'not malicious' should not trigger suspicious."""
        result = triage_alert("10.0.0.1", "This is NOT malicious")
        assert result.verdict != "SUSPICIOUS"
        assert result.verdict == "NEEDS_INVESTIGATION"

    def test_negation_no_evidence(self):
        """Test negation: 'no evidence of malicious'."""
        result = triage_alert("8.8.8.8", "No evidence of malicious activity")
        assert result.verdict != "SUSPICIOUS"

    def test_negation_false_positive(self):
        """Test negation: 'false positive' triggers benign."""
        result = triage_alert("1.2.3.4", "Ruled out - false positive")
        assert result.verdict == "BENIGN"

    def test_negation_ruled_out(self):
        """Test negation: 'ruled out' triggers benign."""
        result = triage_alert("1.2.3.4", "Threat has been ruled out")
        assert result.verdict == "BENIGN"

    def test_negation_clear_of(self):
        """Test negation: 'clear of threats'."""
        result = triage_alert("10.0.0.5", "System is clear of threats")
        assert result.verdict == "BENIGN"

    def test_negation_in_sentence_context(self):
        """
        Test sentence-level negation handling.

        When negation is present in ANY sentence, suspicious markers are ignored.
        This is conservative - we prefer to investigate rather than miss something.
        """
        result = triage_alert("1.1.1.1", "Suspicious beacon detected. However, it is not malicious.")
        # Negation present in text, so suspicious is ignored
        assert result.verdict == "NEEDS_INVESTIGATION"

    # ============ Edge Cases ============

    def test_partial_word_matching_prevented(self):
        """Test that partial word matches don't trigger."""
        # "infrastructure" contains "struct" but shouldn't match "struct"
        result = triage_alert("10.0.0.1", "This is a test infrastructure")
        assert result.verdict == "NEEDS_INVESTIGATION"  # Not BENIGN

    def test_compound_suspicious_benign_benign_wins(self):
        """Test that benign markers take priority over suspicious."""
        result = triage_alert("10.0.0.5", "Suspicious beacon but known infrastructure")
        assert result.verdict == "BENIGN"

    def test_empty_context(self):
        """Test with no context."""
        result = triage_alert("192.168.1.1")
        assert result.verdict == "NEEDS_INVESTIGATION"

    def test_empty_indicator(self):
        """Test with no indicator value."""
        result = triage_alert("", "suspicious beacon")
        assert result.verdict == "SUSPICIOUS"

    def test_multiple_suspicious_markers(self):
        """Test multiple suspicious markers."""
        result = triage_alert("1.1.1.1", "Malicious beacon and data exfiltration detected")
        assert result.verdict == "SUSPICIOUS"

    # ============ Threat Category Tests ============

    def test_ransomware_marker(self):
        """Test ransomware detection."""
        result = triage_alert("10.0.0.1", "ransomware infection detected")
        assert result.verdict == "SUSPICIOUS"

    def test_backdoor_marker(self):
        """Test backdoor detection."""
        result = triage_alert("10.0.0.1", "backdoor installed")
        assert result.verdict == "SUSPICIOUS"

    def test_cobalt_strike_marker(self):
        """Test Cobalt Strike detection."""
        result = triage_alert("10.0.0.1", "cobalt strike beacon")
        assert result.verdict == "SUSPICIOUS"

    def test_apt_marker(self):
        """Test APT detection."""
        result = triage_alert("10.0.0.1", "apt activity suspected")
        assert result.verdict == "SUSPICIOUS"

    def test_trojan_marker(self):
        """Test trojan detection."""
        result = triage_alert("10.0.0.1", "trojan downloader")
        assert result.verdict == "SUSPICIOUS"

    # ============ Confidence Tests ============

    def test_confidence_for_benign(self):
        """Test confidence level for benign verdict."""
        result = triage_alert("10.0.0.1", "known infrastructure")
        assert result.confidence == "MEDIUM"

    def test_confidence_for_suspicious(self):
        """Test confidence level for suspicious verdict."""
        result = triage_alert("1.1.1.1", "malicious beacon")
        assert result.confidence == "MEDIUM"

    def test_confidence_for_needs_investigation(self):
        """Test confidence level for needs investigation."""
        result = triage_alert("192.168.1.1", "some activity")
        assert result.confidence == "LOW"

    # ============ Backward Compatibility Tests ============

    def test_result_has_to_dict(self):
        """Test TriageResult.to_dict() method."""
        result = triage_alert("1.1.1.1", "malicious")
        d = result.to_dict()
        assert "verdict" in d
        assert "reason" in d
        assert "confidence" in d

    def test_triage_engine_direct_usage(self):
        """Test direct TriageEngine usage."""
        engine = TriageEngine()
        result = engine.triage("1.1.1.1", "suspicious beacon")
        assert result.verdict == "SUSPICIOUS"

    # ============ Regression Tests ============

    def test_regression_original_behavior_preserved(self):
        """Test that original triage behavior is preserved."""
        # Original markers that should still work
        assert triage_alert("192.168.1.1", "malicious").verdict == "SUSPICIOUS"
        assert triage_alert("10.0.0.1", "known infrastructure").verdict == "BENIGN"
        assert triage_alert("10.0.0.1", "allowlisted").verdict == "BENIGN"
        assert triage_alert("10.0.0.1", "expected").verdict == "BENIGN"
        assert triage_alert("192.168.1.1", "beacon").verdict == "SUSPICIOUS"
        assert triage_alert("192.168.1.1", "exfil").verdict == "SUSPICIOUS"
        assert triage_alert("192.168.1.1", "scan").verdict == "SUSPICIOUS"
        assert triage_alert("192.168.1.1", "anomaly").verdict == "SUSPICIOUS"
