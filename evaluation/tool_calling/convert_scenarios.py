#!/usr/bin/env python3
"""
Convert existing scenarios to R1 benchmark format.

Usage:
    python evaluation/tool_calling/convert_scenarios.py
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from evaluation.tool_calling.models import (
    CaseCategory,
    CaseDifficulty,
    ExpectedCall,
    ToolCallCase,
)


def convert_scenario(scenario: dict) -> ToolCallCase:
    """Convert a scenario to benchmark case."""
    case_id = scenario["case_id"]
    indicator = scenario["initial_indicator"]
    ground_truth = scenario.get("ground_truth", {})
    test_data = scenario.get("test_data", {})

    # Build expected calls
    expected_tools = ground_truth.get("expected_tools", [])
    expected_calls = []
    forbidden_tools = []

    indicator_value = indicator["value"]
    indicator_type = indicator.get("type", "unknown")

    for i, tool in enumerate(expected_tools):
        call_id = f"call_{i + 1}"

        if tool == "cti_enrichment":
            args = {"indicator": indicator_value}
            if indicator_type in ("ipv4", "domain", "hash", "url"):
                args["indicator_type"] = indicator_type
            expected_calls.append(ExpectedCall(
                call_id=call_id,
                tool="cti_enrichment",
                required_arguments=args,
                critical_arguments=["indicator"],
            ))

        elif tool == "network_investigation":
            expected_calls.append(ExpectedCall(
                call_id=call_id,
                tool="network_investigation",
                required_arguments={"indicator": indicator_value},
                critical_arguments=["indicator"],
            ))

        elif tool == "endpoint_investigation":
            host = test_data.get("endpoint_data", {}).get("host", indicator_value)
            expected_calls.append(ExpectedCall(
                call_id=call_id,
                tool="endpoint_investigation",
                required_arguments={"host": host},
                critical_arguments=["host"],
            ))

    # Determine category
    if indicator_type == "hostname":
        category = CaseCategory.HOSTNAME_LED
    elif indicator_type == "hash":
        category = CaseCategory.HASH_LED
    elif indicator_type == "url":
        category = CaseCategory.URL_LED
    elif len(expected_calls) == 1:
        tool = expected_calls[0].tool
        if tool == "cti_enrichment":
            category = CaseCategory.CTI_ONLY
        elif tool == "network_investigation":
            category = CaseCategory.NETWORK_ONLY
        elif tool == "endpoint_investigation":
            category = CaseCategory.ENDPOINT_ONLY
        else:
            category = CaseCategory.CTI_ONLY
    elif len(expected_calls) == 2:
        tools = {c.tool for c in expected_calls}
        if "cti_enrichment" in tools and "network_investigation" in tools:
            category = CaseCategory.CTI_NETWORK
        elif "cti_enrichment" in tools and "endpoint_investigation" in tools:
            category = CaseCategory.CTI_ENDPOINT
        elif "network_investigation" in tools and "endpoint_investigation" in tools:
            category = CaseCategory.NETWORK_ENDPOINT
        else:
            category = CaseCategory.CTI_NETWORK
    else:
        category = CaseCategory.CTI_NETWORK_ENDPOINT

    # For hostname cases, forbid CTI until endpoint provides IOC
    if indicator_type == "hostname":
        forbidden_tools = ["cti_enrichment"]

    # Determine difficulty (simplified)
    if len(expected_calls) == 1:
        difficulty = CaseDifficulty.BASIC
    elif len(expected_calls) == 2:
        difficulty = CaseDifficulty.INTERMEDIATE
    else:
        difficulty = CaseDifficulty.ADVANCED

    return ToolCallCase(
        case_id=case_id,
        category=category,
        difficulty=difficulty,
        request=scenario.get("description", indicator.get("context", "")),
        reference_time="2026-09-22T00:00:00Z",
        expected_calls=expected_calls,
        forbidden_tools=forbidden_tools,
        notes=scenario.get("evaluation_notes", ""),
    )


def main():
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--scenarios-dir", type=Path, default=Path("scenarios"))
    parser.add_argument("--output-dir", type=Path, default=Path("evaluation/tool_calling/benchmarks"))
    parser.add_argument("--split", choices=["dev", "frozen"], default="dev")
    args = parser.parse_args()

    output_dir = args.output_dir / args.split
    output_dir.mkdir(parents=True, exist_ok=True)

    # Load all scenarios
    scenarios = sorted(args.scenarios_dir.glob("case_*.json"))

    print(f"Converting {len(scenarios)} scenarios...")

    for scenario_file in scenarios:
        with open(scenario_file) as f:
            scenario = json.load(f)

        case = convert_scenario(scenario)

        output_file = output_dir / f"{case.case_id}.json"
        with open(output_file, "w") as f:
            json.dump(case.to_dict(), f, indent=2)

        print(f"  {case.case_id}: {case.category.value} ({case.difficulty.value})")

    print(f"\nConverted {len(scenarios)} cases to {output_dir}")


if __name__ == "__main__":
    main()
