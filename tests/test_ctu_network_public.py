from __future__ import annotations

import csv
import hashlib
import json
from pathlib import Path

import pytest

from scripts.build_ctu_network_public_snapshot import (
    build_ctu_network_snapshot,
    logical_content_hash,
)


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _manifest(tmp_path: Path, *, bad_hash: bool = False) -> Path:
    sources = []
    for dataset_id, label in (("ctu13_s5", "flow=From-Botnet-V42"), ("ctu13_s7", "flow=Background")):
        path = tmp_path / f"{dataset_id}.binetflow"
        with path.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=["StartTime", "Proto", "SrcAddr", "Sport", "DstAddr", "Dport", "State", "TotBytes", "SrcBytes", "Label"])
            writer.writeheader()
            writer.writerow({"StartTime": "2011/08/15 16:43:20.000001", "Proto": "tcp", "SrcAddr": "192.0.2.1", "Sport": "123", "DstAddr": "198.51.100.2", "Dport": "443", "State": "CON", "TotBytes": "100", "SrcBytes": "40", "Label": label})
        sources.append({"archive_member": None, "dataset_id": dataset_id, "source_name": dataset_id, "source_url": "https://example.invalid/ctu", "retrieved_at": "2026-09-27T00:00:00+00:00", "format": "ctu13_binetflow", "license_note": "test", "path": str(path), "file_sha256": "0" * 64 if bad_hash else _sha(path)})
    manifest = tmp_path / "manifest.json"
    manifest.write_text(json.dumps({"schema_version": "1", "sources": sources}), encoding="utf-8")
    return manifest


def test_ctu_only_snapshot_has_only_network_and_rebuilds_logically(tmp_path):
    manifest = _manifest(tmp_path)
    first = tmp_path / "first.duckdb"
    second = tmp_path / "second.duckdb"
    first_report = build_ctu_network_snapshot(manifest, first)
    second_report = build_ctu_network_snapshot(manifest, second)

    assert first_report["row_counts"] == {"network_flows": 2}
    assert first_report["distinct_source_row_id"] == 2
    assert logical_content_hash(first)[1] == logical_content_hash(second)[1]
    assert first_report["content_sha256"] == second_report["content_sha256"]
    import duckdb
    with duckdb.connect(str(first), read_only=True) as conn:
        assert {row[0] for row in conn.execute("SHOW TABLES").fetchall()} == {"dataset_provenance", "network_flows"}
        assert conn.execute("SELECT count(*) FROM network_flows").fetchone()[0] == 2


def test_ctu_only_builder_rejects_bad_source_checksum_before_load(tmp_path):
    with pytest.raises(ValueError, match="checksum"):
        build_ctu_network_snapshot(_manifest(tmp_path, bad_hash=True), tmp_path / "snapshot.duckdb")
