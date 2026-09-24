"""Benchmark-contract tests for R1 dev/frozen splits."""

from pathlib import Path
import json
import ipaddress

from evaluation.tool_calling.decision_runner import DecisionRunner
from evaluation.tool_calling.provenance import canonical_sha256
from evaluation.tool_calling.matching import compute_case_metrics
from evaluation.tool_calling.models import PredictedCall


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


def test_dev_v2_gold_is_consistent_with_runtime_and_category():
    base = Path('evaluation/tool_calling/benchmarks/dev')
    cases = {p.stem: json.loads(p.read_text(encoding='utf-8')) for p in base.glob('*.json')}
    assert len(cases) == 24
    expected_categories = {
        frozenset(): 'no_tool',
        frozenset({'cti_enrichment'}): 'cti_only',
        frozenset({'network_investigation'}): 'network_only',
        frozenset({'endpoint_investigation'}): 'endpoint_only',
        frozenset({'cti_enrichment', 'network_investigation'}): 'cti_network',
        frozenset({'cti_enrichment', 'endpoint_investigation'}): 'cti_endpoint',
        frozenset({'network_investigation', 'endpoint_investigation'}): 'network_endpoint',
        frozenset({'cti_enrichment', 'network_investigation', 'endpoint_investigation'}): 'cti_network_endpoint',
    }
    for data in cases.values():
        tools = frozenset(call['tool'] for call in data['expected_calls'])
        if data['category'] not in {'hostname_led', 'hash_led'}:
            assert data['category'] == expected_categories[tools], data['case_id']
        for call in data['expected_calls']:
            indicator = call['required_arguments'].get('indicator')
            if call['tool'] == 'network_investigation':
                assert indicator is not None and ipaddress.ip_address(indicator).version == 4, data['case_id']
            if call['tool'] == 'cti_enrichment' and indicator:
                try:
                    is_rfc1918 = ipaddress.ip_address(indicator) in (
                        ipaddress.ip_network('10.0.0.0/8')
                    ) or ipaddress.ip_address(indicator) in ipaddress.ip_network('192.168.0.0/16')
                except ValueError:
                    is_rfc1918 = False
                if is_rfc1918:
                    assert 'check CTI' in data['request'], data['case_id']


def test_dev_v2_dns_flow_case_and_evidence_gap_case():
    runner = DecisionRunner.__new__(DecisionRunner)
    runner.benchmarks_dir = Path('evaluation/tool_calling/benchmarks')
    first = runner.load_case('case_001', 'dev')
    assert first.category.value == 'network_only'
    assert [c.tool for c in first.expected_calls] == ['network_investigation']
    assert 'connection' in first.request.lower() and 'dns query' not in first.request.lower()

    gap = runner.load_case('case_019', 'dev')
    assert gap.category.value == 'no_tool' and gap.expected_calls == []
    assert 'evidence gap' in gap.request.lower()
    assert 'do not call' in gap.request.lower()
    assert set(gap.forbidden_tools) == {
        'cti_enrichment', 'network_investigation', 'endpoint_investigation'
    }

    dlp = runner.load_case('case_003', 'dev')
    assert [c.tool for c in dlp.expected_calls] == ['endpoint_investigation']
    score = compute_case_metrics(dlp, [
        PredictedCall(tool='network_investigation', arguments={'indicator': '192.168.1.100'}),
        PredictedCall(tool='endpoint_investigation', arguments={'host': 'WS100'}),
    ])
    assert score['fp'] == 1 and score['trajectory_success'] is False


def test_dev_v2_manifest_locks_cases_and_scorer():
    manifest = json.loads(Path('evaluation/tool_calling/benchmarks/dev/VERSION.lock').read_text())
    base = Path('evaluation/tool_calling/benchmarks/dev')
    cases = {p.name: json.loads(p.read_text(encoding='utf-8')) for p in sorted(base.glob('case_*.json'))}
    assert manifest['version'] == 'r1_a1_dev_v2'
    assert manifest['case_count'] == len(cases) == 24
    assert manifest['benchmark_split_sha256'] == canonical_sha256(cases)
    from hashlib import sha256
    scorer_paths = manifest['scorer_files']
    assert scorer_paths == sorted(scorer_paths)
    scorer_contents = {p: sha256(Path(p).read_bytes()).hexdigest() for p in scorer_paths}
    assert scorer_contents == manifest['scorer_file_sha256']
    assert manifest['scorer_sha256'] == canonical_sha256(scorer_contents)
