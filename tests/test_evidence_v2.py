from agent.evidence import Evidence, EvidenceStore


def test_legacy_evidence_defaults_to_observed():
    ev = Evidence(
        evidence_id="ev_1",
        source_tool="network_investigation",
        type="network_result",
        data={"x": 1},
        collected_at="2026-09-18T00:00:00Z",
    )
    assert ev.evidence_class == "OBSERVED"
    assert ev.to_dict()["source_name"] == "network_investigation"


def test_derived_evidence_keeps_parent_links_and_provenance():
    store = EvidenceStore()
    ev = store.add_evidence(
        source_tool="network_investigation",
        evidence_type="periodic_beaconing",
        data={"interval_mean": 60.0, "interval_std": 1.0},
        evidence_class="DERIVED",
        source_name="beaconing_rule_v1",
        confidence="high",
        provenance={"algorithm": "periodicity_rule"},
        related_evidence_ids=["ev_raw_1", "ev_raw_2"],
    )
    payload = ev.to_dict()
    assert payload["evidence_class"] == "DERIVED"
    assert payload["related_evidence_ids"] == ["ev_raw_1", "ev_raw_2"]
    assert payload["provenance"]["algorithm"] == "periodicity_rule"


def test_invalid_evidence_class_is_rejected():
    try:
        Evidence(
            evidence_id="ev_bad",
            source_tool="x",
            type="x",
            data={},
            collected_at="2026-09-18T00:00:00Z",
            evidence_class="HYPOTHESIS",
        )
        assert False, "Expected ValueError"
    except ValueError:
        pass
