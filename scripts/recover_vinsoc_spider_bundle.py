"""Recover pinned Spider data under a new identity; never replace historical locks.

Run from the repository: python -m scripts.recover_vinsoc_spider_bundle --repo .
This is offline gold/data validation, never a model evaluation or paid release.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import sys
import tempfile
import zipfile
from collections import Counter
from copy import deepcopy
from datetime import UTC, datetime
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import duckdb

from evaluation.r2_cross_domain_v1.benchmark import ReferenceCase, validate_gold_parity
from evaluation.r2_cross_domain_v1.benchmark_lock import (
    FIELDS,
    file_hash,
    select_oracle,
    validate_inventory,
    verify_runtime,
)
from evaluation.r2_cross_domain_v1.data import (
    DatabaseContext,
    RegistryError,
    build_duckdb_snapshot,
    materialize_archive_member,
    verify_archive_sha256,
)
from evaluation.r2_cross_domain_v1.semantic_scoring import score_case
from scripts.prepare_r2_cross_domain import acquire_source_archive

VERSION = "r2_cross_domain_spider_recovery_v1"
IDENTITY_FIELDS = (
    "source_sha256", "logical_sha256", "duckdb_content_sha256",
    "schema", "relationships", "row_counts", "primary_keys",
)


def assert_recovered_identity(expected, observed):
    """Require all original content identities, allowing only new binary bytes."""
    for field in IDENTITY_FIELDS:
        if expected[field] != observed[field]:
            raise RegistryError("RECOVERY_IDENTITY_MISMATCH:" + field)


def verify_closed_snapshot(path, expected):
    if Path(str(path) + ".wal").exists():
        raise RegistryError("RECOVERY_WAL_PRESENT")
    if file_hash(path) != expected:
        raise RegistryError("RECOVERY_BINARY_CHANGED")


def write_new(path, value):
    with path.open("x", encoding="utf-8", newline="\n") as handle:
        json.dump(value, handle, indent=2, sort_keys=True)
        handle.write("\n")


def baseline(repo):
    base = repo / "evaluation/r2_cross_domain_v1"
    lock = json.loads((base / "benchmark.lock.json").read_text(encoding="utf-8"))
    for name, expected in lock["files"].items():
        if file_hash(repo / name) != expected:
            raise RegistryError("PROTECTED_DATA_IDENTITY_MISMATCH:" + name)
    changed = [name for name, expected in lock["source_files"].items()
               if file_hash(repo / name, portable=True) != expected]
    # This existing executor adapter is separately bound by the current runtime.
    if set(changed) - {"evaluation/r2_cross_domain_v1/tools.py"}:
        raise RegistryError("PROTECTED_SCORER_OR_PRIMITIVE_CHANGED")
    registry = json.loads((base / "runtime_registry.json").read_text(encoding="utf-8"))
    if file_hash(base / "runtime_registry.json") != lock["registry_sha256"]:
        raise RegistryError("HISTORICAL_REGISTRY_IDENTITY_MISMATCH")
    entries = registry["databases"]
    if len(entries) != 13 or len({e["database_id"] for e in entries}) != 13:
        raise RegistryError("RECOVERY_DATABASE_SET_INCOMPLETE")
    refs = [json.loads(p.read_text(encoding="utf-8"))
            for p in sorted((base / "benchmarks/references").glob("*/*.json"))]
    inventory = validate_inventory(refs)
    runtime = []
    for split in ("calibration", "evaluation"):
        runtime += json.loads((base / f"benchmarks/{split}_runtime.json").read_text(encoding="utf-8"))
    verify_runtime(refs, runtime)
    if json.loads((base / "benchmarks/oracle_subset.json").read_text())["case_ids"] != select_oracle(refs):
        raise RegistryError("ORACLE_SUBSET_IDENTITY_MISMATCH")
    source = json.loads((base / "source_manifest.json").read_text(encoding="utf-8"))
    receipt = json.loads((base / "source_receipts/spider_dev.json").read_text(encoding="utf-8"))
    if set(receipt["selected_database_ids"]) != {e["database_id"] for e in entries if e["database_id"] != "ctu_dev"}:
        raise RegistryError("ORIGINAL_DATABASE_SELECTION_MISMATCH")
    return base, lock, registry, refs, inventory, source, receipt, changed


def recover(repo, output, archive=None, *, check_only=False):
    repo = repo.resolve()
    output = (repo / output).resolve()
    recovery_root = (repo / ".vinsoc").resolve()
    if not output.is_relative_to(recovery_root) or output == recovery_root:
        raise RegistryError("OUTPUT_OUTSIDE_RECOVERY_ROOT")
    base, old_lock, original, refs, inventory, source, source_receipt, changed = baseline(repo)
    input_archive = Path(archive).resolve() if archive is not None else output / "sources" / source["archive_filename"]
    if check_only:
        if not input_archive.is_file():
            raise RegistryError("SOURCE_ARCHIVE_MISSING")
        verify_archive_sha256(input_archive, source["archive_sha256"])
        return {"status": "SOURCE_VERIFIED_READY_FOR_RECOVERY", "external_model_calls": 0,
                "historical_data_files_verified": len(old_lock["files"]), "full_data_gate_pass": False}
    if output.exists():
        raise RegistryError("RECOVERY_OUTPUT_ALREADY_EXISTS")
    if duckdb.__version__ != "1.5.5":
        raise RegistryError("PINNED_DUCKDB_1_5_5_REQUIRED")
    output.mkdir(parents=True)
    try:
        sources = output / "sources"
        sources.mkdir()
        target_archive = sources / source["archive_filename"]
        if archive is None:
            acquire_source_archive(source, target_archive)
        else:
            verify_archive_sha256(input_archive, source["archive_sha256"])
            shutil.copyfile(input_archive, target_archive)
        verify_archive_sha256(target_archive, source["archive_sha256"])
        members = [source["split_member"], source["schema_member"]]
        members += [e["source_sqlite_member"] for e in original["databases"] if e["database_id"] != "ctu_dev"]
        member_hashes = {}
        for member in members:
            observed = materialize_archive_member(target_archive, member, sources)
            if observed != source_receipt["verified_member_hashes"][member]:
                raise RegistryError("ORIGINAL_SOURCE_MEMBER_MISMATCH:" + member)
            member_hashes[member] = observed
        registry = deepcopy(original)
        registry.update(version=VERSION, status="RECOVERED_RUNTIME_NOT_PAID_RELEASE", database_count=13)
        builds, blockers = [], []
        for entry in registry["databases"]:
            identifier = entry["database_id"]
            destination = output / "snapshots" / identifier / "build_1.duckdb"
            if identifier == "ctu_dev":
                historical = (base / entry["snapshot_path"]).resolve()
                if not historical.is_file():
                    blockers.append({"database_id": identifier, "status": "EXACT_CTU_BINARY_MISSING",
                                     "expected_sha256": entry["duckdb_binary_sha256"]})
                    entry["snapshot_path"] = Path(os.path.relpath(historical, output)).as_posix()
                    continue
                if Path(str(historical) + ".wal").exists():
                    raise RegistryError("CTU_WAL_PRESENT")
                DatabaseContext.from_manifest(base / "runtime_registry.json", identifier)
                from evaluation.ctu_network_public.contract import validate
                if validate(historical)["logical_snapshot_sha256"] != entry["origin_logical_sha256"]:
                    raise RegistryError("CTU_ORIGIN_IDENTITY_MISMATCH")
                destination.parent.mkdir(parents=True)
                shutil.copyfile(historical, destination)
            else:
                # Build outside the synced checkout. File synchronization can
                # resurrect a deleted transient WAL while the build is closing.
                # Only closed, verified binary bytes enter the delivery tree.
                with tempfile.TemporaryDirectory(prefix="vinsoc-spider-build-") as work:
                    staged = Path(work) / "snapshot.duckdb"
                    built = build_duckdb_snapshot(sources / entry["source_sqlite_member"], staged, identifier)
                    verify_closed_snapshot(staged, built["duckdb_binary_sha256"])
                    destination.parent.mkdir(parents=True)
                    with staged.open("rb") as src, destination.open("xb") as dst:
                        shutil.copyfileobj(src, dst)
                verify_closed_snapshot(destination, built["duckdb_binary_sha256"])
                assert_recovered_identity(entry, built)
                builds.append({"database_id": identifier, "original_binary_status": "EXACT_BINARY_UNAVAILABLE_ON_THIS_HOST",
                               "historical_binary_sha256": entry["duckdb_binary_sha256"],
                               "recovered_binary_sha256": built["duckdb_binary_sha256"],
                               "logical_sha256": built["logical_sha256"],
                               "duckdb_content_sha256": built["duckdb_content_sha256"],
                               "all_original_content_identities_verified": True})
                entry["duckdb_binary_sha256"] = built["duckdb_binary_sha256"]
            entry["snapshot_path"] = destination.relative_to(output).as_posix()
        registry_path = output / "runtime_registry.json"
        write_new(registry_path, registry)
        contexts = {e["database_id"]: DatabaseContext.from_manifest(registry_path, e["database_id"])
                    for e in registry["databases"] if e["database_id"] not in {b["database_id"] for b in blockers}}
        replay = []
        for ref in refs:
            if ref["database_id"] not in contexts:
                continue
            context = contexts[ref["database_id"]]
            if ref.get("source_gold_sql"):
                parity = validate_gold_parity(ref["source_gold_sql"], sources / context.identity["source_sqlite_member"], context, ref["comparator"])
                if not parity["parity"] or parity["adapted_sql"] != ref["gold_sql"]:
                    raise RegistryError("RECOVERED_GOLD_PARITY_MISMATCH:" + ref["case_id"])
            reference = ReferenceCase(**{key: ref[key] for key in FIELDS})
            record = score_case(reference, {"final_sql": ref["gold_sql"], "error_category": "OK"},
                                [{"instance_id": "recovered_base", "context": context, "fixture_only": False}])
            if not record["execution_accurate"]:
                raise RegistryError("RECOVERED_BASE_GOLD_FAILED:" + ref["case_id"])
            replay.append({"case_id": ref["case_id"], "database_id": ref["database_id"],
                           "split": ref["split"], "gold_execution_verified": True})
        # Verify preservation again after all actual reads/builds/query executions.
        baseline(repo)
        for context in contexts.values():
            verify_closed_snapshot(context.snapshot_path, context.identity["duckdb_binary_sha256"])
        receipt = {"version": VERSION, "scope": "offline_source_recovery_and_gold_validation_not_model_score",
                   "status": "SPIDER_RECOVERED_CTU_PENDING" if blockers else "ALL_120_GOLD_VALIDATED_RECOVERY_IDENTITY",
                   "created_at_utc": datetime.now(UTC).isoformat(), "external_model_calls": 0,
                   "paid_authorized": False, "full_data_gate_pass": not blockers,
                   "runtime_worker_gate_pass": False, "historical_data_files_verified": len(old_lock["files"]),
                   "historical_runtime_changed_files": changed, "historical_code_lock_pass": not changed,
                   "inventory": inventory, "recovered_spider_databases": len(builds),
                   "planned_gold_cases": 120, "base_gold_replayed": len(replay),
                   "replayed_by_split": dict(Counter(r["split"] for r in replay)),
                   "pending_gold_case_ids": [r["case_id"] for r in refs if r["database_id"] not in contexts],
                   "blockers": blockers, "builds": builds, "gold_replay": replay,
                   "source_attribution": {k: source[k] for k in ("source_id", "source_version", "license", "official_project_url", "archive_sha256")}}
        write_new(output / "recovery_receipt.json", receipt)
        recovery_lock = {"version": VERSION, "paid_authorized": False, "external_model_calls_at_lock": 0,
                         "approval": "User approved separately versioned recovery on 2026-10-10 before new model output",
                         "historical_benchmark_lock_sha256": file_hash(base / "benchmark.lock.json"),
                         "preserved_historical_files": old_lock["files"], "verified_source_members": member_hashes,
                         "registry_sha256": file_hash(registry_path), "receipt_sha256": file_hash(output / "recovery_receipt.json"),
                         "files": {p.relative_to(output).as_posix(): file_hash(p) for p in sorted(output.rglob("*")) if p.is_file()}}
        write_new(output / "recovery.lock.json", recovery_lock)
        bundle = output / "VinSOC_Spider_Recovery_v1.zip"
        with zipfile.ZipFile(bundle, "x", compression=zipfile.ZIP_DEFLATED) as handle:
            for p in sorted(output.rglob("*")):
                if p.is_file() and p != bundle:
                    handle.write(p, p.relative_to(output).as_posix())
        with zipfile.ZipFile(bundle) as handle:
            for name, expected in recovery_lock["files"].items():
                if hashlib.sha256(handle.read(name)).hexdigest() != expected:
                    raise RegistryError("BUNDLE_MEMBER_IDENTITY_MISMATCH")
            if hashlib.sha256(handle.read("recovery.lock.json")).hexdigest() != file_hash(output / "recovery.lock.json"):
                raise RegistryError("BUNDLE_LOCK_IDENTITY_MISMATCH")
        write_new(output / "bundle_receipt.json", {"bundle": bundle.name, "sha256": file_hash(bundle),
                  "database_count": len(contexts), "includes_pinned_source_archive": True})
        return receipt
    except Exception as error:
        write_new(output / "failure_receipt.json", {"status": "FAILED_RECOVERY_PRESERVED_PARTIAL",
                  "safe_error_type": type(error).__name__, "external_model_calls": 0, "paid_authorized": False})
        raise


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", required=True, type=Path)
    parser.add_argument("--output", type=Path, default=Path(".vinsoc/spider-recovery-v1"))
    parser.add_argument("--archive", type=Path)
    parser.add_argument("--check-only", action="store_true")
    args = parser.parse_args()
    try:
        receipt = recover(args.repo, args.output, args.archive, check_only=args.check_only)
    except (ValueError, OSError, duckdb.Error, zipfile.BadZipFile) as error:
        print(json.dumps({"status": "BLOCKED_" + str(error) if isinstance(error, RegistryError) else "FAILED_RECOVERY",
                          "safe_error_type": type(error).__name__, "external_model_calls": 0, "paid_authorized": False}))
        return 1
    print(json.dumps({k: receipt[k] for k in ("status", "external_model_calls", "full_data_gate_pass")}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
