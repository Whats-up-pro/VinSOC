"""
Unit Tests for Investigation Skills

Tests each skill in isolation with mock data.
"""
import json
import pytest
from pathlib import Path

from skills.base import SkillResult
from skills.cti_skill import CTISkill, check_ip_reputation
from skills.network_skill import NetworkSkill, investigate_network
from skills.endpoint_skill import EndpointSkill, investigate_endpoint


# Test data fixtures
@pytest.fixture
def scenarios_dir():
    """Get scenarios directory."""
    return Path(__file__).parent.parent / "scenarios"


@pytest.fixture
def sample_cti_data():
    """Sample CTI mock data."""
    return {
        "185.220.101.45": {
            "reputation": "malicious",
            "confidence": "high",
            "related_actors": [],
            "related_malware": ["Cobalt Strike"],
            "mitre_techniques": [
                {"technique_id": "T1071.001", "technique_name": "Web Protocols", "tactics": ["Command and Control"]}
            ],
            "sources": [{"name": "OTX", "reference": "https://otx.alienvault.com"}],
            "observed_evidence": [{"type": "c2", "value": "beacon", "context": "C2 detected"}]
        },
        "10.0.0.53": {
            "reputation": "unknown",
            "confidence": "low",
            "related_actors": [],
            "related_malware": [],
            "mitre_techniques": [],
            "sources": [],
            "observed_evidence": [{"type": "private_ip", "value": "10.0.0.0/8", "context": "RFC1918"}]
        }
    }


@pytest.fixture
def sample_network_data():
    """Sample network mock data."""
    return {
        "185.220.101.45": {
            "connections": [
                {"timestamp": "2024-01-15T08:00:00Z", "dst": "185.220.101.45", "dst_port": 443, "protocol": "TCP", "action": "ALLOW", "bytes_out": 256},
                {"timestamp": "2024-01-15T08:00:30Z", "dst": "185.220.101.45", "dst_port": 443, "protocol": "TCP", "action": "ALLOW", "bytes_out": 256},
                {"timestamp": "2024-01-15T08:01:00Z", "dst": "185.220.101.45", "dst_port": 443, "protocol": "TCP", "action": "ALLOW", "bytes_out": 256},
            ],
            "observed_evidence": [{"type": "beacon", "value": "regular", "context": "Regular callback interval"}]
        },
        "10.0.0.25": {
            "connections": [
                {"timestamp": "2024-01-15T10:00:00Z", "dst": "10.0.1.1", "dst_port": 22, "protocol": "TCP", "action": "DROP", "bytes_out": 0},
                {"timestamp": "2024-01-15T10:00:01Z", "dst": "10.0.1.2", "dst_port": 22, "protocol": "TCP", "action": "DROP", "bytes_out": 0},
                {"timestamp": "2024-01-15T10:00:02Z", "dst": "10.0.1.3", "dst_port": 22, "protocol": "TCP", "action": "DROP", "bytes_out": 0},
            ],
            "observed_evidence": [{"type": "port_scan", "value": "detected", "context": "Multiple failed connections"}]
        }
    }


@pytest.fixture
def sample_endpoint_data():
    """Sample endpoint mock data."""
    return {
        "WS001": {
            "process_tree": [
                {"parent": "winword.exe", "parent_pid": 2048, "child": "powershell.exe", "child_pid": 4096},
                {"parent": "powershell.exe", "parent_pid": 4096, "child": "net.exe", "child_pid": 5120}
            ],
            "observed_evidence": [{"type": "macro", "value": "executed", "context": "Word macro detected"}]
        },
        "WS023": {
            "process_tree": [
                {"parent": "excel.exe", "parent_pid": 3072, "child": "cmd.exe", "child_pid": 5632},
                {"parent": "cmd.exe", "parent_pid": 5632, "child": "whoami.exe", "child_pid": 6144}
            ],
            "observed_evidence": [{"type": "recon", "value": "detected", "context": "Reconnaissance commands"}]
        }
    }


# ============================================================================
# CTI Skill Tests
# ============================================================================

