from __future__ import annotations

from pathlib import Path

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
