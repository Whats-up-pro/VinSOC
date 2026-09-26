"""Validate the normalized CTI load using the exact encrypted run-5 source bytes."""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import sys
import tempfile
import zipfile
from pathlib import Path
from typing import Any

from evaluation.text_to_sql_snapshot import sha256_file
from scripts.build_vinsoc_public_snapshot import (
    BUILDER_VERSION,
    _bulk_insert_rows,
    normalize_threatfox_csv_with_diagnostics,
)
from vinsoc_data.duckdb_store import SocSnapshotBuilder

SOURCE_RUN_ID = 36235433476
SOURCE_ARTIFACT_ID = 10904266318
SOURCE_ARTIFACT_DIGEST = (
    "sha256:a3858d1a92f15b70fc0d629a46f7c6eff6763caffde8b43077eabff74186d8f8"
)
SOURCE_CIPHERTEXT_SHA256 = (
    "b39c70b47bdef1c9668d3dde250ad11880516744ebb7edd98748fc8eded61f65"
)
EXPECTED_THREATFOX_ZIP_SHA256 = (
    "0aa5b4371970bc4fd16c111cc65b2a7a54c744a810fa15054206640de36260ac"
)
EXPECTED_THREATFOX_FULL_CSV_SHA256 = (
    "5df2498e5abc1d5f9c1564d16b6f00618611943cba7cc25dab12b2ed5c5ccd46"
)
EXPECTED_NORMALIZED_ROWS = 107834
_GIT_SHA_PATTERN = re.compile(r"^[0-9a-f]{40}$")
_NULLABLE_CTI_FIELDS = (
    "threat_type",
    "malware_printable",
    "confidence_level",
    "first_seen",
    "last_seen",
    "reference_url",
)


class Run5CtiValidationError(RuntimeError):
    """A source-value-free validation failure."""


def _safe_fail(message: str) -> None:
    raise Run5CtiValidationError(message) from None


def _write_json_atomic(path: Path, payload: dict[str, Any]) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        "w", encoding="utf-8", dir=path.parent, delete=False
    ) as handle:
        temporary_path = Path(handle.name)
        json.dump(payload, handle, sort_keys=True, indent=2)
        handle.write("\n")
    os.replace(temporary_path, path)


def _extract_verified_full_csv(archive_path: Path, destination: Path) -> None:
    if sha256_file(archive_path) != EXPECTED_THREATFOX_ZIP_SHA256:
        _safe_fail("ThreatFox ZIP identity mismatch")
    destination.parent.mkdir(parents=True, exist_ok=True)
    try:
        with (
            zipfile.ZipFile(archive_path) as archive,
            archive.open("full.csv") as source,
            destination.open("wb") as target,
        ):
            shutil.copyfileobj(source, target, length=1024 * 1024)
    except (KeyError, OSError, zipfile.BadZipFile):
        _safe_fail("ThreatFox archive extraction failed")
    if sha256_file(destination) != EXPECTED_THREATFOX_FULL_CSV_SHA256:
        _safe_fail("ThreatFox full.csv identity mismatch")


def _aggregate_loaded_rows(snapshot_path: Path) -> dict[str, Any]:
    import duckdb

    null_expressions = ", ".join(
        f"COUNT(*) FILTER (WHERE {field} IS NULL) AS {field}"
        for field in _NULLABLE_CTI_FIELDS
    )
    with duckdb.connect(str(snapshot_path), read_only=True) as connection:
        loaded_rows, distinct_ids = connection.execute(
            "SELECT COUNT(*), COUNT(DISTINCT source_row_id) FROM cti_indicators"
        ).fetchone()
        null_values = connection.execute(
            f"SELECT {null_expressions} FROM cti_indicators"
        ).fetchone()
    return {
        "loaded_cti_rows": loaded_rows,
        "distinct_source_row_id": distinct_ids,
        "nullable_field_null_counts": dict(zip(_NULLABLE_CTI_FIELDS, null_values)),
    }


