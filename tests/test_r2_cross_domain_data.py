"""Offline fixtures for cross-domain registry and deterministic SQLite conversion."""
from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest


def _source_db(path: Path) -> None:
    with sqlite3.connect(path) as conn:
        conn.executescript("""
            CREATE TABLE parent (id INTEGER PRIMARY KEY, name TEXT);
            CREATE TABLE child (id INTEGER PRIMARY KEY, parent_id INTEGER, note TEXT,
                                FOREIGN KEY(parent_id) REFERENCES parent(id));
            INSERT INTO parent VALUES (1, 'one'), (2, NULL);
            INSERT INTO child VALUES (10, 1, 'duplicate'), (11, 1, 'duplicate');
        """)


def test_context_preserves_pk_fk_null_and_duplicate_rows(tmp_path: Path):
    from evaluation.r2_cross_domain_v1.data import build_duckdb_snapshot

    source = tmp_path / "fixture.sqlite"
    _source_db(source)
    receipt = build_duckdb_snapshot(source, tmp_path / "one.duckdb", "fixture")

    assert receipt["row_counts"] == {"child": 2, "parent": 2}
    assert receipt["snapshot_row_counts"] == receipt["row_counts"]
    assert len(receipt["duckdb_content_sha256"]) == 64
    assert receipt["relationships"] == [{"from_column": "parent_id", "from_table": "child", "to_column": "id", "to_table": "parent"}]
    assert receipt["primary_keys"] == {"child": ["id"], "parent": ["id"]}


def test_logical_hash_is_repeatable_and_changes_with_row_multiplicity(tmp_path: Path):
    from evaluation.r2_cross_domain_v1.data import build_duckdb_snapshot

    source = tmp_path / "fixture.sqlite"
    _source_db(source)
    first = build_duckdb_snapshot(source, tmp_path / "one.duckdb", "fixture")
    second = build_duckdb_snapshot(source, tmp_path / "two.duckdb", "fixture")
    assert first["logical_sha256"] == second["logical_sha256"]
    assert first["duckdb_content_sha256"] == second["duckdb_content_sha256"]
    with sqlite3.connect(source) as conn:
        conn.execute("INSERT INTO child VALUES (12, 1, 'duplicate')")
    third = build_duckdb_snapshot(source, tmp_path / "three.duckdb", "fixture")
    assert third["logical_sha256"] != first["logical_sha256"]


def test_registry_rejects_duplicate_database_ids_and_missing_source():
    from evaluation.r2_cross_domain_v1.data import RegistryError, select_database_ids

    with pytest.raises(RegistryError, match="DUPLICATE_DATABASE_ID"):
        select_database_ids([{"db_id": "a"}, {"db_id": "a"}], {"a": 8}, count=1, seed=20261005)
    with pytest.raises(RegistryError, match="SOURCE_DB_MISSING"):
        select_database_ids([{"db_id": "a"}], {}, count=1, seed=20261005)


def test_source_archive_checksum_mismatch_fails_closed(tmp_path: Path):
    from evaluation.r2_cross_domain_v1.data import RegistryError, verify_archive_sha256

    archive = tmp_path / "spider_data.zip"
    archive.write_bytes(b"not the expected source")
    with pytest.raises(RegistryError, match="SOURCE_CHECKSUM_MISMATCH"):
        verify_archive_sha256(archive, "0" * 64)


def test_snapshot_content_must_equal_source_and_not_only_second_build(tmp_path, monkeypatch):
    import evaluation.r2_cross_domain_v1.data as data

    source = tmp_path / "fixture.sqlite"
    _source_db(source)
    monkeypatch.setattr(data, "_verify_duckdb_snapshot", lambda *args: ({"child": 2, "parent": 2}, "0" * 64))
    with pytest.raises(data.RegistryError, match="SNAPSHOT_CONTENT_MISMATCH"):
        data.build_duckdb_snapshot(source, tmp_path / "snapshot.duckdb", "fixture")


def test_extracted_member_must_match_locked_archive(tmp_path):
    import zipfile
    from evaluation.r2_cross_domain_v1.data import RegistryError, verify_archive_member

    archive = tmp_path / "source.zip"
    with zipfile.ZipFile(archive, "w") as handle:
        handle.writestr("database/a.sqlite", b"original bytes")
    extracted = tmp_path / "a.sqlite"
    extracted.write_bytes(b"changed bytes")
    with pytest.raises(RegistryError, match="ARCHIVE_MEMBER_MISMATCH"):
        verify_archive_member(archive, "database/a.sqlite", extracted)


