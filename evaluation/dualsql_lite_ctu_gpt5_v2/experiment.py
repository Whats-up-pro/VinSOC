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


def load_cases(cases_dir: Path) -> list[SQLBenchmarkCase]:
    """Load cases from directory."""
    cases = []
    for path in sorted(cases_dir.glob("*.json")):
        with open(path) as f:
            data = json.load(f)
        cases.append(SQLBenchmarkCase.from_dict(data))
    return cases


def run_condition(
    condition: str,
    cases: list[SQLBenchmarkCase],
    snapshot_path: Path,
    client,
    output_dir: Path,
    manifest_path: Path,
) -> dict[str, Any]:
    """Run one condition (E0-E3) for v2."""
    output_dir.mkdir(parents=True, exist_ok=True)
    tools = V2DatabaseTools(snapshot_path, manifest_path)
    schema = tools.schema_context()

    results = []
    for case in cases:
        result = run_case(case, condition, tools, client, schema)
        results.append(result)

        # Save individual result
        (output_dir / f"{case.case_id}_{condition}.json").write_text(
            json.dumps(result, indent=2, default=str) + "\n"
        )

    # Aggregate metrics
    accurate = sum(1 for r in results if r.get("execution_accurate"))
    syntax_valid = sum(1 for r in results if r.get("syntax_valid"))

    report = {
        "series_version": SERIES_VERSION,
        "condition": condition,
        "case_count": len(cases),
        "metrics": {
            "execution_accuracy": f"{accurate}/{len(cases)}",
            "syntax_valid": f"{syntax_valid}/{len(cases)}",
        },
        "total_cost_usd": sum(r.get("total_cost_usd", 0) for r in results),
        "case_ids": [r["case_id"] for r in results],
    }

    (output_dir / f"{condition}_report.json").write_text(
        json.dumps(report, indent=2) + "\n"
    )

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

    from openai import OpenAI
    client = OpenAI(api_key=args.api_key)

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
