"""
R1 Tool Calling Evaluation - A1 Decision-Only Runner

Runs evaluation against LLM with pinned provider.
No production skill execution.
"""
from __future__ import annotations

import json
import subprocess
import uuid
from copy import deepcopy
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional

from agent.provider import (
    LLMProvider, ModelPricing, MonthlyBudgetGuard, OpenAIProvider, ProviderError,
    create_provider,
)
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
from evaluation.tool_calling.provenance import build_a1_provenance


@dataclass(frozen=True)
class RunGateReceipt:
    """Offline authorization and immutable-input check before provider creation."""

    passed: bool
    errors: tuple[str, ...]
    case_count: int
    distribution: dict[str, int]
    lock_sha256: str | None
    authorization_id: str | None
    authorization_sha256: str | None
    requested_model: str
    budget_limit_usd: Decimal
    worst_case_cost_usd: Decimal
    pricing: dict[str, Any]
    provider_created: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "format": "r1_generalization_run_gate_v1",
            "passed": self.passed,
            "errors": list(self.errors),
            "case_count": self.case_count,
            "distribution": self.distribution,
            "lock_sha256": self.lock_sha256,
            "authorization_id": self.authorization_id,
            "authorization_sha256": self.authorization_sha256,
            "requested_model": self.requested_model,
            "budget_limit_usd": str(self.budget_limit_usd),
            "worst_case_cost_usd": str(self.worst_case_cost_usd),
            "pricing": self.pricing,
            "provider_created": self.provider_created,
            "model_calls": 0,
        }


def generalization_git_identity(root: Path = Path(".")) -> dict[str, Any]:
    """Read the local release identity without modifying the repository."""

    def git(*args: str) -> str:
        return subprocess.run(
            ["git", *args], cwd=root, check=True, capture_output=True,
            text=True, timeout=10,
        ).stdout.strip()

    try:
        return {
            "commit_sha": git("rev-parse", "HEAD"),
            "origin_master_sha": git("rev-parse", "origin/master"),
            "branch": git("symbolic-ref", "--quiet", "--short", "HEAD"),
            "working_tree_clean": not bool(git("status", "--porcelain")),
        }
    except (OSError, subprocess.SubprocessError):
        return {
            "commit_sha": None,
            "origin_master_sha": None,
            "branch": None,
            "working_tree_clean": False,
        }


def _positive_decimal(value: Any) -> Decimal | None:
    if isinstance(value, bool) or not isinstance(value, (str, int, Decimal)):
        return None
    try:
        number = Decimal(value)
    except (InvalidOperation, ValueError):
        return None
    return number if number.is_finite() and number > 0 else None


