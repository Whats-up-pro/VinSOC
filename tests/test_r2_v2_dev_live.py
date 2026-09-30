"""Offline real-SDK transport fixtures exercise live gates and actual pipeline."""
import json
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path

import httpx
import pytest
from openai import OpenAI

from tests.r2_remediation_fixtures import case, make_tools


@pytest.fixture
def live(tmp_path, monkeypatch):
    from scripts import run_r2_v2_dev_live as module
    tools, _ = make_tools(tmp_path)
    cases = [replace(case("Count Group 5 flows", gold="SELECT 3 AS GOLD_SENTINEL"), case_id=f"ctu_sql_{i:03d}") for i in range(1, 9)]
    identity = {"git_sha": "f" * 40, "dirty_state": False, "snapshot_sha256": "snapshot", "logical_snapshot_sha256": "logical", "case_file_sha256": {str(i): str(i) for i in range(8)}, "sources": {"alpha": "source"}, "scorer_builder_sha256": {"scorer": "hash"}, "prompt_sha256": {"prompt": "hash"}, "tool_schema_sha256": "schema", "catalog_sha256": tools.catalog_sha256, "request_contract": {"model": module.MODEL}}
    monkeypatch.setattr(module, "verified_environment", lambda p: (cases, tools, dict(identity)))
    monkeypatch.setattr(module, "git_state", lambda: {"sha": "f" * 40, "origin": "f" * 40, "branch": "master", "dirty": False})
    monkeypatch.setattr(module, "ATTEMPTS_ROOT", tmp_path / "claims")
    gates = {"implementation_sha": "f" * 40, "ci": {"headSha": "f" * 40, "conclusion": "success", "jobs": [{"name": "test (3.11)", "conclusion": "success"}, {"name": "test (3.12)", "conclusion": "success"}]}, "account": {"source": "owner_confirmation", "confirmed_utc": datetime.now(timezone.utc).isoformat(), "credit_at_least_usd": .75, "hard_limit_at_least_usd": .75, "project_verified": True}, "pricing": {"url": module.PRICING_URL, "checked_utc": datetime.now(timezone.utc).isoformat(), "source_sha256": "a" * 64, "input": .25, "cached_input": .025, "output": 2.0}, "new_live_budget_usd": .75, "total_authorized_usd": 2.0, "historical_cost_complete": False, "historical_recorded_lower_bound_usd": .0650815}
    monkeypatch.setattr(module, "load_gates", lambda: gates)
    monkeypatch.setattr(module, "key_configuration", lambda: ("fixture-key", {"source": "synthetic", "organization": None, "project": None}))
    return module, gates, tmp_path, identity


def sdk_factory(replies, requests):
    def handler(request):
        requests.append(json.loads(request.content))
        reply = replies.pop(0)
        if isinstance(reply, int):
            return httpx.Response(reply, json={"error": {"message": "credential-sentinel", "type": "test_error"}})
        return httpx.Response(200, json=reply)
    return lambda: OpenAI(api_key="fixture-key", base_url="https://api.openai.com/v1", max_retries=0, http_client=httpx.Client(transport=httpx.MockTransport(handler)))


def reply(content=None, calls=None, model="gpt-5-mini-2025-08-07", usage=True):
    return {"id": "chatcmpl-fixture", "object": "chat.completion", "created": 1, "model": model, "service_tier": "default", "choices": [{"index": 0, "finish_reason": "tool_calls" if calls else "stop", "message": {"role": "assistant", "content": content, "tool_calls": calls}}], "usage": {"prompt_tokens": 100, "completion_tokens": 20, "total_tokens": 120, "prompt_tokens_details": {"cached_tokens": 40}} if usage else None}


def pipeline_replies(sql="SELECT 9"):
    return [reply(calls=[{"id": "call-1", "type": "function", "function": {"name": "value_search", "arguments": '{"query":"Group 5"}'}}]), reply(json.dumps({"tables": [{"table": "network_flows", "columns": ["source_dataset"]}], "grounded_values": [{"table": "network_flows", "column": "source_dataset", "value": "alpha"}]})), reply(sql)]


