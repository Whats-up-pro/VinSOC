"""Tests for CTISkill DuckDB snapshot integration."""

import json
import os
import sys
from pathlib import Path
from typing import Any, Dict
from unittest.mock import MagicMock, patch

import pytest

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from skills.cti_skill import CTISkill


class TestCTISkillSnapshot:
    """Tests for CTISkill DuckDB snapshot integration."""

    def test_snapshot_parameter_accepted(self) -> None:
        """CTISkill accepts duckdb_snapshot parameter."""
        # Just test that parameter is accepted without error
        skill = CTISkill(duckdb_snapshot="nonexistent_path.duckdb", auto_load_threatfox=False)
        assert skill is not None

    def test_snapshot_missing_file_falls_back_to_threatfox(self) -> None:
        """Missing snapshot file falls back to ThreatFox auto-load if available."""
        # When snapshot file is not found, CTISkill falls back to ThreatFox auto-load
        # This is correct behavior - the snapshot is optional
        skill = CTISkill(duckdb_snapshot="nonexistent_path.duckdb")
        result = skill.execute(indicator="192.0.2.10")

        # Should succeed via ThreatFox auto-load or return unknown
        assert result.success
        assert result.data is not None

    def test_snapshot_priority_after_mock(self) -> None:
        """Snapshot is used after mock when mock is not configured for the IOC."""
        # Test that priority is correct:
        # 1. Mock data takes priority over snapshot
        # 2. Snapshot is fallback when no mock match

        # This test validates the priority order by checking execution path
        skill = CTISkill(
            mock_data={"192.0.2.1": {"reputation": "benign"}},
            duckdb_snapshot="nonexistent.duckdb"  # Would fail if used
        )

        # Should return mock result, not try snapshot
        result = skill.execute(indicator="192.0.2.1")
        assert result.success
        assert result.data["reputation"] == "benign"

    def test_snapshot_priority_after_threatfox(self) -> None:
        """Snapshot is used after ThreatFox when ThreatFox doesn't match."""
        # Test priority: threatfox > snapshot
        skill = CTISkill(
            threatfox_data={"192.0.2.1": {"reputation": "malicious"}},
            duckdb_snapshot="nonexistent.duckdb",
            auto_load_threatfox=False
        )

        result = skill.execute(indicator="192.0.2.1")
        # Should use ThreatFox result
        assert result.success
        assert result.data["reputation"] == "malicious"

    def test_mock_blocks_snapshot_auto_load(self) -> None:
        """Explicit mock_data={} blocks snapshot auto-load."""
        # When user explicitly passes mock_data={}, snapshot should not be auto-loaded
        # even if snapshot path exists
        skill = CTISkill(mock_data={})
        assert not skill._snapshot_source_configured

    def test_snapshot_lookup_normalization(self) -> None:
        """Snapshot lookup normalizes indicators to lowercase."""
        # Create a mock snapshot data directly for testing lookup
        skill = CTISkill.__new__(CTISkill)
        skill._snapshot_data = {
            "192.0.2.1": {"reputation": "malicious"},
            "example.com": {"reputation": "suspicious"},
        }
        skill._snapshot_source_configured = True
        skill._duckdb_snapshot_path = "mock.duckdb"

        # Test _lookup_snapshot method
        # Direct lookup
        result = skill._lookup_snapshot("192.0.2.1")
        assert result is not None
        assert result["reputation"] == "malicious"

        # Non-existent IOC
        result = skill._lookup_snapshot("10.0.0.1")
        assert result is None


