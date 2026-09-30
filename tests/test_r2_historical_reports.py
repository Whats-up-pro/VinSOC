"""Audit saved flags without SQL execution or provider access."""
import json
from pathlib import Path

import pytest


def fixture(root):
    for name in ("baseline_e0", "v2_e3"):
        folder = root / name
        folder.mkdir()
        (folder / "a.json").write_text(json.dumps({"case_id": "a", "execution_accurate": True, "syntax_valid": True, "error_category": "OK"}))
        (folder / "report.json").write_text(json.dumps({"case_ids": ["a"], "case_count": 1, "metrics": {"execution_accuracy": "1/1", "syntax_valid": "1/1"}, "total_cost_usd": .01}))


def test_audit_flags_and_cost_limits_without_database_or_provider(tmp_path, monkeypatch):
    from scripts.audit_r2_historical_reports import audit_historical_reports
    fixture(tmp_path)
    def forbidden(*a, **k):
        pytest.fail("auditor used external execution")
    monkeypatch.setattr("duckdb.connect", forbidden)
    monkeypatch.setattr("openai.OpenAI", forbidden)
    result = audit_historical_reports(tmp_path)
    assert result["conditions"]["v2_e3"]["execution_accurate"] == 1
    assert result["cost_unknown"] and not result["official_eligible"]
    assert len(result["artifact_sha256"]) == 4


@pytest.mark.parametrize("duplicate", [False, True])
def test_summary_mismatch_and_duplicate_ids_rejected(tmp_path, duplicate):
    from scripts.audit_r2_historical_reports import audit_historical_reports
    fixture(tmp_path)
    if duplicate:
        (tmp_path / "v2_e3" / "b.json").write_bytes((tmp_path / "v2_e3" / "a.json").read_bytes())
    else:
        p = tmp_path / "v2_e3" / "report.json"
        data = json.loads(p.read_text()); data["metrics"]["execution_accuracy"] = "0/1"
        p.write_text(json.dumps(data))
    with pytest.raises(ValueError, match="HISTORICAL_REPORT_MISMATCH"):
        audit_historical_reports(tmp_path)


def test_receipt_cannot_overwrite(tmp_path):
    from scripts.audit_r2_historical_reports import write_receipt
    p = tmp_path / "receipt.json"; p.write_text("original")
    with pytest.raises(FileExistsError):
        write_receipt(p, {})
    assert p.read_text() == "original"
