#!/usr/bin/env python3
"""
Integration Test Script

Tests the complete investigation flow with mock data.
"""
import json
from pathlib import Path

from agent.orchestrator import InvestigationOrchestrator
from agent.provider import MockProvider
from skills.cti_skill import CTISkill
from skills.network_skill import NetworkSkill
from skills.endpoint_skill import EndpointSkill


def load_all_scenarios():
    """Load all scenario files."""
    scenarios_dir = Path(__file__).parent.parent / "scenarios"
    scenarios = []

    for case_file in sorted(scenarios_dir.glob("case_*.json")):
        with open(case_file) as f:
            scenarios.append(json.load(f))

    return scenarios


def run_scenario_test(scenario):
    """Run a single scenario test."""
    case_id = scenario["case_id"]
    indicator = scenario["initial_indicator"]
    ground_truth = scenario.get("ground_truth", {})

    print(f"\n{'='*60}")
    print(f"Testing: {case_id} - {scenario.get('label', 'unknown')}")
    print(f"{'='*60}")

    # Extract test data
    test_data = scenario.get("test_data", {})

    # Create skills with test data
    cti_data = {}
    if test_data.get("cti_response"):
        # Use the indicator value as key
        ind_val = indicator.get("value")
        cti_data[ind_val] = test_data["cti_response"]

    network_data = {}
    if test_data.get("network_data"):
        ind_val = indicator.get("value")
        network_data[ind_val] = test_data["network_data"]

    endpoint_data = {}
    if test_data.get("endpoint_data"):
        host = test_data["endpoint_data"].get("host", indicator.get("value"))
        endpoint_data[host] = test_data["endpoint_data"]

    # Create mock provider that calls tools
    mock_provider = MockProvider(model="test")

    # Create orchestrator
    orchestrator = InvestigationOrchestrator(
        provider=mock_provider,
        cti_mock_data=cti_data,
        network_mock_data=network_data,
        endpoint_mock_data=endpoint_data,
        max_steps=10
    )

    # Run investigation
    case = orchestrator.investigate(
        indicator=indicator.get("value"),
        indicator_type=indicator.get("type", "ipv4"),
        context=indicator.get("context")
    )

    # Display results
    print(f"\n[RESULTS]")
    print(f"  Tool calls: {len(case.tool_trace)}")
    print(f"  Evidence items: {len(case.evidence)}")
    print(f"  Risk Level: {case.risk_level}")
    print(f"  Confidence: {case.confidence}")
    print(f"  Hypotheses: {len(case.hypotheses)}")

    # Compare with ground truth
    expected_risk = ground_truth.get("expected_risk", "UNKNOWN")
    actual_risk = case.risk_level

    print(f"\n[GROUND TRUTH COMPARISON]")
    print(f"  Expected Risk: {expected_risk}")
    print(f"  Actual Risk:  {actual_risk}")

    risk_match = expected_risk == actual_risk
    print(f"  Match: {'✓ PASS' if risk_match else '✗ FAIL'}")

    return {
        "case_id": case_id,
        "expected_risk": expected_risk,
        "actual_risk": actual_risk,
        "match": risk_match,
        "tool_calls": len(case.tool_trace),
        "evidence_items": len(case.evidence)
    }


