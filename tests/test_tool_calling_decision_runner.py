"""A1 decision-only runner regression tests."""

import json
import subprocess
from types import SimpleNamespace
from pathlib import Path

import evaluation.tool_calling.decision_runner as decision_module
import evaluation.tool_calling.__main__ as cli_module
import evaluation.tool_calling.provenance as provenance_module
from agent.provider import LLMResponse, ProviderError, ProviderFailureKind
from agent.tools import get_tool_schemas
from evaluation.tool_calling.decision_runner import A1Config, DecisionRunner
from evaluation.tool_calling.metrics import aggregate_case_results
from evaluation.tool_calling.models import (
    CaseCategory,
    CaseDifficulty,
    ExpectedCall,
    CaseResult,
    ToolCallCase,
)
from evaluation.tool_calling.provenance import canonical_sha256


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


def test_a1_helper_and_cli_share_captured_input_provenance(monkeypatch, tmp_path):
    from types import SimpleNamespace

    benchmark_dir = tmp_path / "benchmarks"
    split_dir = benchmark_dir / "dev"
    split_dir.mkdir(parents=True)
    case = _case()
    (split_dir / "case_001.json").write_text(json.dumps(case.to_dict()), encoding="utf-8")
    response = LLMResponse(content="", tool_calls=[], raw={}, metadata={})
    original_runner = DecisionRunner

    def fake_runner(config=None):
        return original_runner(
            config=config, benchmarks_dir=benchmark_dir,
            provider=FakeProvider(response=response),
        )

    monkeypatch.setattr(decision_module, "DecisionRunner", fake_runner)
    monkeypatch.setattr(cli_module, "DecisionRunner", fake_runner)
    monkeypatch.chdir(tmp_path)
    output = tmp_path / "helper.json"
    helper = decision_module.run_a1_benchmark(
        split="dev", output_path=output,
        config=A1Config(provider="fake", model="fake-model", temperature=0.0),
    )
    cli_module.run_benchmark(SimpleNamespace(
        mode="decision", split="dev", cases=None,
        provider="fake", model="fake-model", temperature=0.0,
    ))
    cli_output = next((tmp_path / "results" / "tool_calling").glob("*/metrics.json"))
    cli_report = json.loads(cli_output.read_text(encoding="utf-8"))
    helper_report = json.loads(output.read_text(encoding="utf-8"))

    assert helper_report == helper
    assert cli_report["provenance"] == helper["provenance"]
    provenance = helper["provenance"]
    assert provenance["git"]["commit_sha"]
    assert isinstance(provenance["git"]["working_tree_clean"], bool)
    assert provenance["benchmark_split_sha256"]
    assert provenance["production_schema_sha256"]
    assert provenance["prompt_sha256"] == canonical_sha256(provenance["prompts"])
    assert provenance["prompts"][0]["messages"] == [
        {"role": "user", "content": case.request}
    ]
    assert provenance["prompts"][0]["system_prompt"]
    assert provenance["official_eligible"] is False  # FakeProvider has no actual model telemetry.
    assert helper["config"] == cli_report["config"]
    assert helper["provider_metadata"] == cli_report["provider_metadata"]


def test_a1_provenance_hashes_captured_prompt_schema_and_logical_split(monkeypatch, tmp_path):
    benchmark_dir = tmp_path / "benchmarks"
    split_dir = benchmark_dir / "dev"
    split_dir.mkdir(parents=True)
    case = _case()
    path = split_dir / "case_001.json"
    path.write_text(json.dumps(case.to_dict()), encoding="utf-8")
    schemas = [{"function": {"name": "cti_enrichment", "parameters": {"type": "object"}}}]
    monkeypatch.setattr(decision_module, "get_tool_schemas", lambda: schemas)
    response = LLMResponse(content="", tool_calls=[], raw={}, metadata={})

    def run(prompt=None):
        runner = DecisionRunner(
            config=A1Config(provider="fake", model="fake-model", system_prompt=prompt),
            benchmarks_dir=benchmark_dir, provider=FakeProvider(response=response),
        )
        cases = runner.load_cases("dev")
        runner._run_cases = cases
        results = [runner.run_decision(item) for item in cases]
        from evaluation.tool_calling.provenance import build_a1_provenance
        return build_a1_provenance(runner, "dev", results)

    original = run()
    changed_prompt = run("A different system prompt")
    assert original["prompt_sha256"] != changed_prompt["prompt_sha256"]
    assert original["production_schema_sha256"] == changed_prompt["production_schema_sha256"]

    schemas[0]["function"]["parameters"]["additionalProperties"] = False
    changed_schema = run()
    assert original["production_schema_sha256"] != changed_schema["production_schema_sha256"]
    assert original["prompt_sha256"] == changed_schema["prompt_sha256"]
    schemas[0]["function"]["parameters"] = dict(
        reversed(list(schemas[0]["function"]["parameters"].items()))
    )
    assert changed_schema["production_schema_sha256"] == run()["production_schema_sha256"]

    reordered = dict(reversed(list(case.to_dict().items())))
    path.write_text(json.dumps(reordered, indent=4), encoding="utf-8")
    assert changed_schema["benchmark_split_sha256"] == run()["benchmark_split_sha256"]
    reordered["request"] = "Different investigation request"
    path.write_text(json.dumps(reordered), encoding="utf-8")
    assert changed_schema["benchmark_split_sha256"] != run()["benchmark_split_sha256"]

    second = _case()
    second.case_id = "a1_test_002"
    (split_dir / "case_002.json").write_text(json.dumps(second.to_dict()), encoding="utf-8")
    both_cases = run()
    original_glob = Path.glob
    monkeypatch.setattr(
        Path, "glob", lambda self, pattern: reversed(list(original_glob(self, pattern)))
    )
    reversed_read_order = run()
    assert both_cases["benchmark_split_sha256"] == reversed_read_order["benchmark_split_sha256"]
    assert both_cases["prompt_sha256"] == reversed_read_order["prompt_sha256"]


