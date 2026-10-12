"""CLI contract tests for reproducible R1 decision benchmarks."""

import json
from types import SimpleNamespace

import pytest

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


def test_generalization_cli_lists_and_verifies_locked_cases_offline(monkeypatch, capsys):
    def no_provider(*args, **kwargs):
        raise AssertionError("provider created during offline command")

    monkeypatch.setattr(cli, "DecisionRunner", no_provider)
    assert cli.main(["list", "generalization_v1"]) == 0
    assert "Available cases in 'generalization_v1': 120" in capsys.readouterr().out

    assert cli.main(["lock", "generalization_v1"]) == 0
    lock_receipt = json.loads(capsys.readouterr().out)
    assert lock_receipt["passed"] is True
    assert lock_receipt["case_count"] == 120
    assert lock_receipt["distribution"] == {
        "no_tool": 24, "single_tool": 54, "two_tool": 30, "three_tool": 12,
    }


@pytest.mark.parametrize(
    "argv",
    [
        ["preflight", "generalization_v1"],
        ["run", "--mode", "decision", "--split", "generalization_v1"],
        ["run", "--mode", "integration", "--split", "generalization_v1"],
        ["run", "--mode", "decision", "--split", "generalization_v1", "--cases", "gen_001"],
    ],
)
def test_generalization_cli_blocks_before_provider_without_suite_authorization(
    monkeypatch, capsys, argv
):
    def no_provider(*args, **kwargs):
        raise AssertionError("provider created before generalization gate")

    monkeypatch.setattr(cli, "DecisionRunner", no_provider)
    assert cli.main(argv) == 1
    assert '"provider_created": false' in capsys.readouterr().out.lower()


def test_generalization_run_validates_gate_before_runner_construction(monkeypatch, tmp_path):
    sequence = []

    def checked_gate(*args, **kwargs):
        sequence.append("gate")
        return SimpleNamespace(passed=True, errors=(), provider_created=False)

    class FakeDecisionRunner:
        def __init__(self, *, config, split, generalization_gate):
            sequence.append("runner")
            assert generalization_gate.passed and split == "generalization_v1"

        def run_suite(self, *, split, case_ids):
            assert split == "generalization_v1" and case_ids is None
            return []

    monkeypatch.setattr(cli, "validate_generalization_run_gate", checked_gate)
    monkeypatch.setattr(cli, "DecisionRunner", FakeDecisionRunner)
    auth = tmp_path / "authorized.json"
    auth.write_text(json.dumps({"scope": "r1_tool_calling_generalization_v1"}))

    assert cli.main([
        "run", "--mode", "decision", "--split", "generalization_v1",
        "--model", "pinned-model", "--authorization", str(auth),
        "--budget-usd", "7.00",
    ]) == 1  # Empty suite cannot produce a successful run artifact.
    assert sequence == ["gate", "runner"]