def validate_generalization_run_gate(
    split_dir: Path,
    lock_path: Path,
    authorization: Mapping[str, Any],
    requested_model: str,
    budget_limit_usd: Decimal,
    git_identity: Mapping[str, Any],
) -> RunGateReceipt:
    """Fail closed on review, lock, exact SHA, one-suite authority and cost."""

    from evaluation.tool_calling.generalization import verify_generalization_lock
    from evaluation.tool_calling.provenance import canonical_sha256

    verification = verify_generalization_lock(split_dir, lock_path)
    errors = list(verification.errors)
    if not verification.passed:
        errors.append("generalization lock verification failed")

    commit_sha = git_identity.get("commit_sha")
    if git_identity.get("branch") != "master":
        errors.append("run requires master branch")
    if git_identity.get("working_tree_clean") is not True:
        errors.append("run requires a clean working tree")
    if not commit_sha or git_identity.get("origin_master_sha") != commit_sha:
        errors.append("HEAD must equal origin/master")

    if authorization.get("authorized") is not True:
        errors.append("explicit authorization is required")
    if authorization.get("scope") != "r1_tool_calling_generalization_v1":
        errors.append("authorization scope must be R1 generalization only")
    authorization_id = authorization.get("authorization_id")
    if not isinstance(authorization_id, str) or not authorization_id.strip():
        errors.append("authorization ID is required")
    if not isinstance(authorization.get("authorized_by"), str) or not authorization["authorized_by"].strip():
        errors.append("authorization identity is required")
    if type(authorization.get("max_suites")) is not int or authorization["max_suites"] != 1:
        errors.append("authorization must grant exactly one suite")
    if authorization.get("provider") != "openai":
        errors.append("authorization provider must be openai")
    if not requested_model or authorization.get("model") != requested_model:
        errors.append("authorization model does not match requested model")
    if authorization.get("implementation_sha") != commit_sha:
        errors.append("authorization implementation SHA does not match HEAD")
    if authorization.get("lock_sha256") != verification.lock_sha256:
        errors.append("authorization lock hash mismatch")
    try:
        locked_split_hash = json.loads(Path(lock_path).read_text(encoding="utf-8"))["split_sha256"]
    except (OSError, KeyError, ValueError, TypeError):
        locked_split_hash = None
    if authorization.get("split_sha256") != locked_split_hash or not locked_split_hash:
        errors.append("authorization split hash mismatch")
    if type(authorization.get("max_completion_tokens")) is not int or authorization["max_completion_tokens"] != 1000:
        errors.append("output limit must be 1000 tokens")
    if type(authorization.get("sdk_max_retries")) is not int or authorization["sdk_max_retries"] != 0:
        errors.append("zero retry is required")

    pricing = authorization.get("pricing")
    pricing = pricing if isinstance(pricing, dict) else {}
    input_rate = _positive_decimal(pricing.get("input_usd_per_million"))
    output_rate = _positive_decimal(pricing.get("output_usd_per_million"))
    max_input_tokens = pricing.get("max_input_tokens")
    if (
        input_rate is None or output_rate is None
        or type(max_input_tokens) is not int or max_input_tokens <= 0
        or not isinstance(pricing.get("source"), str) or not pricing["source"].strip()
        or not isinstance(pricing.get("checked_utc"), str) or not pricing["checked_utc"].strip()
    ):
        errors.append("complete positive pricing and max input bound are required")
        worst_case_cost = Decimal("0")
    else:
        worst_case_cost = (
            Decimal(120) * (Decimal(max_input_tokens) * input_rate + Decimal(1000) * output_rate)
            / Decimal(1_000_000)
        )
    approved_budget = _positive_decimal(authorization.get("budget_limit_usd"))
    requested_budget = _positive_decimal(budget_limit_usd)
    if (
        approved_budget is None or requested_budget is None
        or requested_budget > approved_budget
        or worst_case_cost > requested_budget
    ):
        errors.append("budget is missing, mismatched or below the 120-case cost bound")

    return RunGateReceipt(
        passed=not errors,
        errors=tuple(errors),
        case_count=verification.case_count,
        distribution=verification.distribution,
        lock_sha256=verification.lock_sha256,
        authorization_id=authorization_id if isinstance(authorization_id, str) else None,
        authorization_sha256=canonical_sha256(dict(authorization)) if authorization else None,
        requested_model=requested_model,
        budget_limit_usd=requested_budget or Decimal("0"),
        worst_case_cost_usd=worst_case_cost,
        pricing=pricing,
    )


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
        split: str = "dev",
        generalization_gate: Optional[RunGateReceipt] = None,
    ):
        self.config = config or A1Config()
        self.generalization_gate = generalization_gate
        self.authorized_split = split
        self._generalization_suite_started = False
        self._generalization_suite_active = False
        if split == "generalization_v1":
            if (generalization_gate is None or not generalization_gate.passed
                    or generalization_gate.case_count != 120
                    or generalization_gate.requested_model != self.config.model
                    or self.config.provider != "openai"
                    or self.config.max_tokens != 1000
                    or self.config.temperature != 0.0
                    or provider is not None):
                raise ValueError("generalization gate must pass before provider creation")
        if type(self.config.max_tokens) is not int or self.config.max_tokens <= 0:
            raise ValueError("max_tokens must be a positive integer")
        if not isinstance(self.config.provider, str):
            raise ValueError("provider must be a string")
        self.config.provider = self.config.provider.lower()
        self.benchmarks_dir = benchmarks_dir or Path("evaluation/tool_calling/benchmarks")
        self._input_records: List[Dict[str, Any]] = []
        self._run_cases: List[ToolCallCase] = []
        if provider is not None:
            self.provider = provider
            if (self.config.provider == "openai"
                    and isinstance(provider, OpenAIProvider)
                    and provider.provider_name == "openai"):
                provider.request_overrides = {
                    **provider.request_overrides,
                    "max_completion_tokens": self.config.max_tokens,
                }
        else:
            provider_kwargs: Dict[str, Any] = {}
            if self.config.provider == "openai":
                provider_kwargs["request_overrides"] = {
                    "max_completion_tokens": self.config.max_tokens,
                }
                if split == "generalization_v1":
                    assert generalization_gate is not None
                    pricing = generalization_gate.pricing
                    provider_kwargs.update({
                        "max_retries": 0,
                        "pricing": ModelPricing(
                            float(pricing["input_usd_per_million"]),
                            float(pricing["output_usd_per_million"]),
                            pricing["source"], pricing["checked_utc"],
                        ),
                        "budget_guard": MonthlyBudgetGuard(
                            limit_usd=float(generalization_gate.budget_limit_usd),
                        ),
                    })
            if self.config.provider == "routed":
                # Evaluation must stay on the pinned provider/model.
                provider_kwargs["mode"] = "evaluation"
            self.provider = create_provider(
                provider_type=self.config.provider,
                model=self.config.model,
                **provider_kwargs,
            )
        self.applied_max_completion_tokens = (
            self.provider.request_overrides.get("max_completion_tokens")
            if self.config.provider == "openai"
            and isinstance(self.provider, OpenAIProvider)
            and self.provider.provider_name == "openai"
            else None
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
        if self.authorized_split == "generalization_v1" and not self._generalization_suite_active:
            raise ValueError("generalization requires a full 120-case suite")
        result = CaseResult(
            case_id=case.case_id,
            expected_calls=case.expected_calls,
            predicted_calls=[],
        )

        try:
            system_prompt, user_prompt = self.build_prompt(case, self.config.system_prompt)
            messages = [{"role": "user", "content": user_prompt}]
            schemas = get_tool_schemas()
            self._input_records.append({
                "prompt": {
                    "case_id": case.case_id,
                    "system_prompt": system_prompt,
                    "messages": deepcopy(messages),
                },
                "tool_schemas": deepcopy(schemas),
            })
            response = self.provider.generate(
                messages=messages,
                tools=schemas,
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
        result.forbidden_tool_violations = metrics["forbidden_violations"]
        if result.forbidden_tool_violations:
            result.errors.append("FORBIDDEN_TOOL")
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
        if split == "generalization_v1" or self.authorized_split == "generalization_v1":
            if (split != "generalization_v1" or self.authorized_split != split
                    or self.generalization_gate is None or not self.generalization_gate.passed):
                raise ValueError("generalization gate is required for this split")
            if case_ids is not None:
                raise ValueError("generalization requires a full 120-case suite")
            if self._generalization_suite_started:
                raise ValueError("generalization authorization allows only one suite")
            from evaluation.tool_calling.generalization import verify_generalization_lock
            split_dir = self.benchmarks_dir / split
            verification = verify_generalization_lock(split_dir, split_dir / "GENERALIZATION.lock")
            if (not verification.passed or verification.case_count != 120
                    or verification.lock_sha256 != self.generalization_gate.lock_sha256):
                raise ValueError("generalization lock changed after preflight")
        if case_ids is None:
            cases = self.load_cases(split)
            case_ids = [c.case_id for c in cases]
        else:
            cases = [self.load_case(cid, split) for cid in case_ids]
        if split == "generalization_v1" and len(cases) != 120:
            raise ValueError("generalization requires a full 120-case suite")

        self._run_cases = cases
        results = []
        if split == "generalization_v1":
            self._generalization_suite_started = True
            self._generalization_suite_active = True
        try:
            for case in cases:
                result = self.run_decision(case)
                results.append(result)
        finally:
            self._generalization_suite_active = False

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
    if split == "generalization_v1":
        raise ValueError("generalization gate is required; use the authorized CLI run")
    runner = DecisionRunner(config=config)

    # Load cases
    cases = runner.load_cases(split)

    if not cases:
        return {
            "error": f"No cases found in split '{split}'",
            "mode": "decision",
            "split": split,
        }

    runner._run_cases = cases
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
            **({"max_completion_tokens": runner.applied_max_completion_tokens}
               if runner.applied_max_completion_tokens is not None else {}),
        },
        "aggregate": aggregate.to_dict(),
        "error_summary": error_summary,
        "case_results": [result.to_dict() for result in case_results],
        "provenance": build_a1_provenance(runner, split, case_results),
    }

    if output_path:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, "w") as f:
            json.dump(result_dict, f, indent=2)

    return result_dict
