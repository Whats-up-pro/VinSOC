"""Renderer/parser arithmetic fixtures only, never experiment receipts."""

from pathlib import Path
import json
import pytest
from tests.soc_support import feature
from vinsoc_data.soc_corpus import digest


def test_citation_case_validity_is_independent_of_completion():
    """Metric facts only; no provider responses or experiment receipts."""
    m = feature("evaluation.soc_traces_v1.reporting")
    assert hasattr(m, "citation_case_valid")
    assert not m.citation_case_valid(
        {"technical_valid": True, "citation_references": 0, "unknown_citations": 0}
    )
    assert m.citation_case_valid(
        {"technical_valid": False, "citation_references": 2, "unknown_citations": 0}
    )
    assert not m.citation_case_valid(
        {"technical_valid": True, "citation_references": 2, "unknown_citations": 1}
    )


ROOT = Path(__file__).resolve().parents[1]


def receipt():
    return {
        "scenario_id": "unit",
        "condition": "S0",
        "status": "not_run",
        "input": {"description": "Unit boundary: <script>界</script>"},
        "report": None,
        "model_outputs": [],
        "unit_parser_only": True,
    }


def test_missing_failed_abstained_remain_denominator():
    m = feature("evaluation.soc_traces_v1.reporting")
    inv = json.loads((ROOT / "results/evaluation_v1/soc_traces_v1/inventory.json").read_text())
    r = m.build_suite_report(inv, [], [])
    for c in ("S0", "S1"):
        assert r["conditions"][c]["planned"] == 64 and r["conditions"][c]["not_run"] == 64
    assert r["paired"]["incomplete"] == 64
    assert r["status"] == "not_run"


def test_review_hash_binding():
    m = feature("evaluation.soc_traces_v1.reporting")
    with pytest.raises(ValueError):
        m.validate_review({"receipt_sha256": "foreign"}, receipt=receipt())


def test_render_full_unicode_and_escape(tmp_path):
    m = feature("evaluation.soc_traces_v1.reporting")
    r = receipt()
    r["input"]["description"] += "界" * 3000
    r["receipt_sha256"] = digest(r)
    p = tmp_path / "receipt.json"
    p.write_text(json.dumps(r, ensure_ascii=False))
    out = m.render_case(p, tmp_path / "view")
    text = Path(out["html"]).read_text()
    assert "<script>" not in text and "&lt;script&gt;" in text and "界" * 3000 in text
    assert json.loads(Path(out["json"]).read_text()) == r


def test_no_output_no_success_report(tmp_path):
    m = feature("evaluation.soc_traces_v1.reporting")
    r = receipt()
    r["receipt_sha256"] = digest(r)
    p = tmp_path / "receipt.json"
    p.write_text(json.dumps(r))
    out = m.render_case(p, tmp_path / "view")
    text = Path(out["html"]).read_text()
    assert "not_run" in text and "Chưa có báo cáo model" in text
    assert "risk_rationale" not in text


def test_input_only_citations_separate():
    m = feature("evaluation.soc_traces_v1.reporting")
    r = m.score_record(receipt(), {"label": "malicious", "family": "unit"})
    assert r["tool_citation_validity"] is None and r["input_citations"] == 0 and not r["correct"]


def test_full_model_summary_format_unit_only():
    from tests.test_soc_report_policy import report

    m = feature("evaluation.soc_traces_v1.reporting")
    r = report()
    r["summary"] = "界" * 3000 + "<script>"
    content = "".join(m._format_report(r))
    assert "界" * 3000 in content and "&lt;script&gt;" in content
    assert "<script>" not in content


def test_invalid_raw_citations_count_unit_only():
    m = feature("evaluation.soc_traces_v1.reporting")
    r = receipt()
    r["status"] = "failed"
    r["model_outputs"] = [{"message": {"content": json.dumps({"evidence_ids": ["foreign-id"]})}}]
    s = m.score_record(r, {"label": "malicious", "family": "unit"})
    assert s["citation_validity"] == 0 and s["unknown_citations"] == 1 and not s["correct"]


def test_missing_demos_remain_visible(tmp_path):
    m = feature("evaluation.soc_traces_v1.reporting")
    inv = json.loads((ROOT / "results/evaluation_v1/soc_traces_v1/inventory.json").read_text())
    selection = json.loads(
        (ROOT / "results/evaluation_v1/soc_traces_v1/demo_selection.json").read_text()
    )
    summary = m.build_suite_report(inv, [], [])
    page = Path(m.render_suite(summary, demo_ids=selection["ids"], output_dir=tmp_path)).read_text()
    for scenario in selection["ids"]:
        assert scenario in page
    assert "not_run" in page
