"""Prepare reproducible Spider-dev source receipts and registry snapshots offline."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import uuid
import urllib.request
from urllib.parse import urlsplit
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from evaluation.r2_cross_domain_v1.data import (
    RegistryError,
    build_duckdb_snapshot,
    inspect_sqlite,
    select_database_ids,
    validate_registry_entries,
    verify_archive_sha256,
    materialize_archive_member,
)
from evaluation.r2_cross_domain_v1.selection import qualification_report, select_external_candidates


SELECTION_SEED = 20261005


def acquire_source_archive(manifest: dict[str, Any], archive: Path) -> str:
    """Download only the manifest URL once, verify bytes, and preserve existing files."""
    if archive.exists():
        return verify_archive_sha256(archive, manifest["archive_sha256"])
    url = manifest["download_url"]
    parsed = urlsplit(url)
    if parsed.scheme != "https" or parsed.hostname != "drive.usercontent.google.com" or parsed.username or parsed.password:
        raise RegistryError("UNAPPROVED_SOURCE_URL")
    archive.parent.mkdir(parents=True, exist_ok=True)
    partial = archive.with_suffix(archive.suffix + ".partial")
    with urllib.request.urlopen(url, timeout=60) as response, partial.open("xb") as handle:
        while chunk := response.read(1024 * 1024):
            handle.write(chunk)
    observed = verify_archive_sha256(partial, manifest["archive_sha256"])
    partial.rename(archive)
    return observed


def _read_json(path: Path) -> Any:
    with path.open(encoding="utf-8") as handle:
        return json.load(handle)


def _write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n")


def _content_sha256(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


def prepare_spider_dev(output: Path, metadata: Path) -> dict[str, Any]:
    """Verify acquired Spider bytes, then make two independent DuckDB builds per DB."""
    manifest_path = metadata / "source_manifest.json"
    if not manifest_path.is_file():
        raise RegistryError(f"SOURCE_MANIFEST_MISSING: {manifest_path}")
    manifest = _read_json(manifest_path)
    archive = output / "sources" / manifest["archive_filename"]
    archive_sha256 = acquire_source_archive(manifest, archive)
    source_root = output / "sources" / manifest["archive_root"]
    dev_path = source_root / "dev.json"
    member_hashes = {
        member: materialize_archive_member(archive, member, output / "sources")
        for member in (manifest["split_member"], manifest["schema_member"])
    }
    dev_cases = _read_json(dev_path)
    if not isinstance(dev_cases, list) or not dev_cases or any(
        not isinstance(case, dict) or not all(key in case for key in ("db_id", "question", "sql"))
        for case in dev_cases
    ):
        raise RegistryError("INVALID_SOURCE_CASE_CONTRACT")
    question_counts = Counter(case["db_id"] for case in dev_cases if case.get("question"))

    inspections: dict[str, dict[str, Any]] = {}
    exclusions: list[dict[str, str]] = []
    for database_id in sorted(question_counts):
        sqlite_path = source_root / "database" / database_id / f"{database_id}.sqlite"
        member = manifest["sqlite_member_pattern"].format(database_id=database_id)
        member_hashes[member] = materialize_archive_member(archive, member, output / "sources")
        try:
            inspections[database_id] = inspect_sqlite(sqlite_path)
        except RegistryError as error:
            exclusions.append({"database_id": database_id, "reason": str(error)})

    qualification = qualification_report(dev_cases)
    for database_id, inspection in inspections.items():
        inspection["evaluation_quota_eligible"] = qualification["databases"][database_id]["evaluation_quota_eligible"]
    selected = select_database_ids(inspections, question_counts, count=12, seed=SELECTION_SEED)
    calibration_ids, evaluation_ids = selected[:4], selected[4:]
    selected_set = set(selected)
    for database_id in sorted(inspections):
        if database_id not in selected_set:
            if question_counts[database_id] < 8:
                reason = "QUESTION_COUNT_LT_8"
            elif len(inspections[database_id]["schema"]) < 2:
                reason = "SINGLE_TABLE"
            elif not inspections[database_id]["relationships"]:
                reason = "NO_FOREIGN_KEY"
            elif not inspections[database_id]["evaluation_quota_eligible"]:
                reason = "DIFFICULTY_QUOTA_UNMET"
            else:
                reason = "NOT_SELECTED_BY_HASH_ORDER"
            exclusions.append({"database_id": database_id, "reason": reason})

    registry: list[dict[str, Any]] = []
    receipts: list[dict[str, Any]] = []
    build_id = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ") + "_" + uuid.uuid4().hex[:8]
    for database_id in selected:
        sqlite_path = source_root / "database" / database_id / f"{database_id}.sqlite"
        first_path = output / "snapshots" / build_id / database_id / "build_1.duckdb"
        second_path = output / "snapshots" / build_id / database_id / "build_2.duckdb"
        first = build_duckdb_snapshot(sqlite_path, first_path, database_id)
        second = build_duckdb_snapshot(sqlite_path, second_path, database_id)
        for field in (
            "logical_sha256",
            "schema",
            "relationships",
            "row_counts",
            "snapshot_row_counts",
            "duckdb_content_sha256",
            "source_sha256",
        ):
            if first[field] != second[field]:
                raise RegistryError(f"NONDETERMINISTIC_LOGICAL_BUILD: {database_id}:{field}")
        split = "calibration" if database_id in calibration_ids else "evaluation_locked_candidate"
        registry_entry = {
            "database_id": database_id,
            "source_version": manifest["source_version"],
            "source_dialect": "sqlite",
            "target_dialect": "duckdb",
            "split": split,
            "question_count_dev": question_counts[database_id],
            "source_sha256": first["source_sha256"],
            "schema": first["schema"],
            "snapshot_path": Path(os.path.relpath(first_path, metadata)).as_posix(),
            "duckdb_binary_sha256": first["duckdb_binary_sha256"],
            "duckdb_content_sha256": first["duckdb_content_sha256"],
            "logical_sha256": first["logical_sha256"],
            "row_counts": first["row_counts"],
            "relationships": first["relationships"],
            "primary_keys": first["primary_keys"],
            "tables": [table["name"] for table in first["schema"]],
            "source_sqlite_member": manifest["sqlite_member_pattern"].format(database_id=database_id),
        }
        registry.append(registry_entry)
        receipt = {
            "database_id": database_id,
            "build_1": {
                key: first[key]
                for key in ("duckdb_binary_sha256", "duckdb_content_sha256", "logical_sha256", "source_sha256")
            },
            "build_2": {
                key: second[key]
                for key in ("duckdb_binary_sha256", "duckdb_content_sha256", "logical_sha256", "source_sha256")
            },
            "logical_identity_matches": True,
            "sqlite_duckdb_content_matches": first["source_content_sha256"] == first["duckdb_content_sha256"],
            "reopened_read_only": first["snapshot_read_only_verified"] and second["snapshot_read_only_verified"],
            "source_sqlite_member": registry_entry["source_sqlite_member"],
        }
        _write_json(metadata / "build_receipts" / f"{database_id}.json", receipt)
        receipts.append(receipt)

    validate_registry_entries(registry)
    candidate_selection = select_external_candidates(dev_cases, registry, seed=SELECTION_SEED)
    for database_id, record in qualification["databases"].items():
        record["sqlite_readable"] = database_id in inspections
        record["selected"] = database_id in selected_set
    _write_json(metadata / "external_candidate_inventory.json", candidate_selection)
    _write_json(metadata / "source_qualification.json", qualification)
    source_receipt = {
        "source_id": manifest["source_id"],
        "source_version": manifest["source_version"],
        "prepared_at_utc": datetime.now(UTC).isoformat(),
        "archive_sha256": archive_sha256,
        "verified_member_hashes": member_hashes,
        "build_id": build_id,
        "archive_sha256_provenance": manifest["archive_sha256_provenance"],
        "archive_filename": manifest["archive_filename"],
        "license": manifest["license"],
        "official_project_url": manifest["official_project_url"],
        "selected_database_ids": selected,
        "calibration_database_ids": calibration_ids,
        "evaluation_database_ids": evaluation_ids,
        "selection_seed": SELECTION_SEED,
        "dev_case_count": len(dev_cases),
        "dev_database_count": len(question_counts),
    }
    _write_json(metadata / "source_receipts" / "spider_dev.json", source_receipt)
    _write_json(
        metadata / "database_registry.json",
        {
            "status": "REGISTRY_ONLY_NOT_BENCHMARK_LOCKED",
            "selection_seed": SELECTION_SEED,
            "database_count": len(registry),
            "conversion_rules": {
                "sqlite_integer": "BIGINT",
                "sqlite_real": "DOUBLE",
                "sqlite_numeric_decimal": "DECIMAL(38, 10)",
                "sqlite_text_and_dates": "VARCHAR; date/time text is not coerced during this registry task",
                "nulls_and_duplicate_rows": "preserved by parameterized insertion",
            },
            "domain_annotation_status": "PENDING_CASE_AND_BENCHMARK_LOCK_TASK",
            "databases": registry,
        },
    )
    _write_json(metadata / "selection_exclusions.json", sorted(exclusions, key=lambda item: (item["database_id"], item["reason"])))
    parity = {
        "database_count": len(registry),
        "all_logical_identities_match": all(receipt["logical_identity_matches"] for receipt in receipts),
        "all_sqlite_duckdb_content_matches": all(receipt["sqlite_duckdb_content_matches"] for receipt in receipts),
        "gold_sql_dialect_parity": "PENDING_BENCHMARK_QUALIFICATION_TASK_3",
        "registry_content_sha256": _content_sha256(registry),
        "note": "Binary hashes identify each build; logical hashes compare source content across independent builds.",
    }
    _write_json(metadata / "parity_report.json", parity)
    return parity


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", required=True, choices=("spider-dev",))
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--metadata", required=True, type=Path)
    args = parser.parse_args()
    try:
        result = prepare_spider_dev(args.output, args.metadata)
    except RegistryError as error:
        print(f"PREPARE_FAILED: {error}")
        return 2
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
