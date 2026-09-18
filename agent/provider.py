"""
LLM Provider Adapters

Abstract interface for LLM providers (OpenAI, Gemini, etc.)
so the orchestrator is provider-agnostic.
"""

import json
import os
from abc import ABC, abstractmethod
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from time import perf_counter
from typing import Any, Dict, List, Optional


@dataclass
class LLMResponse:
    """Container for LLM response."""

    content: str
    tool_calls: List[Dict[str, Any]]
    raw: Dict[str, Any]
    metadata: Dict[str, Any] = field(default_factory=dict)


class ProviderFailureKind(str, Enum):
    """Normalized provider failures used by the routing policy."""

    BUDGET_EXCEEDED = "budget_exceeded"
    RATE_LIMIT = "rate_limit"
    TIMEOUT = "timeout"
    UNAVAILABLE = "unavailable"
    INVALID_REQUEST = "invalid_request"
    MODERATION = "moderation"
    VALIDATION = "validation"
    UNKNOWN = "unknown"


class ProviderError(RuntimeError):
    """Provider error with a stable, policy-friendly failure category."""

    def __init__(
        self,
        message: str,
        kind: ProviderFailureKind = ProviderFailureKind.UNKNOWN,
        provider: Optional[str] = None,
        model: Optional[str] = None,
    ):
        super().__init__(message)
        self.kind = kind
        self.provider = provider
        self.model = model


@dataclass(frozen=True)
class ModelPricing:
    """Token pricing snapshot. Rates are USD per one million tokens."""

    input_usd_per_million: float
    output_usd_per_million: float
    source: str
    effective_date: str

    def estimate(self, input_tokens: int, output_tokens: int) -> float:
        return (
            input_tokens * self.input_usd_per_million + output_tokens * self.output_usd_per_million
        ) / 1_000_000


# Pricing is deliberately versioned and overridable because provider prices change.
# Source checked 2026-09-18: https://developers.openai.com/api/docs/pricing
OPENAI_PRICING_SNAPSHOT: Dict[str, ModelPricing] = {
    "gpt-5.6-luna": ModelPricing(0.20, 1.20, "OpenAI API pricing", "2026-09-18"),
    "gpt-5.6-terra": ModelPricing(2.00, 12.00, "OpenAI API pricing", "2026-09-18"),
}

DEFAULT_OPENROUTER_FREE_MODEL = "inclusionai/ling-3.0-flash-vl:free"
OPENROUTER_FREE_PRICING = ModelPricing(
    0.0,
    0.0,
    "OpenRouter model catalog",
    "2026-09-18",
)