def test_actual_smoke_and_suite_same_identity_with_mismatch_allowed(live):
    module, _, root, _ = live
    requests = []
    factory = sdk_factory(pipeline_replies() + pipeline_replies() * 8, requests)
    smoke = module.run_live_dev("smoke", Path("fixture"), root / "smoke", factory)
    assert smoke["smoke_gate_passed"] and smoke["counts"]["execution_accurate"] == 0
    suite = module.run_live_dev("suite", Path("fixture"), root / "suite", factory, root / "smoke" / "report.json")
    assert suite["completed_case_count"] == 8 and suite["status"] == "complete"
    assert suite["attempted_calls"] == suite["response_count"] == 24
    assert suite["db_calls"] == 8
    assert not suite["official_eligible"]  # custom HTTP fixture is never real evidence
    assert suite["identity_sha256"] == smoke["identity_sha256"]
    assert suite["cost_complete"] and suite["observed_cost_usd"] == pytest.approx(24 * (.000015 + .000001 + .00004))
    assert len(requests) == 27
    for request in requests:
        assert request["model"] == module.MODEL and request["reasoning_effort"] == "low"
        assert request["max_completion_tokens"] == 1000 and "temperature" not in request
        assert "GOLD_SENTINEL" not in json.dumps(request)
    assert (root / "suite" / "partial.jsonl").exists()


@pytest.mark.parametrize("gate", ["ci", "credit", "pricing", "dirty", "snapshot", "key", "output", "budget"])
def test_preflight_blocks_before_client_factory(live, monkeypatch, gate):
    module, gates, root, _ = live
    if gate == "ci": gates["ci"]["headSha"] = "other"
    elif gate == "credit": gates["account"]["credit_at_least_usd"] = .01
    elif gate == "pricing": gates["pricing"]["input"] = 99
    elif gate == "dirty": monkeypatch.setattr(module, "git_state", lambda: {"sha": "f" * 40, "origin": "f" * 40, "branch": "master", "dirty": True})
    elif gate == "snapshot": monkeypatch.setattr(module, "verified_environment", lambda p: (_ for _ in ()).throw(ValueError("private-path")))
    elif gate == "key": monkeypatch.setattr(module, "key_configuration", lambda: (_ for _ in ()).throw(module.GateError("KEY_SOURCE_CONFLICT")))
    elif gate == "output": (root / "output").mkdir()
    elif gate == "budget": gates["new_live_budget_usd"] = 99
    def forbidden():
        pytest.fail("client factory called before gate")
    with pytest.raises((module.GateError, FileExistsError)):
        module.run_live_dev("smoke", Path("fixture"), root / "output", forbidden)


@pytest.mark.parametrize("first,error", [(429, "RATE_LIMIT"), (404, "MODEL_UNAVAILABLE"), (400, "API_CONTRACT_ERROR"), (reply("broken"), "LINKER_FORMAT_ERROR"), (reply("SELECT 1", model="other"), "MODEL_IDENTITY_MISMATCH"), (reply("SELECT 1", usage=False), "USAGE_INCOMPLETE")])
def test_failed_smoke_consumed_no_retry_no_suite(live, first, error):
    module, _, root, _ = live
    requests = []; factory = sdk_factory([first], requests)
    smoke = module.run_live_dev("smoke", Path("fixture"), root / "smoke", factory)
    assert not smoke["smoke_gate_passed"] and smoke["case_results"][0]["error_category"] == error
    assert len(requests) == 1
    partial = (root / "smoke" / "partial.jsonl").read_text()
    assert "credential-sentinel" not in partial
    with pytest.raises(module.GateError):
        module.run_live_dev("smoke", Path("fixture"), root / "another", factory)
    with pytest.raises(module.GateError):
        module.run_live_dev("suite", Path("fixture"), root / "suite", factory, root / "smoke" / "report.json")
    assert len(requests) == 1


def test_smoke_identity_or_digest_tamper_stops_suite(live):
    module, _, root, identity = live
    requests = []; factory = sdk_factory(pipeline_replies(), requests)
    module.run_live_dev("smoke", Path("fixture"), root / "smoke", factory)
    report = root / "smoke" / "report.json"
    report.write_text(report.read_text() + " ")
    with pytest.raises(module.GateError, match="SMOKE"):
        module.run_live_dev("suite", Path("fixture"), root / "suite", factory, report)
    assert len(requests) == 3


def test_bound_reserves_ninety_calls_and_checks_context(live):
    module, _, root, _ = live
    bound = module.preflight_bound()
    assert bound["combined_max_calls"] == 90
    assert 0 < bound["smoke_ceiling_usd"] <= .10
    assert bound["combined_ceiling_usd"] <= .75
    requests = []; factory = sdk_factory([reply("broken")], requests)
    # A request exceeding the declared serialized-context bound is blocked pre-SDK.
    with pytest.raises(module.GateError, match="REQUEST_CONTEXT_LIMIT"):
        module.validate_request({"model": module.MODEL, "reasoning_effort": "low", "max_completion_tokens": 1000, "messages": [{"role": "user", "content": "x" * 30000}]})
    assert not requests


