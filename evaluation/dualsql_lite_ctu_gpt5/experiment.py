"""Controlled E0-E3 CTU-only series with immutable evidence and a spend gate."""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from evaluation.dualsql_lite_ctu_gpt5.agents import (
    GENERATOR_INSTRUCTIONS, GENERATOR_PROMPT_VERSION,
    LINKER_INSTRUCTIONS, LINKER_PROMPT_VERSION, MAX_TURNS,
    DualSQLCaseRunner, InvalidEvidenceRun,
)
from evaluation.dualsql_lite_ctu_gpt5.tools import DatabaseTools, TOOL_SCHEMAS, TOOL_VERSION
from evaluation.text_to_sql import SQLBenchmarkCase


CONDITIONS = ("E0", "E1", "E2", "E3")
SERIES_VERSION = "dualsql_lite_ctu_gpt5_v1"

INPUT_USD_M = 0.15
OUTPUT_USD_M = 0.60


def cost_usd(input_tokens: int, output_tokens: int) -> float:
    return (input_tokens * INPUT_USD_M + output_tokens * OUTPUT_USD_M) / 1_000_000


def _write_partial(path: Path, data: dict[str, Any]) -> None:
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(data, sort_keys=True, default=str, indent=2) + "\n")
    os.replace(temporary, path)


class BudgetGate:
    """Reserve every possible model turn before a paid series starts."""

    def __init__(self, cases: list[SQLBenchmarkCase], schema: str, budget_usd: float):
        if not 0 < budget_usd <= 100:
            raise ValueError("budget_usd must be positive and finite within the configured limit")
        self.budget_usd = budget_usd
        self.slots: dict[tuple[str, str], list[tuple[str, int]]] = {}
        for experiment in CONDITIONS:
            for case in cases:
                roles = []
                if experiment in {"E1", "E3"}:
                    roles.append(("linker", LINKER_INSTRUCTIONS + "\nDatabase schema:\n" + schema,
                                  MAX_TURNS, True))
                if experiment == "E0":
                    roles.append(("generator", GENERATOR_INSTRUCTIONS + "\nDatabase schema:\n" + schema,
                                  1, False))
                elif experiment == "E2":
                    roles.append(("generator", GENERATOR_INSTRUCTIONS + "\nDatabase schema:\n" + schema,
                                  MAX_TURNS, True))
                else:
                    roles.append(("generator", GENERATOR_INSTRUCTIONS + "\nValidated linked schema:\n"
                                  + '{"tables":[],"grounded_values":[]}',
                                  1 if experiment == "E1" else MAX_TURNS,
                                  experiment == "E3"))
                bounds = []
                for role, system, turns, tools_enabled in roles:
                    initial = {
                        "model": "gpt-5-mini-2025-08-07",
                        "reasoning_effort": "low",
                        "max_completion_tokens": 1000,
                        "messages": [{"role": "system", "content": system},
                                     {"role": "user", "content": case.question}],
                        "tools": TOOL_SCHEMAS if tools_enabled else None
                    }
                    if role == "linker":
                        initial["response_format"] = {"type": "json_object"}
                    size = len(json.dumps(initial, ensure_ascii=True).encode())
                    FRAMING_TOKENS = 50
                    MAX_RESPONSE_BYTES = 1650
                    for turn in range(turns):
                        bounds.append((role, size + FRAMING_TOKENS
                                       + turn * (6000 + MAX_RESPONSE_BYTES + 1024)))
                self.slots[(experiment, case.case_id)] = bounds
        self.ceiling_usd = sum(cost_usd(bound, 1000)
                               for bounds in self.slots.values() for _, bound in bounds)
        if self.ceiling_usd >= budget_usd:
            raise ValueError(f"preflight spend ceiling ${self.ceiling_usd:.4f} exceeds budget ${budget_usd:.2f}")
        self.remaining_usd = self.ceiling_usd
        self.known_usd = 0.0


def make_client(api_key: str | None = None) -> Any:
    """Create OpenAI client."""
    from openai import OpenAI
    return OpenAI(api_key=api_key)


def run_condition(
    condition: str,
    cases: list[SQLBenchmarkCase],
    snapshot_path: Path,
    client: Any,
    output_dir: Path,
    *,
    before_call: Any = None,
    after_call: Any = None,
) -> dict[str, Any]:
    """Run one condition (E0-E3) across all cases."""
    output_dir.mkdir(parents=True, exist_ok=True)
    report_path = output_dir / f"{condition.lower()}_report.json"
    case_results = []
    runner = DualSQLCaseRunner(snapshot_path, client, before_call, after_call)

    for case in cases:
        result = runner.run_case(case, condition)
        case_results.append(result)
        _write_partial(output_dir / f"{case.case_id}_{condition.lower()}.json", result)

    metrics = {
        "execution_accuracy": sum(1 for r in case_results if r["execution_accurate"]),
        "syntax_valid": sum(1 for r in case_results if r["syntax_valid"]),
        "execution_success": sum(1 for r in case_results if r["execution_success"]),
        "safety_rejected": sum(1 for r in case_results if r["safety_rejected"]),
    }

    report = {
        "experiment_id": condition,
        "series_version": SERIES_VERSION,
        "case_count": len(cases),
        "case_results": case_results,
        "metrics": {**metrics, "execution_accuracy": f"{metrics['execution_accuracy']}/{len(cases)}"},
        "total_cost_usd": sum(r["cost_usd"] for r in case_results),
        "model_calls": sum(r["model_calls"] for r in case_results),
        "latency_ms": sum(r["latency_ms"] for r in case_results),
        "eligible": all(r["execution_success"] for r in case_results),
    }

    _write_partial(report_path, report)
    return report


def main() -> int:
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--condition", required=True, choices=CONDITIONS)
    parser.add_argument("--snapshot", type=Path, required=True)
    parser.add_argument("--cases-dir", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--api-key", default=None)
    args = parser.parse_args()

    cases = []
    for path in sorted(args.cases_dir.glob("*.json")):
        with open(path) as f:
            data = json.load(f)
        cases.append(SQLBenchmarkCase.from_dict(data))

    client = make_client(args.api_key)

    report = run_condition(
        args.condition, cases, args.snapshot, client, args.output_dir
    )
    print(json.dumps({
        "condition": report["experiment_id"],
        "execution_accuracy": report["metrics"]["execution_accuracy"],
        "total_cost_usd": report["total_cost_usd"],
    }))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
