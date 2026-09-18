"""Tests for deterministic provider routing and budget controls."""

from pathlib import Path
from typing import Any, Dict, List, Optional

import pytest

from agent.orchestrator import InvestigationOrchestrator
from agent.provider import (
    DEFAULT_OPENROUTER_FREE_MODEL,
    LLMProvider,
    LLMResponse,
    MockProvider,
    ModelPricing,
    MonthlyBudgetGuard,
    OpenRouterProvider,
    ProviderError,
    ProviderFailureKind,
    RoutedProvider,
)


class StubProvider(LLMProvider):
    """Small deterministic provider used to exercise routing policy."""

    def __init__(
        self,
        model: str,
        provider_name: str,
        failure: Optional[ProviderFailureKind] = None,
    ):
        self.model = model
        self.provider_name = provider_name
        self.failure = failure
        self.calls = 0

    def generate(
        self,
        messages: List[Dict[str, Any]],
        tools: Optional[List[Dict[str, Any]]] = None,
        system_prompt: Optional[str] = None,
        temperature: float = 0.0,
    ) -> LLMResponse:
        self.calls += 1
        if self.failure:
            raise ProviderError(
                "stub failure",
                kind=self.failure,
                provider=self.provider_name,
                model=self.model,
            )
        return LLMResponse(
            content="ok",
            tool_calls=[],
            raw={},
            metadata={
                "actual_provider": self.provider_name,
                "actual_model": self.model,
                "status": "succeeded",
                "input_tokens": 100,
                "output_tokens": 20,
                "total_tokens": 120,
                "estimated_cost_usd": 0.001,
                "latency_ms": 10.0,
            },
        )

    def get_name(self) -> str:
        return f"{self.provider_name} {self.model}"


def test_evaluation_mode_never_falls_back() -> None:
    primary = StubProvider("primary-model", "openai", ProviderFailureKind.RATE_LIMIT)
    fallback = StubProvider("fallback-model", "openrouter")
    router = RoutedProvider(primary, fallback, mode="evaluation")

    with pytest.raises(ProviderError) as error:
        router.generate([{"role": "user", "content": "test"}])

    assert error.value.kind == ProviderFailureKind.RATE_LIMIT
    assert primary.calls == 1
    assert fallback.calls == 0


@pytest.mark.parametrize(
    "failure",
    [
        ProviderFailureKind.BUDGET_EXCEEDED,
        ProviderFailureKind.RATE_LIMIT,
        ProviderFailureKind.TIMEOUT,
        ProviderFailureKind.UNAVAILABLE,
    ],
)
def test_development_mode_falls_back_only_for_operational_failures(
    failure: ProviderFailureKind,
) -> None:
    primary = StubProvider("primary-model", "openai", failure)
    fallback = StubProvider("fallback-model", "openrouter")
    router = RoutedProvider(primary, fallback, mode="development")

    response = router.generate([{"role": "user", "content": "test"}])

    assert response.content == "ok"
    assert response.metadata["actual_provider"] == "openrouter"
    assert response.metadata["fallback_triggered"] is True
    assert response.metadata["fallback_reason"] == failure.value
    assert router.get_run_metadata()["fallback_count"] == 1


@pytest.mark.parametrize(
    "failure",
    [
        ProviderFailureKind.INVALID_REQUEST,
        ProviderFailureKind.MODERATION,
        ProviderFailureKind.VALIDATION,
        ProviderFailureKind.UNKNOWN,
    ],
)
def test_development_mode_does_not_hide_non_operational_failures(
    failure: ProviderFailureKind,
) -> None:
    primary = StubProvider("primary-model", "openai", failure)
    fallback = StubProvider("fallback-model", "openrouter")
    router = RoutedProvider(primary, fallback, mode="development")

    with pytest.raises(ProviderError) as error:
        router.generate([{"role": "user", "content": "test"}])

    assert error.value.kind == failure
    assert fallback.calls == 0


def test_monthly_budget_guard_persists_and_fails_closed(tmp_path: Path) -> None:
    ledger = tmp_path / "usage.json"
    guard = MonthlyBudgetGuard(limit_usd=0.01, ledger_path=ledger)
    guard.record(0.01)

    reloaded = MonthlyBudgetGuard(limit_usd=0.01, ledger_path=ledger)

    assert reloaded.spent_usd == pytest.approx(0.01)
    with pytest.raises(ProviderError) as error:
        reloaded.ensure_available()
    assert error.value.kind == ProviderFailureKind.BUDGET_EXCEEDED


def test_pricing_snapshot_calculates_request_cost() -> None:
    pricing = ModelPricing(
        input_usd_per_million=0.20,
        output_usd_per_million=1.20,
        source="test",
        effective_date="2026-09-18",
    )

    assert pricing.estimate(10_000, 2_000) == pytest.approx(0.0044)


def test_openrouter_free_only_policy_rejects_paid_model() -> None:
    with pytest.raises(ValueError, match="requires a model ending in ':free'"):
        OpenRouterProvider(
            model="vendor/paid-model",
            api_key="test-key",
            free_only=True,
        )


def test_openrouter_free_only_policy_sets_zero_max_price() -> None:
    provider = OpenRouterProvider(
        model=DEFAULT_OPENROUTER_FREE_MODEL,
        api_key="test-key",
        free_only=True,
    )

    routing = provider.request_overrides["extra_body"]["provider"]
    assert routing["max_price"] == {"prompt": 0, "completion": 0}
    assert provider.pricing is not None
    assert provider.pricing.estimate(10_000, 2_000) == 0.0


def test_investigation_case_contains_provider_run_metadata() -> None:
    orchestrator = InvestigationOrchestrator(
        provider=MockProvider(model="metadata-test"),
        cti_mock_data={
            "185.220.101.45": {
                "reputation": "malicious",
                "confidence": "high",
                "sources": [],
            }
        },
    )

    case = orchestrator.investigate(
        "185.220.101.45",
        context="Suspicious outbound connection",
    )

    assert case.metadata["llm_run"]["mock"] is True
    assert case.metadata["llm_run"]["total_calls"] > 0
