"""Offline replay of the eight immutable public_dev v1 SQL predictions.

The v1 report and lock stay untouched. No provider is created or called.
"""

from __future__ import annotations

import argparse
import json
from dataclasses import asdict
from pathlib import Path

from evaluation.public_pilot.contract import (
    R2, ROOT, build_lock, canonical_sha256, validate, verify_locked_files,
)
from evaluation.text_to_sql import (
    SQLBenchmarkCase, _sql_error_category, aggregate_sql_metrics, evaluate_sql_case,
)
from evaluation.text_to_sql_snapshot import sha256_file
from vinsoc_data.duckdb_store import DuckDBSnapshot


SOURCE_REPORT = Path("results/evaluation_v1/public_pilot/public-r2.json")
SOURCE_SHA256 = "0bac8abd8523eb5fe7faaa90e1708fee779ba217acead125b71fb90d4c72f636"
SCORER_VERSION = "r2_public_dev_replay_scorer_v2_terminal_semicolon"


def replay_saved_predictions(saved: list[dict], cases: list[SQLBenchmarkCase],
                             snapshot: DuckDBSnapshot) -> tuple[list[dict], dict]:
    """Score the saved SQL, retaining each immutable v1 verdict alongside v2."""
    ids = [item.get("case_id") for item in saved]
    expected = [case.case_id for case in cases]
    if len(ids) != len(expected) or len(set(ids)) != len(ids) or set(ids) != set(expected):
        raise ValueError("Saved case IDs do not match the locked split")
    by_id = {item["case_id"]: item for item in saved}
    evaluations = []
    rows = []
    for case in cases:
        original = by_id[case.case_id]
        sql = original.get("generated_sql")
        if not isinstance(sql, str) or not sql.strip():
            raise ValueError(f"Missing saved SQL for {case.case_id}")
        result = evaluate_sql_case(case, sql, snapshot)
        evaluations.append(result)
        rows.append({
            "case_id": case.case_id, "category": case.category,
            "difficulty": case.difficulty, "generated_sql": sql,
            "v1": {key: original.get(key) for key in (
                "error_category", "syntax_valid", "execution_success",
                "execution_accurate", "safety_rejected", "error",
            )},
            "v2": {"error_category": _sql_error_category(result), **asdict(result)},
        })
        rows[-1]["v2"].pop("case_id")
    return rows, aggregate_sql_metrics(evaluations)


def replay(snapshot_path: Path, source_path: Path = SOURCE_REPORT) -> dict:
    """Verify original report, source, split, snapshot and new scorer before replay."""
    if sha256_file(source_path) != SOURCE_SHA256:
        raise ValueError("Immutable v1 JSON report SHA-256 does not match")
    source = json.loads(source_path.read_text(encoding="utf-8"))
    if (source.get("track"), source.get("split"), source.get("run_status")) != (
        "r2", "public_dev", "completed",
    ) or not source.get("pilot_eligible"):
        raise ValueError("Source report is not the completed public_dev R2 pilot")
    lock = json.loads((ROOT / "VERSION.lock").read_text(encoding="utf-8"))
    if source.get("scorer_file_sha256") != lock["scorer_file_sha256"]:
        raise ValueError("Original scorer file hashes changed")
    if source.get("scorer_sha256") != canonical_sha256(lock["scorer_file_sha256"]):
        raise ValueError("Original scorer digest is inconsistent")
    current = build_lock(snapshot_path)
    for key, value in lock.items():
        if key != "scorer_file_sha256" and current.get(key) != value:
            raise ValueError(f"Pilot source, snapshot or split hash changed: {key}")
    if (source.get("snapshot_content_sha256") != lock["snapshot_content_sha256"]
            or source.get("source_file_sha256") != lock["source_file_sha256"]
            or source.get("benchmark_split_sha256") != lock["r2_split_sha256"]):
        raise ValueError("Original report does not match v1 version lock")
    # Validation expects the lock to include the current scorer hashes. Make a
    # temporary copy so it can recheck evidence and all eight gold SQL queries
    # without modifying the historic v1 VERSION.lock.
    import tempfile
    with tempfile.TemporaryDirectory(prefix="vinsoc-r2-replay-") as temp:
        updated = Path(temp) / "lock.json"
        updated.write_text(json.dumps(current), encoding="utf-8")
        gold_validation = validate(snapshot_path, lock_path=updated)
    if gold_validation["gold_results"] != source["gold_validation"]:
        raise ValueError("Gold query results changed from the original report")
    files = verify_locked_files(R2, lock["r2_split_sha256"])
    cases = [SQLBenchmarkCase.from_dict(item) for item in files.values()]
    if len(cases) != 8 or source.get("case_ids") != [c.case_id for c in cases]:
        raise ValueError("Source report is missing or reordering locked case IDs")
    if source.get("case_count") != 8 or source.get("provider_metadata", {}).get("total_calls") != 8:
        raise ValueError("Source report is not the complete 8-call baseline")
    rows, metrics = replay_saved_predictions(source["case_results"], cases, DuckDBSnapshot(snapshot_path))
    scorer_files = {**current["scorer_file_sha256"],
                    "scripts/replay_r2_public_pilot.py": sha256_file(Path(__file__))}
    return {
        "track": "r2", "split": "public_dev", "benchmark_version": lock["version"],
        "replay_mode": "offline_saved_predictions", "model_api_calls": 0,
        "additional_cost_usd": 0.0, "source_report_sha256": SOURCE_SHA256,
        "original_evaluator_commit_sha": source["evaluator_commit_sha"],
        "original_scorer_sha256": source["scorer_sha256"],
        "scorer_version": SCORER_VERSION, "scorer_file_sha256": scorer_files,
        "scorer_sha256": canonical_sha256(scorer_files),
        "source_file_sha256": lock["source_file_sha256"],
        "benchmark_split_sha256": lock["r2_split_sha256"],
        "snapshot_content_sha256": lock["snapshot_content_sha256"],
        "snapshot_binary_sha256": sha256_file(snapshot_path),
        "case_ids": [c.case_id for c in cases], "case_count": 8,
        "original_metrics_v1": source["metrics"], "replay_metrics_v2": metrics,
        "case_results": rows,
        "semantic_counterexamples": {
            "public_sql_003": "Missing source_dataset filter: cross-scenario fixture changes result",
            "public_sql_008": "LIKE versus ILIKE: mixed-case process-image fixture changes result",
        },
        "interpretation": "Execution equality on this snapshot does not prove SQL semantic equivalence.",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--snapshot", type=Path, required=True)
    parser.add_argument("--source-report", type=Path, default=SOURCE_REPORT)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    report = replay(args.snapshot, args.source_report)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    temporary = args.out.with_suffix(".tmp")
    temporary.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    temporary.replace(args.out)
    print(json.dumps({"replay_metrics_v2": report["replay_metrics_v2"],
                      "case_count": report["case_count"],
                      "scorer_sha256": report["scorer_sha256"],
                      "model_api_calls": 0}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
