"""CLI contract tests for reproducible R1 decision benchmarks."""

from types import SimpleNamespace

import evaluation.tool_calling.__main__ as cli
from evaluation.tool_calling.decision_runner import A1Config
from evaluation.tool_calling.models import CaseResult


def test_decision_cli_passes_pinned_provider_model_and_temperature(monkeypatch):
    captured = {}

    class FakeDecisionRunner:
        def __init__(self, config=None):
            captured["config"] = config

        def run_suite(self, split="dev", case_ids=None):
            return []

    monkeypatch.setattr(cli, "DecisionRunner", FakeDecisionRunner)
    args = SimpleNamespace(
        mode="decision",
        split="dev",
        cases=None,
        provider="openai",
        model="pinned-model",
        temperature=0.25,
    )

    cli.run_benchmark(args)

    assert isinstance(captured["config"], A1Config)
    assert captured["config"].provider == "openai"
    assert captured["config"].model == "pinned-model"
    assert captured["config"].temperature == 0.25


def test_decision_cli_persists_provider_and_config_metadata(monkeypatch, tmp_path):
    class FakeProvider:
        def get_name(self):
            return "fake-provider"

        def get_run_metadata(self):
            return {"total_calls": 1, "actual_model": "pinned-model"}

    class FakeDecisionRunner:
        def __init__(self, config=None):
            self.config = config
            self.provider = FakeProvider()

        def run_suite(self, split="dev", case_ids=None):
            return [
                CaseResult(
                    case_id="case_001",
                    expected_calls=[],
                    predicted_calls=[],
                    trajectory_success=True,
                )
            ]

    monkeypatch.setattr(cli, "DecisionRunner", FakeDecisionRunner)
    monkeypatch.chdir(tmp_path)
    args = SimpleNamespace(
        mode="decision",
        split="dev",
        cases=None,
        provider="openai",
        model="pinned-model",
        temperature=0.0,
    )

    cli.run_benchmark(args)

    metrics_path = next((tmp_path / "results" / "tool_calling").glob("*/metrics.json"))
    payload = __import__("json").loads(metrics_path.read_text(encoding="utf-8"))
    assert payload["provider"] == "fake-provider"
    assert payload["provider_metadata"]["actual_model"] == "pinned-model"
    assert payload["config"] == {
        "provider": "openai",
        "model": "pinned-model",
        "temperature": 0.0,
    }