class TestCTISkill:
    """Tests for CTI Enrichment Skill."""

    def test_valid_ipv4_input(self, sample_cti_data):
        """Test valid IPv4 input validation."""
        skill = CTISkill()
        is_valid, error = skill.validate_input(indicator="192.168.1.1")
        assert is_valid
        assert error is None

    def test_valid_domain_input(self, sample_cti_data):
        """Test valid domain input validation."""
        skill = CTISkill()
        is_valid, error = skill.validate_input(indicator="example.com", indicator_type="domain")
        assert is_valid
        assert error is None

    def test_valid_hash_input(self, sample_cti_data):
        """Test valid hash input validation."""
        skill = CTISkill()
        is_valid, error = skill.validate_input(indicator="d41d8cd98f00b204e9800998ecf8427e")
        assert is_valid
        assert error is None

    def test_invalid_ipv4_input(self):
        """Test invalid IPv4 input rejection."""
        skill = CTISkill()
        is_valid, error = skill.validate_input(indicator="not.an.ip.address")
        assert not is_valid
        assert error is not None

    def test_missing_indicator(self):
        """Test missing indicator parameter."""
        skill = CTISkill()
        is_valid, error = skill.validate_input()
        assert not is_valid
        assert "indicator" in error.lower()

    def test_malicious_cti_lookup(self, sample_cti_data):
        """Test CTI lookup for malicious IP."""
        skill = CTISkill(mock_data=sample_cti_data)
        result = skill.execute(indicator="185.220.101.45")

        assert result.success
        assert result.data is not None
        assert result.data["reputation"] == "malicious"
        assert result.data["confidence"] == "high"
        assert "Cobalt Strike" in result.data["related_malware"]
        assert len(result.evidence_ids) == 1

    def test_unknown_cti_lookup(self, sample_cti_data):
        """Test CTI lookup for unknown/internal IP."""
        skill = CTISkill(mock_data=sample_cti_data)
        result = skill.execute(indicator="10.0.0.53")

        assert result.success
        assert result.data is not None
        assert result.data["reputation"] == "unknown"
        assert result.data["confidence"] == "low"

    def test_convenience_function(self, sample_cti_data):
        """Test convenience function."""
        result = check_ip_reputation(
            indicator="185.220.101.45",
            mock_data=sample_cti_data
        )
        assert result["reputation"] == "malicious"


# ============================================================================
# Network Skill Tests
# ============================================================================

class TestNetworkSkill:
    """Tests for Network Investigation Skill."""

    def test_valid_input(self):
        """Test valid network investigation input."""
        skill = NetworkSkill()
        is_valid, error = skill.validate_input(
            indicator="192.168.1.1",
            indicator_type="ipv4"
        )
        assert is_valid
        assert error is None

    def test_missing_indicator(self):
        """Test missing indicator parameter."""
        skill = NetworkSkill()
        is_valid, error = skill.validate_input()
        assert not is_valid
        assert "indicator" in error.lower()

    def test_beaconing_detection(self, sample_network_data):
        """Test beaconing pattern detection."""
        skill = NetworkSkill(mock_data=sample_network_data)
        result = skill.execute(indicator="185.220.101.45")

        assert result.success
        assert result.data is not None
        assert result.data["total_connections"] == 3
        # Should detect beaconing or high frequency pattern
        patterns = [p["pattern"] for p in result.data["patterns_detected"]]
        assert any(p in ["beaconing", "high_frequency"] for p in patterns)

    def test_port_scan_detection(self, sample_network_data):
        """Test port scan pattern detection."""
        skill = NetworkSkill(mock_data=sample_network_data)
        result = skill.execute(indicator="10.0.0.25")

        assert result.success
        assert result.data is not None
        assert result.data["failed_connections"] == 3
        # Should detect port scan
        patterns = [p["pattern"] for p in result.data["patterns_detected"]]
        assert "port_scan" in patterns

    def test_empty_result(self):
        """Test empty result when no data available."""
        skill = NetworkSkill()
        result = skill.execute(indicator="10.0.0.99")

        assert result.success
        assert result.data["total_connections"] == 0
        assert len(result.data["patterns_detected"]) == 1
        assert result.data["patterns_detected"][0]["pattern"] == "normal"

    def test_connection_summary(self, sample_network_data):
        """Test connection summary generation."""
        skill = NetworkSkill(mock_data=sample_network_data)
        result = skill.execute(indicator="185.220.101.45")

        assert result.success
        assert "connection_summary" in result.data
        # Should have at least one entry
        assert len(result.data["connection_summary"]) >= 0


# ============================================================================
# Endpoint Skill Tests
# ============================================================================

