"""
R1 Tool Calling Evaluation - A1 Decision-Only Runner

Runs evaluation against LLM with pinned provider.
No production skill execution.
"""
from __future__ import annotations

import json
import uuid
from dataclasses import dataclass, field
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
from evaluation.tool_calling.arguments import normalize_arguments
from evaluation.tool_calling.matching import compute_case_metrics
from evaluation.tool_calling.metrics import aggregate_case_results, generate_error_summary


@dataclass
class A1Config:
    """Configuration for A1 evaluation."""
    provider: str = "openai"
    model: str = "gpt-4o"
    temperature: float = 0.0
    fallback_enabled: bool = False
    system_prompt: Optional[str] = None
    max_tokens: int = 1000


class DecisionRunner:
    """
    A1 Decision-Only Evaluation Runner.

    Sends cases to LLM and evaluates tool call decisions.
    No production skill execution.
    """

    def __init__(
        self,
        config: Optional[A1Config] = None,
        benchmarks_dir: Optional[Path] = None,
    ):
        self.config = config or A1Config()
        self.benchmarks_dir = benchmarks_dir or Path("evaluation/tool_calling/benchmarks")

    def load_case(self, case_id: str, split: str = "dev") -> ToolCallCase:
        """Load a benchmark case."""
        case_file = self.benchmarks_dir / split / f"{case_id}.json"
        with open(case_file) as f:
            data = json.load(f)
        return ToolCallCase.from_dict(data)

    def load_cases(self, split: str = "dev") -> List[ToolCallCase]:
        """Load all cases from a split."""
        split_dir = self.benchmarks_dir / split
        if not split_dir.exists():
            return []

        cases = []
        for case_file in sorted(split_dir.glob("*.json")):
            with open(case_file) as f:
                data = json.load(f)
            cases.append(ToolCallCase.from_dict(data))
        return cases

    def parse_tool_calls(self, llm_response: str) -> List[PredictedCall]:
        """
        Parse tool calls from LLM response.

        Handles multiple formats:
        - JSON with tool_calls array
        - Natural language description
        """
        # Try JSON parsing first
        try:
            # Look for JSON in response
            if "```json" in llm_response:
                json_str = llm_response.split("```json")[1].split("```")[0]
            elif "{" in llm_response:
                start = llm_response.find("{")
                end = llm_response.rfind("}") + 1
                json_str = llm_response[start:end]
            else:
                json_str = llm_response

            data = json.loads(json_str)

            calls = []
            if isinstance(data, list):
                for item in data:
                    if isinstance(item, dict) and "tool" in item:
                        tool = item["tool"]
                        args = item.get("arguments", {})
                        calls.append(PredictedCall(tool=tool, arguments=args))
            elif isinstance(data, dict) and "tool_calls" in data:
                for item in data["tool_calls"]:
                    if isinstance(item, dict):
                        tool = item.get("tool") or item.get("name")
                        args = item.get("arguments", {})
                        calls.append(PredictedCall(tool=tool, arguments=args))

            return calls

        except (json.JSONDecodeError, KeyError):
            pass

        # Fallback: regex extraction
        calls = []
        for tool_name in ["cti_enrichment", "network_investigation", "endpoint_investigation"]:
            if tool_name in llm_response.lower():
                calls.append(PredictedCall(tool=tool_name, arguments={}))

        return calls

    def build_prompt(
        self,
        case: ToolCallCase,
        system_prompt: Optional[str] = None,
    ) -> tuple[str, str]:
        """
        Build prompt for a case.

        Returns (system_prompt, user_prompt).
        """
        from agent.tools import get_tool_schemas

        if system_prompt is None:
            # Default system prompt from orchestrator
            system_prompt = """You are a SOC analyst assistant.

Given an investigation request, determine which tools to call.

Tools available:
- cti_enrichment: Look up threat intelligence for IP, domain, hash, or URL
- network_investigation: Analyze network telemetry for an indicator
- endpoint_investigation: Investigate endpoint process relationships

Choose ONLY the tools necessary for this investigation.
Do not call tools that are not relevant."""

        user_prompt = f"""Investigation Request:
{case.request}

Initial indicator: {case.case_id.split('_')[1] if '_' in case.case_id else case.case_id}

What tools should be called?
Provide the tool calls in JSON format."""

        return system_prompt, user_prompt

    def run_decision(
        self,
        case: ToolCallCase,
    ) -> CaseResult:
        """
        Run A1 decision evaluation for a single case.
        """
        result = CaseResult(
            case_id=case.case_id,
            expected_calls=case.expected_calls,
            predicted_calls=[],
        )

        try:
            # Build prompt
            system_prompt, user_prompt = self.build_prompt(case, self.config.system_prompt)

            # Call LLM
            # For now, use a simple mock
            # TODO: Implement actual LLM call
            raise NotImplementedError("A1 LLM integration not yet implemented")

        except NotImplementedError:
            # Mock response for testing
            result.error_message = "A1 LLM integration not implemented"
            result.errors.append("NOT_IMPLEMENTED")

        except Exception as e:
            result.error_message = str(e)
            result.errors.append("EXECUTION_ERROR")

        # Compute metrics
        metrics = compute_case_metrics(case, result.predicted_calls)
        result.matches = metrics["matches"]
        result.true_positives = metrics["tp"]
        result.false_positives = metrics["fp"]
        result.false_negatives = metrics["fn"]
        result.trajectory_success = metrics["trajectory_success"]

        return result

    def run_suite(
        self,
        split: str = "dev",
        case_ids: Optional[List[str]] = None,
    ) -> List[CaseResult]:
        """
        Run A1 evaluation for a suite of cases.
        """
        if case_ids is None:
            cases = self.load_cases(split)
            case_ids = [c.case_id for c in cases]
        else:
            cases = [self.load_case(cid, split) for cid in case_ids]

        results = []
        for case in cases:
            result = self.run_decision(case)
            results.append(result)

        return results


def run_a1_benchmark(
    split: str = "dev",
    output_path: Optional[Path] = None,
    config: Optional[A1Config] = None,
) -> Dict[str, Any]:
    """
    Run A1 decision-only benchmark.

    Returns results dict.
    """
    runner = DecisionRunner(config=config)

    # Load cases
    cases = runner.load_cases(split)

    if not cases:
        return {
            "error": f"No cases found in split '{split}'",
            "mode": "decision",
            "split": split,
        }

    # Run evaluation
    case_results = []
    for case in cases:
        result = runner.run_decision(case)
        case_results.append(result)

    # Aggregate
    run_id = f"a1_decision_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}"
    aggregate = aggregate_case_results(run_id, case_results)
    error_summary = generate_error_summary(case_results)

    result_dict = {
        "run_id": run_id,
        "mode": "decision",
        "split": split,
        "case_count": len(cases),
        "aggregate": aggregate.to_dict(),
        "error_summary": error_summary,
    }

    if output_path:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, "w") as f:
            json.dump(result_dict, f, indent=2)

    return result_dict