def test_paid_response_retained_if_controller_raises(live, monkeypatch):
    module, _, root, _ = live
    def crashing_controller(case, condition, tools, client, schema, **kwargs):
        client.chat.completions.create(model=module.MODEL, reasoning_effort="low", max_completion_tokens=1000, messages=[])
        raise ValueError("credential-sentinel")
    monkeypatch.setattr(module, "run_case", crashing_controller)
    report = module.run_live_dev("smoke", Path("fixture"), root / "smoke", sdk_factory([reply("broken")], []))
    assert report["status"] == "partial" and not report["smoke_gate_passed"]
    assert report["response_count"] == 1 and report["input_tokens"] == 100
    assert report["observed_cost_usd"] == pytest.approx(.000056)
    assert len(report["response_usage"]) == 1
    assert "credential-sentinel" not in (root / "smoke" / "report.json").read_text()


def test_malformed_native_arguments_preserve_charged_response(live):
    module, _, root, _ = live
    bad = reply(calls=[{"id": "bad", "type": "function", "function": {"name": "value_search", "arguments": "{"}}])
    report = module.run_live_dev("smoke", Path("fixture"), root / "smoke", sdk_factory([bad], []))
    assert not report["smoke_gate_passed"] and report["cost_complete"]
    assert report["case_results"][0]["error_category"] == "MALFORMED_TOOL_ARGUMENTS"
    assert report["attempted_calls"] == report["response_count"] == 1
    assert report["observed_cost_usd"] == pytest.approx(.000056)


def test_sdk_retry_or_endpoint_override_consumes_attempt_without_api(live):
    module, _, root, _ = live
    requests = []
    def factory():
        client = sdk_factory([reply("broken")], requests)()
        client.max_retries = 2
        return client
    report = module.run_live_dev("smoke", Path("fixture"), root / "smoke", factory)
    assert not report["smoke_gate_passed"] and not requests
    assert report["infrastructure_error"] == "PROVIDER_CONTRACT_ERROR"
    assert not report["cost_complete"]


def test_journal_sync_failure_does_not_lose_paid_cost(live, monkeypatch):
    module, _, root, _ = live
    original = module.os.fsync
    calls = 0
    def fail_once(fd):
        nonlocal calls
        calls += 1
        if calls == 4:
            raise OSError("credential-sentinel")
        original(fd)
    monkeypatch.setattr(module.os, "fsync", fail_once)
    report = module.run_live_dev("smoke", Path("fixture"), root / "smoke", sdk_factory([reply("broken")], []))
    assert report["attempted_calls"] == report["response_count"] == 1
    assert report["observed_cost_usd"] == pytest.approx(sum(u["cost_usd"] for u in report["response_usage"]))
    assert report["observed_cost_usd"] == pytest.approx(.000056)
    assert report["case_results"][0]["error_category"] == "TELEMETRY_WRITE_ERROR"
    assert not report["smoke_gate_passed"]


def test_tool_infrastructure_failure_stops_before_next_sdk_call(live, monkeypatch):
    module, _, root, _ = live
    requests = []
    factory = sdk_factory(pipeline_replies() + pipeline_replies() * 8, requests)
    module.run_live_dev("smoke", Path("fixture"), root / "smoke", factory)
    old_environment = module.verified_environment
    def broken_environment(path):
        cases, tools, identity = old_environment(path)
        def broken_invoke(*args):
            raise OSError("credential-sentinel")
        tools.invoke = broken_invoke
        return cases, tools, identity
    monkeypatch.setattr(module, "verified_environment", broken_environment)
    report = module.run_live_dev("suite", Path("fixture"), root / "suite", factory, root / "smoke" / "report.json")
    assert report["status"] == "partial" and report["completed_case_count"] == 1
    assert report["case_count"] == 8 and len(report["missing_case_ids"]) == 7
    assert report["case_results"][0]["error_category"] == "TOOL_INFRASTRUCTURE_ERROR"
    assert report["attempted_calls"] == 1 and len(requests) == 4


def test_synthetic_smoke_cannot_authorize_production_suite(live, monkeypatch):
    module, _, root, _ = live
    requests = []; factory = sdk_factory(pipeline_replies(), requests)
    module.run_live_dev("smoke", Path("fixture"), root / "smoke", factory)
    monkeypatch.setattr(module, "production_client", factory)
    with pytest.raises(module.GateError, match="SMOKE"):
        module.run_live_dev("suite", Path("fixture"), root / "suite", factory, root / "smoke" / "report.json")
    assert len(requests) == 3