def _fixed_identity() -> dict[str, Any]:
    return {
        "source_run_id": SOURCE_RUN_ID,
        "source_artifact_id": SOURCE_ARTIFACT_ID,
        "source_artifact_digest": SOURCE_ARTIFACT_DIGEST,
        "ciphertext_sha256": SOURCE_CIPHERTEXT_SHA256,
        "threatfox_zip_sha256": EXPECTED_THREATFOX_ZIP_SHA256,
        "threatfox_full_csv_sha256": EXPECTED_THREATFOX_FULL_CSV_SHA256,
    }


def validate_run5_cti_load(
    *,
    threatfox_zip_path: Path,
    output_path: Path,
    working_directory: Path,
    git_sha: str,
) -> dict[str, Any]:
    """Normalize and load only CTI, returning credential-free aggregate evidence."""
    if not _GIT_SHA_PATTERN.fullmatch(git_sha):
        _safe_fail("Git SHA is not an exact commit identity")
    working_directory = Path(working_directory)
    working_directory.mkdir(parents=True, exist_ok=True)
    full_csv_path = working_directory / "full.csv"
    snapshot_path = working_directory / "run5-cti-validation.duckdb"
    _extract_verified_full_csv(Path(threatfox_zip_path), full_csv_path)

    rows, diagnostics = normalize_threatfox_csv_with_diagnostics(
        full_csv_path, "threatfox_full"
    )
    if diagnostics["data_rows_seen"] != EXPECTED_NORMALIZED_ROWS:
        _safe_fail("Unexpected ThreatFox source row count")
    if diagnostics["rows_accepted"] != EXPECTED_NORMALIZED_ROWS:
        _safe_fail("Unexpected ThreatFox normalized row count")
    if diagnostics["rows_rejected"] != 0:
        _safe_fail("ThreatFox normalization rejected rows")

    SocSnapshotBuilder(snapshot_path).create_empty_snapshot()
    loaded = _bulk_insert_rows(
        snapshot_path, "cti_indicators", rows, working_directory
    )
    aggregates = _aggregate_loaded_rows(snapshot_path)
    if loaded != EXPECTED_NORMALIZED_ROWS:
        _safe_fail("Bulk loader returned an unexpected row count")
    if aggregates["loaded_cti_rows"] != EXPECTED_NORMALIZED_ROWS:
        _safe_fail("DuckDB contains an unexpected CTI row count")
    if aggregates["distinct_source_row_id"] != EXPECTED_NORMALIZED_ROWS:
        _safe_fail("ThreatFox source_row_id values are not unique")

    builder_path = Path(__file__).with_name("build_vinsoc_public_snapshot.py")
    result = {
        "schema_version": "r2_run5_cti_load_validation_v1",
        "status": "passed",
        "git_sha": git_sha,
        "input_identity": _fixed_identity(),
        "builder": {
            "version": BUILDER_VERSION,
            "sha256": sha256_file(builder_path),
        },
        "normalized_rows": diagnostics["rows_accepted"],
        **aggregates,
    }
    _write_json_atomic(Path(output_path), result)
    return result


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--threatfox-zip", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--work-dir", type=Path, required=True)
    parser.add_argument("--git-sha", required=True)
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    try:
        validate_run5_cti_load(
            threatfox_zip_path=args.threatfox_zip,
            output_path=args.output,
            working_directory=args.work_dir,
            git_sha=args.git_sha.strip().lower(),
        )
    except Exception:  # noqa: BLE001 - never emit source-bearing provider errors
        _write_json_atomic(
            args.output,
            {
                "schema_version": "r2_run5_cti_load_validation_v1",
                "status": "failed",
                "git_sha": args.git_sha.strip().lower(),
                "input_identity": _fixed_identity(),
                "failure": {"category": "run5_cti_validation_error"},
            },
        )
        print("Run-5 CTI load validation failed; inspect aggregate evidence.", file=sys.stderr)
        return 1
    print("Run-5 CTI load validation passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
