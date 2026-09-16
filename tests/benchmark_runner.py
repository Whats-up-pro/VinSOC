"""
Benchmark helper comparing evidence-driven and fixed-pipeline orchestration.
"""
import json
from pathlib import Path
from statistics import mean
from typing import Any, Dict, List, Optional

from agent.orchestrator import InvestigationOrchestrator
from agent.provider import MockProvider


def _load_scenarios() -> List[Dict[str, Any]]:
    scenarios_dir = Path(__file__).parent.parent / "scenarios"
    scenarios = []
    for case_file in sorted(scenarios_dir.glob("case_*.json")):
        with open(case_file) as f:
            scenarios.append(json.load(f))
    return scenarios


def _extract_test_data(scenario: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    test_data = scenario.get("test_data", {})
    indicator_value = scenario.get("initial_indicator", {}).get("value")
    cti_response = test_data.get("cti_response")
    network_response = test_data.get("network_data")
    endpoint_response = test_data.get("endpoint_data")
    endpoint_host = endpoint_response.get("host") if endpoint_response else None
    return {
        "cti_mock_data": {indicator_value: cti_response} if indicator_value and cti_response else {},
        "network_mock_data": {indicator_value: network_response} if indicator_value and network_response else {},
        "endpoint_mock_data": {endpoint_host: endpoint_response} if endpoint_host and endpoint_response else {},
    }


def _new_orchestrator(test_data: Dict[str, Dict[str, Any]]) -> InvestigationOrchestrator:
    return InvestigationOrchestrator(
        provider=MockProvider(model="benchmark"),
        cti_mock_data=test_data.get("cti_mock_data"),
        network_mock_data=test_data.get("network_mock_data"),
        endpoint_mock_data=test_data.get("endpoint_mock_data"),
        max_steps=10,
    )


def run_benchmark_suite(limit: Optional[int] = None) -> Dict[str, Any]:
    scenarios = _load_scenarios()
    if limit:
        scenarios = scenarios[:limit]

    ed_results = []
    fp_results = []

    for scenario in scenarios:
        indicator = scenario["initial_indicator"]
        expected_risk = scenario.get("ground_truth", {}).get("expected_risk", "UNKNOWN")
        test_data = _extract_test_data(scenario)

        ed = _new_orchestrator(test_data).investigate(
            indicator=indicator["value"],
            indicator_type=indicator.get("type", "ipv4"),
            context=indicator.get("context"),
        )
        fp = _new_orchestrator(test_data).investigate_fixed_pipeline(
            indicator=indicator["value"],
            indicator_type=indicator.get("type", "ipv4"),
            context=indicator.get("context"),
        )

        ed_results.append({
            "match": ed.risk_level == expected_risk,
            "tool_calls": len(ed.tool_trace),
        })
        fp_results.append({
            "match": fp.risk_level == expected_risk,
            "tool_calls": len(fp.tool_trace),
        })

    scenarios_count = len(scenarios) or 1
    return {
        "scenarios": len(scenarios),
        "evidence_driven_match_rate": sum(1 for r in ed_results if r["match"]) / scenarios_count,
        "fixed_pipeline_match_rate": sum(1 for r in fp_results if r["match"]) / scenarios_count,
        "evidence_driven_avg_tools": mean([r["tool_calls"] for r in ed_results]) if ed_results else 0.0,
        "fixed_pipeline_avg_tools": mean([r["tool_calls"] for r in fp_results]) if fp_results else 0.0,
    }