@dataclass
class MonthlyBudgetGuard:
    """Persistent monthly cost guard for one provider account."""

    limit_usd: float
    ledger_path: Optional[Path] = None
    spent_usd: float = 0.0
    month: str = field(default_factory=lambda: datetime.now(timezone.utc).strftime("%Y-%m"))

    def __post_init__(self) -> None:
        if self.limit_usd <= 0:
            raise ValueError("Monthly budget limit must be positive")
        if self.ledger_path:
            self.ledger_path = Path(self.ledger_path)
            self._load()

    @property
    def remaining_usd(self) -> float:
        return max(0.0, self.limit_usd - self.spent_usd)

    def ensure_available(self) -> None:
        if self.spent_usd >= self.limit_usd:
            raise ProviderError(
                f"Monthly provider budget exhausted ({self.spent_usd:.6f}/{self.limit_usd:.2f} USD)",
                kind=ProviderFailureKind.BUDGET_EXCEEDED,
            )

    def record(self, cost_usd: float) -> None:
        if cost_usd < 0:
            raise ValueError("Cost cannot be negative")
        self.spent_usd += cost_usd
        self._persist()

    def to_dict(self) -> Dict[str, Any]:
        return {
            "month": self.month,
            "limit_usd": self.limit_usd,
            "spent_usd": round(self.spent_usd, 8),
            "remaining_usd": round(self.remaining_usd, 8),
        }

    def _load(self) -> None:
        if not self.ledger_path or not self.ledger_path.exists():
            return
        try:
            data = json.loads(self.ledger_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise ProviderError(
                f"Cannot read budget ledger: {exc}",
                kind=ProviderFailureKind.VALIDATION,
            ) from exc
        if data.get("month") == self.month:
            self.spent_usd = float(data.get("spent_usd", 0.0))

    def _persist(self) -> None:
        if not self.ledger_path:
            return
        self.ledger_path.parent.mkdir(parents=True, exist_ok=True)
        temporary_path = self.ledger_path.with_suffix(f"{self.ledger_path.suffix}.tmp")
        temporary_path.write_text(json.dumps(self.to_dict(), indent=2), encoding="utf-8")
        os.replace(temporary_path, self.ledger_path)


@dataclass
class ProviderCallRecord:
    """Reproducibility and cost metadata for a single LLM request."""

    requested_provider: str
    actual_provider: Optional[str]
    requested_model: str
    actual_model: Optional[str]
    status: str
    fallback_triggered: bool = False
    fallback_reason: Optional[str] = None
    input_tokens: int = 0
    output_tokens: int = 0
    total_tokens: int = 0
    estimated_cost_usd: Optional[float] = None
    latency_ms: float = 0.0
    error_kind: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class LLMProvider(ABC):
    """
    Abstract base class for LLM providers.

    Implement this interface to add support for different LLM providers.
    """

    @abstractmethod
    def __init__(self, model: str = "gpt-4o", api_key: Optional[str] = None):
        """Initialize the provider."""
        pass

    @abstractmethod
    def generate(
        self,
        messages: List[Dict[str, Any]],
        tools: Optional[List[Dict[str, Any]]] = None,
        system_prompt: Optional[str] = None,
        temperature: float = 0.0,
    ) -> LLMResponse:
        """
        Generate a response from the LLM.

        Args:
            messages: Conversation history
            tools: Optional tool definitions
            system_prompt: Optional system prompt override
            temperature: Sampling temperature

        Returns:
            LLMResponse with content and/or tool calls
        """
        pass

    @abstractmethod
    def get_name(self) -> str:
        """Get provider name."""
        pass

    def reset_tracking(self) -> None:
        """Reset per-investigation provider telemetry."""

    def get_run_metadata(self) -> Dict[str, Any]:
        """Return provider telemetry for the current investigation."""
        return {"calls": [], "total_calls": 0, "estimated_cost_usd": 0.0}


class OpenAIProvider(LLMProvider):
    """
    OpenAI GPT provider implementation.
    """

    def __init__(
        self,
        model: str = "gpt-4o",
        api_key: Optional[str] = None,
        *,
        base_url: Optional[str] = None,
        provider_name: str = "openai",
        pricing: Optional[ModelPricing] = None,
        budget_guard: Optional[MonthlyBudgetGuard] = None,
        timeout_seconds: float = 60.0,
        max_retries: int = 2,
        request_overrides: Optional[Dict[str, Any]] = None,
    ):
        """
        Initialize OpenAI provider.

        Args:
            model: Model to use (gpt-4o, gpt-4o-mini, gpt-4-turbo)
            api_key: OpenAI API key. Uses env OPENAI_API_KEY if not provided.
        """
        self.model = model
        self.api_key = api_key
        self.provider_name = provider_name
        self.pricing = pricing or OPENAI_PRICING_SNAPSHOT.get(model)
        self.budget_guard = budget_guard
        if self.budget_guard and self.pricing is None:
            raise ValueError(f"Pricing is required to enforce a budget for model {model!r}")
        self.request_overrides = request_overrides or {}
        self.call_records: List[ProviderCallRecord] = []
        self.client: Any

        # Import openai here to allow graceful fallback
        try:
            from openai import OpenAI

            client_kwargs: Dict[str, Any] = {
                "api_key": api_key,
                "timeout": timeout_seconds,
                "max_retries": max_retries,
            }
            if base_url:
                client_kwargs["base_url"] = base_url
            self.client = OpenAI(**client_kwargs)
        except ImportError:
            self.client = None
            print("Warning: OpenAI SDK not installed. Install with: pip install openai")

    def generate(
        self,
        messages: List[Dict[str, Any]],
        tools: Optional[List[Dict[str, Any]]] = None,
        system_prompt: Optional[str] = None,
        temperature: float = 0.0,
    ) -> LLMResponse:
        """Generate response using OpenAI API."""
        if self.client is None:
            raise ProviderError(
                "OpenAI client not initialized. Install openai package.",
                kind=ProviderFailureKind.UNAVAILABLE,
                provider=self.provider_name,
                model=self.model,
            )

        if self.budget_guard:
            self.budget_guard.ensure_available()

        # Build messages with system prompt
        all_messages = []
        if system_prompt:
            all_messages.append({"role": "system", "content": system_prompt})
        all_messages.extend(messages)

        request: Dict[str, Any] = {
            "model": self.model,
            "messages": all_messages,
            "tools": tools,
            "temperature": temperature,
        }
        request.update(self.request_overrides)

        started_at = perf_counter()
        try:
            response = self.client.chat.completions.create(**request)
        except Exception as exc:
            error = self._normalize_error(exc)
            self.call_records.append(
                ProviderCallRecord(
                    requested_provider=self.provider_name,
                    actual_provider=None,
                    requested_model=self.model,
                    actual_model=None,
                    status="failed",
                    latency_ms=(perf_counter() - started_at) * 1000,
                    error_kind=error.kind.value,
                )
            )
            raise error from exc

        # Extract content and tool calls
        message = response.choices[0].message
        content = message.content or ""
        tool_calls = []

        if message.tool_calls:
            for call in message.tool_calls:
                try:
                    arguments = json.loads(call.function.arguments)
                except json.JSONDecodeError as exc:
                    raise ProviderError(
                        f"Provider returned invalid tool arguments for {call.function.name}",
                        kind=ProviderFailureKind.VALIDATION,
                        provider=self.provider_name,
                        model=self.model,
                    ) from exc
                tool_calls.append(
                    {
                        "id": call.id,
                        "name": call.function.name,
                        "arguments": arguments,
                    }
                )

        usage = getattr(response, "usage", None)
        input_tokens = int(getattr(usage, "prompt_tokens", 0) or 0)
        output_tokens = int(getattr(usage, "completion_tokens", 0) or 0)
        total_tokens = int(getattr(usage, "total_tokens", input_tokens + output_tokens) or 0)
        actual_model = getattr(response, "model", None) or self.model
        estimated_cost = (
            self.pricing.estimate(input_tokens, output_tokens) if self.pricing else None
        )
        if self.budget_guard and estimated_cost is not None:
            self.budget_guard.record(estimated_cost)

        record = ProviderCallRecord(
            requested_provider=self.provider_name,
            actual_provider=self.provider_name,
            requested_model=self.model,
            actual_model=actual_model,
            status="succeeded",
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            total_tokens=total_tokens,
            estimated_cost_usd=estimated_cost,
            latency_ms=(perf_counter() - started_at) * 1000,
        )
        self.call_records.append(record)

        return LLMResponse(
            content=content,
            tool_calls=tool_calls,
            raw=response.model_dump(),
            metadata=record.to_dict(),
        )

    def get_name(self) -> str:
        """Get provider name."""
        return f"{self.provider_name} {self.model}"

    def reset_tracking(self) -> None:
        self.call_records = []

    def get_run_metadata(self) -> Dict[str, Any]:
        known_costs = [
            record.estimated_cost_usd
            for record in self.call_records
            if record.estimated_cost_usd is not None
        ]
        metadata: Dict[str, Any] = {
            "calls": [record.to_dict() for record in self.call_records],
            "total_calls": len(self.call_records),
            "estimated_cost_usd": round(sum(known_costs), 8),
            "cost_complete": len(known_costs) == len(self.call_records),
        }
        if self.pricing:
            metadata["pricing"] = asdict(self.pricing)
        if self.budget_guard:
            metadata["budget"] = self.budget_guard.to_dict()
        return metadata

    def _normalize_error(self, exc: Exception) -> ProviderError:
        status_code = getattr(exc, "status_code", None)
        error_code = str(getattr(exc, "code", "") or "").lower()
        message = str(exc)
        class_name = exc.__class__.__name__.lower()

        if status_code == 429 and error_code in {
            "insufficient_quota",
            "billing_hard_limit_reached",
        }:
            kind = ProviderFailureKind.BUDGET_EXCEEDED
        elif status_code == 429:
            kind = ProviderFailureKind.RATE_LIMIT
        elif "timeout" in class_name:
            kind = ProviderFailureKind.TIMEOUT
        elif status_code is not None and status_code >= 500:
            kind = ProviderFailureKind.UNAVAILABLE
        elif error_code in {"content_policy_violation", "moderation_blocked"}:
            kind = ProviderFailureKind.MODERATION
        elif status_code is not None and 400 <= status_code < 500:
            kind = ProviderFailureKind.INVALID_REQUEST
        else:
            kind = ProviderFailureKind.UNKNOWN

        return ProviderError(message, kind, self.provider_name, self.model)


class OpenRouterProvider(OpenAIProvider):
    """OpenRouter adapter using its OpenAI-compatible endpoint."""

    def __init__(
        self,
        model: str,
        api_key: Optional[str] = None,
        *,
        pricing: Optional[ModelPricing] = None,
        budget_guard: Optional[MonthlyBudgetGuard] = None,
        allow_provider_fallbacks: bool = False,
        free_only: bool = False,
        timeout_seconds: float = 60.0,
        max_retries: int = 2,
    ):
        if free_only and not model.endswith(":free"):
            raise ValueError("OpenRouter free-only policy requires a model ending in ':free'")

        api_key = api_key or os.getenv("OPENROUTER_API_KEY")
        provider_preferences: Dict[str, Any] = {
            "allow_fallbacks": allow_provider_fallbacks,
            "require_parameters": True,
        }
        if free_only:
            provider_preferences["max_price"] = {
                "prompt": 0,
                "completion": 0,
            }
            pricing = pricing or OPENROUTER_FREE_PRICING

        super().__init__(
            model=model,
            api_key=api_key,
            base_url="https://openrouter.ai/api/v1",
            provider_name="openrouter",
            pricing=pricing,
            budget_guard=budget_guard,
            timeout_seconds=timeout_seconds,
            max_retries=max_retries,
            request_overrides={"extra_body": {"provider": provider_preferences}},
        )


class RoutedProvider(LLMProvider):
    """Route to OpenRouter only for approved operational failures."""

    FALLBACK_FAILURES = {
        ProviderFailureKind.BUDGET_EXCEEDED,
        ProviderFailureKind.RATE_LIMIT,
        ProviderFailureKind.TIMEOUT,
        ProviderFailureKind.UNAVAILABLE,
    }

    def __init__(
        self,
        primary: LLMProvider,
        fallback: LLMProvider,
        mode: str = "evaluation",
    ):
        if mode not in {"evaluation", "development", "demo"}:
            raise ValueError("mode must be evaluation, development, or demo")
        self.primary = primary
        self.fallback = fallback
        self.mode = mode
        self.call_records: List[ProviderCallRecord] = []

    def generate(
        self,
        messages: List[Dict[str, Any]],
        tools: Optional[List[Dict[str, Any]]] = None,
        system_prompt: Optional[str] = None,
        temperature: float = 0.0,
    ) -> LLMResponse:
        try:
            response = self.primary.generate(messages, tools, system_prompt, temperature)
            record = self._record_from_response(response, fallback_triggered=False)
            self.call_records.append(record)
            response.metadata = record.to_dict()
            return response
        except ProviderError as primary_error:
            if self.mode == "evaluation" or primary_error.kind not in self.FALLBACK_FAILURES:
                raise

            try:
                response = self.fallback.generate(messages, tools, system_prompt, temperature)
            except ProviderError as fallback_error:
                self.call_records.append(
                    ProviderCallRecord(
                        requested_provider=self._provider_name(self.primary),
                        actual_provider=None,
                        requested_model=self._model_name(self.primary),
                        actual_model=None,
                        status="failed",
                        fallback_triggered=True,
                        fallback_reason=primary_error.kind.value,
                        error_kind=fallback_error.kind.value,
                    )
                )
                raise

            record = self._record_from_response(
                response,
                fallback_triggered=True,
                fallback_reason=primary_error.kind.value,
            )
            self.call_records.append(record)
            response.metadata = record.to_dict()
            return response

    def get_name(self) -> str:
        return f"RoutedProvider(primary={self.primary.get_name()}, fallback={self.fallback.get_name()}, mode={self.mode})"

    def reset_tracking(self) -> None:
        self.call_records = []
        self.primary.reset_tracking()
        self.fallback.reset_tracking()

    def get_run_metadata(self) -> Dict[str, Any]:
        known_costs = [
            record.estimated_cost_usd
            for record in self.call_records
            if record.estimated_cost_usd is not None
        ]
        return {
            "mode": self.mode,
            "calls": [record.to_dict() for record in self.call_records],
            "total_calls": len(self.call_records),
            "fallback_count": sum(record.fallback_triggered for record in self.call_records),
            "estimated_cost_usd": round(sum(known_costs), 8),
            "cost_complete": len(known_costs) == len(self.call_records),
            "primary": self.primary.get_run_metadata(),
            "fallback": self.fallback.get_run_metadata(),
        }

    def _record_from_response(
        self,
        response: LLMResponse,
        fallback_triggered: bool,
        fallback_reason: Optional[str] = None,
    ) -> ProviderCallRecord:
        metadata = response.metadata
        return ProviderCallRecord(
            requested_provider=self._provider_name(self.primary),
            actual_provider=metadata.get("actual_provider"),
            requested_model=self._model_name(self.primary),
            actual_model=metadata.get("actual_model"),
            status=metadata.get("status", "succeeded"),
            fallback_triggered=fallback_triggered,
            fallback_reason=fallback_reason,
            input_tokens=int(metadata.get("input_tokens", 0)),
            output_tokens=int(metadata.get("output_tokens", 0)),
            total_tokens=int(metadata.get("total_tokens", 0)),
            estimated_cost_usd=metadata.get("estimated_cost_usd"),
            latency_ms=float(metadata.get("latency_ms", 0.0)),
            error_kind=metadata.get("error_kind"),
        )

    @staticmethod
    def _model_name(provider: LLMProvider) -> str:
        return str(getattr(provider, "model", provider.get_name()))

    @staticmethod
    def _provider_name(provider: LLMProvider) -> str:
        return str(getattr(provider, "provider_name", provider.get_name()))


class MockProvider(LLMProvider):
    """
    Mock LLM provider for testing.

    Returns predefined responses based on prompts.
    """

    def __init__(self, model: str = "mock", responses: Optional[Dict[str, str]] = None):
        """
        Initialize mock provider.

        Args:
            model: Mock model name
            responses: Dict mapping prompt keywords to responses
        """
        self.model = model
        self.responses = responses or {}
        self.call_history: List[Dict[str, Any]] = []

    def generate(
        self,
        messages: List[Dict[str, Any]],
        tools: Optional[List[Dict[str, Any]]] = None,
        system_prompt: Optional[str] = None,
        temperature: float = 0.0,
    ) -> LLMResponse:
        """Generate mock response."""
        # Record call
        self.call_history.append(
            {
                "messages": messages,
                "tools": tools,
                "system_prompt": system_prompt,
            }
        )

        # Find matching response
        last_message = messages[-1]["content"] if messages else ""
        response_text = self._match_response(last_message)
        tool_calls = self._next_tool_call(messages)

        return LLMResponse(
            content=response_text,
            tool_calls=tool_calls,
            raw={"mock": True, "tool_calls": tool_calls},
        )

    def _next_tool_call(self, messages: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Select the next read-only tool from observed evidence, not a fixed pipeline."""
        called: List[str] = []
        for message in messages:
            if message.get("role") == "assistant" and message.get("tool_calls"):
                called.extend(call["function"]["name"] for call in message["tool_calls"])

        tool_messages = [
            message["content"].lower() for message in messages if message.get("role") == "tool"
        ]
        context = " ".join(message.get("content", "").lower() for message in messages)
        network_markers = ("scan", "beacon", "exfil", "traffic", "connection", "dns", "c2")
        endpoint_markers = ("edr", "process", "workstation", "endpoint", "macro", "powershell")
        deep_endpoint_markers = (
            "ransomware",
            "apt",
            "kill chain",
            "lateral movement",
            "supply chain",
        )
        if not called:
            return [
                {
                    "id": "mock_cti_1",
                    "name": "cti_enrichment",
                    "arguments": {"indicator": self._indicator(messages)},
                }
            ]
        if (
            "cti_enrichment" in called
            and "network_investigation" not in called
            and "endpoint_investigation" not in called
        ):
            if any(marker in context for marker in network_markers) or (
                tool_messages
                and any(word in tool_messages[-1] for word in ("malicious", "suspicious"))
            ):
                return [
                    {
                        "id": "mock_network_1",
                        "name": "network_investigation",
                        "arguments": {"indicator": self._indicator(messages)},
                    }
                ]
            if any(marker in context for marker in endpoint_markers):
                host = self._endpoint_host(messages)
                if host:
                    return [
                        {
                            "id": "mock_endpoint_1",
                            "name": "endpoint_investigation",
                            "arguments": {"host": host},
                        }
                    ]
        if "network_investigation" in called and "endpoint_investigation" not in called:
            if any(marker in context for marker in deep_endpoint_markers):
                host = self._endpoint_host(messages)
                if host:
                    return [
                        {
                            "id": "mock_endpoint_1",
                            "name": "endpoint_investigation",
                            "arguments": {"host": host},
                        }
                    ]
        return []

    @staticmethod
    def _indicator(messages: List[Dict[str, Any]]) -> str:
        for message in messages:
            content = message.get("content", "")
            marker = "**Indicator**:"
            if isinstance(content, str) and marker in content:
                return content.split(marker, 1)[1].splitlines()[0].strip()
        return "unknown"

    @staticmethod
    def _endpoint_host(messages: List[Dict[str, Any]]) -> Optional[str]:
        for message in messages:
            content = message.get("content", "")
            marker = "**Endpoint pivots**:"
            if isinstance(content, str) and marker in content:
                return content.split(marker, 1)[1].splitlines()[0].strip().split(",")[0]
        return None

    def _match_response(self, prompt: str) -> str:
        """Match prompt to predefined response."""
        prompt_lower = prompt.lower()

        for keyword, response in self.responses.items():
            if keyword.lower() in prompt_lower:
                return response

        return "I need to investigate further. Let me call the appropriate tool."

    def get_name(self) -> str:
        """Get provider name."""
        return f"MockProvider ({self.model})"

    def add_response(self, keyword: str, response: str):
        """Add a response mapping."""
        self.responses[keyword] = response

    def reset_tracking(self) -> None:
        self.call_history = []

    def get_run_metadata(self) -> Dict[str, Any]:
        return {
            "calls": [],
            "total_calls": len(self.call_history),
            "estimated_cost_usd": 0.0,
            "cost_complete": True,
            "mock": True,
        }


def create_provider(
    provider_type: str = "openai", model: str = "gpt-4o", api_key: Optional[str] = None, **kwargs
) -> LLMProvider:
    """
    Factory function to create LLM provider.

    Args:
        provider_type: "openai", "openrouter", "routed", or "mock"
        model: Model name
        api_key: API key
        **kwargs: Additional provider-specific arguments

    Returns:
        LLMProvider instance
    """
    provider_type = provider_type.lower()
    if provider_type == "openai":
        return OpenAIProvider(model=model, api_key=api_key, **kwargs)
    if provider_type == "openrouter":
        return OpenRouterProvider(model=model, api_key=api_key, **kwargs)
    if provider_type == "routed":
        fallback_model = kwargs.pop("fallback_model", DEFAULT_OPENROUTER_FREE_MODEL)

        mode = kwargs.pop("mode", "evaluation")
        monthly_budget_usd = kwargs.pop("monthly_budget_usd", None)
        budget_ledger_path = kwargs.pop("budget_ledger_path", ".vinsoc/openai_budget.json")
        primary_pricing = kwargs.pop("primary_pricing", None)
        fallback_pricing = kwargs.pop("fallback_pricing", None)
        openrouter_api_key = kwargs.pop("openrouter_api_key", None)
        allow_provider_fallbacks = kwargs.pop("allow_provider_fallbacks", False)
        free_only = kwargs.pop("free_only", True)
        if kwargs:
            unknown = ", ".join(sorted(kwargs))
            raise ValueError(f"Unknown routed provider options: {unknown}")

        budget_guard = None
        if monthly_budget_usd is not None:
            budget_guard = MonthlyBudgetGuard(
                limit_usd=float(monthly_budget_usd),
                ledger_path=Path(budget_ledger_path),
            )

        primary = OpenAIProvider(
            model=model,
            api_key=api_key,
            pricing=primary_pricing,
            budget_guard=budget_guard,
        )
        fallback = OpenRouterProvider(
            model=fallback_model,
            api_key=openrouter_api_key,
            pricing=fallback_pricing,
            allow_provider_fallbacks=allow_provider_fallbacks,
            free_only=free_only,
        )
        return RoutedProvider(primary=primary, fallback=fallback, mode=mode)
    if provider_type == "mock":
        return MockProvider(model=model, **kwargs)
    raise ValueError(f"Unknown provider type: {provider_type}")
