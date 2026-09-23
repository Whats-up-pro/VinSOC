"""Benchmark-contract tests for R1 dev/frozen splits."""

from pathlib import Path

from evaluation.tool_calling.decision_runner import DecisionRunner


def _observable_required_values(case):
    values = []
    for call in case.expected_calls:
        for arg_name in call.critical_arguments:
            value = call.required_arguments.get(arg_name)
            if isinstance(value, str):
                values.append(value)
    return values


def test_dev_cases_expose_critical_argument_values_in_model_input():
    runner = DecisionRunner.__new__(DecisionRunner)
    runner.benchmarks_dir = Path("evaluation/tool_calling/benchmarks")
    cases = runner.load_cases("dev")
    assert cases
    for case in cases:
        prompt = case.request.casefold()
        for value in _observable_required_values(case):
            assert value.casefold() in prompt, (
                f"{case.case_id}: critical value {value!r} is hidden from model input"
            )


def test_frozen_split_is_nonempty_and_disjoint_from_dev():
    runner = DecisionRunner.__new__(DecisionRunner)
    runner.benchmarks_dir = Path("evaluation/tool_calling/benchmarks")
    dev_ids = {case.case_id for case in runner.load_cases("dev")}
    frozen_ids = {case.case_id for case in runner.load_cases("frozen")}

    assert dev_ids
    assert frozen_ids
    assert dev_ids.isdisjoint(frozen_ids)


def test_dev_has_meaningful_no_tool_coverage():
    runner = DecisionRunner.__new__(DecisionRunner)
    runner.benchmarks_dir = Path("evaluation/tool_calling/benchmarks")
    no_tool_cases = [
        case for case in runner.load_cases("dev") if case.category.value == "no_tool"
    ]
    production_tools = {
        "cti_enrichment",
        "network_investigation",
        "endpoint_investigation",
    }

    assert len(no_tool_cases) >= 4
    for case in no_tool_cases:
        assert case.expected_calls == []
        assert set(case.forbidden_tools) == production_tools
