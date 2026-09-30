"""Offline receipts are exclusive, complete about uncertainty and never eligible."""
import json
import sys

import pytest

from evaluation.dualsql_lite_ctu_gpt5_v2 import experiment
from tests.r2_remediation_fixtures import FakeClient, case, make_tools, response


def inputs(tmp_path, monkeypatch):
    tools, manifest = make_tools(tmp_path)
    monkeypatch.setattr(experiment, "verify_dev_inputs", lambda *a: {"logical_snapshot_sha256": "fixture-logical", "source_file_sha256": {"alpha": "fixture-source"}})
    return tools, manifest


def test_identity_and_all_response_telemetry(tmp_path, monkeypatch):
    tools, manifest = inputs(tmp_path, monkeypatch)
    client = FakeClient([response("SELECT count(*) FROM network_flows")])
    report = experiment.run_condition("E0", [case()], tools.snapshot_path, client, tmp_path / "output", manifest)
    identity = report["identity"]
    for key in ("git_sha", "dirty_state", "case_hashes", "snapshot_sha256", "logical_snapshot_sha256", "sources", "scorer_builder_sha256", "prompt_sha256", "tool_schema_sha256", "tool_implementation_sha256", "catalog_sha256", "request_contract"):
        assert identity[key] is not None
    assert report["official_eligible"] is False
    assert "synthetic_provider" in report["eligibility_reasons"]
    assert report["status"] == "complete" and report["cost_complete"]
    assert report["response_count"] == 1
    tel = report["case_results"][0]["usage"][0]
    assert tel["response_id"] and tel["model"] == client.requests[0]["model"]
    assert report["observed_cost_usd"] == tel["cost_usd"]
    assert report["input_tokens"] == 10 and report["output_tokens"] == 20
    assert "temperature" not in client.requests[0]
    assert "tools" not in client.requests[0]
    assert (tmp_path / "output" / "partial.jsonl").exists()


@pytest.mark.parametrize("reply,error", [(response("SELECT 1", model="other"), "MODEL_IDENTITY_MISMATCH"), (response("SELECT 1", tokens=False), "USAGE_INCOMPLETE"), (RuntimeError("credential-sentinel"), "PROVIDER_ERROR")])
def test_invalid_run_keeps_partial_evidence(tmp_path, monkeypatch, reply, error):
    tools, manifest = inputs(tmp_path, monkeypatch)
    client = FakeClient([reply, response("SELECT 1")])
    second = case(); second = type(second)("second", second.question, second.database_snapshot, second.gold_sql, second.category, second.difficulty, second.result_comparator)
    report = experiment.run_condition("E0", [case(), second], tools.snapshot_path, client, tmp_path / "output", manifest)
    assert len(client.requests) == 1
    assert report["status"] == "partial" and not report["cost_complete"]
    assert report["cost_unknown"] and error in report["eligibility_reasons"]
    evidence = (tmp_path / "output" / "partial.jsonl").read_text()
    assert "credential-sentinel" not in evidence
    if not isinstance(reply, Exception):
        assert "response-fixture" in evidence


def test_output_and_case_contract_fail_before_request(tmp_path):
    tools, manifest = make_tools(tmp_path)
    client = FakeClient([])
    output = tmp_path / "output"; output.mkdir(); (output / "partial.jsonl").write_text("original")
    with pytest.raises(FileExistsError):
        experiment.run_condition("E0", [case()], tools.snapshot_path, client, output, manifest)
    with pytest.raises(ValueError, match="DEV_CASE_IDENTITY_MISMATCH"):
        experiment.run_condition("E0", [case(), case()], tools.snapshot_path, client, tmp_path / "another", manifest)
    assert client.requests == []
    assert (output / "partial.jsonl").read_text() == "original"


def test_generic_cases_directory_rejected_before_read(tmp_path):
    with pytest.raises(ValueError, match="DEV_CASE_DIRECTORY_MISMATCH"):
        experiment.load_cases(tmp_path)


def test_cli_closed_before_client_or_database(monkeypatch, tmp_path):
    def forbidden(*a, **k):
        pytest.fail("CLI created client or DB")
    monkeypatch.setattr("openai.OpenAI", forbidden)
    monkeypatch.setattr("duckdb.connect", forbidden)
    monkeypatch.setattr(sys, "argv", ["v2", "--condition", "E0", "--snapshot", "absent", "--cases-dir", str(tmp_path), "--output-dir", str(tmp_path / "new")])
    with pytest.raises(RuntimeError, match="PAID_EXECUTION_DISABLED"):
        experiment.main()


def test_usage_inconsistent_total_is_not_complete(tmp_path, monkeypatch):
    tools, manifest = inputs(tmp_path, monkeypatch)
    reply = response("SELECT 1"); reply.usage.total_tokens = 999
    report = experiment.run_condition("E0", [case()], tools.snapshot_path, FakeClient([reply]), tmp_path / "output", manifest)
    assert not report["cost_complete"] and report["cost_unknown"]


def test_non_numeric_usage_keeps_partial_without_aggregation_crash(tmp_path, monkeypatch):
    tools, manifest = inputs(tmp_path, monkeypatch)
    reply = response("SELECT 1"); reply.usage.prompt_tokens = "invalid"
    report = experiment.run_condition("E0", [case()], tools.snapshot_path, FakeClient([reply]), tmp_path / "output", manifest)
    assert report["status"] == "partial" and report["cost_unknown"]
    assert report["case_results"][0]["usage"][0]["input_tokens"] == "invalid"


def test_missing_dev_case_rejected_before_provider(tmp_path):
    from evaluation.ctu_network_public.contract import CASES
    tools, manifest = make_tools(tmp_path)
    cases = experiment.load_cases(CASES)[:-1]
    client = FakeClient([])
    with pytest.raises(ValueError, match="DEV_CASE_IDENTITY_MISMATCH"):
        experiment.run_condition("E0", cases, tools.snapshot_path, client, tmp_path / "output", manifest)
    assert not client.requests
