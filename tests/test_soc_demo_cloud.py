"""One-case real-demo contract; tests never create a model client."""

import json
from pathlib import Path

import pytest


def test_demo_release_is_locked_to_preselected_case_and_one_dollar():
    from evaluation.soc_traces_v1.demo import build_demo_release, validate_demo_release

    root = Path(__file__).resolve().parents[1]
    artifacts = root / "results/evaluation_v1/soc_traces_v1"
    receipt = json.loads((root / "data/soc_traces_v1/final/corpus_receipt.json").read_text())
    inventory = json.loads((artifacts / "inventory.json").read_text())
    demo = json.loads((artifacts / "demo_selection.json").read_text())
    release = build_demo_release(
        identities={
            "inventory": inventory,
            "demo_selection": demo,
            "corpus_receipt": receipt,
        },
        implementation_sha="a" * 40,
        api_key_sha256="b" * 64,
        operator="Thiên Vũ Hiếu",
        authorization_statement="Run one real E2E demonstration before human source review.",
    )

    checked = validate_demo_release(release, validate_runtime=False)
    assert checked["case_id"] == "SCT-087094"
    assert checked["condition"] == "S1"
    assert checked["budget_limit_usd"] == 1.0
    assert checked["request_limit"] == 6
    assert checked["source_review_status"] == "deferred_after_demo"
    assert release["caps"] == {
        "S0": 1,
        "S1": 6,
        "suite": 6,
        "tool_calls": 5,
        "output_tokens": 2000,
        "request_bytes": 128000,
        "messages": 16,
    }


def test_demo_release_rejects_case_not_in_preselected_demo():
    from evaluation.soc_traces_v1.demo import build_demo_release, validate_demo_release

    root = Path(__file__).resolve().parents[1]
    artifacts = root / "results/evaluation_v1/soc_traces_v1"
    receipt = json.loads((root / "data/soc_traces_v1/final/corpus_receipt.json").read_text())
    inventory = json.loads((artifacts / "inventory.json").read_text())
    demo = json.loads((artifacts / "demo_selection.json").read_text())
    release = build_demo_release(
        identities={
            "inventory": inventory,
            "demo_selection": demo,
            "corpus_receipt": receipt,
        },
        implementation_sha="a" * 40,
        api_key_sha256="b" * 64,
        operator="Thiên Vũ Hiếu",
        authorization_statement="Run one real E2E demonstration before human source review.",
    )
    release["demo"]["case_id"] = next(
        row["scenario_id"]
        for row in inventory["cases"]
        if row["scenario_id"] not in demo["ids"]
    )

    with pytest.raises(ValueError, match="SOC_DEMO_CASE_NOT_PRESELECTED"):
        validate_demo_release(release, validate_runtime=False)


def test_demo_journal_allows_only_locked_s1_case(tmp_path):
    import os

    from evaluation.soc_traces_v1.demo import SocDemoJournal
    from evaluation.soc_traces_v1.accounting import atomic_json

    release = {
        "release_sha256": "c" * 64,
        "case_ids": ["SCT-087094"],
        "demo": {"case_id": "SCT-087094", "condition": "S1", "request_limit": 6},
    }
    checked = {
        "evidence": {
            "account": {"api_key_sha256": "b" * 64},
            "pricing": {"input_usd_per_million": 0.4, "output_usd_per_million": 1.6},
            "request_bound": {"framing_token_reserve": 8192},
            "budget": {"limit_usd": 1.0},
        }
    }
    ledger = tmp_path / "ledger.json"
    atomic_json(
        ledger,
        {
            "release_sha256": "c" * 64,
            "owner_pid": os.getpid(),
            "status": "running",
            "unknown_cost": False,
            "reservations": [],
        },
    )
    journal = SocDemoJournal(ledger, release, checked)

    journal.ensure_case_capacity("SCT-087094", "S1")
    with pytest.raises(ValueError, match="SOC_DEMO_SCOPE_MISMATCH"):
        journal.ensure_case_capacity("SCT-087094", "S0")
    with pytest.raises(ValueError, match="SOC_DEMO_SCOPE_MISMATCH"):
        journal.ensure_case_capacity("SCT-004523", "S1")


def test_demo_workflow_uses_real_secret_and_native_runner():
    root = Path(__file__).resolve().parents[1]
    workflow = (root / ".github/workflows/soc-traces-demo-e2e-once.yml").read_text()

    assert "OPENAI_API_KEY: ${{ secrets.OPENAI_API_KEY }}" in workflow
    assert "python scripts/run_soc_demo_cloud.py" in workflow
    assert "mock" not in workflow.lower()
    assert "SOC_E2E_GATES_JSON" not in workflow
