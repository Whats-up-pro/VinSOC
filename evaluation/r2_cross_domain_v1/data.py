"""Read-only SQLite inspection and deterministic DuckDB snapshot building."""

from __future__ import annotations

import hashlib
import json
import sqlite3
import zipfile
from collections import Counter
from contextlib import closing
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path, PurePosixPath
from typing import Any

import duckdb


class RegistryError(ValueError):
    """Raised when a registry or source database violates the offline contract."""


def verify_archive_sha256(archive: Path, expected_sha256: str) -> str:
    """Verify acquired source bytes before any parsing or conversion."""
    archive = Path(archive)
    if not archive.is_file():
        raise RegistryError("SOURCE_ARCHIVE_MISSING")
    observed = hashlib.sha256(archive.read_bytes()).hexdigest()
    if len(expected_sha256) != 64 or observed.lower() != expected_sha256.lower():
        raise RegistryError("SOURCE_CHECKSUM_MISMATCH")
    return observed


def verify_archive_member(archive: Path, member: str, extracted: Path) -> str:
    """Bind a parsed file to a unique member of the previously verified archive."""
    with zipfile.ZipFile(archive) as handle:
        if handle.namelist().count(member) != 1:
            raise RegistryError(f"ARCHIVE_MEMBER_MISSING_OR_DUPLICATE: {member}")
        expected = hashlib.sha256(handle.read(member)).hexdigest()
    if not extracted.is_file() or hashlib.sha256(extracted.read_bytes()).hexdigest() != expected:
        raise RegistryError(f"ARCHIVE_MEMBER_MISMATCH: {member}")
    return expected


def materialize_archive_member(archive: Path, member: str, target_root: Path) -> str:
    """Extract exactly one relative member; never overwrite an existing source file."""
    parts = PurePosixPath(member)
    if parts.is_absolute() or ".." in parts.parts or "\\" in member or ":" in member:
        raise RegistryError("UNSAFE_ARCHIVE_MEMBER")
    root = target_root.resolve()
    target = (root / member).resolve()
    if not target.is_relative_to(root):
        raise RegistryError("UNSAFE_ARCHIVE_MEMBER")
    if not target.exists():
        with zipfile.ZipFile(archive) as handle:
            if handle.namelist().count(member) != 1:
                raise RegistryError(f"ARCHIVE_MEMBER_MISSING_OR_DUPLICATE: {member}")
            target.parent.mkdir(parents=True, exist_ok=True)
            with target.open("xb") as output:
                output.write(handle.read(member))
    return verify_archive_member(archive, member, target)


def _quote(identifier: str) -> str:
    return '"' + identifier.replace('"', '""') + '"'


def _canonical(value: Any) -> Any:
    if isinstance(value, (int, float, Decimal)) and not isinstance(value, bool):
        number = Decimal(str(value))
        if not number.is_finite():
            raise RegistryError("NONFINITE_NUMBER_UNSUPPORTED")
        rendered = format(number, "f")
        if "." in rendered:
            rendered = rendered.rstrip("0").rstrip(".")
        return {"__number__": "0" if number == 0 else rendered}
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    if isinstance(value, bytes):
        return {"__bytes_hex__": value.hex()}
    return {"__repr__": repr(value)}


def _sqlite_type(type_name: str) -> str:
    normalized = (type_name or "").upper()
    if "INT" in normalized:
        return "BIGINT"
    if any(token in normalized for token in ("REAL", "FLOA", "DOUB")):
        return "DOUBLE"
    if any(token in normalized for token in ("NUM", "DEC")):
        return "DECIMAL(38, 10)"
    if "BLOB" in normalized:
        return "BLOB"
    return "VARCHAR"


def _read_sqlite(source: Path) -> tuple[list[dict[str, Any]], list[dict[str, Any]], dict[str, list[tuple[Any, ...]]]]:
    uri = f"file:{source.resolve().as_posix()}?mode=ro"
    with closing(sqlite3.connect(uri, uri=True)) as connection:
        tables = [
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table' AND name NOT LIKE 'sqlite_%' ORDER BY name"
            )
        ]
        if not tables:
            raise RegistryError(f"No user tables in SQLite source: {source}")

        schema: list[dict[str, Any]] = []
        relationships: list[dict[str, Any]] = []
        rows: dict[str, list[tuple[Any, ...]]] = {}
        for table in tables:
            columns = []
            for cid, name, type_name, not_null, default, primary_key_position in connection.execute(
                f"PRAGMA table_info({_quote(table)})"
            ):
                columns.append(
                    {
                        "ordinal": cid,
                        "name": name,
                        "sqlite_type": type_name or "",
                        "duckdb_type": _sqlite_type(type_name),
                        "not_null": bool(not_null),
                        "default": default,
                        "primary_key_position": primary_key_position,
                    }
                )
            schema.append({"name": table, "columns": columns})
            for fk in connection.execute(f"PRAGMA foreign_key_list({_quote(table)})"):
                _, _sequence, referenced_table, from_column, to_column, _on_update, _on_delete, _match = fk
                relationships.append(
                    {
                        "from_table": table,
                        "from_column": from_column,
                        "to_table": referenced_table,
                        "to_column": to_column,
                    }
                )
            rows[table] = list(connection.execute(f"SELECT * FROM {_quote(table)}"))
    return schema, sorted(relationships, key=lambda item: json.dumps(item, sort_keys=True)), rows


