"""Additional uncertainty/coverage analysis without changing the locked scorer."""
from __future__ import annotations

import json
import math
from collections import defaultdict
from pathlib import Path
from statistics import NormalDist

from evaluation.tool_calling.matching import check_required_args, check_critical_args, detect_duplicates
from evaluation.tool_calling.metrics import aggregate_case_results, generate_error_summary

ROOT = Path(__file__).resolve().parents[2]


def wilson_interval(successes, total, confidence=.95):
    if type(successes) is not int or type(total) is not int or not 0 <= successes <= total or total < 1:
        raise ValueError('INVALID_BINOMIAL_COUNTS')
    if not 0 < confidence < 1:
        raise ValueError('INVALID_CONFIDENCE')
    z = NormalDist().inv_cdf((1+confidence)/2)
    p = successes/total
    center = (p+z*z/(2*total))/(1+z*z/total)
    half = z*math.sqrt(p*(1-p)/total+z*z/(4*total*total))/(1+z*z/total)
    return max(0., center-half), min(1., center+half)


def exact_mcnemar(left, right):
    if not left or set(left) != set(right) or any(type(v) is not bool for v in [*left.values(), *right.values()]):
        raise ValueError('COMPLETE_PAIRED_BOOLEAN_RECORDS_REQUIRED')
    b = sum(left[k] and not right[k] for k in left)
    c = sum(right[k] and not left[k] for k in left)
    n = b+c
    return {'pairs': len(left), 'left_only': b, 'right_only': c,
            'p_value': min(1., 2*sum(math.comb(n, k) for k in range(min(b,c)+1))/2**n) if n else 1.,
            'method': 'two-sided exact binomial McNemar'}


def full_denominator_argument_coverage(results):
    totals = {'required': {'matched': 0, 'total': 0}, 'critical': {'matched': 0, 'total': 0}}
    for result in results:
        for expected in result.expected_calls:
            totals['required']['total'] += len(expected.required_arguments)
            totals['critical']['total'] += len(expected.critical_arguments)
        seen = set()
        for match in result.matches:
            expected, predicted = match.expected_call, match.predicted_call
            if expected is None or predicted is None or expected.call_id in seen or expected.tool != predicted.tool:
                continue
            seen.add(expected.call_id)
            totals['required']['matched'] += len(check_required_args(predicted.arguments, expected)[1])
            totals['critical']['matched'] += len(check_critical_args(predicted.arguments, expected)[1])
    for group in totals.values():
        group['rate'] = group['matched']/group['total'] if group['total'] else None
    return totals


def _success(successes, total, measured=True):
    return {'successes': successes, 'total': total, 'rate': successes/total if total and measured else None,
            'wilson_95': wilson_interval(successes, total) if total and measured else None}


