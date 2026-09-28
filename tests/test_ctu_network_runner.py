from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from evaluation.ctu_network_public import run_model as runner


class Result:
    def __init__(self, rows):
        self.rows = rows
        self.truncated = False


class Snapshot:
    def __init__(self, _path):
        pass

    def query(self, sql):
        if "information_schema.columns" in sql:
            return Result([{"table_name": "network_flows", "column_name": "source_dataset", "data_type": "VARCHAR"}])
        return Result([{"value": 1}])


class FakeCompletions:
    def __init__(self, mode="ok", *, prompt_tokens=100):
        self.mode = mode
        self.prompt_tokens = prompt_tokens
        self.requests = []

    def create(self, **request):
        self.requests.append(request)
        if self.mode == "provider_error":
            raise RuntimeError("provider unavailable")
        usage = None if self.mode == "missing_usage" else SimpleNamespace(prompt_tokens=self.prompt_tokens, completion_tokens=10)
        model = "wrong-model" if self.mode == "wrong_model" else runner.MODEL
        return SimpleNamespace(model=model, usage=usage, choices=[SimpleNamespace(message=SimpleNamespace(content="SELECT 1"))])


class FakeClient:
    def __init__(self, mode="ok", *, prompt_tokens=100):
        self.completions = FakeCompletions(mode, prompt_tokens=prompt_tokens)
        self.chat = SimpleNamespace(completions=self.completions)


def setup_run(monkeypatch, tmp_path):
    cases = tmp_path / "cases"
    cases.mkdir()
    for index in range(1, 9):
        (cases / f"ctu_sql_{index:03d}.json").write_text(json.dumps({
            "case_id": f"ctu_sql_{index:03d}", "question": f"question {index}",
            "database_snapshot": "snapshot.duckdb", "gold_sql": ["SELECT 1"],
            "category": "network", "difficulty": "basic", "result_comparator": "scalar",
        }), encoding="utf-8")
    lock = {"version": runner.MODEL, "logical_snapshot_sha256": "a" * 64,
            "split_sha256": "b" * 64, "source_file_sha256": {}, "builder_scorer_sha256": {}}
    monkeypatch.setattr(runner, "CASES", cases)
    monkeypatch.setattr(runner, "validate", lambda *_args, **_kwargs: lock)
    monkeypatch.setattr(runner, "DuckDBSnapshot", Snapshot)
    monkeypatch.setattr(runner.subprocess, "check_output", lambda *_args, **_kwargs: "f" * 40)
    monkeypatch.setenv("GITHUB_REF", "refs/heads/master")
    monkeypatch.setenv("GITHUB_SHA", "f" * 40)


def test_runner_sends_eight_pinned_requests_and_records_usage(monkeypatch, tmp_path):
    setup_run(monkeypatch, tmp_path)
    client = FakeClient()
    report = runner.run(tmp_path / "snapshot.duckdb", tmp_path / "report.json", client=client)
    assert report["case_ids"] == [f"ctu_sql_{index:03d}" for index in range(1, 9)]
    assert report["attempted_calls"] == 8
    assert report["responses_received"] == 8
    assert report["calls_with_valid_usage"] == 8
    assert report["run_status"] == "complete"
    # Check gpt-5-mini specific fields: model, reasoning_effort, no temperature
    for request in client.completions.requests:
        assert request["model"] == runner.MODEL
        assert request["reasoning_effort"] == "low"
        assert "temperature" not in request
        assert request["max_completion_tokens"] == 1000
    assert report["pricing"]["known_cost_usd"] > 0
    # Config reflects gpt-5-mini migration
    assert report["config"]["model"] == "gpt-5-mini-2025-08-07"
    assert report["config"]["reasoning_effort"] == "low"
    assert report["config"]["temperature"] is None


@pytest.mark.parametrize("mode", ["wrong_model", "missing_usage", "provider_error"])
def test_runner_stops_and_preserves_partial_report(monkeypatch, tmp_path, mode):
    setup_run(monkeypatch, tmp_path)
    output = tmp_path / "partial.json"
    with pytest.raises((ValueError, RuntimeError)):
        runner.run(tmp_path / "snapshot.duckdb", output, client=FakeClient(mode))
    partial = json.loads(output.read_text(encoding="utf-8"))
    assert partial["run_status"] == "provider_or_validation_error"
    assert partial["pricing"]["cost_unknown"] is True
    assert partial["attempted_calls"] == 1
    assert partial["responses_received"] <= 1


def test_runner_records_known_charge_before_scoring_failure(monkeypatch, tmp_path):
    setup_run(monkeypatch, tmp_path)
    output = tmp_path / "partial.json"
    monkeypatch.setattr(runner, "evaluate_sql_case", lambda *_args, **_kwargs: (_ for _ in ()).throw(RuntimeError("scoring failed")))
    report = runner.run(tmp_path / "snapshot.duckdb", output, client=FakeClient())
    persisted = json.loads(output.read_text(encoding="utf-8"))
    assert report["attempted_calls"] == 8
    assert persisted["pricing"]["known_cost_usd"] > 0
    assert persisted["case_results"][0]["scoring_error"] == "RuntimeError"
    assert persisted["case_results"][0]["cost_usd"] > 0


