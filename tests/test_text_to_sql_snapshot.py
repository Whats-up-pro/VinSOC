import importlib
import importlib.util
import json
from pathlib import Path

import pytest

from vinsoc_data.duckdb_store import SocSnapshotBuilder


def _snapshot_module():
    spec = importlib.util.find_spec("evaluation.text_to_sql_snapshot")
    assert spec is not None, "snapshot manifest support is missing"
    return importlib.import_module("evaluation.text_to_sql_snapshot")


def _write_manifest(path, snapshot_path, sha256, snapshot_id=None):
    payload = {
        "snapshot_id": snapshot_id or snapshot_path.stem,
        "path": str(snapshot_path),
        "sha256": sha256,
        "schema_version": "1",
    }
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def test_correct_snapshot_path_and_sha_pass(tmp_path):
    module = _snapshot_module()
    snapshot = tmp_path / "vinsoc_public_v1.duckdb"
    snapshot.write_bytes(b"stable snapshot bytes")
    manifest_path = _write_manifest(
        tmp_path / "manifest.json",
        snapshot,
        module.sha256_file(snapshot),
    )

    manifest = module.load_snapshot_manifest(manifest_path)

    module.verify_snapshot(snapshot, manifest)


def test_changed_snapshot_bytes_fail_even_when_filename_matches(tmp_path):
    module = _snapshot_module()
    snapshot = tmp_path / "vinsoc_public_v1.duckdb"
    snapshot.write_bytes(b"original")
    manifest_path = _write_manifest(
        tmp_path / "manifest.json",
        snapshot,
        module.sha256_file(snapshot),
    )
    manifest = module.load_snapshot_manifest(manifest_path)
    snapshot.write_bytes(b"changed")

    with pytest.raises(ValueError, match="SHA-256"):
        module.verify_snapshot(snapshot, manifest)


def test_wrong_snapshot_path_fails_even_when_bytes_match(tmp_path):
    module = _snapshot_module()
    expected = tmp_path / "vinsoc_public_v1.duckdb"
    actual = tmp_path / "copy" / "vinsoc_public_v1.duckdb"
    actual.parent.mkdir()
    expected.write_bytes(b"same")
    actual.write_bytes(b"same")
    manifest = module.load_snapshot_manifest(
        _write_manifest(
            tmp_path / "manifest.json",
            expected,
            module.sha256_file(expected),
        )
    )

    with pytest.raises(ValueError, match="path"):
        module.verify_snapshot(actual, manifest)


def test_snapshot_id_must_match_canonical_filename(tmp_path):
    module = _snapshot_module()
    snapshot = tmp_path / "vinsoc_public_v1.duckdb"
    snapshot.write_bytes(b"stable")
    manifest = module.load_snapshot_manifest(
        _write_manifest(
            tmp_path / "manifest.json",
            snapshot,
            module.sha256_file(snapshot),
            snapshot_id="wrong_snapshot",
        )
    )

    with pytest.raises(ValueError, match="snapshot_id"):
        module.verify_snapshot(snapshot, manifest)


def _build_three_table_snapshot(path: Path, *, reverse: bool = False) -> None:
    builder = SocSnapshotBuilder(path)
    builder.create_empty_snapshot()
    sources = (
        ("threatfox_full", "ThreatFox"),
        ("ctu13_s3", "CTU-13"),
        ("otrf_apt29_day1", "OTRF"),
    )
    for dataset_id, source_name in sources:
        builder.register_provenance(
            dataset_id=dataset_id,
            source_name=source_name,
            source_url=f"https://example.invalid/{dataset_id}",
            retrieved_at="2026-09-26T00:00:00+00:00",
            file_sha256="a" * 64,
            license_note="Test-only fixture.",
        )
    cti_rows = [
        {
            "source_dataset": "threatfox_full",
            "source_row_id": row_id,
            "indicator": indicator,
            "indicator_type": "ip:port",
        }
        for row_id, indicator in (("line:2", "192.0.2.2:443"), ("line:1", "192.0.2.1:80"))
    ]
    if reverse:
        cti_rows.reverse()
    builder.insert_rows("cti_indicators", cti_rows, source_dataset="threatfox_full")
    builder.insert_rows(
        "network_flows",
        [{
            "source_dataset": "ctu13_s3",
            "source_row_id": "line:2",
            "event_time": "2011-08-12T15:00:37",
            "src_ip": "192.0.2.10",
            "dst_ip": "198.51.100.20",
            "bytes_out": 12,
            "bytes_in": 34,
        }],
        source_dataset="ctu13_s3",
    )
    builder.insert_rows(
        "sysmon_process_events",
        [{
            "source_dataset": "otrf_apt29_day1",
            "source_row_id": "events.json:line:1",
            "event_time": "2020-04-29T20:07:43",
            "host": "HOST01",
            "event_id": 1,
            "image": "cmd.exe",
            "process_id": 99,
        }],
        source_dataset="otrf_apt29_day1",
    )


