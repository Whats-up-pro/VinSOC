"""The model-driven demo must execute validated model arguments and cite real evidence."""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import duckdb
import pytest


def _snapshot(path: Path) -> Path:
    with duckdb.connect(str(path)) as conn:
        conn.execute(
            "CREATE TABLE network_flows (source_dataset VARCHAR, source_row_id VARCHAR, event_time TIMESTAMP, "
            "src_ip VARCHAR, src_port INTEGER, dst_ip VARCHAR, dst_port INTEGER, protocol VARCHAR, "
            "action VARCHAR, bytes_out BIGINT, bytes_in BIGINT, label VARCHAR)"
        )
        conn.execute(
            "INSERT INTO network_flows VALUES "
            "('ctu13_s7', '42', TIMESTAMP '2011-08-16 10:00:00', '192.0.2.10', 4444, "
            "'198.51.100.10', 80, 'TCP', 'CON', 12, 6, 'Botnet'), "
            "('ctu13_s5', '43', TIMESTAMP '2011-08-15 10:00:00', '192.0.2.11', 4445, "
            "'198.51.100.11', 443, 'TCP', 'CON', 12, 6, 'flow=From-Normal-V46-Grill')"
        )
    return path


class FakeClient:
    def __init__(self, *, invalid_indicator: bool = False):
        self.requests = []
        self.invalid_indicator = invalid_indicator
        self.chat = SimpleNamespace(completions=self)

    def create(self, **request):
        self.requests.append(request)
        if request.get("tools"):
            text = request["messages"][-1]["content"]
            indicator = "192.0.2.10" if "192.0.2.10" in text else "192.0.2.11"
            if self.invalid_indicator:
                indicator = "203.0.113.77"
            scenario = json.loads(text)
            args = {"indicator": indicator, "indicator_type": "ipv4", "time_range": scenario["time_range"]}
            message = SimpleNamespace(tool_calls=[SimpleNamespace(
                id="fake_tool_call", function=SimpleNamespace(
                    name="network_investigation", arguments=json.dumps(args)),
            )], content=None)
        else:
            evidence = json.loads(request["messages"][-1]["content"])["evidence"]
            evidence_ids = [item["evidence_id"] for item in evidence]
            message = SimpleNamespace(tool_calls=None, content=json.dumps({
                "assessment": f"Observed network evidence {evidence_ids[0]}." if evidence_ids else "No network evidence observed.",
                "evidence_ids": evidence_ids[:1],
                "limitations": ["CTI and endpoint evidence unavailable."],
            }))
        return SimpleNamespace(
            id=f"fake_response_{len(self.requests)}", model="gpt-4.1-mini-2025-04-14",
            usage=SimpleNamespace(prompt_tokens=100, completion_tokens=50),
            choices=[SimpleNamespace(message=message)],
        )


def test_model_arguments_reach_network_tool_and_model_assesses_evidence(monkeypatch, tmp_path):
    from scripts import demo_ctu_network_public_model_driven as demo

    monkeypatch.setattr(demo, "validate", lambda *_args, **_kwargs: {
        "version": "ctu_network_public_dev_v1", "logical_snapshot_sha256": "a" * 64,
    })
    output = tmp_path / "result.json"
    client = FakeClient()
    report = demo.run_model_driven_demo(_snapshot(tmp_path / "ctu.duckdb"), output, client=client)

    assert report["status"] == "complete"
    assert report["attempted_calls"] == report["responses_received"] == 4
    assert report["execution_semantics"]["model_generated_arguments_executed"] is True
    assert report["execution_semantics"]["model_generated_assessment"] is True
    assert all(len(request.get("tools", [])) == 1 for request in client.requests[::2])
    assert all(not request.get("tools") for request in client.requests[1::2])
    assert [item["tool_trace"][0]["arguments"]["indicator"] for item in report["scenarios"]] == [
        "192.0.2.10", "192.0.2.11"
    ]
    for item in report["scenarios"]:
        assert item["assessment_evidence_ids"]
        assert set(item["assessment_evidence_ids"]) <= set(item["evidence_ids"])
        assert item["assessment_evidence_ids"][0] in item["assessment"]
    assert json.loads(output.read_text(encoding="utf-8"))["status"] == "complete"


def test_out_of_scope_model_indicator_stops_before_tool_execution(monkeypatch, tmp_path):
    from scripts import demo_ctu_network_public_model_driven as demo

    monkeypatch.setattr(demo, "validate", lambda *_args, **_kwargs: {
        "version": "ctu_network_public_dev_v1", "logical_snapshot_sha256": "a" * 64,
    })
    output = tmp_path / "partial.json"
    client = FakeClient(invalid_indicator=True)
    with pytest.raises(ValueError, match="model tool arguments"):
        demo.run_model_driven_demo(_snapshot(tmp_path / "ctu.duckdb"), output, client=client)
    report = json.loads(output.read_text(encoding="utf-8"))
    assert report["attempted_calls"] == report["responses_received"] == 1
    assert report["known_cost_usd"] > 0
    assert report["status"] == "invalid_tool_arguments"
    assert report["scenarios"] == []
    assert report["execution_semantics"]["model_generated_arguments_executed"] is False
    assert report["execution_semantics"]["model_generated_assessment"] is False


def test_budget_gate_stops_before_api_call(monkeypatch, tmp_path):
    from scripts import demo_ctu_network_public_model_driven as demo

    monkeypatch.setattr(demo, "validate", lambda *_args, **_kwargs: {
        "version": "ctu_network_public_dev_v1", "logical_snapshot_sha256": "a" * 64,
    })
    output = tmp_path / "partial.json"
    client = FakeClient()
    with pytest.raises(ValueError, match="budget"):
        demo.run_model_driven_demo(
            _snapshot(tmp_path / "ctu.duckdb"), output, client=client, budget_usd=0.001371,
        )
    report = json.loads(output.read_text(encoding="utf-8"))
    assert report["attempted_calls"] == 0
    assert client.requests == []
