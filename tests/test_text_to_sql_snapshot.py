import importlib
import importlib.util
import json

import pytest


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
