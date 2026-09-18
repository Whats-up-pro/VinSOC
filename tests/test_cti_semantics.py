"""
CTI Skill Semantics Contract Tests

These tests enforce the fail-closed product contract for CTISkill:
- Invalid IOC / unsupported indicator type → FAIL
- Valid IOC + no CTI source configured → FAIL
- Valid IOC + CTI source exists + IOC not found → SUCCESS / UNKNOWN
- Valid IOC + CTI source exists + IOC matched → SUCCESS / CTI RESULT
"""
import pytest
from skills.cti_skill import CTISkill


class TestCTIFailClosedContract:
    """Contract tests for CTI fail-closed semantics."""

    def test_cti_without_source_fails_closed(self):
        """
        Test: No CTI source configured → FAIL

        No CTI source ≠ unknown CTI reputation.
        A lookup must actually be performed to return "unknown".
        """
        skill = CTISkill(auto_load_threatfox=False)
        result = skill.execute(indicator="10.0.0.53", indicator_type="ipv4")

        assert not result.success, "No CTI source should return failure"
        assert result.data is None, "No data should be returned on failure"
        assert "source" in result.error.lower() or "configured" in result.error.lower(), \
            f"Error should mention source configuration: {result.error}"

    def test_cti_rejects_hostname_indicator(self):
        """
        Test: hostname indicator type → FAIL validation

        hostname is NOT a supported CTI IOC type.
        Even with a fixture present, validation should reject hostname.
        """
        # Fixture exists but should NOT bypass input contract
        skill = CTISkill(
            mock_data={"WS001": {"reputation": "malicious"}},
            auto_load_threatfox=False
        )
        result = skill.execute(indicator="WS001", indicator_type="hostname")

        assert not result.success, "hostname type should fail validation"
        assert "hostname" in result.error.lower() or "indicator_type" in result.error.lower(), \
            f"Error should mention invalid indicator_type: {result.error}"

    def test_cti_rejects_hostname_auto_detected(self):
        """
        Test: Auto-detected hostname format → FAIL

        Strings that look like hostnames (no dots, no valid IP) should not
        be accepted even if auto-detection marks them as "unknown" type.
        """
        skill = CTISkill(auto_load_threatfox=False)

        # These should fail validation (not just return unknown reputation)
        for indicator in ["WS001", "WS023", "WORKSTATION-01", "DESKTOP-PC"]:
            result = skill.execute(indicator=indicator)
            assert not result.success, \
                f"'{indicator}' should fail validation (not unknown type)"
            assert "indicator_type" in result.error.lower() or "invalid" in result.error.lower(), \
                f"Error should indicate invalid type: {result.error}"

    def test_cti_configured_source_no_match_returns_unknown(self):
        """
        Test: Configured source + IOC not in data → SUCCESS / UNKNOWN

        This is the key distinction from test_cti_without_source_fails_closed.
        When a source IS configured but the specific IOC is not found,
        we return a valid CTI result with reputation=unknown.
        """
        skill = CTISkill(
            mock_data={
                "1.1.1.1": {"reputation": "benign", "confidence": "high"}
            },
            auto_load_threatfox=False
        )
        result = skill.execute(indicator="8.8.8.8", indicator_type="ipv4")

        assert result.success, "Configured source with no match should succeed"
        assert result.data is not None, "Should return data on success"
        assert result.data["reputation"] == "unknown", \
            "No match should return reputation=unknown"
        assert result.data["confidence"] == "low", \
            "Unknown reputation should have low confidence"

    def test_cti_valid_fixture_match_succeeds(self):
        """
        Test: Configured source + IOC matched → SUCCESS

        Valid match returns actual CTI data.
        """
        skill = CTISkill(
            mock_data={
                "185.220.101.45": {
                    "reputation": "malicious",
                    "confidence": "high",
                    "related_malware": ["Cobalt Strike"]
                }
            },
            auto_load_threatfox=False
        )
        result = skill.execute(indicator="185.220.101.45", indicator_type="ipv4")

        assert result.success, "Matched IOC should succeed"
        assert result.data["reputation"] == "malicious"
        assert result.data["confidence"] == "high"
        assert "Cobalt Strike" in result.data["related_malware"]

    def test_cti_malformed_domain_fails_validation(self):
        """
        Test: Malformed input → FAIL validation

        SQL injection style inputs should fail validation,
        not be silently converted to unknown.
        """
        skill = CTISkill(auto_load_threatfox=False)

        malicious_inputs = [
            "example.com'; DROP TABLE users;--",
            "test.com UNION SELECT * FROM passwords",
            "http://evil.com/<script>alert(1)</script>",
        ]

        for inp in malicious_inputs:
            result = skill.execute(indicator=inp)
            assert not result.success, \
                f"Malicious input '{inp[:30]}...' should fail validation"
            assert result.data is None, \
                "No data should be returned on validation failure"

    def test_cti_empty_mock_data_is_no_source(self):
        """
        Test: Empty mock_data {} → No source configured → FAIL

        An empty mock_data dict should be treated as "no source configured",
        not as an empty source that returns unknown for everything.
        """
        skill = CTISkill(mock_data={}, auto_load_threatfox=False)
        result = skill.execute(indicator="10.0.0.53", indicator_type="ipv4")

        assert not result.success, "Empty mock_data should be treated as no source"
        assert "source" in result.error.lower() or "configured" in result.error.lower()