def _logical_hash(database_id: str, schema: list[dict[str, Any]], relationships: list[dict[str, Any]], rows: dict[str, list[tuple[Any, ...]]]) -> str:
    payload = {
        "database_id": database_id,
        "schema": schema,
        "relationships": relationships,
        "rows": {
            table: sorted(
                [list(map(_canonical, row)) for row in table_rows],
                key=lambda row: json.dumps(row, ensure_ascii=False, separators=(",", ":")),
            )
            for table, table_rows in sorted(rows.items())
        },
    }
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _snapshot_content_hash(database_id: str, schema: list[dict[str, Any]], rows: dict[str, list[tuple[Any, ...]]]) -> str:
    payload = {
        "database_id": database_id,
        "schema": [{"name": table["name"], "columns": [column["name"] for column in table["columns"]]} for table in schema],
        "rows": {
            table: sorted(
                [list(map(_canonical, row)) for row in table_rows],
                key=lambda row: json.dumps(row, ensure_ascii=False, separators=(",", ":")),
            )
            for table, table_rows in sorted(rows.items())
        },
    }
    return hashlib.sha256(
        json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


def _verify_duckdb_snapshot(
    destination: Path,
    schema: list[dict[str, Any]],
    database_id: str,
    expected_logical_sha256: str | None = None,
    relationships: list[dict[str, Any]] | None = None,
) -> tuple[dict[str, int], str]:
    """Reopen the created DuckDB file read-only and hash its actual rows."""
    connection = duckdb.connect(str(destination), read_only=True)
    try:
        actual_tables = {row[0] for row in connection.execute("SELECT table_name FROM information_schema.tables WHERE table_schema='main' AND table_type='BASE TABLE'").fetchall()}
        if actual_tables != {table["name"] for table in schema}:
            raise RegistryError("CATALOG_SCHEMA_MISMATCH")
        for table in schema:
            actual = connection.execute(f"PRAGMA table_info({_quote(table['name'])})").fetchall()
            actual_columns = [(row[1], row[2].replace(" ", "")) for row in actual]
            expected_columns = [(column["name"], column["duckdb_type"].replace(" ", "")) for column in table["columns"]]
            if actual_columns != expected_columns:
                raise RegistryError("CATALOG_SCHEMA_MISMATCH")
        rows = {
            table["name"]: connection.execute(f"SELECT * FROM {_quote(table['name'])}").fetchall()
            for table in schema
        }
    finally:
        connection.close()
    counts = {table: len(table_rows) for table, table_rows in sorted(rows.items())}
    if expected_logical_sha256 is not None and _logical_hash(database_id, schema, relationships or [], rows) != expected_logical_sha256:
        raise RegistryError("CATALOG_LOGICAL_IDENTITY_MISMATCH")
    return counts, _snapshot_content_hash(database_id, schema, rows)


def inspect_sqlite(source: Path) -> dict[str, Any]:
    """Return schema/content identity without opening SQLite read-write."""
    source = Path(source)
    if not source.is_file():
        raise RegistryError(f"SQLite source is missing: {source}")
    try:
        schema, relationships, rows = _read_sqlite(source)
    except sqlite3.Error as error:
        raise RegistryError(f"SQLITE_READ_FAILED: {source.name}: {type(error).__name__}") from error
    return {
        "source_sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
        "schema": schema,
        "relationships": relationships,
        "row_counts": {table: len(table_rows) for table, table_rows in sorted(rows.items())},
        "logical_sha256": _logical_hash(source.stem, schema, relationships, rows),
    }


def build_duckdb_snapshot(source: Path, destination: Path, database_id: str) -> dict[str, Any]:
    """Build a DuckDB snapshot from SQLite bytes using an explicit type mapping."""
    source = Path(source)
    destination = Path(destination)
    if not database_id:
        raise RegistryError("database_id is required")
    if destination.exists():
        raise RegistryError("SNAPSHOT_ALREADY_EXISTS")
    schema, relationships, rows = _read_sqlite(source)
    destination.parent.mkdir(parents=True, exist_ok=True)

    connection = duckdb.connect(str(destination))
    try:
        for table in schema:
            columns = table["columns"]
            definition = ", ".join(
                f"{_quote(column['name'])} {column['duckdb_type']}" for column in columns
            )
            connection.execute(f"CREATE TABLE {_quote(table['name'])} ({definition})")
            if rows[table["name"]]:
                placeholders = ", ".join("?" for _ in columns)
                connection.executemany(
                    f"INSERT INTO {_quote(table['name'])} VALUES ({placeholders})",
                    rows[table["name"]],
                )
    finally:
        connection.close()

    source_sha256 = hashlib.sha256(source.read_bytes()).hexdigest()
    snapshot_row_counts, duckdb_content_sha256 = _verify_duckdb_snapshot(destination, schema, database_id)
    expected_row_counts = {table: len(table_rows) for table, table_rows in sorted(rows.items())}
    if snapshot_row_counts != expected_row_counts:
        raise RegistryError("SNAPSHOT_ROW_COUNT_MISMATCH")
    source_content_sha256 = _snapshot_content_hash(database_id, schema, rows)
    if duckdb_content_sha256 != source_content_sha256:
        raise RegistryError(f"SNAPSHOT_CONTENT_MISMATCH: {database_id}")
    return {
        "database_id": database_id,
        "source_path": source.as_posix(),
        "source_sha256": source_sha256,
        "duckdb_binary_sha256": hashlib.sha256(destination.read_bytes()).hexdigest(),
        "schema": schema,
        "relationships": relationships,
        "primary_keys": {
            table["name"]: [
                column["name"]
                for column in table["columns"]
                if column["primary_key_position"]
            ]
            for table in schema
        },
        "row_counts": expected_row_counts,
        "snapshot_row_counts": snapshot_row_counts,
        "duckdb_content_sha256": duckdb_content_sha256,
        "source_content_sha256": source_content_sha256,
        "snapshot_read_only_verified": True,
        "logical_sha256": _logical_hash(database_id, schema, relationships, rows),
    }


def select_database_ids(
    table_metadata: dict[str, dict[str, Any]] | list[dict[str, Any]],
    question_counts: Counter[str] | dict[str, int],
    *,
    count: int,
    seed: int,
) -> list[str]:
    """Select qualified databases by a stable hash order, independent of filesystem order."""
    if count <= 0:
        raise RegistryError("count must be positive")
    if isinstance(table_metadata, list):
        ids = [entry.get("db_id") for entry in table_metadata]
        if any(not database_id for database_id in ids) or len(ids) != len(set(ids)):
            raise RegistryError("DUPLICATE_DATABASE_ID")
        if any(database_id not in question_counts for database_id in ids):
            raise RegistryError("SOURCE_DB_MISSING")
        table_metadata = {entry["db_id"]: entry for entry in table_metadata}
    qualified = []
    for database_id, metadata in table_metadata.items():
        if not database_id or question_counts[database_id] < 8:
            continue
        if len(metadata.get("schema", [])) < 2 or not metadata.get("relationships"):
            continue
        if metadata.get("evaluation_quota_eligible") is False:
            continue
        qualified.append(database_id)
    if len(qualified) < count:
        raise RegistryError(f"Only {len(qualified)} qualified databases; need {count}")
    return sorted(qualified, key=lambda database_id: hashlib.sha256(f"{seed}:{database_id}".encode()).hexdigest())[:count]


def validate_registry_entries(entries: list[dict[str, Any]]) -> None:
    """Fail closed for duplicate IDs and missing source identity evidence."""
    identifiers = [entry.get("database_id") for entry in entries]
    if any(not identifier for identifier in identifiers) or len(set(identifiers)) != len(identifiers):
        raise RegistryError("Registry database_id values must be present and unique")
    for entry in entries:
        if not entry.get("source_sha256") or not entry.get("logical_sha256"):
            raise RegistryError(f"Registry entry lacks source identity: {entry['database_id']}")


def describe_existing_snapshot(snapshot: Path, database_id: str, source_identity: dict) -> dict:
    """Bind an already verified source receipt to existing read-only bytes.

    This does not build data or certify the supplied source receipt. Callers must
    run their source validator first. Its source_type/scope remain explicit; a
    manifest digest must never be relabeled as a SQLite or source-member digest.
    The generic logical identity is separate from any originating legacy hash.
    """
    if not database_id or not source_identity.get('source_type') or not source_identity.get('source_sha256_scope'):
        raise RegistryError('EXPLICIT_SOURCE_IDENTITY_REQUIRED')
    if len(source_identity.get('source_sha256', '')) != 64:
        raise RegistryError('EXPLICIT_SOURCE_IDENTITY_REQUIRED')
    snapshot = Path(snapshot)
    binary = hashlib.sha256(snapshot.read_bytes()).hexdigest()
    schema, relationships, rows, primary_keys = [], [], {}, {}
    with duckdb.connect(str(snapshot), read_only=True, config={'enable_external_access':False, 'threads':1}) as connection:
        tables = sorted(row[0] for row in connection.execute("SELECT table_name FROM information_schema.tables WHERE table_schema='main' AND table_type='BASE TABLE'").fetchall())
        if not tables:
            raise RegistryError('EMPTY_SNAPSHOT')
        for table in tables:
            keys = connection.execute("SELECT constraint_column_names FROM duckdb_constraints() WHERE table_name=? AND constraint_type='PRIMARY KEY'", [table]).fetchall()
            key = keys[0][0] if len(keys) == 1 else []
            primary_keys[table] = key
            columns = [{'ordinal':r[0], 'name':r[1], 'duckdb_type':r[2], 'not_null':r[3], 'default':r[4],
                        'primary_key_position':key.index(r[1])+1 if r[1] in key else 0}
                       for r in connection.execute(f'PRAGMA table_info({_quote(table)})').fetchall()]
            schema.append({'name':table, 'columns':columns})
            rows[table] = connection.execute(f'SELECT * FROM {_quote(table)}').fetchall()
            fk = connection.execute("SELECT constraint_column_names, referenced_table, referenced_column_names FROM duckdb_constraints() WHERE table_name=? AND constraint_type='FOREIGN KEY'", [table]).fetchall()
            for from_cols, target, to_cols in fk:
                if len(from_cols) != 1:
                    raise RegistryError('COMPOSITE_EXISTING_FOREIGN_KEY_UNSUPPORTED')
                relationships.append({'from_table':table, 'from_column':from_cols[0], 'to_table':target, 'to_column':to_cols[0]})
    if hashlib.sha256(snapshot.read_bytes()).hexdigest() != binary:
        raise RegistryError('SNAPSHOT_CHANGED_DURING_INSPECTION')
    return {**source_identity, 'database_id':database_id, 'schema':schema, 'relationships':relationships,
            'primary_keys':primary_keys, 'row_counts':{table:len(value) for table,value in rows.items()},
            'duckdb_binary_sha256':binary, 'logical_sha256':_logical_hash(database_id, schema, relationships, rows),
            'logical_identity_policy':'cross_domain_typed_row_multiset_v1',
            'duckdb_content_sha256':_snapshot_content_hash(database_id, schema, rows), 'snapshot_read_only_verified':True}


@dataclass(frozen=True)
class DatabaseContext:
    """Verified database identity and public multi-table catalog for runtime tools."""

    database_id: str
    snapshot_path: Path
    identity: dict[str, Any]

    @classmethod
    def from_manifest(cls, path: Path, database_id: str) -> DatabaseContext:
        path = Path(path)
        manifest = json.loads(path.read_text(encoding="utf-8"))
        entries = manifest["databases"]
        validate_registry_entries(entries)
        selected = next((entry for entry in entries if entry["database_id"] == database_id), None)
        if selected is None:
            raise RegistryError("DATABASE_NOT_REGISTERED")
        snapshot = (path.parent / selected["snapshot_path"]).resolve()
        expected = selected.get("duckdb_binary_sha256")
        if not expected or not snapshot.is_file() or hashlib.sha256(snapshot.read_bytes()).hexdigest() != expected:
            raise RegistryError("SNAPSHOT_CHECKSUM_MISMATCH")
        counts, content = _verify_duckdb_snapshot(snapshot, selected["schema"], database_id, selected["logical_sha256"], selected["relationships"])
        if counts != selected["row_counts"] or content != selected["duckdb_content_sha256"]:
            raise RegistryError("SNAPSHOT_CONTENT_MISMATCH")
        return cls(database_id, snapshot, selected)

    def schema_context(self) -> dict[str, Any]:
        return {
            "database_id": self.database_id,
            "snapshot_identity": self.identity["logical_sha256"],
            "tables": self.identity["schema"],
            "primary_keys": self.identity["primary_keys"],
            "relationships": self.identity["relationships"],
        }
