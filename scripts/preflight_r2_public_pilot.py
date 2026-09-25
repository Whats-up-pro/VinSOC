"""Verify the complete pilot and bound the 20+8 real request payloads without API calls."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from evaluation.public_pilot.contract import R1, R2, validate
from evaluation.public_pilot.run_model import (
    BUDGET_USD, _schema_context, build_r1_request, build_r2_request, preflight_bounds,
)
from evaluation.text_to_sql import SQLBenchmarkCase
from evaluation.tool_calling.models import ToolCallCase
from vinsoc_data.duckdb_store import DuckDBSnapshot


def preflight(snapshot_path: Path) -> dict:
    validated = validate(snapshot_path)
    schema = _schema_context(DuckDBSnapshot(snapshot_path))
    r1 = [ToolCallCase.from_dict(json.loads(p.read_text())) for p in sorted(R1.glob("*.json"))]
    r2 = [SQLBenchmarkCase.from_dict(json.loads(p.read_text())) for p in sorted(R2.glob("*.json"))]
    requests = [build_r1_request(case) for case in r1]
    requests += [build_r2_request(case.question, schema) for case in r2]
    limits = preflight_bounds(requests)
    if len(requests) != 28 or limits["cost_ceiling_usd"] >= BUDGET_USD:
        raise ValueError("Combined pilot bound is not below $1 for exactly 28 model requests")
    return {"validation": validated, "preflight": limits, "r1_count": len(r1),
            "r2_count": len(r2), "combined_cost_ceiling_usd": limits["cost_ceiling_usd"]}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--snapshot", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()
    report = preflight(args.snapshot)
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, sort_keys=True, indent=2) + "\n")
    print(f"R1={report['r1_count']} R2={report['r2_count']} total_bound_usd={report['combined_cost_ceiling_usd']:.6f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