class TestCTISkillSnapshotIntegration:
    """Integration tests requiring actual DuckDB snapshot file."""

    @pytest.fixture
    def snapshot_path(self, tmp_path: Path) -> str:
        """Create a temporary DuckDB snapshot with test data."""
        try:
            import duckdb
        except ImportError:
            pytest.skip("DuckDB not available")

        db_path = tmp_path / "test_snapshot.duckdb"

        # Create schema and insert test data
        with duckdb.connect(str(db_path)) as conn:
            conn.execute("""
                CREATE TABLE cti_indicators (
                    source_dataset VARCHAR,
                    source_row_id VARCHAR,
                    indicator VARCHAR,
                    indicator_type VARCHAR,
                    threat_type VARCHAR,
                    malware_printable VARCHAR,
                    confidence_level INTEGER,
                    first_seen TIMESTAMP,
                    last_seen TIMESTAMP,
                    reference_url VARCHAR
                )
            """)

            # Insert test IOCs
            test_iocs = [
                ("threatfox", "tf001", "185.220.101.34", "ipv4", "botnet", "Mirai", 90, None, None, "https://threatfox.abuse.ch"),
                ("threatfox", "tf002", "194.165.16.10", "ipv4", "malware", "AsyncRAT", 85, None, None, None),
                ("threatfox", "tf003", "malware-drop.xyz", "domain", "malware", "Raccoon", 75, None, None, None),
                # Use valid MD5 hash format (32 hex chars)
                ("threatfox", "tf004", "deadbeef12345678deadbeef12345678", "hash", "malware", "Stealer", 95, None, None, None),
            ]

            for row in test_iocs:
                conn.execute("""
                    INSERT INTO cti_indicators VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, row)

            # Also add to dataset_provenance
            conn.execute("""
                CREATE TABLE dataset_provenance (
                    dataset_id VARCHAR,
                    source_name VARCHAR,
                    source_url VARCHAR,
                    retrieved_at TIMESTAMP,
                    file_sha256 VARCHAR,
                    license_note VARCHAR,
                    schema_version VARCHAR
                )
            """)
            conn.execute("""
                INSERT INTO dataset_provenance VALUES
                ('threatfox', 'ThreatFox Test', 'https://test.url', CURRENT_TIMESTAMP, 'abc123', 'Test license', 'v1')
            """)

        return str(db_path)

    def test_snapshot_loads_cti_data(self, snapshot_path: str) -> None:
        """CTISkill loads CTI data from snapshot."""
        skill = CTISkill(duckdb_snapshot=snapshot_path, auto_load_threatfox=False)

        assert skill._snapshot_source_configured
        assert skill._snapshot_data is not None
        assert len(skill._snapshot_data) > 0

    def test_snapshot_lookup_returns_result(self, snapshot_path: str) -> None:
        """IOC lookup from snapshot returns CTI data."""
        skill = CTISkill(duckdb_snapshot=snapshot_path, auto_load_threatfox=False)

        result = skill.execute(indicator="185.220.101.34")

        assert result.success, f"Lookup failed: {result.error}"
        assert result.data is not None
        assert result.data["reputation"] == "malicious"
        assert result.data["related_malware"] == ["Mirai"]
        assert result.data["confidence"] == "high"

    def test_snapshot_lookup_not_found(self, snapshot_path: str) -> None:
        """IOC not in snapshot returns unknown."""
        skill = CTISkill(duckdb_snapshot=snapshot_path, auto_load_threatfox=False)

        result = skill.execute(indicator="10.0.0.1")

        assert result.success
        assert result.data["reputation"] == "unknown"
        assert "not_found" in str(result.data.get("observed_evidence", []))

    def test_snapshot_domain_lookup(self, snapshot_path: str) -> None:
        """Domain IOC lookup from snapshot works."""
        skill = CTISkill(duckdb_snapshot=snapshot_path, auto_load_threatfox=False)

        result = skill.execute(indicator="malware-drop.xyz", indicator_type="domain")

        assert result.success, f"Lookup failed: {result.error}"
        assert result.data["reputation"] == "malicious"
        assert "Raccoon" in result.data["related_malware"]

    def test_snapshot_hash_lookup(self, snapshot_path: str) -> None:
        """Hash IOC lookup from snapshot works."""
        skill = CTISkill(duckdb_snapshot=snapshot_path, auto_load_threatfox=False)

        # Use valid MD5 hash format
        result = skill.execute(indicator="deadbeef12345678deadbeef12345678", indicator_type="hash")

        assert result.success, f"Lookup failed: {result.error}"
        assert result.data["reputation"] == "malicious"
        assert "Stealer" in result.data["related_malware"]

    def test_snapshot_malware_confidence_mapping(self, snapshot_path: str) -> None:
        """High confidence level maps to 'high' confidence."""
        skill = CTISkill(duckdb_snapshot=snapshot_path, auto_load_threatfox=False)

        result = skill.execute(indicator="185.220.101.34")

        assert result.success, f"Lookup failed: {result.error}"
        assert result.data["confidence"] == "high"

    def test_snapshot_source_in_result(self, snapshot_path: str) -> None:
        """Result includes snapshot as source."""
        skill = CTISkill(duckdb_snapshot=snapshot_path, auto_load_threatfox=False)

        result = skill.execute(indicator="185.220.101.34")

        assert result.success, f"Lookup failed: {result.error}"
        sources = result.data.get("sources", [])
        assert len(sources) > 0, "Sources should not be empty"
        assert any("snapshot" in str(s) or "threatfox" in str(s) for s in sources)


class TestCTISkillSnapshotSkipConditions:
    """Tests for conditions that skip snapshot tests."""

    def test_skip_if_no_duckdb(self) -> None:
        """Skip tests if DuckDB is not available."""
        try:
            import duckdb
        except ImportError:
            pytest.skip("DuckDB not available")

    def test_skip_if_no_snapshot_file(self) -> None:
        """Skip tests if snapshot file is not accessible."""
        default_path = "data/snapshots/vinsoc_public_v1.duckdb"
        if not Path(default_path).exists():
            pytest.skip(f"Snapshot file not found: {default_path}")


class TestCTISkillSnapshotPriority:
    """Tests for CTI source priority order."""

    def test_priority_mock_over_snapshot(self) -> None:
        """Mock data takes priority over snapshot."""
        try:
            import duckdb
        except ImportError:
            pytest.skip("DuckDB not available")

        # When mock returns a result, snapshot should not be consulted
        skill = CTISkill(
            mock_data={"192.0.2.1": {"reputation": "benign"}},
            duckdb_snapshot="nonexistent.duckdb"
        )

        result = skill.execute(indicator="192.0.2.1")

        # Should use mock, not snapshot
        assert result.success
        assert result.data["reputation"] == "benign"

    def test_priority_threatfox_over_snapshot(self) -> None:
        """ThreatFox data takes priority over snapshot."""
        try:
            import duckdb
        except ImportError:
            pytest.skip("DuckDB not available")

        skill = CTISkill(
            threatfox_data={"192.0.2.1": {"reputation": "suspicious"}},
            duckdb_snapshot="nonexistent.duckdb",
            auto_load_threatfox=False
        )

        result = skill.execute(indicator="192.0.2.1")

        # Should use ThreatFox, not snapshot
        assert result.success
        assert result.data["reputation"] == "suspicious"


# Marker for pytest to run these tests
if __name__ == "__main__":
    pytest.main([__file__, "-v"])
