"""Offline S1/S4 source and snapshot builder contract tests."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

import scripts.build_ctu_network_frozen_snapshot as frozen_builder
from scripts.build_ctu_network_frozen_snapshot import build_ctu_network_frozen_snapshot

HEADER = "StartTime,Dur,Proto,SrcAddr,Sport,Dir,DstAddr,Dport,State,sTos,dTos,TotPkts,TotBytes,SrcBytes,Label\n"
URLS = {
    "ctu13_s1": "https://mcfp.felk.cvut.cz/publicDatasets/CTU-Malware-Capture-Botnet-42/detailed-bidirectional-flow-labels/capture20110810.binetflow",
    "ctu13_s4": "https://mcfp.felk.cvut.cz/publicDatasets/CTU-Malware-Capture-Botnet-45/detailed-bidirectional-flow-labels/capture20110815.binetflow",
}


def _sources(tmp_path: Path) -> tuple[Path, Path]:
    rows = {
        "ctu13_s1": "2011/08/10 00:00:00.000001,1,tcp,1.1.1.1,1234,->,2.2.2.2,80,S0,0,0,2,100,60,flow=From-Botnet-Test\n",
        "ctu13_s4": "2011/08/15 00:00:00.000001,1,udp,3.3.3.3,4321,->,4.4.4.4,53,S0,0,0,2,200,90,flow=From-Normal-Test\n",
    }
    sources = []
    checks = {}
    for dataset_id, row in rows.items():
        path = tmp_path / (dataset_id + ".binetflow")
        path.write_text(HEADER + row, encoding="utf-8", newline="")
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        sources.append({
            "archive_member": None, "dataset_id": dataset_id, "file_sha256": digest,
            "format": "ctu13_binetflow", "license_note": "CTU-13 test fixture",
            "path": str(path), "retrieved_at": "2026-09-29T00:00:00Z",
            "source_name": dataset_id, "source_url": URLS[dataset_id],
        })
        checks[dataset_id] = {"source_url": URLS[dataset_id],
                              "sha256_stream_and_disk": digest,
                              "content_length_bytes": path.stat().st_size}
    manifest = tmp_path / "manifest.json"
    manifest.write_text(json.dumps({"schema_version": "1", "sources": sources}), encoding="utf-8")
    receipt = tmp_path / "receipt.json"
    receipt.write_text(json.dumps({"source_checks": checks}), encoding="utf-8")
    return manifest, receipt


def test_two_independent_builds_have_same_logical_hash_and_only_s1_s4(tmp_path, monkeypatch):
    monkeypatch.setattr("agent.provider.create_provider", lambda *a, **kw: pytest.fail("provider called"))
    manifest, receipt = _sources(tmp_path)
    first = build_ctu_network_frozen_snapshot(manifest, receipt, tmp_path / "a.duckdb", tmp_path / "work-a")
    second = build_ctu_network_frozen_snapshot(manifest, receipt, tmp_path / "b.duckdb", tmp_path / "work-b")
    assert first["logical_snapshot_sha256"] == second["logical_snapshot_sha256"]
    assert first["source_row_counts"] == {"ctu13_s1": 1, "ctu13_s4": 1}
    assert first["distinct_source_row_id"] == 2
    assert first["tables"] == ["dataset_provenance", "network_flows"]
    assert first["model_calls"] == second["model_calls"] == 0


def test_source_checksum_mismatch_stops_before_snapshot(tmp_path):
    manifest, receipt = _sources(tmp_path)
    source = tmp_path / "ctu13_s1.binetflow"
    source.write_bytes(source.read_bytes() + b"changed")
    with pytest.raises(ValueError, match="checksum|SHA-256"):
        build_ctu_network_frozen_snapshot(manifest, receipt, tmp_path / "bad.duckdb", tmp_path / "work")
    assert not (tmp_path / "bad.duckdb").exists()


def test_source_url_receipt_mismatch_stops_before_snapshot(tmp_path):
    manifest, receipt = _sources(tmp_path)
    data = json.loads(receipt.read_text(encoding="utf-8"))
    data["source_checks"]["ctu13_s4"]["source_url"] = "https://invalid.example/file"
    receipt.write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(ValueError, match="provenance|URL"):
        build_ctu_network_frozen_snapshot(manifest, receipt, tmp_path / "bad.duckdb", tmp_path / "work")


def test_existing_snapshot_is_never_overwritten(tmp_path):
    manifest, receipt = _sources(tmp_path)
    output = tmp_path / "existing.duckdb"
    output.write_bytes(b"history")
    with pytest.raises(FileExistsError):
        build_ctu_network_frozen_snapshot(manifest, receipt, output, tmp_path / "work")
    assert output.read_bytes() == b"history"


def test_internal_csv_copy_preserves_comma_null_and_types(tmp_path, monkeypatch):
    """The staging round trip keeps CSV quoting and typed NULLs intact."""
    import duckdb

    manifest, receipt = _sources(tmp_path)

    def rows(_path, dataset_id):
        return iter([{
            "source_dataset": dataset_id,
            "source_row_id": "000123",
            "event_time": "2011-08-10 00:00:00.123456" if dataset_id == "ctu13_s1" else None,
            "src_ip": "1.1.1.1", "src_port": None,
            "dst_ip": "2.2.2.2", "dst_port": 53,
            "protocol": "TCP", "action": "S0",
            "bytes_out": 60, "bytes_in": None,
            "label": "flow=From-Botnet,quoted",
        }])

    monkeypatch.setattr(frozen_builder, "iter_ctu_rows", rows)
    snapshot = tmp_path / "typed.duckdb"
    build_ctu_network_frozen_snapshot(manifest, receipt, snapshot, tmp_path / "work")
    with duckdb.connect(str(snapshot), read_only=True) as conn:
        actual = conn.execute(
            "SELECT source_dataset, source_row_id, event_time, src_port, dst_port, "
            "bytes_out, bytes_in, label FROM network_flows ORDER BY source_dataset"
        ).fetchall()
        types = dict(conn.execute(
            "SELECT column_name, data_type FROM information_schema.columns "
            "WHERE table_name = 'network_flows'"
        ).fetchall())
    assert actual[0][1] == "000123"
    assert actual[0][2].isoformat(sep=" ") == "2011-08-10 00:00:00.123456"
    assert actual[1][2] is None
    assert all(row[3] is None and row[4] == 53 and row[5] == 60
               and row[6] is None and row[7] == "flow=From-Botnet,quoted"
               for row in actual)
    assert types["source_row_id"] == "VARCHAR"
    assert types["event_time"] == "TIMESTAMP"
    assert types["dst_port"] == "INTEGER"
    assert types["bytes_out"] == "BIGINT"


def _observe_duckdb_sql(monkeypatch):
    """Observe actual DuckDB statements while delegating every operation."""
    import duckdb

    real_connect = duckdb.connect
    statements = []

    class ObservedConnection:
        def __init__(self, connection):
            self.connection = connection

        def __enter__(self):
            self.connection.__enter__()
            return self

        def __exit__(self, *args):
            return self.connection.__exit__(*args)

        def execute(self, sql, *args, **kwargs):
            statements.append(sql)
            self.connection.execute(sql, *args, **kwargs)
            return self

        def __getattr__(self, name):
            return getattr(self.connection, name)

    monkeypatch.setattr(duckdb, "connect", lambda *a, **kw: ObservedConnection(real_connect(*a, **kw)))
    return statements


def test_copy_contract_disables_auto_detect(tmp_path, monkeypatch):
    manifest, receipt = _sources(tmp_path)
    statements = _observe_duckdb_sql(monkeypatch)
    build_ctu_network_frozen_snapshot(manifest, receipt, tmp_path / "copy.duckdb", tmp_path / "work")
    copy_sql = [sql.upper() for sql in statements if sql.upper().startswith("COPY NETWORK_FLOWS")]
    assert len(copy_sql) == 2
    assert all("AUTO_DETECT FALSE" in sql and "FORMAT CSV" in sql
               and "HEADER TRUE" in sql and "DELIMITER ','" in sql
               and "QUOTE '\"'" in sql and "ESCAPE '\"'" in sql
               and "NULL ''" in sql for sql in copy_sql)


def test_distinct_source_row_id_is_measured_from_database(tmp_path, monkeypatch):
    manifest, receipt = _sources(tmp_path)
    statements = _observe_duckdb_sql(monkeypatch)
    result = build_ctu_network_frozen_snapshot(
        manifest, receipt, tmp_path / "identity.duckdb", tmp_path / "work"
    )
    assert any("COUNT(DISTINCT SOURCE_DATASET || ':' || SOURCE_ROW_ID)" in sql.upper()
               for sql in statements)
    assert result["distinct_source_row_id"] == 2