def build_generalization_report(cases, results, journal, gate, *, failed_case_id=None):
    """Report missing rows explicitly and keep the full locked denominator."""
    ids = [case.case_id for case in cases]
    observed = {result.case_id: result for result in results}
    if len(ids) != 120 or len(set(ids)) != 120 or len(observed) != len(results) or set(observed)-set(ids):
        raise ValueError('EXACT_120_UNIQUE_INVENTORY_REQUIRED')
    missing = [cid for cid in ids if cid not in observed]
    failed = [r.case_id for r in results if {'PROVIDER_ERROR', 'EXECUTION_ERROR', 'INVALID_TOOL_CALL'} & set(r.errors)]
    complete = not missing and not failed and not journal.get('cost_unknown', True)
    telemetry_complete = (journal.get('attempted') == journal.get('received') == 120
                          and len(journal.get('events', [])) == 120)
    success = sum(r.trajectory_success for r in results)
    historical = json.loads((ROOT/'results/evaluation_v1/r1/r1_a1_dev_v2_852e543.json').read_text())
    dev_success = sum(row['trajectory_success'] for row in historical['case_results'])
    groups = defaultdict(list)
    for case in cases:
        meta = json.loads(case.notes) if case.notes.startswith('{') else {}
        labels = {'category': case.category.value, 'difficulty': case.difficulty.value,
                  'tool_count': str(len(case.expected_calls)),
                  **{key: meta[key] for key in ('scenario_family', 'template_family', 'source_kind') if key in meta}}
        for dimension, value in labels.items():
            groups[(dimension, value)].append(case.case_id)
        for tag in meta.get('coverage_tags', []):
            groups[('coverage_tag', tag)].append(case.case_id)
    breakdown = {}
    for (dimension, label), members in sorted(groups.items()):
        breakdown.setdefault(dimension, {})[label] = {
            **_success(sum(bool(observed[cid].trajectory_success) for cid in members if cid in observed), len(members),
                       any(cid in observed for cid in members)),
            'observed': sum(cid in observed for cid in members)}
    events = journal.get('events', [])
    latencies = sorted(e['latency_seconds'] for e in events if isinstance(e.get('latency_seconds'), (int,float)))
    no_tool = [case for case in cases if not case.expected_calls]
    aggregate = aggregate_case_results('r1-generalization-v1', results).to_dict() if results else None
    coverage = full_denominator_argument_coverage(results)
    for label, field in [('required', 'required_arguments'), ('critical', 'critical_arguments')]:
        coverage[label]['total'] = sum(len(getattr(call, field)) for case in cases for call in case.expected_calls)
        coverage[label]['rate'] = coverage[label]['matched']/coverage[label]['total'] if coverage[label]['total'] and results else None
    return {'format': 'r1_generalization_report_v1', 'mode': 'decision', 'split': 'generalization_v1',
            'run_status': 'completed' if complete and telemetry_complete else 'partial_failure',
            'metric_status': 'NOT_MEASURED' if not results else ('MEASURED' if complete and telemetry_complete else 'PARTIAL'),
            'official_eligible': bool(complete and telemetry_complete and gate.get('passed')),
            'expected_case_ids': ids, 'completed_case_ids': list(observed), 'missing_case_ids': missing,
            'failed_case_id': failed_case_id or (failed[0] if failed else None),
            'success': _success(success, 120, bool(results)),
            'comparison': [{'split': 'dev', **_success(dev_success, len(historical['case_results'])),
                            'historical_artifact': 'results/evaluation_v1/r1/r1_a1_dev_v2_852e543.json'},
                           {'split': 'generalization_v1', **_success(success, 120, bool(results))}],
            'aggregate_observed_only': aggregate, 'observed_count': len(results),
            'full_denominator_argument_coverage': coverage,
            'no_tool': _success(sum(bool(observed[c.case_id].trajectory_success) for c in no_tool if c.case_id in observed), len(no_tool),
                                any(c.case_id in observed for c in no_tool)),
            'forbidden_violations': sum(len(r.forbidden_tool_violations) for r in results),
            'extra_calls': sum(r.false_positives for r in results),
            'duplicate_calls': sum(len(detect_duplicates(r.predicted_calls,r.expected_calls)) for r in results),
            'error_counts_are_nonexclusive': True,
            'breakdown': breakdown,
            'macro_success_by_dimension': {dim:sum(row['rate'] for row in groups.values())/len(groups)
                                           if complete and telemetry_complete else None
                                           for dim, groups in breakdown.items()},
            'error_summary': generate_error_summary(results),
            'latency_seconds': {'count': len(latencies), 'p50': latencies[math.ceil(.5*len(latencies))-1] if latencies else None,
                                'p95': latencies[math.ceil(.95*len(latencies))-1] if latencies else None},
            'usage': {key: sum(e.get('usage', {}).get(key, 0) for e in events if e.get('usage'))
                      for key in ('input_tokens','cached_tokens','output_tokens')},
            'known_cost_usd': journal.get('known_usd'), 'cost_unknown': journal.get('cost_unknown', True),
            'journal': journal, 'gate': gate, 'case_results': [r.to_dict() for r in results],
            'paired_statistics': {'status': 'NOT_APPLICABLE', 'reason': 'one model, one locked suite; dev and added split are not paired'},
            'human_review': {'status': 'NOT_PERFORMED_BY_RUNNER'},
            'limitations': ['Decision-only native tool selection; production tools are not executed.',
                            'Historical dev-v2 gold includes 11/24 cases adjudicated after model outputs; dev is not independent held-out evidence.',
                            'The added split is authored and reviewed, not a representative random SOC population sample.',
                            'Wilson intervals describe binomial uncertainty under independence assumptions; overlapping families/templates limit population claims.',
                            'Reviewer identities are reproduced from the existing lock; the runner does not certify either as human.',
                            'Dev and generalization denominators remain separate; missing cases are not discarded.']}
