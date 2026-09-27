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
    def __init__(self, mode="ok"):
        self.mode = mode
        self.requests = []

    def create(self, **request):
        self.requests.append(request)
        if self.mode == "provider_error":
            raise RuntimeError("provider unavailable")
        usage = None if self.mode == "missing_usage" else SimpleNamespace(prompt_tokens=100, completion_tokens=10)
        model = "wrong-model" if self.mode == "wrong_model" else runner.MODEL
        return SimpleNamespace(model=model, usage=usage, choices=[SimpleNamespace(message=SimpleNamespace(content="SELECT 1"))])


class FakeClient:
    def __init__(self, mode="ok"):
        self.completions = FakeCompletions(mode)
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
    assert report["provider_calls"] == 8
    assert report["run_status"] == "complete"
    assert all(request["model"] == runner.MODEL and request["temperature"] == 0 and request["max_completion_tokens"] == 1000 for request in client.completions.requests)
    assert report["pricing"]["known_cost_usd"] > 0


@pytest.mark.parametrize("mode", ["wrong_model", "missing_usage", "provider_error"])
def test_runner_stops_and_preserves_partial_report(monkeypatch, tmp_path, mode):
    setup_run(monkeypatch, tmp_path)
    output = tmp_path / "partial.json"
    with pytest.raises((ValueError, RuntimeError)):
        runner.run(tmp_path / "snapshot.duckdb", output, client=FakeClient(mode))
    partial = json.loads(output.read_text(encoding="utf-8"))
    assert partial["run_status"] == "provider_or_validation_error"
    assert partial["pricing"]["cost_unknown"] is True
    assert partial["provider_calls"] <= 1


def test_preflight_blocks_combined_budget_before_calls(monkeypatch):
    request = runner.build_request(
        SimpleNamespace(question="q"), "network_flows(source_dataset VARCHAR)"
    )
    monkeypatch.setattr(runner, "BUDGET_USD", 0.000001)
    with pytest.raises(ValueError, match="exceeds"):
        runner.preflight_bounds([request] * 8)


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
