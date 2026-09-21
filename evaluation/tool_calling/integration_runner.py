"""
R1 Tool Calling Evaluation - A2 Integration Runner

Runs evaluation through the production orchestrator with mock/provider.
Reuses the same matching and metrics engine.
"""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from agent.orchestrator import InvestigationOrchestrator
from agent.provider import MockProvider
from evaluation.tool_calling.models import (
    CaseResult,
    ExpectedCall,
    PredictedCall,
    ToolCallCase,
)
from evaluation.tool_calling.matching import compute_case_metrics
from evaluation.tool_calling.metrics import aggregate_case_results, generate_error_summary


class IntegrationRunner:
    """
    Runs A2 integration evaluation through the production orchestrator.

    This evaluates:
    - MockProvider decisions
    - Orchestrator execution
    - Production skills
    - Evidence collection

    Matching and metrics reuse the same engine as A1.
    """

    def __init__(
        self,
        scenarios_dir: Optional[Path] = None,
    ):
        self.scenarios_dir = scenarios_dir or Path("scenarios")

    def load_scenario(self, case_id: str) -> Dict[str, Any]:
        """Load a scenario file."""
        scenario_file = self.scenarios_dir / f"{case_id}.json"
        with open(scenario_file) as f:
            return json.load(f)

    def convert_to_benchmark_case(self, scenario: Dict[str, Any]) -> ToolCallCase:
        """
        Convert a scenario to benchmark case format.

        Note: This is for regression testing. The existing 20 scenarios
        are development data, not frozen benchmark data.
        """
        case_id = scenario["case_id"]
        indicator = scenario["initial_indicator"]
        ground_truth = scenario.get("ground_truth", {})
        test_data = scenario.get("test_data", {})

        # Build expected calls from ground_truth.expected_tools
        expected_tools = ground_truth.get("expected_tools", [])
        expected_calls = []

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
        category_map = {
            "cti_only": 1 if len(expected_calls) == 1 and expected_calls[0].tool == "cti_enrichment" else None,
            "endpoint_only": 1 if expected_calls and all(c.tool == "endpoint_investigation" for c in expected_calls) else None,
        }

        # Detect hostname-led cases
        if indicator_type == "hostname":
            category = "hostname_led"
        else:
            category = "cti_only" if len(expected_calls) == 1 and expected_calls[0].tool == "cti_enrichment" else "cti_network"

        return ToolCallCase(
            case_id=case_id,
            category=category,
            difficulty="basic",
            request=scenario.get("description", indicator.get("context", "")),
            reference_time="2026-09-22T00:00:00Z",
            expected_calls=expected_calls,
            notes=scenario.get("evaluation_notes", ""),
        )

    def run_integration(
        self,
        case: ToolCallCase,
        scenario: Dict[str, Any],
    ) -> CaseResult:
        """
        Run integration evaluation for a single case.
        """
        result = CaseResult(
            case_id=case.case_id,
            expected_calls=case.expected_calls,
            predicted_calls=[],
        )

        try:
            # Build mock data from scenario
            test_data = scenario.get("test_data", {})
            mock_data = {}

            if test_data.get("cti_response"):
                indicator = scenario["initial_indicator"]["value"]
                mock_data["cti_mock_data"] = {indicator: test_data["cti_response"]}

            if test_data.get("network_data"):
                indicator = scenario["initial_indicator"]["value"]
                mock_data["network_mock_data"] = {indicator: test_data["network_data"]}

            if test_data.get("endpoint_data"):
                host = test_data["endpoint_data"].get("host", scenario["initial_indicator"]["value"])
                mock_data["endpoint_mock_data"] = {host: test_data["endpoint_data"]}

            # Create orchestrator with mock provider
            provider = MockProvider(mock_data)
            orchestrator = InvestigationOrchestrator(provider=provider)

            # Execute
            indicator = scenario["initial_indicator"]["value"]
            indicator_type = scenario["initial_indicator"].get("type", "ipv4")

            start_time = datetime.utcnow()
            investigation_case = orchestrator.investigate(
                indicator=indicator,
                indicator_type=indicator_type,
                context=scenario.get("initial_indicator", {}).get("context"),
            )
            end_time = datetime.utcnow()

            result.latency_ms = (end_time - start_time).total_seconds() * 1000

            # Extract tool calls from tool trace
            predicted_calls = []
            for tool_call in investigation_case.tool_trace:
                tool_name = tool_call["tool"]
                args = tool_call.get("arguments", {})

                predicted_calls.append(PredictedCall(
                    tool=tool_name,
                    arguments=args,
                ))

            result.predicted_calls = predicted_calls

        except Exception as e:
            result.error_message = str(e)
            result.errors.append("EXECUTION_ERROR")

        # Compute metrics
        metrics = compute_case_metrics(case, result.predicted_calls)
        result.matches = metrics["matches"]
        result.true_positives = metrics["tp"]
        result.false_positives = metrics["fp"]
        result.false_negatives = metrics["fn"]
        result.forbidden_tool_violations = metrics["forbidden_violations"]
        result.duplicate_calls = [str(d) for d in metrics["duplicates"]]
        result.ordering_violations = metrics["ordering_violations"]
        result.critical_arg_errors = metrics["critical_arg_errors"]
        result.trajectory_success = metrics["trajectory_success"]

        # Build error list
        if result.trajectory_success:
            pass
        elif result.false_positives > 0:
            result.errors.append("EXTRA_TOOL")
        if result.false_negatives > 0:
            result.errors.append("MISSING_TOOL")
        if result.forbidden_tool_violations:
            result.errors.append("FORBIDDEN_TOOL")
        if result.critical_arg_errors > 0:
            result.errors.append("WRONG_CRITICAL_ARGUMENT")

        return result

    def run_suite(
        self,
        case_ids: Optional[List[str]] = None,
    ) -> List[CaseResult]:
        """
        Run integration evaluation for a suite of cases.
        """
        if case_ids is None:
            # Run all scenarios
            case_ids = [f"case_{i:03d}" for i in range(1, 21)]

        results = []

        for case_id in case_ids:
            try:
                scenario = self.load_scenario(case_id)
                case = self.convert_to_benchmark_case(scenario)
                result = self.run_integration(case, scenario)
                results.append(result)
            except Exception as e:
                # Create failure result
                results.append(CaseResult(
                    case_id=case_id,
                    expected_calls=[],
                    predicted_calls=[],
                    errors=["LOAD_ERROR"],
                    error_message=str(e),
                ))

        return results


def run_legacy_integration_benchmark(
    output_path: Optional[Path] = None,
) -> Dict[str, Any]:
    """
    Run the legacy integration benchmark (A2) on existing scenarios.

    Returns results for comparison with the formal R1 benchmark.
    """
    runner = IntegrationRunner()

    # Run all 20 scenarios
    case_ids = [f"case_{i:03d}" for i in range(1, 21)]
    case_results = runner.run_suite(case_ids)

    # Aggregate
    run_id = f"legacy_integration_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}"
    aggregate = aggregate_case_results(run_id, case_results)
    error_summary = generate_error_summary(case_results)

    # Convert to dict
    result_dict = {
        "run_id": run_id,
        "mode": "integration_legacy",
        "aggregate": aggregate.to_dict(),
        "error_summary": error_summary,
        "case_results": [r.to_dict() for r in case_results],
    }

    # Save if path provided
    if output_path:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, "w") as f:
            json.dump(result_dict, f, indent=2)

    return result_dict
