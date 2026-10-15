"""Statistics checked against known values and the preserved real dev artifact."""
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


def historical_results():
    from evaluation.tool_calling.models import ToolCallCase, CaseResult, PredictedCall
    from evaluation.tool_calling.matching import compute_case_metrics
    data = json.loads((ROOT / 'results/evaluation_v1/r1/r1_a1_dev_v2_852e543.json').read_text())
    results = []
    for row in data['case_results']:
        case = ToolCallCase.from_dict(json.loads((ROOT / 'evaluation/tool_calling/benchmarks/dev' / (row['case_id']+'.json')).read_text()))
        calls = [PredictedCall(tool=c['tool'], arguments=c['arguments']) for c in row['predicted_calls']]
        result = CaseResult(case_id=case.case_id, expected_calls=case.expected_calls, predicted_calls=calls)
        result.matches = compute_case_metrics(case, calls)['matches']
        results.append(result)
    return results


def test_wilson_known_values():
    from evaluation.tool_calling.generalization_reporting import wilson_interval
    assert wilson_interval(22, 24) == pytest.approx((.7415, .9768), abs=.0001)
    assert wilson_interval(5, 5) == pytest.approx((.5655, 1), abs=.0001)
    with pytest.raises(ValueError):
        wilson_interval(1, 0)


def test_exact_mcnemar_pairs_and_rejects_missing():
    from evaluation.tool_calling.generalization_reporting import exact_mcnemar
    left = {str(i): i < 4 for i in range(5)}
    right = {k: not v for k, v in left.items()}
    assert exact_mcnemar(left, right)['p_value'] == .375
    with pytest.raises(ValueError, match='PAIRED'):
        exact_mcnemar(left, {'missing': True})


def test_real_historical_full_denominator_coverage():
    from evaluation.tool_calling.generalization_reporting import full_denominator_argument_coverage
    coverage = full_denominator_argument_coverage(historical_results())
    assert coverage['required']['matched'] == 37
    assert coverage['required']['total'] == 41
    assert coverage['critical']['matched'] == 29
    assert coverage['critical']['total'] == 31


def test_partial_report_keeps_120_denominator_and_separate_dev():
    from evaluation.tool_calling.generalization_reporting import build_generalization_report
    from evaluation.tool_calling.models import ToolCallCase
    cases = [ToolCallCase.from_dict(json.loads(p.read_text())) for p in sorted((ROOT/'evaluation/tool_calling/benchmarks/generalization_v1').glob('gen_*.json'))]
    report = build_generalization_report(cases, [], {'attempted': 0, 'received': 0, 'events': [], 'known_usd': 0, 'cost_unknown': False}, {}, failed_case_id='gen_001')
    assert report['run_status'] == 'partial_failure'
    assert report['expected_case_ids'] == [c.case_id for c in cases]
    assert len(report['missing_case_ids']) == 120
    assert report['case_results'] == []
    assert report['success']['total'] == 120
    assert report['success']['rate'] is None
    assert report['success']['wilson_95'] is None
    assert report['metric_status'] == 'NOT_MEASURED'
    assert [(r['split'], r['total']) for r in report['comparison']] == [('dev', 24), ('generalization_v1', 120)]
    assert report['comparison'][0]['successes'] == 22
    assert report['official_eligible'] is False
    coverage = report['full_denominator_argument_coverage']
    assert coverage['required']['total'] == sum(len(call.required_arguments) for c in cases for call in c.expected_calls)
    assert coverage['required']['matched'] == 0
