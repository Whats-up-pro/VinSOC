"""The paid pilot request is pinned, bounded and auditable without real API use."""

from types import SimpleNamespace

import pytest

from evaluation.public_pilot.run_model import (
    MODEL, CAP, build_r1_request, build_r2_request, preflight_bounds,
    send_request, checked_usage, make_client,
)
from evaluation.tool_calling.models import ToolCallCase


class CaptureClient:
    def __init__(self, response):
        self.response = response
        self.request = None
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self.create))

    def create(self, **kwargs):
        self.request = kwargs
        return self.response


def test_real_chat_completions_boundary_receives_cap_for_r1_and_r2():
    case = ToolCallCase.from_dict({"case_id": "x", "category": "network_only", "difficulty": "basic",
                                   "request": "Investigate IP 1.2.3.4", "reference_time": "2020-01-01T00:00:00Z",
                                   "expected_calls": []})
    client = CaptureClient(SimpleNamespace(model=MODEL))
    for request in (build_r1_request(case), build_r2_request("Count rows", "network_flows(src_ip VARCHAR)")):
        send_request(client, request)
        assert client.request["model"] == MODEL
        assert client.request["temperature"] == 0
        assert client.request["max_completion_tokens"] == CAP == 1000
        assert client.request["tools"] == request["tools"]


def test_wrong_model_or_missing_usage_stops_before_next_request():
    with pytest.raises(ValueError, match="actual model"):
        checked_usage(SimpleNamespace(model="different", usage=SimpleNamespace(prompt_tokens=20, completion_tokens=10)))
    with pytest.raises(ValueError, match="usage"):
        checked_usage(SimpleNamespace(model=MODEL, usage=None))


def test_preflight_bounds_all_requests_not_one_smoke_payload():
    case = ToolCallCase.from_dict({"case_id": "x", "category": "no_tool", "difficulty": "basic",
                                   "request": "Explain logs", "reference_time": "2020-01-01T00:00:00Z"})
    short = build_r1_request(case)
    long = build_r2_request("x" * 10000, "network_flows(src_ip VARCHAR)")
    estimates = preflight_bounds([short, long])
    assert len(estimates["bounds"]) == 2
    assert estimates["bounds"][1]["input_token_bound"] > estimates["bounds"][0]["input_token_bound"]
    assert estimates["cost_ceiling_usd"] == sum(b["max_cost_usd"] for b in estimates["bounds"])


def test_openai_client_has_zero_sdk_retries(monkeypatch):
    import openai

    captured = {}
    monkeypatch.setenv("OPENAI_API_KEY", "dummy-test-key")
    monkeypatch.setattr(openai, "OpenAI", lambda **kwargs: captured.update(kwargs) or object())
    make_client()
    assert captured["max_retries"] == 0
    assert captured["timeout"] == 60


def test_alternate_openai_base_url_is_rejected_before_request(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "dummy-test-key")
    monkeypatch.setenv("OPENAI_BASE_URL", "https://another-provider.example/v1")
    with pytest.raises(ValueError, match="OPENAI_BASE_URL"):
        make_client()
