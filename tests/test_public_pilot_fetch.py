"""A download must match the manifest before it can enter a snapshot."""

import hashlib
import io
import json

import pytest

from scripts.fetch_r2_public_pilot_sources import fetch_sources


def test_bad_source_checksum_never_publishes_file(tmp_path, monkeypatch):
    manifest = tmp_path / "manifest.json"
    source_path = tmp_path / "raw.binetflow"
    source = {
        "dataset_id": "ctu13_s5", "source_name": "source",
        "source_url": "https://mcfp.felk.cvut.cz/publicDatasets/raw.binetflow",
        "retrieved_at": "2026-09-25T04:00:00Z", "file_sha256": "0" * 64,
        "license_note": "Test fixture", "format": "ctu13_binetflow",
        "path": str(source_path), "archive_member": None,
    }
    second = {**source, "dataset_id": "ctu13_s7", "path": str(tmp_path / "second.binetflow"),
              "file_sha256": hashlib.sha256(b"real bytes").hexdigest()}
    third = {**source, "dataset_id": "otrf_apt29_day1", "path": str(tmp_path / "third.zip"),
             "format": "sysmon_zip_jsonl", "archive_member": "events.json",
             "file_sha256": hashlib.sha256(b"real bytes").hexdigest()}
    manifest.write_text(json.dumps({"schema_version": "1", "sources": [source, second, third]}))
    monkeypatch.setattr("scripts.fetch_r2_public_pilot_sources.urlopen", lambda *a, **kw: io.BytesIO(b"real bytes"))
    with pytest.raises(ValueError, match="checksum"):
        fetch_sources(manifest)
    assert not source_path.exists()
