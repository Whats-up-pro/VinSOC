"""v2 experiment - separate from v1, uses v2 prompts and runner."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from evaluation.dualsql_lite_ctu_gpt5_v2.prompts import (
    GENERATOR_PROMPT_VERSION, LINKER_PROMPT_VERSION,
)
from evaluation.dualsql_lite_ctu_gpt5_v2.runner import run_case, run_role
from evaluation.dualsql_lite_ctu_gpt5_v2.tools import V2DatabaseTools, TOOL_VERSION
from evaluation.text_to_sql import SQLBenchmarkCase

CONDITIONS = ["E0", "E1", "E2", "E3"]
SERIES_VERSION = "dualsql_lite_ctu_gpt5_v2"


def create_client():
    """No live client until a separate paid plan implements every pre-run gate."""
    raise RuntimeError("PAID_EXECUTION_DISABLED")


def load_cases(cases_dir: Path) -> list[SQLBenchmarkCase]:
    """Load cases from directory."""
    cases = []
    for path in sorted(cases_dir.glob("*.json")):
        with open(path) as f:
            data = json.load(f)
        cases.append(SQLBenchmarkCase.from_dict(data))
    return cases


def verify_dev_inputs(cases: list[SQLBenchmarkCase], snapshot_path: Path, manifest_path: Path) -> dict[str, Any]:
    from dataclasses import asdict
    from evaluation.ctu_network_public.contract import CASES, split_data, validate
    raw = split_data(CASES)
    expected = [SQLBenchmarkCase.from_dict(v) for v in raw.values()]
    if (len(cases) != len(expected) or len({c.case_id for c in cases}) != len(cases)
            or sorted((asdict(c) for c in cases), key=lambda c: c["case_id"])
            != sorted((asdict(c) for c in expected), key=lambda c: c["case_id"])):
        raise ValueError("DEV_CASE_IDENTITY_MISMATCH")
    return validate(snapshot_path, manifest_path=manifest_path)


def score_record(case: SQLBenchmarkCase, record: dict[str, Any], snapshot) -> None:
    """Only the locked evaluator supplies score flags; diagnostics do not alter them."""
    from evaluation.text_to_sql import evaluate_sql_case
    result = evaluate_sql_case(case, record.get("final_sql") or "", snapshot)
    for field in ("syntax_valid", "execution_success", "execution_accurate", "safety_rejected"):
        record[field] = getattr(result, field)
    if record.get("error_category") == "OK":
        record["error_category"] = ("SYNTAX_ERROR" if not result.syntax_valid else
                                    "SAFETY_REJECTION" if result.safety_rejected else
                                    "EXECUTION_ERROR" if not result.execution_success else
                                    "RESULT_MISMATCH" if not result.execution_accurate else "OK")
    # Do not serialize DuckDB/provider exception strings from the evaluator.


def run_condition(condition: str, cases: list[SQLBenchmarkCase], snapshot_path: Path,
                  client: Any, output_dir: Path, manifest_path: Path) -> dict[str, Any]:
    from evaluation.dualsql_lite_ctu_gpt5.tools import SnapshotOnlyDuckDBSnapshot
    if condition not in CONDITIONS:
        raise ValueError("INVALID_CONDITION")
    if output_dir.exists():
        raise FileExistsError("OUTPUT_EXISTS")
    verify_dev_inputs(cases, snapshot_path, manifest_path)
    tools = V2DatabaseTools(snapshot_path, manifest_path)
    snapshot = SnapshotOnlyDuckDBSnapshot(snapshot_path)
    output_dir.mkdir(parents=True, exist_ok=False)
    results = []
    for case in cases:
        record = run_case(case, condition, tools, client, tools.schema_context())
        # Gold becomes available only here, after final submission/failure.
        score_record(case, record, snapshot)
        results.append(record)
        with (output_dir / f"{case.case_id}.json").open("x", encoding="utf-8") as stream:
            json.dump(record, stream, indent=2, default=str)
            stream.write("\n")
    counts = {field: sum(r[field] for r in results) for field in
              ("syntax_valid", "execution_success", "execution_accurate", "safety_rejected")}
    report = {"series_version": SERIES_VERSION, "condition": condition, "case_count": len(cases),
              "case_ids": [r["case_id"] for r in results], "counts": counts,
              "rates": {key: count / len(cases) if cases else 0 for key, count in counts.items()},
              "observed_cost_usd": sum(r["observed_cost_usd"] for r in results), "case_results": results}
    with (output_dir / "report.json").open("x", encoding="utf-8") as stream:
        json.dump(report, stream, indent=2, default=str)
        stream.write("\n")
    return report


def main():
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--condition", required=True, choices=CONDITIONS)
    parser.add_argument("--snapshot", type=Path, required=True)
    parser.add_argument("--cases-dir", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--api-key", default=None)
    args = parser.parse_args()

    client = create_client()

    cases = load_cases(args.cases_dir)
    print(f"Loaded {len(cases)} cases from {args.cases_dir}")

    report = run_condition(
        args.condition, cases, args.snapshot, client, args.output_dir
    )

    print(f"\n=== {args.condition} Results ===")
    print(f"Accuracy: {report['metrics']['execution_accuracy']}")
    print(f"Cost: ${report['total_cost_usd']:.6f}")


if __name__ == "__main__":
    main()