def _write_official_contract_fixture(tmp_path: Path):
    module = _snapshot_module()
    snapshot = tmp_path / "vinsoc_public_v1.duckdb"
    _build_three_table_snapshot(snapshot)
    snapshot_manifest = _write_manifest(
        tmp_path / "snapshot_manifest.json", snapshot, module.sha256_file(snapshot)
    )
    builder_path = tmp_path / "build_snapshot.py"
    builder_path.write_text("BUILDER_VERSION = 'official-v1'\n", encoding="utf-8")
    receipts = tmp_path / "receipts"
    receipts.mkdir()
    source_specs = (
        ("ctu13_s3", "ctu13_binetflow", None),
        ("otrf_apt29_day1", "sysmon_zip_jsonl", "events.json"),
        ("threatfox_full", "threatfox_csv", None),
    )
    sources = []
    for index, (dataset_id, source_format, member) in enumerate(source_specs, start=1):
        source_sha = str(index) * 64
        source_url = f"https://example.invalid/{dataset_id}"
        receipt = {
            "canonical_source_url": source_url,
            "dataset_id": dataset_id,
            "format": source_format,
            "ingest": {"bytes": index, "sha256": source_sha},
            "license_note": "Test-only fixture.",
            "retrieved_at": "2026-09-26T00:00:00+00:00",
            "source_name": dataset_id,
            "status": "verified_bytes",
            "transport": {"bytes": index, "sha256": source_sha},
        }
        if member:
            receipt["ingest"]["archive_member"] = member
        (receipts / f"{dataset_id}.json").write_text(
            json.dumps(receipt), encoding="utf-8"
        )
        sources.append({
            "archive_member": member,
            "dataset_id": dataset_id,
            "file_sha256": source_sha,
            "format": source_format,
            "license_note": "Test-only fixture.",
            "path": f"data/official_r2/sources/{dataset_id}",
            "retrieved_at": "2026-09-26T00:00:00+00:00",
            "source_name": dataset_id,
            "source_url": source_url,
        })
    dataset_manifest = tmp_path / "dataset_manifest.json"
    dataset_manifest.write_text(
        json.dumps({"schema_version": "1", "sources": sources}), encoding="utf-8"
    )
    lock_path = tmp_path / "official_snapshot.lock"
    lock = module.build_official_snapshot_lock(
        snapshot_path=snapshot,
        snapshot_manifest_path=snapshot_manifest,
        dataset_manifest_path=dataset_manifest,
        receipt_dir=receipts,
        builder_path=builder_path,
        builder_version="official-v1",
    )
    lock_path.write_text(json.dumps(lock), encoding="utf-8")
    return {
        "snapshot_path": snapshot,
        "snapshot_manifest_path": snapshot_manifest,
        "dataset_manifest_path": dataset_manifest,
        "receipt_dir": receipts,
        "builder_path": builder_path,
        "builder_version": "official-v1",
        "official_lock_path": lock_path,
    }


def test_logical_content_identity_is_stable_across_insert_order(tmp_path):
    module = _snapshot_module()
    first = tmp_path / "first.duckdb"
    second = tmp_path / "second.duckdb"
    _build_three_table_snapshot(first)
    _build_three_table_snapshot(second, reverse=True)

    first_counts, first_sha = module.logical_content_identity(first)
    second_counts, second_sha = module.logical_content_identity(second)

    assert first_counts == second_counts == {
        "cti_indicators": 2,
        "network_flows": 1,
        "sysmon_process_events": 1,
    }
    assert first_sha == second_sha


def test_official_snapshot_contract_accepts_exact_provenance_chain(tmp_path):
    module = _snapshot_module()
    paths = _write_official_contract_fixture(tmp_path)

    verified = module.verify_official_snapshot_contract(**paths)

    assert verified["expected_source_ids"] == [
        "ctu13_s3",
        "otrf_apt29_day1",
        "threatfox_full",
    ]
    assert verified["row_counts"]["cti_indicators"] == 2


@pytest.mark.parametrize("tamper", ["receipt", "dataset_manifest", "binary", "logical"])
def test_official_snapshot_contract_fails_closed_on_identity_mismatch(tmp_path, tamper):
    module = _snapshot_module()
    paths = _write_official_contract_fixture(tmp_path)
    if tamper == "receipt":
        receipt = paths["receipt_dir"] / "ctu13_s3.json"
        receipt.write_text(receipt.read_text(encoding="utf-8") + "\n", encoding="utf-8")
    elif tamper == "dataset_manifest":
        manifest = paths["dataset_manifest_path"]
        manifest.write_text(manifest.read_text(encoding="utf-8") + "\n", encoding="utf-8")
    elif tamper == "binary":
        paths["snapshot_path"].write_bytes(paths["snapshot_path"].read_bytes() + b"tamper")
    else:
        lock = json.loads(paths["official_lock_path"].read_text(encoding="utf-8"))
        lock["snapshot_logical_sha256"] = "f" * 64
        paths["official_lock_path"].write_text(json.dumps(lock), encoding="utf-8")

    with pytest.raises(ValueError, match="mismatch|SHA-256"):
        module.verify_official_snapshot_contract(**paths)