def test_existing_snapshot_is_preserved(tmp_path):
    from evaluation.r2_cross_domain_v1.data import RegistryError, build_duckdb_snapshot

    source = tmp_path / "fixture.sqlite"
    _source_db(source)
    destination = tmp_path / "existing.duckdb"
    destination.write_bytes(b"historical identity")
    with pytest.raises(RegistryError, match="SNAPSHOT_ALREADY_EXISTS"):
        build_duckdb_snapshot(source, destination, "fixture")
    assert destination.read_bytes() == b"historical identity"


def test_context_verifies_snapshot_and_exposes_qualified_schema_only(tmp_path):
    import json
    from evaluation.r2_cross_domain_v1.data import DatabaseContext, RegistryError, build_duckdb_snapshot

    source = tmp_path / "fixture.sqlite"
    _source_db(source)
    snapshot = tmp_path / "snapshot.duckdb"
    receipt = build_duckdb_snapshot(source, snapshot, "fixture")
    entry = {**receipt, "snapshot_path": "snapshot.duckdb"}
    manifest = tmp_path / "registry.json"
    manifest.write_text(json.dumps({"databases": [entry]}), encoding="utf-8")
    context = DatabaseContext.from_manifest(manifest, "fixture")
    public = context.schema_context()
    assert {table["name"] for table in public["tables"]} == {"child", "parent"}
    assert public["relationships"][0]["from_column"] == "parent_id"
    assert "source_path" not in public and "gold_sql" not in public
    with pytest.raises(RegistryError, match="DATABASE_NOT_REGISTERED"):
        DatabaseContext.from_manifest(manifest, "unknown")
    snapshot.write_bytes(b"tampered")
    with pytest.raises(RegistryError, match="SNAPSHOT_CHECKSUM_MISMATCH"):
        DatabaseContext.from_manifest(manifest, "fixture")


def test_reserved_identifiers_blobs_and_identical_rows_preserved(tmp_path):
    import duckdb
    from evaluation.r2_cross_domain_v1.data import build_duckdb_snapshot

    source = tmp_path / "fixture.sqlite"
    with sqlite3.connect(source) as conn:
        conn.execute('CREATE TABLE "order details" ("select" TEXT, "payload" BLOB)')
        conn.executemany('INSERT INTO "order details" VALUES (?, ?)', [(None, b"\x00\xff"), (None, b"\x00\xff")])
    destination = tmp_path / "snapshot.duckdb"
    receipt = build_duckdb_snapshot(source, destination, "reserved")
    with duckdb.connect(str(destination), read_only=True) as conn:
        assert conn.execute('SELECT * FROM "order details"').fetchall() == [(None, b"\x00\xff"), (None, b"\x00\xff")]
    assert receipt["row_counts"] == {"order details": 2}


def test_lossy_decimal_conversion_fails_closed(tmp_path):
    from evaluation.r2_cross_domain_v1.data import RegistryError, build_duckdb_snapshot

    source = tmp_path / "fixture.sqlite"
    with sqlite3.connect(source) as conn:
        conn.execute("CREATE TABLE measurements (quantity DECIMAL)")
        conn.execute("INSERT INTO measurements VALUES (?)", (0.123456789012345,))
    with pytest.raises(RegistryError, match="SNAPSHOT_CONTENT_MISMATCH"):
        build_duckdb_snapshot(source, tmp_path / "snapshot.duckdb", "precision")


def test_rebuild_from_archive_materializes_only_requested_safe_member(tmp_path):
    import zipfile
    from evaluation.r2_cross_domain_v1.data import RegistryError, materialize_archive_member

    archive = tmp_path / "source.zip"
    with zipfile.ZipFile(archive, "w") as handle:
        handle.writestr("source/db.sqlite", b"verified source bytes")
        handle.writestr("../escape.sqlite", b"unsafe")
    target = tmp_path / "sources"
    materialize_archive_member(archive, "source/db.sqlite", target)
    assert (target / "source/db.sqlite").read_bytes() == b"verified source bytes"
    with pytest.raises(RegistryError, match="UNSAFE_ARCHIVE_MEMBER"):
        materialize_archive_member(archive, "../escape.sqlite", target)
    (target / "source/db.sqlite").write_bytes(b"user changes")
    with pytest.raises(RegistryError, match="ARCHIVE_MEMBER_MISMATCH"):
        materialize_archive_member(archive, "source/db.sqlite", target)


