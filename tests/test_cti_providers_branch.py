from skills.cti_providers import CTIFinding, CTIProvider
from skills.cti_skill import CTISkill
from agent.orchestrator import InvestigationOrchestrator
from agent.provider import MockProvider


class FakeThreatProvider(CTIProvider):
    name = "fake_threat"

    def lookup(self, indicator, indicator_type):
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
    name = "fake_no_match"

    def lookup(self, indicator, indicator_type):
        return CTIFinding(
            source=self.name,
            matched=False,
            provenance={"query_status": "no_result"},
        )


def test_no_provider_is_unknown_not_execution_error():
    skill = CTISkill(providers=[])
    result = skill.execute(indicator="8.8.8.8")
    assert result.success
    assert result.data["reputation"] == "unknown"
    assert result.data["confidence"] == "low"


def test_provider_fusion_preserves_source_and_provenance():
    skill = CTISkill(providers=[FakeThreatProvider(), FakeNoMatchProvider()])
    result = skill.execute(indicator="8.8.8.8")
    assert result.success
    assert result.data["reputation"] == "malicious"
    assert result.data["primary_source"] == "fake_threat"
    assert result.data["provenance"]["matched_sources"] == ["fake_threat"]
    assert "TestRAT" in result.data["related_malware"]


def test_no_match_does_not_become_benign():
    skill = CTISkill(providers=[FakeNoMatchProvider()])
    result = skill.execute(indicator="8.8.4.4")
    assert result.success
    assert result.data["reputation"] == "unknown"


def test_orchestrator_classifies_cti_as_external_intel():
    orch = InvestigationOrchestrator(
        provider=MockProvider(model="cti-evidence-test"),
        cti_mock_data={
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
    )
    case = orch.investigate("1.1.1.1", context="suspicious beacon traffic")
    cti = [ev for ev in case.evidence if ev["source_tool"] == "cti_enrichment"]
    assert cti
    assert all(ev["evidence_class"] == "EXTERNAL_INTEL" for ev in cti)
