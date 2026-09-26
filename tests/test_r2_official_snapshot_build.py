from __future__ import annotations

import csv
import hashlib
import json
import zipfile
from pathlib import Path

from evaluation.text_to_sql_snapshot import verify_official_snapshot_contract
from scripts.build_r2_official_snapshot import build_official_snapshot_pair
from scripts.build_vinsoc_public_snapshot import BUILDER_VERSION


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _write_csv(path: Path, fields: list[str], rows: list[dict[str, str]]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def _source_fixture(tmp_path: Path) -> tuple[Path, Path]:
    threatfox = tmp_path / "full.csv"
    _write_csv(threatfox, ["ioc_id", "ioc_value", "ioc_type"], [{
        "ioc_id": "1", "ioc_value": "malware.example", "ioc_type": "domain"
    }])
    ctu = tmp_path / "capture20110812.binetflow"
    _write_csv(
        ctu,
        ["StartTime", "Proto", "SrcAddr", "DstAddr", "TotBytes", "SrcBytes"],
        [{
            "StartTime": "2011/08/12 15:00:37",
            "Proto": "tcp",
            "SrcAddr": "192.0.2.1",
            "DstAddr": "198.51.100.2",
            "TotBytes": "10",
            "SrcBytes": "4",
        }],
    )
    otrf = tmp_path / "apt29.zip"
    member = "events.json"
    with zipfile.ZipFile(otrf, "w") as archive:
        archive.writestr(member, json.dumps({
            "Channel": "Microsoft-Windows-Sysmon/Operational",
            "Hostname": "HOST01",
            "EventID": 1,
            "UtcTime": "2020-05-01 22:55:25",
            "Image": "cmd.exe",
        }))

    receipts = tmp_path / "receipts"
    receipts.mkdir()
    specs = (
        ("threatfox_full", threatfox, "threatfox_csv", None),
        ("ctu13_s3", ctu, "ctu13_binetflow", None),
        ("otrf_apt29_day1", otrf, "sysmon_zip_jsonl", member),
    )
    sources = []
    for dataset_id, source, source_format, archive_member in specs:
        digest = _sha256(source)
        url = f"https://example.invalid/{source.name}"
        ingest = {"bytes": source.stat().st_size, "sha256": digest}
        if archive_member:
            ingest["archive_member"] = archive_member
        (receipts / f"{dataset_id}.json").write_text(json.dumps({
            "canonical_source_url": url,
            "dataset_id": dataset_id,
            "format": source_format,
            "ingest": ingest,
            "license_note": "Test-only fixture.",
            "retrieved_at": "2026-09-26T00:00:00+00:00",
            "source_name": dataset_id,
            "status": "verified_bytes",
            "transport": {"bytes": source.stat().st_size, "sha256": digest},
        }), encoding="utf-8")
        sources.append({
            "archive_member": archive_member,
            "dataset_id": dataset_id,
            "file_sha256": digest,
            "format": source_format,
            "license_note": "Test-only fixture.",
            "path": str(source),
            "retrieved_at": "2026-09-26T00:00:00+00:00",
            "source_name": dataset_id,
            "source_url": url,
        })
    manifest = tmp_path / "dataset_manifest.json"
    manifest.write_text(json.dumps({"schema_version": "1", "sources": sources}), encoding="utf-8")
    return manifest, receipts


def test_official_builder_rebuilds_same_logical_content_and_writes_lock(tmp_path):
    dataset_manifest, receipts = _source_fixture(tmp_path)
    snapshot = tmp_path / "vinsoc_public_v1.duckdb"
    snapshot_manifest = tmp_path / "snapshot_manifest.json"
    lock = tmp_path / "official_snapshot.lock"
    report = tmp_path / "official_snapshot_build.json"

    result = build_official_snapshot_pair(
        dataset_manifest_path=dataset_manifest,
        receipt_dir=receipts,
        snapshot_path=snapshot,
        snapshot_manifest_path=snapshot_manifest,
        official_lock_path=lock,
        report_path=report,
    )

    assert result["reproducible"] is True
    assert result["first_build"]["snapshot_logical_sha256"] == result["second_build"]["snapshot_logical_sha256"]
    assert result["first_build"]["row_counts"] == {
        "cti_indicators": 1,
        "network_flows": 1,
        "sysmon_process_events": 1,
    }
    assert json.loads(report.read_text(encoding="utf-8")) == result
    verified = verify_official_snapshot_contract(
        snapshot_path=snapshot,
        snapshot_manifest_path=snapshot_manifest,
        dataset_manifest_path=dataset_manifest,
        receipt_dir=receipts,
        builder_path=Path("scripts/build_vinsoc_public_snapshot.py"),
        builder_version=BUILDER_VERSION,
        official_lock_path=lock,
    )
    assert verified["snapshot_logical_sha256"] == result["first_build"]["snapshot_logical_sha256"]
