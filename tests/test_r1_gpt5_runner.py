from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from evaluation.tool_calling import gpt5_dev_runner as runner


class FakeCompletions:
    def __init__(self, model=runner.MODEL):
        self.model = model
        self.requests = []

    def create(self, **request):
        self.requests.append(request)
        return SimpleNamespace(
            id=f"resp_{len(self.requests)}",
            model=self.model,
            usage=SimpleNamespace(prompt_tokens=800, completion_tokens=30),
            choices=[SimpleNamespace(message=SimpleNamespace(content="", tool_calls=[]))],
        )


class FakeClient:
    def __init__(self, model=runner.MODEL):
        self.completions = FakeCompletions(model)
        self.chat = SimpleNamespace(completions=self.completions)


def test_preflight_matches_locked_baseline_without_provider_calls(tmp_path):
    client = FakeClient()
    report = runner.run(tmp_path / "preflight.json", client=client, preflight_only=True)
    assert report["run_status"] == "preflight_complete"
    assert report["benchmark_version"] == "r1_a1_dev_v2"
    assert len(report["expected_case_ids"]) == 24
    assert report["provenance"]["prompt_sha256"] == runner.BASELINE_PROMPT_SHA256
    assert report["provenance"]["production_schema_sha256"] == runner.BASELINE_SCHEMA_SHA256
    assert report["preflight"]["suite_ceiling_usd"] < 0.25
    assert client.completions.requests == []


def test_one_decision_per_case_uses_pinned_gpt5_request_and_saves_usage(monkeypatch, tmp_path):
    monkeypatch.setattr(runner, "git_head", lambda: "a" * 40)
    monkeypatch.setattr(runner, "git_clean", lambda: True)
    monkeypatch.setenv("GITHUB_REF", "refs/heads/master")
    monkeypatch.setenv("GITHUB_SHA", "a" * 40)
    monkeypatch.setenv("GITHUB_RUN_ID", "7654321")
    client = FakeClient()
    output = tmp_path / "result.json"
    report = runner.run(output, client=client)
    assert report["run_status"] == "complete"
    assert report["run_id"] == "7654321"
    assert len(report["case_results"]) == len(client.completions.requests) == 24
    assert report["provider_metadata"]["total_calls"] == 24
    assert report["pricing"]["known_cost_usd"] > 0
    assert all(c["actual_model"] == runner.MODEL for c in report["provider_metadata"]["calls"])
    assert all(x["model"] == runner.MODEL and x["reasoning_effort"] == "low"
               and x["max_completion_tokens"] == 1000 and "temperature" not in x
               for x in client.completions.requests)
    assert json.loads(output.read_text(encoding="utf-8"))["run_status"] == "complete"


def test_actual_model_mismatch_stops_after_one_charged_response(monkeypatch, tmp_path):
    monkeypatch.setattr(runner, "git_head", lambda: "a" * 40)
    monkeypatch.setattr(runner, "git_clean", lambda: True)
    monkeypatch.setenv("GITHUB_REF", "refs/heads/master")
    monkeypatch.setenv("GITHUB_SHA", "a" * 40)
    client = FakeClient("wrong-model")
    output = tmp_path / "partial.json"
    with pytest.raises(ValueError, match="actual model"):
        runner.run(output, client=client)
    partial = json.loads(output.read_text(encoding="utf-8"))
    assert partial["run_status"] == "identity_error"
    assert partial["attempted_calls"] == 1
    assert partial["provider_metadata"]["calls"][0]["actual_model"] == "wrong-model"
    assert partial["pricing"]["known_cost_usd"] > 0
    assert len(client.completions.requests) == 1


def test_wrong_tool_decisions_remain_scored_and_do_not_stop_suite(monkeypatch, tmp_path):
    monkeypatch.setattr(runner, "git_head", lambda: "a" * 40)
    monkeypatch.setattr(runner, "git_clean", lambda: True)
    monkeypatch.setenv("GITHUB_REF", "refs/heads/master")
    monkeypatch.setenv("GITHUB_SHA", "a" * 40)

    class WrongToolCompletions(FakeCompletions):
        def create(self, **request):
            response = super().create(**request)
            response.choices[0].message.tool_calls = [SimpleNamespace(
                id="wrong_tool", function=SimpleNamespace(name="cti_enrichment", arguments='{"indicator":"8.8.8.8"}')
            )]
            return response

    client = FakeClient()
    client.completions = WrongToolCompletions()
    client.chat = SimpleNamespace(completions=client.completions)
    report = runner.run(tmp_path / "result.json", client=client)
    assert report["run_status"] == "complete"
    assert len(report["case_results"]) == 24
    assert any("FORBIDDEN_TOOL" in row["errors"] for row in report["case_results"])


