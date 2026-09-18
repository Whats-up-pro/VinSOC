from datetime import datetime, timedelta, timezone

from agent.orchestrator import InvestigationOrchestrator
from agent.provider import MockProvider
from skills.network_skill import NetworkSkill


def periodic_mock():
    start = datetime(2026, 9, 18, 8, 0, tzinfo=timezone.utc)
    return {
        "1.2.3.4": {
            "connections": [
                {
                    "timestamp": (start + timedelta(seconds=i * 60)).isoformat(),
                    "src": "10.0.0.5",
                    "dst": "1.2.3.4",
                    "dst_port": 443,
                    "protocol": "TCP",
                    "action": "ALLOW",
                    "bytes_out": 100,
                    "bytes_in": 20,
                }
                for i in range(6)
            ]
        }
    }


def test_network_skill_emits_observed_and_derived_items():
    skill = NetworkSkill(mock_data=periodic_mock())
    result = skill.execute(
        indicator="1.2.3.4",
        time_range={
            "start": "2026-09-18T07:00:00+00:00",
            "end": "2026-09-18T10:00:00+00:00",
        },
    )
    assert result.success
    classes = {item["evidence_class"] for item in result.data["evidence_items"]}
    assert "OBSERVED" in classes
    assert "DERIVED" in classes
    assert not any(p["pattern"] == "normal" for p in result.data["patterns_detected"])


def test_orchestrator_resolves_derived_to_observed_evidence_ids():
    orch = InvestigationOrchestrator(
        provider=MockProvider(model="network-v2-test"),
        network_mock_data=periodic_mock(),
        cti_mock_data={
            "1.2.3.4": {
                "reputation": "unknown",
                "confidence": "low",
                "related_actors": [],
                "related_malware": [],
                "mitre_techniques": [],
                "sources": [],
                "observed_evidence": [],
            }
        },
    )
    case = orch.investigate("1.2.3.4", context="suspicious periodic traffic")
    derived = [
        ev for ev in case.evidence
        if ev["source_tool"] == "network_investigation"
        and ev["evidence_class"] == "DERIVED"
    ]
    observed_ids = {
        ev["evidence_id"] for ev in case.evidence
        if ev["source_tool"] == "network_investigation"
        and ev["evidence_class"] == "OBSERVED"
    }
    assert derived
    assert any(set(ev["related_evidence_ids"]) & observed_ids for ev in derived)


def test_large_transfer_does_not_emit_data_exfiltration_pattern():
    skill = NetworkSkill(mock_data={
        "1.2.3.4": {
            "connections": [{
                "timestamp": "2026-09-18T08:00:00+00:00",
                "src": "10.0.0.5",
                "dst": "1.2.3.4",
                "dst_port": 443,
                "protocol": "TCP",
                "action": "ALLOW",
                "bytes_out": 100_000_000,
                "bytes_in": 100,
            }]
        }
    })
    result = skill.execute(
        indicator="1.2.3.4",
        time_range={
            "start": "2026-09-18T07:00:00+00:00",
            "end": "2026-09-18T10:00:00+00:00",
        },
    )
    patterns = [p["pattern"] for p in result.data["patterns_detected"]]
    assert "data_exfiltration" not in patterns
