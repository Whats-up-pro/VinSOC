"""Audit selected source gold offline; never infer, lock a benchmark or overwrite."""
import argparse
from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path

from sqlglot import parse_one

from evaluation.r2_cross_domain_v1.benchmark import validate_gold_parity
from evaluation.r2_cross_domain_v1.data import DatabaseContext, verify_archive_member, verify_archive_sha256
from evaluation.r2_cross_domain_v1.selection import classify_query, sql_family


def audit_candidates(metadata: Path, source_root: Path, output: Path, *, all_registered=False):
    if output.exists():
        raise ValueError("OUTPUT_ALREADY_EXISTS")
    manifest_path = metadata / "source_manifest.json"
    registry_path = metadata / "database_registry.json"
    inventory_path = metadata / "external_candidate_inventory.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    archive = source_root / manifest["archive_filename"]
    verify_archive_sha256(archive, manifest["archive_sha256"])
    dev = source_root / manifest["split_member"]
    verify_archive_member(archive, manifest["split_member"], dev)
    selected = json.loads(inventory_path.read_text(encoding="utf-8"))
    source = json.loads(dev.read_text(encoding="utf-8"))
    original = {}
    for case in source:
        identity = json.dumps({"db_id": case["db_id"], "question": " ".join(case["question"].split()), "sql": case["sql"]}, sort_keys=True)
        case_id = "external_" + case["db_id"] + "_" + hashlib.sha256(identity.encode()).hexdigest()[:16]
        if case_id in original and original[case_id]["query"] != case["query"]:
            raise ValueError("DUPLICATE_ID_CONFLICTING_GOLD")
        original[case_id] = case
    contexts, database_splits = {}, {}
    for entry in json.loads(registry_path.read_text(encoding="utf-8"))["databases"]:
        database_id = entry["database_id"]
        sqlite_path = source_root / entry["source_sqlite_member"]
        verify_archive_member(archive, entry["source_sqlite_member"], sqlite_path)
        contexts[database_id] = (DatabaseContext.from_manifest(registry_path, database_id), sqlite_path)
        database_splits[database_id] = "calibration" if entry["split"] == "calibration" else "evaluation"
    if all_registered:
        selected = {"calibration": [], "evaluation": []}
        for case_id, case in original.items():
            if case["db_id"] in contexts:
                selected[database_splits[case["db_id"]]].append({
                    "case_id": case_id, "database_id": case["db_id"], "question": case["question"],
                    "family_id": sql_family(case["sql"]), **classify_query(case["sql"]),
                })
    results = []
    for split in ("calibration", "evaluation"):
        for candidate in selected[split]:
            row = {**candidate, "split": split, "source_query": original[candidate["case_id"]]["query"]}
            context, sqlite_path = contexts[candidate["database_id"]]
            try:
                tree = parse_one(row["source_query"], read="sqlite")
                comparator = "ordered_rows" if tree.args.get("order") else "unordered_multiset"
                row.update(validate_gold_parity(row["source_query"], sqlite_path, context, comparator))
                row["status"] = "BASE_PARITY_VERIFIED" if row["parity"] else "GOLD_RESULT_PARITY_MISMATCH"
            except Exception as error:
                row["status"] = "GOLD_AUDIT_BLOCKED"
                row["error_code"] = str(error) if isinstance(error, ValueError) else type(error).__name__
            results.append(row)
    qualification = {}
    for database_id, split in database_splits.items():
        valid = [row for row in results if row["database_id"] == database_id and row["status"] == "BASE_PARITY_VERIFIED"]
        counts = Counter(row["difficulty"] for row in valid)
        qualification[database_id] = {"split": split, "base_parity_verified_count": len(valid),
            "difficulty_counts": dict(counts), "quota_eligible": len(valid) >= 4 if split == "calibration" else all(counts[level] >= n for level, n in (("basic", 2), ("medium", 4), ("advanced", 2)))}
    report = {
        "scope": "All source questions in the twelve registered databases" if all_registered else "Selected external candidates only, not a locked 96-case benchmark",
        "audited_at_utc": datetime.now(timezone.utc).isoformat(),
        "source_archive_sha256": manifest["archive_sha256"],
        "manifest_sha256": hashlib.sha256(manifest_path.read_bytes()).hexdigest(),
        "registry_sha256": hashlib.sha256(registry_path.read_bytes()).hexdigest(),
        "candidate_inventory_sha256": hashlib.sha256(inventory_path.read_bytes()).hexdigest(),
        "adapter_sha256": hashlib.sha256(Path("evaluation/r2_cross_domain_v1/benchmark.py").read_bytes()).hexdigest(),
        "result_semantics_sha256": hashlib.sha256(Path("evaluation/r2_cross_domain_v1/semantic_scoring.py").read_bytes()).hexdigest(),
        "case_count": len(results), "status_counts": dict(Counter(row["status"] for row in results)),
        "database_gold_qualification": qualification,
        "all_registered_database_quotas_met": all(row["quota_eligible"] for row in qualification.values()) if all_registered else None,
        "all_selected_external_base_gold_parity_verified": all(row["status"] == "BASE_PARITY_VERIFIED" for row in results),
        "benchmark_locked": False, "paid_gate_open": False,
        "external_model_calls": 0, "new_inference_cost_usd": 0,
        "case_results": results,
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2, default=str) + "\n", encoding="utf-8", newline="\n")
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--metadata", type=Path, default=Path("evaluation/r2_cross_domain_v1"))
    parser.add_argument("--sources", type=Path, default=Path("data/r2_cross_domain_v1/sources"))
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--all-registered", action="store_true")
    args = parser.parse_args()
    report = audit_candidates(args.metadata, args.sources, args.output, all_registered=args.all_registered)
    print(json.dumps({key: report[key] for key in ("case_count", "status_counts", "all_selected_external_base_gold_parity_verified", "external_model_calls", "new_inference_cost_usd")}))
    return 0 if report["all_selected_external_base_gold_parity_verified"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
