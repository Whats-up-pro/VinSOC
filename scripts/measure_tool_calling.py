"""Measure provisional tool-calling metrics on the existing mock scenarios.

This script is for integration regression checks. It does not measure a paid
model and it does not replace the future formal decision-only benchmark.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from agent.orchestrator import InvestigationOrchestrator
from agent.provider import MockProvider


def _scenario_skill_data(scenario: dict[str, Any]) -> dict[str, dict[str, Any]]:
    test_data = scenario.get("test_data", {})
    indicator_value = scenario["initial_indicator"]["value"]
    endpoint_data = test_data.get("endpoint_data")
    endpoint_host = endpoint_data.get("host", indicator_value) if endpoint_data else None
    return {
        "cti_mock_data": (
            {indicator_value: test_data["cti_response"]} if test_data.get("cti_response") else {}
        ),
        "network_mock_data": (
            {indicator_value: test_data["network_data"]} if test_data.get("network_data") else {}
        ),
        "endpoint_mock_data": {endpoint_host: endpoint_data} if endpoint_data else {},
    }


def measure(scenarios_dir: Path) -> dict[str, Any]:
    """Run the deterministic mock integration measurement."""
    true_positive = false_positive = false_negative = 0
    total_calls = execution_successes = exact_sequence = exact_set = 0
    mismatches: list[dict[str, Any]] = []
    scenarios = sorted(scenarios_dir.glob("case_*.json"))

    for scenario_path in scenarios:
        scenario = json.loads(scenario_path.read_text(encoding="utf-8"))
        indicator = scenario["initial_indicator"]
        orchestrator = InvestigationOrchestrator(
            provider=MockProvider(model="benchmark-mock"),
            max_steps=10,
            **_scenario_skill_data(scenario),
        )
        case = orchestrator.investigate(
            indicator=indicator["value"],
            indicator_type=indicator.get("type", "ipv4"),
            context=indicator.get("context"),
        )
        expected = scenario["ground_truth"]["expected_tools"]
        actual = [call["tool"] for call in case.tool_trace]
        expected_counts, actual_counts = Counter(expected), Counter(actual)

        true_positive += sum((expected_counts & actual_counts).values())
        false_positive += sum((actual_counts - expected_counts).values())
        false_negative += sum((expected_counts - actual_counts).values())
        total_calls += len(actual)
        execution_successes += sum(not call.get("error") for call in case.tool_trace)
        exact_sequence += actual == expected
        exact_set += actual_counts == expected_counts

        if actual != expected:
            mismatches.append(
                {
                    "case_id": scenario["case_id"],
                    "expected_tools": expected,
                    "actual_tools": actual,
                }
            )

    precision = true_positive / (true_positive + false_positive) if total_calls else 0.0
    expected_calls = true_positive + false_negative
    recall = true_positive / expected_calls if expected_calls else 0.0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    scenario_count = len(scenarios)
    return {
        "measurement": "mock integration; tool names matched as multisets",
        "scenario_count": scenario_count,
        "actual_tool_calls": total_calls,
        "true_positive": true_positive,
        "false_positive": false_positive,
        "false_negative": false_negative,
        "tool_precision": precision,
        "tool_recall": recall,
        "tool_f1": f1,
        "tool_set_exact_match_rate": exact_set / scenario_count if scenario_count else 0.0,
        "exact_sequence_rate": exact_sequence / scenario_count if scenario_count else 0.0,
        "integration_execution_success_rate": (
            execution_successes / total_calls if total_calls else 0.0
        ),
        "mismatches": mismatches,
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Measure VinSOC's current mock tool-calling integration"
    )
    parser.add_argument("--scenarios-dir", type=Path, default=Path("scenarios"))
    parser.add_argument("--output", type=Path, help="Optional JSON output path")
    args = parser.parse_args()
    result = measure(args.scenarios_dir)
    rendered = json.dumps(result, indent=2)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered + "\n", encoding="utf-8")
    print(rendered)


if __name__ == "__main__":
    main()
