"""Boundary tests for the guarded public-lifecycle network E2E runner."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest


SHA = "a" * 40


def _gates() -> dict:
    now = datetime.now(timezone.utc).isoformat()
    return {
        "schema_version": 1,
        "window_id": "network-finalization-20261006",
        "task_budget_usd": 0.25,
        "implementation_sha": SHA,
        "ci": {
            "head_sha": SHA,
            "run_url": "https://github.com/Whats-up-pro/VinSOC/actions/runs/123",
            "conclusion": "success",
            "jobs": [
                {"name": "test (3.11)", "conclusion": "success", "job_url": "https://github.com/job/311"},
                {"name": "test (3.12)", "conclusion": "success", "job_url": "https://github.com/job/312"},
            ],
        },
        "account": {
            "source": "owner_confirmation", "confirmed_utc": now,
            "project_verified": True, "remaining_allocation_usd": 1.0,
        },
        "pricing": {
            "checked_utc": now,
            "source_url": "https://developers.openai.com/api/docs/models/gpt-4.1-mini",
            "input_usd_per_million": 0.4,
            "cached_input_usd_per_million": 0.1,
            "output_usd_per_million": 1.6,
        },
        "reconciliation": {
            "receipt_hashes": [], "known_prior_cost_usd": 0.0,
            "unresolved_cost_unknown": False,
        },
    }


def _qualify() -> dict:
    return {
        "qualified": True,
        "checks": {
            "logical_sha256": "b" * 64,
            "binary_sha256": "c" * 64,
            "source_counts": {"ctu13_s5": 129831, "ctu13_s7": 114075},
            "distinct_source_pairs": 243906,
        },
    }


def _configure_preflight(monkeypatch, demo, tmp_path: Path):
    monkeypatch.setattr(demo, "qualify_snapshot", lambda _path: _qualify())
    monkeypatch.setattr(demo, "validate_lock", lambda *_args: {"valid": True, "issues": []})
    lock = tmp_path / "lock.json"
    lock.write_text(json.dumps({"contract_identity": "network_e2e_v1"}), encoding="utf-8")
    monkeypatch.setattr(demo, "LOCK_PATH", lock)
    monkeypatch.setattr(demo, "_git_identity", lambda: {"head_sha": SHA, "origin_master_sha": SHA})
    monkeypatch.setattr(
        demo,
        "network_select_scenario",
        lambda _snapshot, name: {
            "name": name,
            "indicator": "10.0.0.1" if name == "botnet" else "10.0.0.2",
            "time_range": {"start": "2011-08-15T10:00:00", "end": "2011-08-15T10:01:00"},
            "label": name.title(),
            "source_dataset": "ctu13_s5" if name == "botnet" else "ctu13_s7",
        },
    )
    gates_path = tmp_path / "gates.json"
    gates_path.write_text(json.dumps(_gates()), encoding="utf-8")
    env_file = tmp_path / "test.env"
    env_file.write_text("OPENAI_API_KEY=test-only-key\n", encoding="utf-8")
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_BASE_URL", raising=False)
    ledger = tmp_path / "network-finalization-20261006" / "ledger.json"
    return gates_path, env_file, ledger


def test_live_missing_gates_blocks_before_client(monkeypatch, tmp_path):
    from scripts import demo_ctu_network_public_model_driven as demo

    factory = MagicMock()
    result = demo.run_e2e_live(
        tmp_path / "snapshot.duckdb",
        tmp_path / "result.json",
        ledger_path=tmp_path / "network-finalization-20261006" / "ledger.json",
        gates_path=tmp_path / "missing-gates.json",
        env_file=tmp_path / "missing.env",
        client_factory=factory,
    )
    assert result["status"] == "blocked"
    assert result["failed_stage"] == "preflight"
    assert result["attempted_calls"] == 0
    factory.assert_not_called()


def test_preflight_uses_gates_env_and_never_creates_client(monkeypatch, tmp_path):
    from scripts import demo_ctu_network_public_model_driven as demo

    gates_path, env_file, ledger = _configure_preflight(monkeypatch, demo, tmp_path)
    result = demo.run_e2e_preflight(
        tmp_path / "snapshot.duckdb",
        tmp_path / "result.json",
        ledger_path=ledger,
        gates_path=gates_path,
        env_file=env_file,
    )
    assert result["status"] == "preflight_pass"
    assert result["client_created"] is False
    assert result["attempted_calls"] == result["responses_received"] == 0
    assert result["key_source"] == "dotenv"
    assert result["ci"]["head_sha"] == SHA


class _FakeCompletions:
    def __init__(self):
        self.requests = []

    def create(self, **request):
        self.requests.append(request)
        return SimpleNamespace(
            id=f"chatcmpl_{len(self.requests)}",
            model="gpt-4.1-mini-2025-04-14",
            usage=SimpleNamespace(
                prompt_tokens=20,
                completion_tokens=10,
                total_tokens=30,
                prompt_tokens_details=SimpleNamespace(cached_tokens=0),
            ),
            choices=[SimpleNamespace(
                finish_reason="stop",
                message=SimpleNamespace(content="{}", tool_calls=None),
            )],
            model_dump=lambda: {},
        )


class _FakeCase:
    def __init__(self, indicator: str, valid: bool = True):
        assessment = {
            "assessment": "Grounded assessment",
            "evidence_ids": ["ev_1"],
            "observations": [
                {"evidence_id": "ev_1", "field": "connection_count", "value": 1},
                {"evidence_id": "ev_1", "field": "dst_ip", "value": "8.8.8.8"},
            ],
            "hypotheses": [], "risk_level": "UNKNOWN", "confidence": "LOW",
            "limitations": ["CTI unavailable"],
        } if valid else None
        self.payload = {
            "case_id": "case",
            "initial_indicator": {"type": "ipv4", "value": indicator},
            "tool_trace": [{
                "call_id": "tc_1", "tool": "network_investigation",
                "arguments": {
                    "indicator": indicator, "indicator_type": "ipv4",
                    "time_range": {"start": "2011-08-15T10:00:00", "end": "2011-08-15T10:01:00"},
                },
                "evidence_ids": ["ev_1"], "error": None,
            }],
            "evidence": [{
                "evidence_id": "ev_1", "evidence_class": "OBSERVED",
                "type": "network_flow_aggregate", "data": {"connection_count": 1, "dst_ip": "8.8.8.8"},
                "provenance": {"source_records": [{"source_dataset": "ctu13_s5", "source_row_id": "1"}]},
                "related_evidence_ids": [],
            }],
            "hypotheses": [], "risk_level": "UNKNOWN", "confidence": "LOW",
            "limitations": ["CTI unavailable"], "final_assessment": "Grounded assessment",
            "supporting_evidence": ["ev_1"],
            "metadata": {
                "network_policy": {
                    "termination": "FINAL_ASSESSMENT" if valid else "ASSESSMENT_VALIDATION_FAILED",
                    "assessment": assessment,
                    "validation": {"valid": valid, "issues": [] if valid else ["invalid"]},
                    "prose_semantics_machine_verified": False,
                },
                "lifecycle_trace": [], "review_status": "not_configured",
            },
        }

    def to_dict(self):
        return self.payload


def test_live_uses_public_investigate_one_guarded_client_and_four_requests(monkeypatch, tmp_path):
    from scripts import demo_ctu_network_public_model_driven as demo

    gates_path, env_file, ledger = _configure_preflight(monkeypatch, demo, tmp_path)
    completions = _FakeCompletions()
    raw_client = SimpleNamespace(chat=SimpleNamespace(completions=completions))
    factory = MagicMock(return_value=raw_client)
    investigate_calls = []

    class FakeOrchestrator:
        def __init__(self, *, provider, investigation_policy, **_kwargs):
            self.provider = provider
            self.policy = investigation_policy

        def investigate(self, indicator, indicator_type="ipv4", context=None):
            investigate_calls.append((indicator, indicator_type, context))
            for _ in range(2):
                self.provider.client.chat.completions.create(
                    model=demo.DEMO_MODEL, messages=[{"role": "user", "content": "bounded"}],
                    tools=self.policy.tool_schemas(), temperature=0,
                    max_completion_tokens=demo.DEMO_CAP, tool_choice="auto",
                )
            return _FakeCase(indicator)

    monkeypatch.setattr(demo, "InvestigationOrchestrator", FakeOrchestrator)
    monkeypatch.setattr(
        demo, "verify_network_evidence",
        lambda *_args: {"verified": True, "issues": [], "checked_source_pairs": 1, "checked_aggregates": 1},
    )
    monkeypatch.setattr(demo, "_e2e_api_call", MagicMock(side_effect=AssertionError("legacy bypass")))

    result = demo.run_e2e_live(
        tmp_path / "snapshot.duckdb", tmp_path / "result.json",
        ledger_path=ledger, gates_path=gates_path, env_file=env_file,
        client_factory=factory, review_mode="deferred",
    )
    assert result["status"] == "technical_complete_awaiting_human"
    assert len(investigate_calls) == 2
    assert len(completions.requests) == 4
    assert result["attempted_calls"] == result["responses_received"] == 4
    assert result["valid_usage_records"] == 4
    assert result["review_status"] == "awaiting_human"
    factory.assert_called_once_with("test-only-key")


def test_invalid_assessment_cannot_be_reported_complete(monkeypatch, tmp_path):
    from scripts import demo_ctu_network_public_model_driven as demo

    gates_path, env_file, ledger = _configure_preflight(monkeypatch, demo, tmp_path)
    completions = _FakeCompletions()

    class FakeOrchestrator:
        calls = 0

        def __init__(self, *, provider, investigation_policy, **_kwargs):
            self.provider = provider
            self.policy = investigation_policy

        def investigate(self, indicator, **_kwargs):
            for _ in range(2):
                self.provider.client.chat.completions.create(
                    model=demo.DEMO_MODEL, messages=[], tools=self.policy.tool_schemas(),
                    temperature=0, max_completion_tokens=demo.DEMO_CAP, tool_choice="auto",
                )
            FakeOrchestrator.calls += 1
            return _FakeCase(indicator, valid=FakeOrchestrator.calls != 2)

    monkeypatch.setattr(demo, "InvestigationOrchestrator", FakeOrchestrator)
    monkeypatch.setattr(
        demo, "verify_network_evidence",
        lambda *_args: {"verified": True, "issues": [], "checked_source_pairs": 1, "checked_aggregates": 1},
    )
    result = demo.run_e2e_live(
        tmp_path / "snapshot.duckdb", tmp_path / "result.json",
        ledger_path=ledger, gates_path=gates_path, env_file=env_file,
        client_factory=lambda _key: SimpleNamespace(chat=SimpleNamespace(completions=completions)),
    )
    assert result["status"] == "partial"
    assert result["scenarios"][1]["assessment"] is None
    assert result["scenarios"][1]["termination"] == "ASSESSMENT_VALIDATION_FAILED"


def test_offline_review_links_receipt_without_api_or_overwrite(tmp_path):
    from agent.hitl import HumanDecision, REVIEW_APPROVE
    from scripts import demo_ctu_network_public_model_driven as demo

    technical = tmp_path / "technical.json"
    original = {
        "schema_version": 1,
        "run_id": "run_1",
        "status": "technical_complete_awaiting_human",
        "review_status": "awaiting_human",
        "implementation_sha": SHA,
        "scenarios": [{
            "name": "botnet", "risk_level": "UNKNOWN", "confidence": "LOW",
            "assessment": "Evidence-grounded text", "validation": {"technical_valid": True},
        }],
    }
    technical.write_text(json.dumps(original, sort_keys=True), encoding="utf-8")
    before = technical.read_bytes()

    class Gate:
        def review_final(self, case):
            assert case.final_assessment == "Evidence-grounded text"
            return HumanDecision(REVIEW_APPROVE, "reviewed", analyst="real-human")

    output = tmp_path / "review.json"
    result = demo.finalize_offline_review(technical, output, gate=Gate())
    assert result["status"] == "approved"
    assert result["input_receipt_sha256"]
    assert result["decisions"][0]["analyst"] == "real-human"
    assert technical.read_bytes() == before
    assert result["api_calls"] == 0