def test_official_eligibility_checks_requested_provider_and_actual_telemetry(monkeypatch, tmp_path):
    case = _case()
    split = tmp_path / "dev"
    split.mkdir()
    (split / "case.json").write_text(json.dumps(case.to_dict()), encoding="utf-8")
    call = {
        "actual_provider": "openai", "actual_model": "pinned-model",
        "fallback_triggered": False,
    }
    runner = SimpleNamespace(
        benchmarks_dir=tmp_path,
        _run_cases=[case],
        _input_records=[{
            "prompt": {"case_id": case.case_id, "system_prompt": "prompt",
                       "messages": [{"role": "user", "content": case.request}]},
            "tool_schemas": [{"name": "cti_enrichment"}],
        }],
        provider=SimpleNamespace(get_run_metadata=lambda: {"calls": [call]}),
        config=SimpleNamespace(provider="openai", model="pinned-model"),
    )
    results = [CaseResult(case_id=case.case_id,
                          expected_calls=case.expected_calls, predicted_calls=[])]
    monkeypatch.setattr(provenance_module, "_git_identity", lambda: {
        "commit_sha": "a" * 40, "branch": "master", "working_tree_clean": True,
    })

    def provenance():
        return provenance_module.build_a1_provenance(runner, "dev", results)

    assert provenance()["official_eligible"] is True
    call["actual_provider"] = "openrouter"
    assert "actual_provider_mismatch" in provenance()["ineligible_reasons"]
    call["actual_provider"] = "openai"
    runner.config.provider = "routed"
    assert "routed_provider_not_official" in provenance()["ineligible_reasons"]
    runner.config.provider = "openai"
    call["fallback_triggered"] = True
    assert "fallback_triggered" in provenance()["ineligible_reasons"]
    call["fallback_triggered"] = False
    call.pop("actual_provider")
    assert "actual_provider_missing" in provenance()["ineligible_reasons"]


def test_repeated_cli_reports_do_not_dirty_git_but_tracked_inputs_do(monkeypatch, tmp_path):
    root = tmp_path
    (root / ".gitignore").write_text(
        (Path(__file__).resolve().parents[1] / ".gitignore").read_text(encoding="utf-8"),
        encoding="utf-8",
    )
    (root / "evaluation" / "tool_calling").mkdir(parents=True)
    (root / "code.py").write_text("value = 1\n", encoding="utf-8")
    case = _case()
    benchmark_dir = root / "benchmarks"
    split_dir = benchmark_dir / "dev"
    split_dir.mkdir(parents=True)
    case_file = split_dir / "case.json"
    case_file.write_text(json.dumps(case.to_dict()), encoding="utf-8")

    def git(*args):
        return subprocess.run(["git", *args], cwd=root, check=True,
                              capture_output=True, text=True).stdout.strip()

    git("init", "-q", "-b", "master")
    git("add", ".")
    git("-c", "user.name=Test", "-c", "user.email=test@example.com",
        "commit", "-qm", "initial")
    monkeypatch.setattr(
        provenance_module, "__file__",
        str(root / "evaluation" / "tool_calling" / "provenance.py"),
    )

    class TelemetryProvider(FakeProvider):
        def __init__(self):
            super().__init__(response=LLMResponse(content="", tool_calls=[], raw={}, metadata={}))
            self.calls = []

        def generate(self, *args, **kwargs):
            self.calls.append({
                "actual_provider": "openai", "actual_model": "pinned-model",
                "fallback_triggered": False,
            })
            return super().generate(*args, **kwargs)

        def get_name(self):
            return "openai pinned-model"

        def get_run_metadata(self):
            return {"calls": self.calls, "total_calls": len(self.calls)}

    original_runner = DecisionRunner
    monkeypatch.setattr(cli_module, "DecisionRunner", lambda config: original_runner(
        config=config, benchmarks_dir=benchmark_dir, provider=TelemetryProvider(),
    ))
    monkeypatch.chdir(root)
    args = SimpleNamespace(mode="decision", split="dev", cases=None,
                           provider="openai", model="pinned-model", temperature=0.0)
    for index in (1, 2):
        cli_module.run_benchmark(args)
        output_dir = next((root / "results" / "tool_calling").iterdir())
        report = json.loads((output_dir / "metrics.json").read_text(encoding="utf-8"))
        assert report["provenance"]["official_eligible"] is True
        assert git("status", "--porcelain") == ""
        output_dir.rename(output_dir.with_name(f"run_{index}"))

    (root / "code.py").write_text("value = 2\n", encoding="utf-8")
    cli_module.run_benchmark(args)
    output_dir = next(path for path in (root / "results" / "tool_calling").iterdir()
                      if path.name not in ("run_1", "run_2"))
    report = json.loads((output_dir / "metrics.json").read_text(encoding="utf-8"))
    assert "evaluator_git_identity_unavailable_or_dirty" in report["provenance"]["ineligible_reasons"]

    (root / "code.py").write_text("value = 1\n", encoding="utf-8")
    output_dir.rename(output_dir.with_name("run_3"))
    case_file.write_text(json.dumps({**case.to_dict(), "request": "changed"}), encoding="utf-8")
    cli_module.run_benchmark(args)
    output_dir = next(path for path in (root / "results" / "tool_calling").iterdir()
                      if path.name not in ("run_1", "run_2", "run_3"))
    report = json.loads((output_dir / "metrics.json").read_text(encoding="utf-8"))
    assert "evaluator_git_identity_unavailable_or_dirty" in report["provenance"]["ineligible_reasons"]
