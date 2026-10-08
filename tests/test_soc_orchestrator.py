"""Offline intake and capability boundaries; no fabricated model workflow."""

import pytest
from tests.soc_support import feature, sources, corpus
from agent.orchestrator import InvestigationOrchestrator


def context(corpus):
    m = feature("skills.soc_corpus_skill")
    r = corpus[0]
    return m.SocCorpusContext(
        r, r.scenario_ids("test")[0], "S1", r.metadata()["source_revision"], r.sha256
    )


def test_ioc_missing_or_ambiguous_blocks_without_calls(corpus):
    c = context(corpus)
    o = InvestigationOrchestrator()
    assert hasattr(o, "investigate_alert")
    with pytest.raises(ValueError, match="IOC_"):
        o.investigate_alert(
            {"kind": "ioc", "value": "not-present.invalid", "indicator_type": "domain"},
            soc_context=c,
        )
    ambiguous = c.repository._query(
        "SELECT kind,value FROM ioc_index GROUP BY kind,value HAVING count(DISTINCT scenario_id)>1 LIMIT 1"
    )[0]
    with pytest.raises(ValueError, match="IOC_AMBIGUOUS"):
        o.investigate_alert(
            {"kind": "ioc", "value": ambiguous[1], "indicator_type": ambiguous[0]}, soc_context=c
        )
    assert not o.evidence_store.get_all_evidence()


def test_scope_provider_mismatch_rejected(corpus):
    c = context(corpus)
    o = InvestigationOrchestrator()
    assert hasattr(o, "investigate_alert")
    with pytest.raises(ValueError, match="OFFICIAL_SOC_PROVIDER"):
        o.investigate_alert(
            {"kind": "alert", "alert": c.repository.input_for(c.scenario_id)}, soc_context=c
        )


def test_soc_does_not_use_legacy_triage_or_analysis():
    import inspect

    assert hasattr(InvestigationOrchestrator, "investigate_alert")
    source = inspect.getsource(InvestigationOrchestrator.investigate_alert)
    assert (
        "_analyze_evidence" not in source
        and "triage_alert(" not in source
        and "_execute_tool(" not in source
    )


def test_only_delivered_evidence_registered(corpus):
    c = context(corpus)
    o = InvestigationOrchestrator()
    assert hasattr(o, "_soc_register_rows")
    rows = c.repository.records(c.scenario_id, "events")[:1]
    ids = o._soc_register_rows(
        rows, tool="soc_search_events", native_call_id="unit-native-id", soc_context=c
    )
    assert ids == [rows[0]["source_record_id"]]
    evidence = o.evidence_store.get_all_evidence()
    assert len(evidence) == 1 and evidence[0].linked_from == "unit-native-id"
    with pytest.raises(ValueError):
        o._soc_register_rows(
            [{**rows[0], "provenance": {"scenario_id": "foreign"}}],
            tool="soc_search_events",
            native_call_id="unit",
            soc_context=c,
        )
