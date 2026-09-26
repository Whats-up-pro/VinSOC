"""Immutable snapshot identity contract for R2 Text-to-SQL evaluation."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time
from decimal import Decimal
import hashlib
import json
from pathlib import Path
import re
from typing import Any


_SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")
_MANIFEST_FIELDS = {"snapshot_id", "path", "sha256", "schema_version"}
OFFICIAL_SNAPSHOT_TABLES = (
    "cti_indicators",
    "network_flows",
    "sysmon_process_events",
)
OFFICIAL_SOURCE_IDS = (
    "ctu13_s3",
    "otrf_apt29_day1",
    "threatfox_full",
)
_OFFICIAL_LOCK_FIELDS = {
    "schema_version",
    "snapshot_id",
    "dataset_manifest_sha256",
    "source_receipt_sha256",
    "source_file_sha256",
    "expected_source_ids",
    "builder_file",
    "builder_version",
    "builder_sha256",
    "snapshot_manifest_sha256",
    "snapshot_binary_sha256",
    "snapshot_logical_sha256",
    "row_counts",
}


@dataclass(frozen=True)
class SnapshotManifest:
    snapshot_id: str
    path: str
    sha256: str
    schema_version: str


def sha256_file(path: Path) -> str:
    """Return the lowercase SHA-256 digest of one file."""
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_snapshot_manifest(path: Path) -> SnapshotManifest:
    """Load and validate the closed R2 snapshot-manifest shape."""
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(payload, dict) or set(payload) != _MANIFEST_FIELDS:
        raise ValueError("Snapshot manifest must contain exactly the required fields")
    if not all(isinstance(payload[field], str) and payload[field] for field in _MANIFEST_FIELDS):
        raise ValueError("Snapshot manifest fields must be non-empty strings")
    if payload["schema_version"] != "1":
        raise ValueError("Unsupported snapshot manifest schema_version")
    if not _SHA256_PATTERN.fullmatch(payload["sha256"]):
        raise ValueError("Snapshot manifest sha256 must be 64 lowercase hex characters")
    return SnapshotManifest(**payload)


def verify_snapshot(path: Path, manifest: SnapshotManifest) -> None:
    """Fail closed unless path, snapshot ID, and file digest match the manifest."""
    actual_path = Path(path).resolve()
    expected_path = Path(manifest.path).resolve()
    if actual_path != expected_path:
        raise ValueError(
            f"Snapshot path mismatch: expected {expected_path}, received {actual_path}"
        )
    if manifest.snapshot_id != expected_path.stem:
        raise ValueError(
            "Snapshot snapshot_id must match the canonical snapshot filename"
        )
    if not actual_path.is_file():
        raise ValueError(f"Snapshot file does not exist: {actual_path}")
    actual_sha256 = sha256_file(actual_path)
    if actual_sha256 != manifest.sha256:
        raise ValueError(
            f"Snapshot SHA-256 mismatch: expected {manifest.sha256}, received {actual_sha256}"
        )


def _canonical_value(value: Any) -> Any:
    if isinstance(value, (datetime, date, time)):
        return {"type": type(value).__name__, "value": value.isoformat()}
    if isinstance(value, Decimal):
        return {"type": "decimal", "value": str(value)}
    if isinstance(value, bytes):
        return {"type": "bytes", "value": value.hex()}
    return value


def logical_content_identity(snapshot_path: Path) -> tuple[dict[str, int], str]:
    """Hash canonical schema and ordered rows for the three official R2 tables.

    DuckDB file bytes can vary with physical layout. This identity deliberately
    describes normalized benchmark content, including column names and types,
    while ordering rows by their stable source identity.
    """
    try:
        import duckdb
    except ImportError as exc:  # pragma: no cover - declared dependency
        raise RuntimeError("DuckDB is required to identify snapshot content") from exc

    snapshot_path = Path(snapshot_path)
    if not snapshot_path.is_file():
        raise ValueError(f"Snapshot file does not exist: {snapshot_path}")
    digest = hashlib.sha256()
    counts: dict[str, int] = {}
    with duckdb.connect(str(snapshot_path), read_only=True) as connection:
        present = {name for (name,) in connection.execute("SHOW TABLES").fetchall()}
        missing = sorted(set(OFFICIAL_SNAPSHOT_TABLES) - present)
        if missing:
            raise ValueError(f"Official snapshot is missing table(s): {', '.join(missing)}")
        for table in OFFICIAL_SNAPSHOT_TABLES:
            description = connection.execute(f"DESCRIBE {table}").fetchall()
            schema = [[row[0], row[1]] for row in description]
            digest.update(
                (json.dumps({"table": table, "schema": schema}, separators=(",", ":")) + "\n")
                .encode("utf-8")
            )
            cursor = connection.execute(
                f"SELECT * FROM {table} ORDER BY source_dataset, source_row_id"
            )
            count = 0
            while batch := cursor.fetchmany(4096):
                for row in batch:
                    if not row[0] or not row[1]:
                        raise ValueError(f"{table} contains a row without source identity")
                    canonical = [_canonical_value(value) for value in row]
                    digest.update(
                        (json.dumps(canonical, ensure_ascii=False, separators=(",", ":")) + "\n")
                        .encode("utf-8")
                    )
                    count += 1
            counts[table] = count
    return counts, digest.hexdigest()


def _load_dataset_source_contract(
    dataset_manifest_path: Path,
    receipt_dir: Path,
) -> tuple[list[str], dict[str, str], dict[str, str]]:
    payload = json.loads(Path(dataset_manifest_path).read_text(encoding="utf-8"))
    if not isinstance(payload, dict) or set(payload) != {"schema_version", "sources"}:
        raise ValueError("Official dataset manifest has an invalid shape")
    if payload["schema_version"] != "1" or not isinstance(payload["sources"], list):
        raise ValueError("Official dataset manifest schema_version is unsupported")
    sources = payload["sources"]
    source_ids = sorted(source.get("dataset_id") for source in sources if isinstance(source, dict))
    if source_ids != list(OFFICIAL_SOURCE_IDS) or len(sources) != len(OFFICIAL_SOURCE_IDS):
        raise ValueError("Official dataset manifest must contain exactly the three approved sources")

    source_hashes: dict[str, str] = {}
    receipt_hashes: dict[str, str] = {}
    for source in sources:
        dataset_id = source["dataset_id"]
        source_hash = source.get("file_sha256")
        if not isinstance(source_hash, str) or not _SHA256_PATTERN.fullmatch(source_hash):
            raise ValueError(f"Invalid source SHA-256 for {dataset_id}")
        receipt_path = Path(receipt_dir) / f"{dataset_id}.json"
        if not receipt_path.is_file():
            raise ValueError(f"Source receipt does not exist: {receipt_path}")
        receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
        if (
            receipt.get("dataset_id") != dataset_id
            or receipt.get("status") != "verified_bytes"
            or receipt.get("canonical_source_url") != source.get("source_url")
        ):
            raise ValueError(f"Source receipt metadata mismatch for {dataset_id}")
        receipt_hash_options = {
            section.get("sha256")
            for name in ("transport", "ingest")
            if isinstance((section := receipt.get(name)), dict)
        }
        if source_hash not in receipt_hash_options:
            raise ValueError(f"Source receipt does not bind manifest bytes for {dataset_id}")
        archive_member = source.get("archive_member")
        receipt_member = receipt.get("ingest", {}).get("archive_member")
        if archive_member is not None and archive_member != receipt_member:
            raise ValueError(f"Source archive member mismatch for {dataset_id}")
        source_hashes[dataset_id] = source_hash
        receipt_hashes[dataset_id] = sha256_file(receipt_path)
    return source_ids, source_hashes, receipt_hashes


def build_official_snapshot_lock(
    *,
    snapshot_path: Path,
    snapshot_manifest_path: Path,
    dataset_manifest_path: Path,
    receipt_dir: Path,
    builder_path: Path,
    builder_version: str,
) -> dict[str, Any]:
    """Build the exact official snapshot identity from verified local artifacts."""
    if not isinstance(builder_version, str) or not builder_version:
        raise ValueError("builder_version must be a non-empty string")
    builder_path = Path(builder_path)
    if not builder_path.is_file():
        raise ValueError(f"Snapshot builder does not exist: {builder_path}")
    manifest = load_snapshot_manifest(Path(snapshot_manifest_path))
    verify_snapshot(Path(snapshot_path), manifest)
    source_ids, source_hashes, receipt_hashes = _load_dataset_source_contract(
        Path(dataset_manifest_path), Path(receipt_dir)
    )
    row_counts, logical_sha256 = logical_content_identity(Path(snapshot_path))
    return {
        "schema_version": "r2_official_snapshot_v1",
        "snapshot_id": manifest.snapshot_id,
        "dataset_manifest_sha256": sha256_file(Path(dataset_manifest_path)),
        "source_receipt_sha256": receipt_hashes,
        "source_file_sha256": source_hashes,
        "expected_source_ids": source_ids,
        "builder_file": builder_path.as_posix(),
        "builder_version": builder_version,
        "builder_sha256": sha256_file(builder_path),
        "snapshot_manifest_sha256": sha256_file(Path(snapshot_manifest_path)),
        "snapshot_binary_sha256": manifest.sha256,
        "snapshot_logical_sha256": logical_sha256,
        "row_counts": row_counts,
    }


def load_official_snapshot_lock(path: Path) -> dict[str, Any]:
    """Load a closed official-snapshot lock shape without trusting its values."""
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(payload, dict) or set(payload) != _OFFICIAL_LOCK_FIELDS:
        raise ValueError("Official snapshot lock must contain exactly the required fields")
    if payload.get("schema_version") != "r2_official_snapshot_v1":
        raise ValueError("Unsupported official snapshot lock schema_version")
    for field in (
        "dataset_manifest_sha256",
        "builder_sha256",
        "snapshot_manifest_sha256",
        "snapshot_binary_sha256",
        "snapshot_logical_sha256",
    ):
        if not isinstance(payload.get(field), str) or not _SHA256_PATTERN.fullmatch(payload[field]):
            raise ValueError(f"Official snapshot lock {field} is not a SHA-256 digest")
    for field in ("source_receipt_sha256", "source_file_sha256"):
        values = payload.get(field)
        if not isinstance(values, dict) or sorted(values) != list(OFFICIAL_SOURCE_IDS):
            raise ValueError(f"Official snapshot lock {field} source IDs mismatch")
        if not all(isinstance(value, str) and _SHA256_PATTERN.fullmatch(value) for value in values.values()):
            raise ValueError(f"Official snapshot lock {field} contains an invalid digest")
    if payload.get("expected_source_ids") != list(OFFICIAL_SOURCE_IDS):
        raise ValueError("Official snapshot lock expected_source_ids mismatch")
    counts = payload.get("row_counts")
    if not isinstance(counts, dict) or tuple(counts) != OFFICIAL_SNAPSHOT_TABLES:
        raise ValueError("Official snapshot lock row_counts table set mismatch")
    if not all(isinstance(value, int) and not isinstance(value, bool) and value > 0 for value in counts.values()):
        raise ValueError("Official snapshot lock row_counts must be positive integers")
    for field in ("snapshot_id", "builder_file", "builder_version"):
        if not isinstance(payload.get(field), str) or not payload[field]:
            raise ValueError(f"Official snapshot lock {field} must be a non-empty string")
    return payload


def verify_official_snapshot_contract(
    *,
    snapshot_path: Path,
    snapshot_manifest_path: Path,
    dataset_manifest_path: Path,
    receipt_dir: Path,
    builder_path: Path,
    builder_version: str,
    official_lock_path: Path,
) -> dict[str, Any]:
    """Fail closed unless every source, builder, binary and logical identity matches."""
    expected = load_official_snapshot_lock(Path(official_lock_path))
    actual = build_official_snapshot_lock(
        snapshot_path=Path(snapshot_path),
        snapshot_manifest_path=Path(snapshot_manifest_path),
        dataset_manifest_path=Path(dataset_manifest_path),
        receipt_dir=Path(receipt_dir),
        builder_path=Path(builder_path),
        builder_version=builder_version,
    )
    if actual != expected:
        changed = sorted(key for key in expected if expected.get(key) != actual.get(key))
        raise ValueError(f"Official snapshot identity mismatch: {', '.join(changed)}")
    return actual
