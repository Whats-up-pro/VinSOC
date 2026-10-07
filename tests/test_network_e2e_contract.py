"""Regression tests for the locked network E2E snapshot and evidence contract."""

from __future__ import annotations

from pathlib import Path

import duckdb
import pytest


def _snapshot(path: Path) -> Path:
    with duckdb.connect(str(path)) as conn:
        conn.execute(
            "CREATE TABLE dataset_provenance (dataset_id VARCHAR, source_name VARCHAR, "
            "source_url VARCHAR, retrieved_at VARCHAR, file_sha256 VARCHAR, license_note VARCHAR)"
        )
        conn.execute(
            "CREATE TABLE network_flows (source_dataset VARCHAR, source_row_id VARCHAR, "
            "event_time TIMESTAMP, src_ip VARCHAR, src_port INTEGER, dst_ip VARCHAR, "
            "dst_port INTEGER, protocol VARCHAR, action VARCHAR, bytes_out BIGINT, "
            "bytes_in BIGINT, label VARCHAR)"
        )
        conn.execute(
            "INSERT INTO dataset_provenance VALUES "
            "('ctu13_s5','CTU 5','https://example.invalid/5','2026-01-01','a','public'),"
            "('ctu13_s7','CTU 7','https://example.invalid/7','2026-01-01','b','public')"
        )
        conn.execute(
            "INSERT INTO network_flows VALUES "
            "('ctu13_s5','1',TIMESTAMP '2011-08-15 10:00:00','10.0.0.1',1000,'8.8.8.8',53,'UDP','CON',12,6,'Botnet'),"
            "('ctu13_s7','2',TIMESTAMP '2011-08-16 10:00:00','10.0.0.2',1001,'1.1.1.1',443,'TCP','CON',20,10,'Normal')"
        )
    return path


def _patch_expected(monkeypatch: pytest.MonkeyPatch, module, snapshot: Path) -> None:
    _counts, logical_sha = module.logical_content_hash(snapshot)
    monkeypatch.setattr(module, "EXPECTED_SOURCE_COUNTS", {"ctu13_s5": 1, "ctu13_s7": 1})
    monkeypatch.setattr(module, "EXPECTED_ROWS", 2)
    monkeypatch.setattr(module, "EXPECTED_DISTINCT_PAIRS", 2)
    monkeypatch.setattr(module, "EXPECTED_LOGICAL_SHA256", logical_sha)


def test_qualification_hashes_rows_not_only_counts(monkeypatch, tmp_path):
    from evaluation.finalization import network_contract as contract

    snapshot = _snapshot(tmp_path / "snapshot.duckdb")
    _patch_expected(monkeypatch, contract, snapshot)
    assert contract.qualify_snapshot(snapshot)["qualified"] is True

    with duckdb.connect(str(snapshot)) as conn:
        conn.execute("UPDATE network_flows SET dst_ip = '9.9.9.9' WHERE source_row_id = '1'")

    with pytest.raises(ValueError, match="Logical content hash mismatch"):
        contract.qualify_snapshot(snapshot)


def test_qualification_rejects_missing_provenance(monkeypatch, tmp_path):
    from evaluation.finalization import network_contract as contract

    snapshot = _snapshot(tmp_path / "snapshot.duckdb")
    _patch_expected(monkeypatch, contract, snapshot)
    with duckdb.connect(str(snapshot)) as conn:
        conn.execute("DELETE FROM dataset_provenance WHERE dataset_id = 'ctu13_s7'")

    with pytest.raises(ValueError, match="Dataset provenance mismatch"):
        contract.qualify_snapshot(snapshot)


def test_evidence_verification_checks_pair_predicate_and_aggregate(tmp_path):
    from evaluation.finalization.network_contract import verify_network_evidence

    snapshot = _snapshot(tmp_path / "snapshot.duckdb")
    arguments = {
        "indicator": "10.0.0.1",
        "indicator_type": "ipv4",
        "time_range": {"start": "2011-08-15T09:59:00", "end": "2011-08-15T10:01:00"},
    }
    evidence = [{
        "evidence_id": "ev_1",
        "evidence_class": "OBSERVED",
        "type": "network_flow_aggregate",
        "data": {
            "src_ip": "10.0.0.1",
            "dst_ip": "8.8.8.8",
            "dst_port": 53,
            "protocol": "UDP",
            "connection_count": 1,
            "first_seen": "2011-08-15T10:00:00",
            "last_seen": "2011-08-15T10:00:00",
            "bytes_src_to_dst": 12,
            "bytes_dst_to_src": 6,
        },
        "provenance": {
            "source_records": [{"source_dataset": "ctu13_s5", "source_row_id": "1"}],
            "source_event_count": 1,
            "record_ids_truncated": False,
        },
    }]

    result = verify_network_evidence(snapshot, arguments, evidence)
    assert result["verified"] is True
    assert result["checked_source_pairs"] == 1
    assert result["checked_aggregates"] == 1

    evidence[0]["provenance"]["source_records"][0] = {
        "source_dataset": "ctu13_s7", "source_row_id": "2"
    }
    result = verify_network_evidence(snapshot, arguments, evidence)
    assert result["verified"] is False
    assert "source_pair_outside_query_scope" in result["issues"]


def test_evidence_verification_rejects_wrong_fact_and_zero_checked(tmp_path):
    from evaluation.finalization.network_contract import verify_network_evidence

    snapshot = _snapshot(tmp_path / "snapshot.duckdb")
    arguments = {
        "indicator": "10.0.0.1",
        "indicator_type": "ipv4",
        "time_range": {"start": "2011-08-15T09:59:00", "end": "2011-08-15T10:01:00"},
    }
    empty = verify_network_evidence(snapshot, arguments, [])
    assert empty["verified"] is False
    assert empty["issues"] == ["no_observed_evidence_verified"]

    wrong = [{
        "evidence_id": "ev_wrong",
        "evidence_class": "OBSERVED",
        "type": "network_flow_aggregate",
        "data": {
            "src_ip": "10.0.0.1", "dst_ip": "8.8.8.8", "dst_port": 53,
            "protocol": "UDP", "connection_count": 99,
            "first_seen": "2011-08-15T10:00:00", "last_seen": "2011-08-15T10:00:00",
            "bytes_src_to_dst": 12, "bytes_dst_to_src": 6,
        },
        "provenance": {
            "source_records": [{"source_dataset": "ctu13_s5", "source_row_id": "1"}],
            "source_event_count": 99,
            "record_ids_truncated": False,
        },
    }]
    result = verify_network_evidence(snapshot, arguments, wrong)
    assert result["verified"] is False
    assert "aggregate_fact_mismatch" in result["issues"]


def test_scenario_selector_uses_earliest_source_row_and_bounded_window(tmp_path):
    from evaluation.finalization.network_contract import select_scenario

    snapshot = _snapshot(tmp_path / "snapshot.duckdb")
    botnet = select_scenario(snapshot, "botnet")
    normal = select_scenario(snapshot, "normal")
    assert botnet == {
        "name": "botnet",
        "indicator": "10.0.0.1",
        "time_range": {"start": "2011-08-15T09:59:00", "end": "2011-08-15T10:01:00"},
        "label": "Botnet",
        "source_dataset": "ctu13_s5",
        "seed_source_row_id": "1",
        "seed_event_time": "2011-08-15T10:00:00",
    }
    assert normal["source_dataset"] == "ctu13_s7"
    assert normal["seed_source_row_id"] == "2"
