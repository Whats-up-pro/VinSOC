from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import duckdb


def _snapshot(path: Path) -> Path:
    with duckdb.connect(str(path)) as conn:
        conn.execute(
            "CREATE TABLE network_flows (source_dataset VARCHAR, source_row_id VARCHAR, event_time TIMESTAMP, "
            "src_ip VARCHAR, src_port INTEGER, dst_ip VARCHAR, dst_port INTEGER, protocol VARCHAR, "
            "action VARCHAR, bytes_out BIGINT, bytes_in BIGINT, label VARCHAR)"
        )
        conn.execute(
            "INSERT INTO network_flows VALUES ('ctu13_s7', '42', TIMESTAMP '2011-08-16 10:00:00', "
            "'192.0.2.10', 4444, '198.51.100.10', 80, 'TCP', 'CON', 12, 6, 'Botnet')"
        )
    return path


def test_offline_demo_uses_network_skill_and_preserves_ctu_evidence_pair(monkeypatch, tmp_path):
    from scripts import demo_ctu_network_public as demo

    monkeypatch.setattr(demo, "validate", lambda *_args, **_kwargs: {
        "version": "ctu_network_public_dev_v1", "logical_snapshot_sha256": "a" * 64,
    })
    result = demo.run_offline_demo(
        _snapshot(tmp_path / "ctu.duckdb"),
        {"name": "botnet", "indicator": "192.0.2.10", "label": "Botnet",
         "time_range": {"start": "2011-08-16T09:59:00", "end": "2011-08-16T10:01:00"}},
    )

    assert result["tool_trace"][0]["tool"] == "network_investigation"
    assert result["tool_trace"][0]["arguments"]["time_range"]["start"].startswith("2011-")
    observed = [item for item in result["evidence"] if item["evidence_class"] == "OBSERVED"]
    assert observed[0]["provenance"]["source_records"] == [
        {"source_dataset": "ctu13_s7", "source_row_id": "42"}
    ]
    assert "CTI" in result["limitations"][0]


def test_offline_demo_reports_evidence_gap_without_a_benign_or_malicious_claim(monkeypatch, tmp_path):
    from scripts import demo_ctu_network_public as demo

    monkeypatch.setattr(demo, "validate", lambda *_args, **_kwargs: {
        "version": "ctu_network_public_dev_v1", "logical_snapshot_sha256": "a" * 64,
    })
    result = demo.run_offline_demo(
        _snapshot(tmp_path / "ctu.duckdb"),
        {"name": "no_evidence", "indicator": "203.0.113.99", "label": None,
         "time_range": {"start": "2011-08-16T09:59:00", "end": "2011-08-16T10:01:00"}},
    )

    assert result["evidence"] == []
    assert "No matching network telemetry" in result["limitations"]
    assert "benign" not in result["assessment"].lower()
    assert "malicious" not in result["assessment"].lower()


def test_normal_scenario_selects_a_ctu_normal_label_with_its_full_label_prefix(tmp_path):
    from scripts import demo_ctu_network_public as demo

    path = _snapshot(tmp_path / "ctu.duckdb")
    with duckdb.connect(str(path)) as conn:
        conn.execute(
            "INSERT INTO network_flows VALUES ('ctu13_s5', '43', TIMESTAMP '2011-08-15 10:00:00', "
            "'192.0.2.11', 4445, '198.51.100.11', 443, 'TCP', 'CON', 12, 6, 'flow=From-Normal-V46-Grill')"
        )
    scenario = demo.select_scenario(path, "normal")
    assert scenario["indicator"] == "192.0.2.11"
    assert scenario["label"] == "Normal"


def test_live_demo_sends_only_network_tool_and_persists_sanitized_usage(monkeypatch, tmp_path):
    from scripts import demo_ctu_network_public as demo

    path = _snapshot(tmp_path / "ctu.duckdb")
    with duckdb.connect(str(path)) as conn:
        conn.execute("INSERT INTO network_flows VALUES ('ctu13_s5', '43', TIMESTAMP '2011-08-15 10:00:00', '192.0.2.11', 1, '198.51.100.11', 443, 'TCP', 'CON', 1, 1, 'flow=From-Normal-V46-Grill')")
    class Client:
        def __init__(self): self.requests = []; self.chat = SimpleNamespace(completions=self)
        def create(self, **request):
            self.requests.append(request)
            call = SimpleNamespace(function=SimpleNamespace(
                name="network_investigation",
                arguments='{"indicator":"203.0.113.77","time_range":{"start":"2026-01-01","end":"2026-01-02"}}',
            ))
            return SimpleNamespace(model=demo.MODEL, usage=SimpleNamespace(prompt_tokens=10, completion_tokens=5), choices=[SimpleNamespace(message=SimpleNamespace(tool_calls=[call]))])
    monkeypatch.setattr(demo, "validate", lambda *_args, **_kwargs: {"version": "v", "logical_snapshot_sha256": "a" * 64})
    client = Client()
    result = demo.run_live_demo(path, tmp_path / "live.json", client=client)
    assert result["attempted_calls"] == result["responses_received"] == 2
    assert all([tool["function"]["name"] for tool in request["tools"]] == ["network_investigation"] for request in client.requests)
    assert result["execution_semantics"] == {
        "model_role": "network_tool_selection_only",
        "tool_arguments_source": "preselected_scenario",
        "model_generated_arguments_executed": False,
        "assessment_source": "deterministic_template",
        "model_generated_assessment": False,
    }
    assert result["scenarios"][0]["tool_trace"][0]["arguments"]["indicator"] == "192.0.2.10"
    assert "content" not in (tmp_path / "live.json").read_text(encoding="utf-8")
