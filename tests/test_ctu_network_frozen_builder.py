"""Offline S1/S4 source and snapshot builder contract tests."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

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
