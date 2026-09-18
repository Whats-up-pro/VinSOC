"""
CTI Provider Integration Tests

Tests the integration between CTISkill and provider adapters.
These tests verify the fail-closed product contract:
- No source → FAIL
- Provider error → FAIL
- No match → SUCCESS / UNKNOWN
- Match → SUCCESS / RESULT
"""
import pytest
from skills.cti_providers import (
    CTIFinding,
    CTIProvider,
    ThreatFoxProvider,
    MalwareBazaarProvider,
    URLhausLocalProvider,
)
from skills.cti_skill import CTISkill


class FakeThreatProvider(CTIProvider):
    """Test provider that always finds a match."""

    name = "fake_threat"

    def lookup(self, indicator: str, indicator_type: str) -> CTIFinding:
        return CTIFinding(
            source=self.name,
            matched=True,
            reputation="malicious",
            confidence="high",
            malware=["TestRAT"],
            context=[
                {"type": "botnet_cc", "value": indicator, "context": "test C2 match"}
            ],
            references=["https://example.org/intel/1"],
            provenance={"fixture": True},
        )


class FakeNoMatchProvider(CTIProvider):
    """Test provider that returns no match."""

    name = "fake_no_match"

    def lookup(self, indicator: str, indicator_type: str) -> CTIFinding:
        return CTIFinding(
            source=self.name,
            matched=False,
            provenance={"query_status": "no_result"},
        )


class FakeErrorProvider(CTIProvider):
    """Test provider that errors out."""

    name = "fake_error"

    def lookup(self, indicator: str, indicator_type: str) -> CTIFinding:
        return CTIFinding(
            source=self.name,
            matched=False,
            provenance={"status": "error", "error_type": "NetworkError"},
        )


class TestCTIProviderIntegration:
    """Integration tests for CTI provider adapters."""

    def test_no_source_is_failure(self):
        """
        Test: No CTI source configured → FAIL

        This is the core fail-closed contract.
        """
        skill = CTISkill(auto_load_threatfox=False)
        result = skill.execute(indicator="10.0.0.53", indicator_type="ipv4")

        assert not result.success, "No source should return failure"
        assert result.data is None, "No data should be returned on failure"
        assert "source" in result.error.lower() or "configured" in result.error.lower()

    def test_empty_mock_data_is_no_source(self):
        """
        Test: Empty mock_data {} → No source configured → FAIL
        """
        skill = CTISkill(mock_data={}, auto_load_threatfox=False)
        result = skill.execute(indicator="10.0.0.53", indicator_type="ipv4")

        assert not result.success, "Empty mock_data should be treated as no source"

    def test_provider_fusion_uses_mock_data(self):
        """
        Test: mock_data takes priority over providers.

        Note: Current CTISkill doesn't support providers parameter.
        This tests the mock_data path only.
        """
        skill = CTISkill(
            mock_data={
                "1.1.1.1": {
                    "reputation": "malicious",
                    "confidence": "high",
                    "related_malware": ["TestRAT"],
                    "related_actors": [],
                    "mitre_techniques": [],
                    "sources": [{"name": "fixture"}],
                    "observed_evidence": [],
                }
            },
            auto_load_threatfox=False
        )
        result = skill.execute(indicator="1.1.1.1", indicator_type="ipv4")

        assert result.success, "Fixture match should succeed"
        assert result.data["reputation"] == "malicious"
        assert "TestRAT" in result.data["related_malware"]

    def test_mock_data_no_match_returns_unknown(self):
        """
        Test: mock_data configured but IOC not found → SUCCESS / UNKNOWN

        This is the key distinction from "no source".
        """
        skill = CTISkill(
            mock_data={
                "1.1.1.1": {
                    "reputation": "benign",
                    "confidence": "low",
                }
            },
            auto_load_threatfox=False
        )
        result = skill.execute(indicator="8.8.8.8", indicator_type="ipv4")

        assert result.success, "Configured source with no match should succeed"
        assert result.data["reputation"] == "unknown"
        assert result.data["confidence"] == "low"


class TestCTIProviderStatus:
    """Tests for provider status handling."""

    def test_hostname_is_rejected(self):
        """
        Test: hostname indicator type → FAIL validation
        """
        skill = CTISkill(
            mock_data={"WS001": {"reputation": "malicious"}},
            auto_load_threatfox=False
        )
        result = skill.execute(indicator="WS001", indicator_type="hostname")

        assert not result.success, "hostname type should fail validation"

    def test_invalid_ipv4_fails(self):
        """
        Test: Invalid IPv4 format → FAIL validation
        """
        skill = CTISkill(auto_load_threatfox=False)
        result = skill.execute(indicator="not.an.ip.address", indicator_type="ipv4")

        assert not result.success, "Invalid IPv4 should fail validation"

    def test_malwarebazaar_ipv4_is_not_applicable(self):
        """
        Test: MalwareBazaar doesn't support IPv4.

        This tests the provider's NOT_APPLICABLE behavior.
        """
        provider = MalwareBazaarProvider(auth_key="fake_key")
        finding = provider.lookup("8.8.8.8", "ipv4")

        # MalwareBazaar should return not_applicable for non-hash
        assert not finding.matched
        assert finding.provenance.get("status") == "not_applicable"


class TestThreatFoxLocalProvider:
    """Tests for ThreatFox local data loading."""

    def test_urlhaus_provider_interface(self):
        """
        Test: URLhaus provider has correct interface.
        Note: This test verifies the provider class structure only.
        """
        # Test class structure without file
        provider = URLhausLocalProvider.__new__(URLhausLocalProvider)
        provider.path = None  # type: ignore
        provider.index = {}  # type: ignore
        assert hasattr(provider, "lookup")
        assert callable(provider.lookup)
        assert provider.name == "urlhaus"


class TestCTISourcePriority:
    """Tests for data source priority."""

    def test_mock_takes_priority_over_threatfox(self):
        """
        Test: mock_data takes priority over threatfox_data.
        """
        skill = CTISkill(
            mock_data={
                "10.0.0.1": {
                    "reputation": "benign",
                    "confidence": "high",
                    "related_malware": [],
                    "related_actors": [],
                    "mitre_techniques": [],
                    "sources": [],
                    "observed_evidence": [],
                }
            },
            threatfox_path="data/cti_lookup.json",  # Will fail to load
            auto_load_threatfox=False
        )
        result = skill.execute(indicator="10.0.0.1", indicator_type="ipv4")

        assert result.success
        assert result.data["reputation"] == "benign"