def test_prepare_registry_reproducibly_from_synthetic_archive(tmp_path):
    import hashlib
    import json
    import zipfile
    from scripts.prepare_r2_cross_domain import prepare_spider_dev
    from evaluation.r2_cross_domain_v1.data import DatabaseContext

    output = tmp_path / "data"
    metadata = tmp_path / "metadata"
    (output / "sources").mkdir(parents=True)
    metadata.mkdir()
    source = tmp_path / "fixture.sqlite"
    _source_db(source)
    archive = output / "sources" / "source.zip"
    from copy import deepcopy
    basic = {
        "select": [False, [[0, [0, [0, 1, False], None]]]],
        "from": {"table_units": [["table_unit", 0]], "conds": []},
        "where": [], "having": [], "groupBy": [], "orderBy": [], "limit": None,
        "intersect": None, "union": None, "except": None,
    }
    cases = []
    for i in range(12):
        for j in range(8):
            sql = deepcopy(basic)
            if 2 <= j < 6:
                sql["from"]["table_units"].append(["table_unit", 1])
            if j >= 6:
                sql["where"] = [[False, 8, [0, [0, 1, False], None], basic, None]]
            cases.append({"db_id": f"fixture_{i}", "question": f"fixture question {j}", "sql": sql})
    with zipfile.ZipFile(archive, "w") as handle:
        handle.writestr("fixtures/dev.json", json.dumps(cases))
        handle.writestr("fixtures/tables.json", "[]")
        for i in range(12):
            handle.writestr(f"fixtures/database/fixture_{i}/fixture_{i}.sqlite", source.read_bytes())
    manifest = {
        "source_id": "synthetic-fixture-only", "source_version": "fixture", "archive_filename": "source.zip",
        "archive_sha256": hashlib.sha256(archive.read_bytes()).hexdigest(), "archive_sha256_provenance": "fixture",
        "archive_root": "fixtures", "split_member": "fixtures/dev.json", "schema_member": "fixtures/tables.json",
        "sqlite_member_pattern": "fixtures/database/{database_id}/{database_id}.sqlite",
        "license": "fixture-only", "official_project_url": "fixture-only",
    }
    (metadata / "source_manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    receipt = prepare_spider_dev(output, metadata)
    assert receipt["database_count"] == 12
    assert receipt["all_sqlite_duckdb_content_matches"] is True
    registry = json.loads((metadata / "database_registry.json").read_text())
    assert sum(entry["split"] == "calibration" for entry in registry["databases"]) == 4
    assert sum(entry["split"] == "evaluation_locked_candidate" for entry in registry["databases"]) == 8
    for entry in registry["databases"]:
        context = DatabaseContext.from_manifest(metadata / "database_registry.json", entry["database_id"])
        assert context.schema_context()["database_id"] == entry["database_id"]


def test_acquire_archive_checks_manifest_hash_and_preserves_existing_bytes(tmp_path, monkeypatch):
    import hashlib
    import io
    from scripts.prepare_r2_cross_domain import acquire_source_archive
    from evaluation.r2_cross_domain_v1.data import RegistryError

    calls = []
    def download(url, timeout):
        calls.append(url)
        return io.BytesIO(b"fixture archive")
    monkeypatch.setattr("urllib.request.urlopen", download)
    manifest = {
        "download_url": "https://drive.usercontent.google.com/download?id=fixture",
        "archive_sha256": hashlib.sha256(b"fixture archive").hexdigest(),
    }
    target = tmp_path / "archive.zip"
    acquire_source_archive(manifest, target)
    assert target.read_bytes() == b"fixture archive" and len(calls) == 1
    target.write_bytes(b"existing user source")
    with pytest.raises(RegistryError, match="SOURCE_CHECKSUM_MISMATCH"):
        acquire_source_archive(manifest, target)
    assert target.read_bytes() == b"existing user source" and len(calls) == 1


def test_metadata_has_platform_independent_lf_bytes(tmp_path):
    from scripts.prepare_r2_cross_domain import _write_json

    target = tmp_path / "receipt.json"
    _write_json(target, {"source": "fixture"})
    assert b"\r\n" not in target.read_bytes()
