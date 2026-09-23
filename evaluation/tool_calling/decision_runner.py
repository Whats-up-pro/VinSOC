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

from agent.provider import LLMProvider, ProviderError, create_provider
from agent.tools import get_tool_schemas
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
        provider: Optional[LLMProvider] = None,
    ):
        self.config = config or A1Config()
        self.benchmarks_dir = benchmarks_dir or Path("evaluation/tool_calling/benchmarks")
        if provider is not None:
            self.provider = provider
        else:
            provider_kwargs: Dict[str, Any] = {}
            if self.config.provider == "routed":
                # Evaluation must stay on the pinned provider/model.
                provider_kwargs["mode"] = "evaluation"
            self.provider = create_provider(
                provider_type=self.config.provider,
                model=self.config.model,
                **provider_kwargs,
            )

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

    def build_prompt(
        self,
        case: ToolCallCase,
        system_prompt: Optional[str] = None,
    ) -> tuple[str, str]:
        """
        Build prompt for a case.

        Returns (system_prompt, user_prompt).
        """
        if system_prompt is None:
            system_prompt = """You are a SOC analyst assistant.

Select only the investigation tools needed to satisfy the user's request.
Use the provided tool schemas as the source of truth for tool names and arguments.
Do not invent tools, arguments, indicators, hosts, or evidence.
If no tool is needed, do not call one."""

        return system_prompt, case.request

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
            system_prompt, user_prompt = self.build_prompt(case, self.config.system_prompt)
            response = self.provider.generate(
                messages=[{"role": "user", "content": user_prompt}],
                tools=get_tool_schemas(),
                system_prompt=system_prompt,
                temperature=self.config.temperature,
            )

            predicted_calls: List[PredictedCall] = []
            for tool_call in response.tool_calls:
                tool_name = tool_call.get("name")
                raw_arguments = tool_call.get("arguments", {})
                if not tool_name or not isinstance(raw_arguments, dict):
                    result.errors.append("INVALID_TOOL_CALL")
                    continue
                predicted_calls.append(
                    PredictedCall(
                        tool=tool_name,
                        arguments=normalize_arguments(tool_name, raw_arguments),
                        raw_arguments=raw_arguments,
                    )
                )
            result.predicted_calls = predicted_calls

            metadata = response.metadata or {}
            result.latency_ms = float(metadata.get("latency_ms", 0.0) or 0.0)
            result.input_tokens = int(metadata.get("input_tokens", 0) or 0)
            result.output_tokens = int(metadata.get("output_tokens", 0) or 0)

        except ProviderError as exc:
            result.error_message = str(exc)
            result.errors.append("PROVIDER_ERROR")
        except Exception as exc:
            result.error_message = str(exc)
            result.errors.append("EXECUTION_ERROR")

        # Compute metrics
        metrics = compute_case_metrics(case, result.predicted_calls)
        result.matches = metrics["matches"]
        result.true_positives = metrics["tp"]
        result.false_positives = metrics["fp"]
        result.false_negatives = metrics["fn"]
        result.trajectory_success = metrics["trajectory_success"]
        result.exact_call_match = metrics["exact_call_match"]
        result.tool_set_match = metrics["tool_set_match"]
        if result.errors:
            # A provider/execution/response failure is never evidence that the
            # model correctly abstained on a no-tool case.
            result.trajectory_success = False
            result.exact_call_match = False
            result.tool_set_match = False

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
        "provider": runner.provider.get_name(),
        "provider_metadata": runner.provider.get_run_metadata(),
        "config": {
            "provider": runner.config.provider,
            "model": runner.config.model,
            "temperature": runner.config.temperature,
        },
        "aggregate": aggregate.to_dict(),
        "error_summary": error_summary,
    }

    if output_path:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, "w") as f:
            json.dump(result_dict, f, indent=2)

    return result_dict
