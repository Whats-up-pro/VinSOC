from __future__ import annotations

import csv
import hashlib
import json
import zipfile
from pathlib import Path

import pytest

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


def _source_fixture(
    tmp_path: Path, *, threatfox_first_seen: str = "2026-09-25 00:00:00"
) -> tuple[Path, Path]:
    threatfox = tmp_path / "full.csv"
    _write_csv(threatfox, ["first_seen_utc", "ioc_id", "ioc_value", "ioc_type"], [{
        "first_seen_utc": threatfox_first_seen,
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


def test_official_builder_persists_private_diagnostics_before_empty_cti_failure(tmp_path):
    dataset_manifest, receipts = _source_fixture(
        tmp_path, threatfox_first_seen="2026-09-25 00:00:00 UTC"
    )
    report = tmp_path / "official_snapshot_build.json"

    with pytest.raises(ValueError, match="Snapshot table has no rows: cti_indicators"):
        build_official_snapshot_pair(
            dataset_manifest_path=dataset_manifest,
            receipt_dir=receipts,
            snapshot_path=tmp_path / "vinsoc_public_v1.duckdb",
            snapshot_manifest_path=tmp_path / "snapshot_manifest.json",
            official_lock_path=tmp_path / "official_snapshot.lock",
            report_path=report,
        )

    diagnostic = json.loads(report.read_text(encoding="utf-8"))
    assert diagnostic["schema_version"] == "r2_official_snapshot_diagnostic_v1"
    assert diagnostic["status"] == "failed"
    assert diagnostic["builder_version"] == BUILDER_VERSION
    assert len(diagnostic["git_sha"]) == 40
    assert diagnostic["failure_stage"] == "snapshot_validation"
    assert diagnostic["failure"] == {
        "category": "ValueError",
        "message": "Snapshot table has no rows: cti_indicators",
    }
    assert diagnostic["table_row_counts"] == {
        "cti_indicators": 0,
        "network_flows": 1,
        "sysmon_process_events": 1,
    }
    assert diagnostic["threatfox"] == {
        "dataset_id": "threatfox_full",
        "data_rows_seen": 1,
        "rows_accepted": 0,
        "rows_rejected": 1,
        "primary_rejection_reasons": {
            "missing_required_value": 0,
            "invalid_first_seen_timestamp": 1,
            "invalid_last_seen_timestamp": 0,
            "invalid_confidence_level": 0,
        },
        "timestamp_shape_counts": {
            "first_seen_ends_with_utc_literal": 1,
            "last_seen_ends_with_utc_literal": 0,
        },
    }
    assert set(diagnostic["source_hashes"]) == {
        "threatfox_full",
        "ctu13_s3",
        "otrf_apt29_day1",
    }
    serialized = json.dumps(diagnostic, sort_keys=True)
    assert "malware.example" not in serialized


def test_official_snapshot_workflow_is_manual_only():
    workflow = Path(".github/workflows/r2-official-snapshot-build.yml").read_text(
        encoding="utf-8"
    ).splitlines()
    on_line = workflow.index("on:")
    trigger_lines = []
    for line in workflow[on_line + 1:]:
        if line and not line.startswith(" "):
            break
        if line.startswith("  ") and not line.startswith("    ") and line.strip():
            trigger_lines.append(line.strip())
    assert trigger_lines == ["workflow_dispatch:"]


def test_official_snapshot_workflow_preserves_exact_same_run_source_bytes():
    workflow = Path(".github/workflows/r2-official-snapshot-build.yml").read_text(
        encoding="utf-8"
    )

    assert "name: r2-official-frozen-source-bytes" in workflow
    assert "${{ runner.temp }}/r2-official-source-probe/raw/" in workflow
    assert "${{ runner.temp }}/r2-official-source-probe/probe.json" in workflow
    assert "${{ runner.temp }}/r2-official-source-probe/receipts/" in workflow
    assert "retention-days: 90" in workflow


def test_official_snapshot_workflow_preserves_source_bytes_after_build_failure():
    workflow = Path(".github/workflows/r2-official-snapshot-build.yml").read_text(
        encoding="utf-8"
    )
    retention_step = workflow.split(
        "- name: Preserve exact verified source bytes for reproducible rebuilds", 1
    )[1].split("- name: Preserve credential-free build metadata", 1)[0]

    assert "if: always()" in retention_step
    assert "if: success()" not in retention_step
    assert "id: source_retention" in retention_step
    assert "steps.source_retention.outputs.artifact-id" in workflow
    assert "steps.source_retention.outputs.artifact-digest" in workflow
    assert "r2-official-source-retention.json" in workflow


def test_staging_rejects_bytes_changed_after_same_run_receipt(tmp_path):
    from scripts.probe_r2_official_sources import probe
    from scripts.stage_r2_official_sources import stage_probe_output
    from tests.test_r2_official_source_probe import Response, zipped

    threatfox = zipped("full.csv", b"first_seen_utc,ioc_id,ioc_value,ioc_type\n2026-09-25,1,a.test,domain\n")
    ctu = b"StartTime,SrcAddr,DstAddr\n2011/08/12 00:00:00,1.1.1.1,2.2.2.2\n"
    otrf = zipped("apt29_evals_day1_manual_2020-05-01225525.json", b'{"Hostname":"h","EventID":1}\n')

    def opener(request, timeout):
        if "threatfox-api" in request.full_url:
            return Response(threatfox)
        if request.full_url.endswith("capture20110812.binetflow"):
            return Response(ctu)
        return Response(otrf)

    probe_dir = tmp_path / "probe"
    probe(probe_dir, environ={"THREATFOX_AUTH_KEY": "secret"}, opener=opener,
          retrieved_at="2026-09-26T00:00:00+00:00")
    (probe_dir / "raw" / "capture20110812.binetflow").write_bytes(b"changed")

    with pytest.raises(ValueError, match="ctu13_s3 transport byte count mismatch"):
        stage_probe_output(
            probe_dir=probe_dir,
            source_root=tmp_path / "sources",
            dataset_manifest_path=tmp_path / "dataset_manifest.json",
            receipt_dir=tmp_path / "receipts",
        )
