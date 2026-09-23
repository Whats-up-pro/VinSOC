"""CLI contract tests for reproducible R1 decision benchmarks."""

from types import SimpleNamespace

import evaluation.tool_calling.__main__ as cli
from evaluation.tool_calling.decision_runner import A1Config


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
