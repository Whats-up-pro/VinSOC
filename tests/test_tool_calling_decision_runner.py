"""A1 decision-only runner regression tests."""

import json

import evaluation.tool_calling.decision_runner as decision_module
from agent.provider import LLMResponse, ProviderError, ProviderFailureKind
from agent.tools import get_tool_schemas
from evaluation.tool_calling.decision_runner import A1Config, DecisionRunner
from evaluation.tool_calling.metrics import aggregate_case_results
from evaluation.tool_calling.models import (
    CaseCategory,
    CaseDifficulty,
    ExpectedCall,
    ToolCallCase,
)


class FakeProvider:
    def __init__(self, response=None, error=None):
        self.response = response
        self.error = error
        self.last_call = None

    def generate(self, messages, tools=None, system_prompt=None, temperature=0.0):
        self.last_call = {
            "messages": messages,
            "tools": tools,
            "system_prompt": system_prompt,
            "temperature": temperature,
        }
        if self.error:
            raise self.error
        return self.response

    def get_name(self):
        return "fake-provider"

    def reset_tracking(self):
        pass

    def get_run_metadata(self):
        return {"total_calls": 1, "estimated_cost_usd": 0.0}


def _case():
    return ToolCallCase(
        case_id="a1_test_001",
        category=CaseCategory.CTI_ONLY,
        difficulty=CaseDifficulty.BASIC,
        request="Investigate IPv4 1.2.3.4 using only evidence needed for this request.",
        reference_time="2026-09-23T00:00:00Z",
        expected_calls=[
            ExpectedCall(
                call_id="cti_1",
                tool="cti_enrichment",
                required_arguments={"indicator": "1.2.3.4"},
                critical_arguments=["indicator"],
            )
        ],
    )


def test_a1_uses_native_tool_calls_and_production_schemas():
    response = LLMResponse(
        content="Do not infer calls from this prose: network_investigation.",
        tool_calls=[
            {
                "id": "call_1",
                "name": "cti_enrichment",
                "arguments": {"indicator": "1.2.3.4"},
            }
        ],
        raw={},
        metadata={
            "latency_ms": 12.5,
            "input_tokens": 17,
            "output_tokens": 9,
            "actual_provider": "fake",
            "actual_model": "fake-model",
        },
    )
    provider = FakeProvider(response=response)
    runner = DecisionRunner(
        config=A1Config(provider="fake", model="fake-model", temperature=0.0),
        provider=provider,
    )

    result = runner.run_decision(_case())

    assert [call.tool for call in result.predicted_calls] == ["cti_enrichment"]
    assert result.predicted_calls[0].arguments == {"indicator": "1.2.3.4"}
    assert provider.last_call["tools"] == get_tool_schemas()
    assert provider.last_call["messages"] == [
        {
            "role": "user",
            "content": "Investigate IPv4 1.2.3.4 using only evidence needed for this request.",
        }
    ]
    assert result.latency_ms == 12.5
    assert result.input_tokens == 17
    assert result.output_tokens == 9
    assert result.trajectory_success is True
    assert result.exact_call_match is True
    assert result.tool_set_match is True
    assert "NOT_IMPLEMENTED" not in result.errors


def test_a1_provider_error_is_explicit_and_does_not_fallback():
    provider = FakeProvider(
        error=ProviderError(
            "rate limited",
            kind=ProviderFailureKind.RATE_LIMIT,
            provider="fake",
            model="fake-model",
        )
    )
    runner = DecisionRunner(
        config=A1Config(provider="fake", model="fake-model"),
        provider=provider,
    )

    result = runner.run_decision(_case())

    assert result.predicted_calls == []
    assert result.errors == ["PROVIDER_ERROR"]
    assert "rate limited" in result.error_message


def test_a1_provider_error_on_no_tool_case_cannot_score_as_correct():
    case = ToolCallCase(
        case_id="a1_no_tool_provider_error",
        category=CaseCategory.NO_TOOL,
        difficulty=CaseDifficulty.BASIC,
        request="Explain what the tool schemas mean without calling a tool.",
        reference_time="2026-09-23T00:00:00Z",
        expected_calls=[],
    )
    provider = FakeProvider(
        error=ProviderError(
            "rate limited",
            kind=ProviderFailureKind.RATE_LIMIT,
            provider="fake",
            model="fake-model",
        )
    )
    runner = DecisionRunner(
        config=A1Config(provider="fake", model="fake-model"),
        provider=provider,
    )

    result = runner.run_decision(case)
    aggregate = aggregate_case_results("provider-error", [result])

    assert result.tool_set_match is False
    assert result.exact_call_match is False
    assert result.trajectory_success is False
    assert aggregate.tool_set_exact_match_rate == 0.0
    assert aggregate.no_tool_accuracy == 0.0
    assert aggregate.trajectory_success_rate == 0.0
    assert aggregate.provider_error_rate == 1.0
    assert aggregate.to_dict()["provider_error_rate"] == 1.0