def test_runner_stops_before_scoring_when_actual_input_exceeds_bound(monkeypatch, tmp_path):
    setup_run(monkeypatch, tmp_path)
    output = tmp_path / "partial.json"
    with pytest.raises(ValueError, match="preflight bound"):
        runner.run(tmp_path / "snapshot.duckdb", output, client=FakeClient(prompt_tokens=999999))
    persisted = json.loads(output.read_text(encoding="utf-8"))
    assert persisted["attempted_calls"] == 1
    assert persisted["responses_received"] == 1
    assert persisted["calls_with_valid_usage"] == 1
    assert persisted["pricing"]["known_cost_usd"] > 0


def test_preflight_blocks_combined_budget_before_calls(monkeypatch):
    request = runner.build_request(
        SimpleNamespace(question="q"), "network_flows(source_dataset VARCHAR)"
    )
    monkeypatch.setattr(runner, "BUDGET_USD", 0.000001)
    with pytest.raises(ValueError, match="exceeds"):
        runner.preflight_bounds([request] * 8)


def test_runner_budget_stop_happens_before_any_api_attempt(monkeypatch, tmp_path):
    setup_run(monkeypatch, tmp_path)
    monkeypatch.setattr(runner, "preflight_bounds", lambda _requests: {
        "r2_bounds": [{"input_token_bound": 1, "max_cost_usd": 0.001}] * 8,
        "reserved_demo_ceiling_usd": 0.001,
        "combined_ceiling_usd": 0.009,
    })
    monkeypatch.setattr(runner, "BUDGET_USD", 0.009)
    client = FakeClient()
    with pytest.raises(ValueError, match="budget"):
        runner.run(tmp_path / "snapshot.duckdb", tmp_path / "budget.json", client=client)
    persisted = json.loads((tmp_path / "budget.json").read_text(encoding="utf-8"))
    assert persisted["run_status"] == "budget_stopped"
    assert persisted["attempted_calls"] == 0
    assert client.completions.requests == []


def test_paid_workflow_is_manual_only_and_scopes_secret_to_paid_step():
    workflow = Path(".github/workflows/ctu-network-public-r2.yml").read_text(encoding="utf-8")
    lines = workflow.splitlines()
    on_line = lines.index("on:")
    triggers = []
    for line in lines[on_line + 1:]:
        if line and not line.startswith(" "):
            break
        if line.startswith("  ") and not line.startswith("    ") and line.strip():
            triggers.append(line.strip())
    assert triggers == ["workflow_dispatch:"]
    assert workflow.count("${{ secrets.OPENAI_API_KEY }}") == 1
    paid = workflow.split("- name: Run exactly one paid eight-case R2 pass", 1)[1].split("- name:", 1)[0]
    assert "OPENAI_API_KEY: ${{ secrets.OPENAI_API_KEY }}" in paid
    assert "--preflight-only" in workflow
    assert "if: always()" in workflow


def test_gpt5mini_model_config_lock_exists():
    """MODEL_CONFIG_GPT5MINI.lock must exist and have required fields."""
    config = json.loads(Path("evaluation/ctu_network_public/MODEL_CONFIG_GPT5MINI.lock").read_text(encoding="utf-8"))
    assert config["model"] == "gpt-5-mini-2025-08-07"
    assert config["temperature"] is None
    assert config["reasoning_effort"] == "low"
    assert config["max_completion_tokens"] == 1000
    assert config["max_retries"] == 0
    assert config["input_price_usd_per_million"] == 0.25
    assert config["output_price_usd_per_million"] == 2.00
    assert config["ceiling_8_cases_usd"] == 0.10


def test_request_bound_rejects_temperature_for_gpt5mini(monkeypatch):
    """gpt-5-mini requires temperature to be absent, not just zero."""
    request = runner.build_request(
        SimpleNamespace(question="q"), "network_flows(source_dataset VARCHAR)"
    )
    # Request should not have temperature
    assert "temperature" not in request
    # Adding temperature should fail request_bound
    request["temperature"] = 0
    with pytest.raises(ValueError, match="temperature must be absent"):
        runner.request_bound(request)


def test_request_bound_checks_reasoning_effort():
    """request_bound validates reasoning_effort is present and correct."""
    request = runner.build_request(
        SimpleNamespace(question="q"), "network_flows(source_dataset VARCHAR)"
    )
    # Valid request
    bound = runner.request_bound(request)
    assert bound["max_output_tokens"] == 1000
    assert bound["max_cost_usd"] > 0

    # Wrong reasoning_effort
    bad = dict(request, reasoning_effort="high")
    with pytest.raises(ValueError, match="Unpinned"):
        runner.request_bound(bad)

    # Missing reasoning_effort
    bad = dict(request)
    del bad["reasoning_effort"]
    with pytest.raises(ValueError, match="Unpinned"):
        runner.request_bound(bad)


def test_ceiling_8_cases_under_10_cents():
    """8-case suite ceiling must be <= $0.10 per MODEL_CONFIG_GPT5MINI.lock."""
    request = runner.build_request(
        SimpleNamespace(question="How many rows are in the network_flows table?"),
        "network_flows(source_dataset VARCHAR, event_time TIMESTAMP, src_ip VARCHAR)"
    )
    # Approximate worst case: 500 prompt tokens + 1000 output tokens
    # Cost = (500 * 0.25 + 1000 * 2.00) / 1M = 0.000125 + 0.002 = 0.002125 per call
    # 8 cases + 2 demo reserved calls * max = 8 * 0.002125 + 2 * 0.002125 = 0.02125
    bound = runner.request_bound(request)
    # Conservative ceiling for 8 cases + 2 demo calls
    ceiling = 8 * bound["max_cost_usd"] + 2 * bound["max_cost_usd"]
    assert ceiling <= 0.10, f"Ceiling {ceiling} exceeds $0.10"
