"""Pure parser fixtures; these are not model predictions or demo evidence."""

import copy
import json
import pytest
from tests.soc_support import feature


def report():
    return {
        "summary": "Unit parser input",
        "verdict": "malicious",
        "hypotheses": [],
        "findings": [{"claim": "Unit claim", "evidence_ids": ["input-id"], "kind": "observed"}],
        "risk_level": "LOW",
        "risk_rationale": "Unit rationale",
        "confidence": "LOW",
        "confidence_rationale": "Unit rationale",
        "limitations": [],
        "recommended_actions": [],
        "evidence_ids": ["input-id"],
    }


def test_all_report_fields_required():
    m = feature("agent.soc_investigation_policy")
    r = report()
    for k in r:
        changed = copy.deepcopy(r)
        del changed[k]
        with pytest.raises(ValueError):
            m.validate_report(changed, delivered_ids={"input-id"})


def test_foreign_or_undelivered_citation_fails():
    m = feature("agent.soc_investigation_policy")
    with pytest.raises(ValueError):
        m.validate_report(report(), delivered_ids={"other-case"})


def test_union_of_citations_exact():
    m = feature("agent.soc_investigation_policy")
    r = report()
    r["evidence_ids"] = []
    with pytest.raises(ValueError):
        m.validate_report(r, delivered_ids={"input-id"})
    r = report()
    r["recommended_actions"] = [
        {
            "action": "Unit suggestion",
            "rationale": "Unit rationale",
            "evidence_ids": ["undelivered"],
        }
    ]
    with pytest.raises(ValueError):
        m.validate_report(r, delivered_ids={"input-id"})


def test_insufficient_requires_limitation():
    m = feature("agent.soc_investigation_policy")
    r = report()
    r["verdict"] = "insufficient_evidence"
    with pytest.raises(ValueError):
        m.validate_report(r, delivered_ids={"input-id"})
    r["limitations"] = ["Unit gap"]
    assert (
        m.validate_report(r, delivered_ids={"input-id"})["prose_semantics_machine_verified"]
        is False
    )


def test_strict_tool_schema_no_scope_argument():
    m = feature("agent.soc_investigation_policy")
    p = m.SocInvestigationPolicy(None)
    for tool in p.tool_schemas():
        schema = tool["function"]["parameters"]
        assert schema["additionalProperties"] is False
        assert set(schema["required"]) == set(schema["properties"])
        assert not {"scenario_id", "sql"} & set(schema["properties"])
    from agent.evidence import EvidenceStore

    for content in ("```json\n{}\n```", "{"):
        with pytest.raises(ValueError):
            p.parse_final_response(content, EvidenceStore())