def test_malformed_native_arguments_are_charged_case_failure_without_retry(monkeypatch, tmp_path):
    monkeypatch.setattr(runner, "git_head", lambda: "a" * 40)
    monkeypatch.setattr(runner, "git_clean", lambda: True)
    monkeypatch.setenv("GITHUB_REF", "refs/heads/master")
    monkeypatch.setenv("GITHUB_SHA", "a" * 40)

    class MalformedOnce(FakeCompletions):
        def create(self, **request):
            response = super().create(**request)
            if len(self.requests) == 1:
                response.choices[0].message.tool_calls = [SimpleNamespace(
                    id="bad_call", function=SimpleNamespace(name="cti_enrichment", arguments="{bad json")
                )]
            return response

    client = FakeClient()
    client.completions = MalformedOnce()
    client.chat = SimpleNamespace(completions=client.completions)
    report = runner.run(tmp_path / "result.json", client=client)
    assert len(client.completions.requests) == report["attempted_calls"] == 24
    assert "INVALID_TOOL_CALL" in report["case_results"][0]["errors"]
    assert report["case_results"][0]["cost_usd"] > 0
    assert report["case_results"][0]["raw_tool_calls"][0]["arguments"] == "{bad json"


def test_truncated_no_tool_response_is_not_counted_as_correct_abstention(monkeypatch, tmp_path):
    monkeypatch.setattr(runner, "git_head", lambda: "a" * 40)
    monkeypatch.setattr(runner, "git_clean", lambda: True)
    monkeypatch.setenv("GITHUB_REF", "refs/heads/master")
    monkeypatch.setenv("GITHUB_SHA", "a" * 40)

    class TruncatedAtNoTool(FakeCompletions):
        def create(self, **request):
            response = super().create(**request)
            response.choices[0].finish_reason = "length" if len(self.requests) == 21 else "stop"
            return response

    client = FakeClient()
    client.completions = TruncatedAtNoTool()
    client.chat = SimpleNamespace(completions=client.completions)
    report = runner.run(tmp_path / "result.json", client=client)
    case = next(row for row in report["case_results"] if row["case_id"] == "case_021")
    assert case["trajectory_success"] is False
    assert "INVALID_TOOL_CALL" in case["errors"]
    assert report["attempted_calls"] == 24


def test_usage_above_cap_stops_but_records_charged_tokens_and_cost(monkeypatch, tmp_path):
    monkeypatch.setattr(runner, "git_head", lambda: "a" * 40)
    monkeypatch.setattr(runner, "git_clean", lambda: True)
    monkeypatch.setenv("GITHUB_REF", "refs/heads/master")
    monkeypatch.setenv("GITHUB_SHA", "a" * 40)

    class OverCap(FakeCompletions):
        def create(self, **request):
            response = super().create(**request)
            response.usage.completion_tokens = 1200
            return response

    client = FakeClient()
    client.completions = OverCap()
    client.chat = SimpleNamespace(completions=client.completions)
    output = tmp_path / "partial.json"
    with pytest.raises(ValueError):
        runner.run(output, client=client)
    partial = json.loads(output.read_text(encoding="utf-8"))
    assert partial["attempted_calls"] == 1
    assert partial["pricing"]["known_cost_usd"] > 0
    assert partial["pricing"]["cost_unknown"] is False
    assert partial["provider_metadata"]["calls"][0]["output_tokens"] == 1200


def test_existing_result_is_append_only(tmp_path):
    output = tmp_path / "result.json"
    output.write_text('{"historical":true}\n', encoding="utf-8")
    with pytest.raises(FileExistsError):
        runner.run(output, client=FakeClient(), preflight_only=True)
    assert output.read_text(encoding="utf-8") == '{"historical":true}\n'
