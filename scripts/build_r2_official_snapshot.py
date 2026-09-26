"""Build and independently reproduce the three-source official R2 snapshot."""

from __future__ import annotations

import argparse
import json
import os
import tempfile
from pathlib import Path
from typing import Any

from evaluation.text_to_sql_snapshot import (
    OFFICIAL_SOURCE_IDS,
    build_official_snapshot_lock,
    logical_content_identity,
    sha256_file,
    verify_official_snapshot_contract,
)
from scripts.build_vinsoc_public_snapshot import BUILDER_VERSION, build_snapshot


DEFAULT_BUILDER_PATH = Path("scripts/build_vinsoc_public_snapshot.py")


def _write_json_atomic(path: Path, payload: dict[str, Any]) -> None:
    path = Path(path)
    if path.exists():
        raise ValueError(f"Refusing to overwrite existing artifact: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        "w", encoding="utf-8", dir=path.parent, delete=False
    ) as handle:
        temporary = Path(handle.name)
        json.dump(payload, handle, sort_keys=True, indent=2)
        handle.write("\n")
    os.replace(temporary, path)


def _provenance_source_ids(snapshot_path: Path) -> list[str]:
    import duckdb

    with duckdb.connect(str(snapshot_path), read_only=True) as connection:
        return [
            row[0]
            for row in connection.execute(
                "SELECT dataset_id FROM dataset_provenance ORDER BY dataset_id"
            ).fetchall()
        ]


def build_official_snapshot_pair(
    *,
    dataset_manifest_path: Path,
    receipt_dir: Path,
    snapshot_path: Path,
    snapshot_manifest_path: Path,
    official_lock_path: Path,
    report_path: Path,
    builder_path: Path = DEFAULT_BUILDER_PATH,
    builder_version: str = BUILDER_VERSION,
) -> dict[str, Any]:
    """Build twice, compare logical content, and publish the canonical first build."""
    dataset_manifest_path = Path(dataset_manifest_path)
    receipt_dir = Path(receipt_dir)
    snapshot_path = Path(snapshot_path)
    snapshot_manifest_path = Path(snapshot_manifest_path)
    official_lock_path = Path(official_lock_path)
    report_path = Path(report_path)
    for output in (official_lock_path, report_path):
        if output.exists():
            raise ValueError(f"Refusing to overwrite existing artifact: {output}")

    first_counts = build_snapshot(
        dataset_manifest_path, snapshot_path, snapshot_manifest_path
    )
    first_logical_counts, first_logical_sha = logical_content_identity(snapshot_path)
    if first_counts != first_logical_counts:
        raise ValueError("First build row counts disagree with logical-content scan")
    first_source_ids = _provenance_source_ids(snapshot_path)
    if first_source_ids != list(OFFICIAL_SOURCE_IDS):
        raise ValueError("First build provenance does not contain the approved sources")

    with tempfile.TemporaryDirectory(
        prefix="vinsoc-official-rebuild-", dir=snapshot_path.parent
    ) as temporary_directory:
        temporary_root = Path(temporary_directory)
        second_snapshot = temporary_root / snapshot_path.name
        second_manifest = temporary_root / snapshot_manifest_path.name
        second_counts = build_snapshot(
            dataset_manifest_path, second_snapshot, second_manifest
        )
        second_logical_counts, second_logical_sha = logical_content_identity(second_snapshot)
        if second_counts != second_logical_counts:
            raise ValueError("Second build row counts disagree with logical-content scan")
        if second_counts != first_counts or second_logical_sha != first_logical_sha:
            raise ValueError("Independent official snapshot builds differ logically")
        if _provenance_source_ids(second_snapshot) != first_source_ids:
            raise ValueError("Independent official snapshot provenance differs")
        second_build = {
            "snapshot_binary_sha256": sha256_file(second_snapshot),
            "snapshot_manifest_sha256": sha256_file(second_manifest),
            "snapshot_logical_sha256": second_logical_sha,
            "row_counts": second_counts,
        }

    lock = build_official_snapshot_lock(
        snapshot_path=snapshot_path,
        snapshot_manifest_path=snapshot_manifest_path,
        dataset_manifest_path=dataset_manifest_path,
        receipt_dir=receipt_dir,
        builder_path=Path(builder_path),
        builder_version=builder_version,
    )
    _write_json_atomic(official_lock_path, lock)
    verified = verify_official_snapshot_contract(
        snapshot_path=snapshot_path,
        snapshot_manifest_path=snapshot_manifest_path,
        dataset_manifest_path=dataset_manifest_path,
        receipt_dir=receipt_dir,
        builder_path=Path(builder_path),
        builder_version=builder_version,
        official_lock_path=official_lock_path,
    )
    report = {
        "schema_version": "r2_official_snapshot_build_v1",
        "reproducible": True,
        "expected_source_ids": first_source_ids,
        "dataset_manifest_sha256": lock["dataset_manifest_sha256"],
        "builder_version": builder_version,
        "builder_sha256": lock["builder_sha256"],
        "official_snapshot_lock_sha256": sha256_file(official_lock_path),
        "first_build": {
            "snapshot_binary_sha256": verified["snapshot_binary_sha256"],
            "snapshot_manifest_sha256": verified["snapshot_manifest_sha256"],
            "snapshot_logical_sha256": verified["snapshot_logical_sha256"],
            "row_counts": verified["row_counts"],
        },
        "second_build": second_build,
    }
    _write_json_atomic(report_path, report)
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--dataset-manifest",
        type=Path,
        default=Path("evaluation/text_to_sql_benchmarks/dataset_manifest.json"),
    )
    parser.add_argument(
        "--receipt-dir",
        type=Path,
        default=Path("evaluation/text_to_sql_benchmarks/source_receipts"),
    )
    parser.add_argument(
        "--snapshot",
        type=Path,
        default=Path("data/snapshots/vinsoc_public_v1.duckdb"),
    )
    parser.add_argument(
        "--snapshot-manifest",
        type=Path,
        default=Path("evaluation/text_to_sql_benchmarks/snapshot_manifest.json"),
    )
    parser.add_argument(
        "--official-lock",
        type=Path,
        default=Path("evaluation/text_to_sql_benchmarks/official_snapshot.lock"),
    )
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()
    result = build_official_snapshot_pair(
        dataset_manifest_path=args.dataset_manifest,
        receipt_dir=args.receipt_dir,
        snapshot_path=args.snapshot,
        snapshot_manifest_path=args.snapshot_manifest,
        official_lock_path=args.official_lock,
        report_path=args.report,
    )
    print(json.dumps({
        "reproducible": result["reproducible"],
        "snapshot_logical_sha256": result["first_build"]["snapshot_logical_sha256"],
        "row_counts": result["first_build"]["row_counts"],
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