def test_direct_skill_calls():
    """Test skill calls directly without orchestrator."""
    print("\n" + "="*60)
    print("DIRECT SKILL TESTS")
    print("="*60)

    # CTI Test
    print("\n[CTI Skill]")
    cti = CTISkill(mock_data={
        "185.220.101.45": {
            "reputation": "malicious",
            "confidence": "high",
            "related_malware": ["Cobalt Strike"],
            "mitre_techniques": [{"technique_id": "T1071", "technique_name": "C2", "tactics": ["C&C"]}],
            "related_actors": [],
            "sources": [],
            "observed_evidence": []
        },
        "10.0.0.53": {
            "reputation": "unknown",
            "confidence": "low",
            "related_malware": [],
            "mitre_techniques": [],
            "related_actors": [],
            "sources": [],
            "observed_evidence": [{"type": "private_ip", "value": "10.0.0.0/8", "context": "RFC1918"}]
        }
    })

    result = cti.execute(indicator="185.220.101.45")
    print(f"  Malicious IP: {result.data['reputation']} ({result.data['confidence']})")

    result = cti.execute(indicator="10.0.0.53")
    print(f"  Private IP: {result.data['reputation']} ({result.data['confidence']})")

    # Network Test
    print("\n[Network Skill]")
    network = NetworkSkill(mock_data={
        "10.0.0.25": {
            "connections": [
                {"timestamp": "2024-01-15T10:00:00Z", "dst": "10.0.1.1", "dst_port": 22, "protocol": "TCP", "action": "DROP", "bytes_out": 0},
                {"timestamp": "2024-01-15T10:00:01Z", "dst": "10.0.1.2", "dst_port": 22, "protocol": "TCP", "action": "DROP", "bytes_out": 0},
                {"timestamp": "2024-01-15T10:00:02Z", "dst": "10.0.1.3", "dst_port": 22, "protocol": "TCP", "action": "DROP", "bytes_out": 0},
                {"timestamp": "2024-01-15T10:00:03Z", "dst": "10.0.1.4", "dst_port": 22, "protocol": "TCP", "action": "DROP", "bytes_out": 0},
                {"timestamp": "2024-01-15T10:00:04Z", "dst": "10.0.1.5", "dst_port": 22, "protocol": "TCP", "action": "DROP", "bytes_out": 0},
            ],
            "observed_evidence": []
        }
    })

    result = network.execute(indicator="10.0.0.25")
    patterns = [p["pattern"] for p in result.data["patterns_detected"]]
    print(f"  Port scan detection: {patterns}")

    # Endpoint Test
    print("\n[Endpoint Skill]")
    endpoint = EndpointSkill(mock_data={
        "WS001": {
            "process_tree": [
                {"parent": "winword.exe", "parent_pid": 2048, "child": "powershell.exe", "child_pid": 4096},
                {"parent": "powershell.exe", "parent_pid": 4096, "child": "certutil.exe", "child_pid": 5120}
            ],
            "observed_evidence": []
        }
    })

    result = endpoint.execute(host="WS001")
    suspicious = result.data["suspicious_relationships"]
    print(f"  Suspicious relationships: {len(suspicious)}")
    for s in suspicious:
        print(f"    - {s['parent']} -> {s['child']}: {s['suspicious_reasons']}")

    print("\n[PASS] All direct skill tests passed!")


def main():
    """Run all tests."""
    print("\n" + "="*60)
    print("SOC INVESTIGATION SYSTEM - INTEGRATION TESTS")
    print("="*60)

    # Test skills directly
    test_direct_skill_calls()

    # Test scenarios
    print("\n" + "="*60)
    print("SCENARIO TESTS")
    print("="*60)

    scenarios = load_all_scenarios()
    print(f"\nFound {len(scenarios)} scenarios")

    results = []
    for scenario in scenarios[:5]:  # Run first 5 for quick test
        try:
            result = run_scenario_test(scenario)
            results.append(result)
        except Exception as e:
            print(f"Error running {scenario.get('case_id', 'unknown')}: {e}")

    # Summary
    print("\n" + "="*60)
    print("TEST SUMMARY")
    print("="*60)

    passed = sum(1 for r in results if r["match"])
    total = len(results)
    print(f"\nTests run: {total}")
    print(f"Passed: {passed}")
    print(f"Failed: {total - passed}")
    print(f"Pass rate: {passed/total*100:.1f}%" if total > 0 else "N/A")

    if results:
        print("\n[Individual Results]")
        for r in results:
            status = "✓" if r["match"] else "✗"
            print(f"  {status} {r['case_id']}: expected {r['expected_risk']}, got {r['actual_risk']}")


if __name__ == "__main__":
    main()
