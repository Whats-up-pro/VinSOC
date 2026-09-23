"""Immutable snapshot identity contract for R2 Text-to-SQL evaluation."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
import re


_SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")
_MANIFEST_FIELDS = {"snapshot_id", "path", "sha256", "schema_version"}


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