def test_a1_forbidden_tool_updates_case_error_and_aggregate_rate():
    case = _case()
    case.forbidden_tools = ["endpoint_investigation"]
    violation_response = LLMResponse(
        content="",
        tool_calls=[
            {
                "id": "call_1",
                "name": "cti_enrichment",
                "arguments": {"indicator": "1.2.3.4"},
            },
            {
                "id": "call_2",
                "name": "endpoint_investigation",
                "arguments": {"host": "WS001"},
            },
        ],
        raw={},
        metadata={},
    )
    clean_response = LLMResponse(
        content="",
        tool_calls=[
            {
                "id": "call_3",
                "name": "cti_enrichment",
                "arguments": {"indicator": "1.2.3.4"},
            }
        ],
        raw={},
        metadata={},
    )
    violation = DecisionRunner(provider=FakeProvider(response=violation_response)).run_decision(case)
    clean = DecisionRunner(provider=FakeProvider(response=clean_response)).run_decision(case)
    aggregate = aggregate_case_results("forbidden-rate", [violation, clean])

    assert violation.forbidden_tool_violations == ["endpoint_investigation"]
    assert violation.errors == ["FORBIDDEN_TOOL"]
    assert violation.trajectory_success is False
    assert clean.forbidden_tool_violations == []
    assert clean.errors == []
    assert aggregate.forbidden_tool_rate == 0.5
    assert aggregate.to_dict()["forbidden_tool_rate"] == 0.5


def test_two_forbidden_calls_in_one_case_count_as_one_violating_case():
    case = _case()
    case.forbidden_tools = ["endpoint_investigation", "network_investigation"]
    response = LLMResponse(
        content="",
        tool_calls=[
            {"id": "call_1", "name": "endpoint_investigation", "arguments": {"host": "WS001"}},
            {"id": "call_2", "name": "network_investigation", "arguments": {"src_ip": "1.2.3.4"}},
        ],
        raw={},
        metadata={},
    )
    result = DecisionRunner(provider=FakeProvider(response=response)).run_decision(case)
    aggregate = aggregate_case_results("two-calls-one-case", [result])

    assert result.forbidden_tool_violations == [
        "endpoint_investigation", "network_investigation"
    ]
    assert result.errors.count("FORBIDDEN_TOOL") == 1
    assert aggregate.case_count == 1
    assert aggregate.forbidden_tool_rate == 1.0


def test_clean_case_set_has_zero_forbidden_tool_rate():
    response = LLMResponse(content="", tool_calls=[], raw={}, metadata={})
    cases = [_case(), _case()]
    for case in cases:
        case.forbidden_tools = ["endpoint_investigation"]
    cases[1].case_id = "a1_test_002"
    results = [
        DecisionRunner(provider=FakeProvider(response=response)).run_decision(case)
        for case in cases
    ]

    assert all(result.forbidden_tool_violations == [] for result in results)
    assert aggregate_case_results("clean", results).forbidden_tool_rate == 0.0


def test_forbidden_tool_name_is_present_in_case_and_json_report(monkeypatch, tmp_path):
    case = _case()
    case.forbidden_tools = ["endpoint_investigation"]
    response = LLMResponse(
        content="",
        tool_calls=[
            {"id": "call_1", "name": "endpoint_investigation", "arguments": {"host": "WS001"}}
        ],
        raw={},
        metadata={},
    )
    monkeypatch.setattr(
        decision_module, "create_provider", lambda **kwargs: FakeProvider(response=response)
    )
    monkeypatch.setattr(DecisionRunner, "load_cases", lambda self, split: [case])
    path = tmp_path / "report.json"

    result = DecisionRunner(provider=FakeProvider(response=response)).run_decision(case)
    assert result.to_dict()["forbidden_tool_violations"] == ["endpoint_investigation"]
    returned = decision_module.run_a1_benchmark(split="dev", output_path=path)
    written = json.loads(path.read_text(encoding="utf-8"))
    for report in (returned, written):
        assert report["case_results"][0]["forbidden_tool_violations"] == [
            "endpoint_investigation"
        ]
        assert report["aggregate"]["forbidden_tool_rate"] == 1.0
    assert written == returned