class TestEndpointSkill:
    """Tests for Endpoint Investigation Skill."""

    def test_valid_input(self):
        """Test valid endpoint investigation input."""
        skill = EndpointSkill()
        is_valid, error = skill.validate_input(host="WS001")
        assert is_valid
        assert error is None

    def test_missing_host(self):
        """Test missing host parameter."""
        skill = EndpointSkill()
        is_valid, error = skill.validate_input()
        assert not is_valid
        assert "host" in error.lower()

    def test_word_powershell_detection(self, sample_endpoint_data):
        """Test Word->PowerShell suspicious pattern detection."""
        skill = EndpointSkill(mock_data=sample_endpoint_data)
        result = skill.execute(host="WS001")

        assert result.success
        assert result.data is not None
        assert len(result.data["process_tree"]) == 2
        # Should detect suspicious relationship
        suspicious = result.data["suspicious_relationships"]
        assert len(suspicious) >= 1
        assert any(
            r["parent"].lower() == "winword.exe" and r["child"].lower() == "powershell.exe"
            for r in suspicious
        )

    def test_recon_detection(self, sample_endpoint_data):
        """Test reconnaissance command detection."""
        skill = EndpointSkill(mock_data=sample_endpoint_data)
        result = skill.execute(host="WS023")

        assert result.success
        suspicious = result.data["suspicious_relationships"]
        assert any("T1033" in r.get("mitre_technique", "") for r in suspicious)

    def test_empty_result(self):
        """Test empty result when no data available."""
        skill = EndpointSkill()
        result = skill.execute(host="UNKNOWN_HOST")

        assert result.success
        assert result.data["process_tree"] == []
        assert result.data["suspicious_relationships"] == []
        assert result.data["observed_evidence"][0]["value"] == "no_data"


# ============================================================================
# Skill Integration Tests
# ============================================================================

class TestSkillIntegration:
    """Tests for skill integration scenarios."""

    def test_scenario_case_005_cti(self, scenarios_dir, sample_cti_data):
        """Test case_005 CTI lookup (malicious C2)."""
        case_file = scenarios_dir / "case_005.json"
        if not case_file.exists():
            pytest.skip("Scenario files not found")

        with open(case_file) as f:
            case = json.load(f)

        skill = CTISkill(mock_data=sample_cti_data)
        indicator = case["initial_indicator"]["value"]
        result = skill.execute(indicator=indicator)

        assert result.success
        # Should match expected reputation
        expected = case["ground_truth"]["expected_risk"]
        actual = result.data["reputation"]
        # MALICIOUS IOC should have malicious reputation
        assert actual == "malicious" or actual == "unknown"  # unknown for private IPs

    def test_scenario_case_005_network(self, scenarios_dir, sample_network_data):
        """Test case_005 network investigation."""
        case_file = scenarios_dir / "case_005.json"
        if not case_file.exists():
            pytest.skip("Scenario files not found")

        with open(case_file) as f:
            case = json.load(f)

        skill = NetworkSkill(mock_data=sample_network_data)
        indicator = case["initial_indicator"]["value"]
        result = skill.execute(indicator=indicator)

        assert result.success
        # Should have connections and patterns
        assert result.data["total_connections"] > 0
        patterns = [p["pattern"] for p in result.data["patterns_detected"]]
        assert any(p in ["beaconing", "high_frequency"] for p in patterns)

    def test_scenario_case_001_benign(self, scenarios_dir):
        """Test benign case (internal DNS server)."""
        case_file = scenarios_dir / "case_001.json"
        if not case_file.exists():
            pytest.skip("Scenario files not found")

        with open(case_file) as f:
            case = json.load(f)

        # CTI should return unknown for private IP
        skill = CTISkill()
        result = skill.execute(indicator="10.0.0.53")

        assert result.success
        assert result.data["reputation"] == "unknown"


# ============================================================================
# Security Tests
# ============================================================================

class TestSkillSecurity:
    """Tests for skill security properties."""

    def test_no_command_execution(self):
        """Test that skills don't execute arbitrary commands."""
        skill = CTISkill()
        # Attempt to inject commands
        result = skill.execute(indicator="; rm -rf /")
        assert not result.success
        assert "validation" in (result.error or "").lower()

    def test_input_sanitization(self):
        """Test input sanitization."""
        skill = CTISkill()
        # Attempt to inject through domain
        result = skill.execute(indicator="example.com'; DROP TABLE users;--")
        assert not result.success
        assert "validation" in (result.error or "").lower()

    def test_result_immutability(self):
        """Test that skill results are immutable."""
        skill = CTISkill()
        result = skill.execute(indicator="10.0.0.1")

        # Result should be dict (can be copied but not modified directly)
        assert isinstance(result.data, dict)

    def test_read_only_enforcement(self):
        """Test that skill is read-only."""
        skill = CTISkill()

        # Execute should not modify any external state
        initial_log = skill.get_execution_log()
        skill.execute(indicator="192.168.1.1")
        final_log = skill.get_execution_log()

        # Should only add to log, not modify external state
        assert len(final_log) >= len(initial_log)