class TestCTIIndicatorValidation:
    """Tests for IOC format validation."""

    def test_valid_ipv4_passes(self):
        """Valid IPv4 should pass validation."""
        skill = CTISkill(auto_load_threatfox=False)
        is_valid, error = skill.validate_input(indicator="192.168.1.1", indicator_type="ipv4")
        assert is_valid
        assert error is None

    def test_invalid_ipv4_fails(self):
        """Invalid IPv4 should fail validation."""
        skill = CTISkill(auto_load_threatfox=False)
        # All octets out of valid range
        is_valid, error = skill.validate_input(indicator="999.999.999.999", indicator_type="ipv4")
        assert not is_valid
        assert error is not None

    def test_valid_domain_passes(self):
        """Valid domain should pass validation."""
        skill = CTISkill(auto_load_threatfox=False)
        is_valid, error = skill.validate_input(indicator="example.com", indicator_type="domain")
        assert is_valid

    def test_valid_hash_passes(self):
        """Valid hash should pass validation."""
        skill = CTISkill(auto_load_threatfox=False)
        for hash_val in [
            "d41d8cd98f00b204e9800998ecf8427e",  # MD5
            "da39a3ee5e6b4b0d3255bfef95601890afd80709",  # SHA1
            "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",  # SHA256
        ]:
            is_valid, error = skill.validate_input(indicator=hash_val, indicator_type="hash")
            assert is_valid, f"Hash {hash_val[:8]}... should be valid"

    def test_valid_url_passes(self):
        """Valid URL should pass validation."""
        skill = CTISkill(auto_load_threatfox=False)
        is_valid, error = skill.validate_input(
            indicator="https://example.com/malware.exe",
            indicator_type="url"
        )
        assert is_valid

    def test_missing_indicator_fails(self):
        """Missing indicator should fail validation."""
        skill = CTISkill(auto_load_threatfox=False)
        is_valid, error = skill.validate_input()
        assert not is_valid
        assert "indicator" in error.lower()


class TestCTISourceAvailability:
    """Tests for different CTI source configurations."""

    def test_threatfox_path_loads_successfully(self):
        """Explicit ThreatFox path should load data."""
        skill = CTISkill(threatfox_path="data/threatfox_samples.json")
        assert len(skill.threatfox_data) > 0, "ThreatFox data should be loaded"

    def test_threatfox_not_found_is_no_source(self):
        """Non-existent ThreatFox path should result in no source."""
        skill = CTISkill(threatfox_path="data/nonexistent.json", auto_load_threatfox=False)
        result = skill.execute(indicator="10.0.0.53", indicator_type="ipv4")

        assert not result.success, "Missing ThreatFox file should result in no source"
        assert "source" in result.error.lower() or "configured" in result.error.lower()

    def test_provider_priority_over_threatfox(self):
        """mock_data should take priority over ThreatFox."""
        skill = CTISkill(
            mock_data={"10.0.0.53": {"reputation": "benign"}},
            threatfox_path="data/threatfox_samples.json"
        )
        result = skill.execute(indicator="10.0.0.53", indicator_type="ipv4")

        assert result.success
        assert result.data["reputation"] == "benign", \
            "mock_data should take priority over ThreatFox"
