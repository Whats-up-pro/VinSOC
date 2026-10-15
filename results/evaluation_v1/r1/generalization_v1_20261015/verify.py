"""Recompute the frozen R1 scorer from authentic native responses; no SDK or tools."""
import argparse
import hashlib
import json
import math
import sys
import zipfile
from collections import Counter
from decimal import Decimal
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = next(p for p in HERE.parents if (p/'.git').exists())
sys.path.insert(0, str(ROOT))


def verify():
    from agent.tools import get_tool_schemas
    from evaluation.tool_calling.arguments import normalize_arguments
    from evaluation.tool_calling.decision_runner import DecisionRunner
    from evaluation.tool_calling.generalization import verify_generalization_lock
    from evaluation.tool_calling.generalization_reporting import build_generalization_report
    from evaluation.tool_calling.matching import compute_case_metrics
    from evaluation.tool_calling.models import ToolCallCase, PredictedCall, CaseResult
    from evaluation.tool_calling.provenance import canonical_sha256

    read = lambda name: json.loads((HERE/name).read_text())
    report, journal, control = read('report.json'), read('journal.json'), read('cloud_run.json')
    gate = read('gate.json')
    split = ROOT/'evaluation/tool_calling/benchmarks/generalization_v1'
    locked = verify_generalization_lock(split, split/'GENERALIZATION.lock')
    assert locked.passed and locked.case_count == 120
    assert report['run_status'] == control['status'] == 'completed'
    assert report['journal'] == journal
    assert journal['attempted'] == journal['received'] == len(journal['events']) == 120
    assert journal['cost_unknown'] is False and journal['pending_exposure_usd'] == 0
    assert gate['passed'] and gate['git']['ci_success']
    assert gate['git']['commit_sha'] == gate['git']['ci_sha'] == 'ff37425719b3009d33d166ae3faa19ccc35a09e8'
    assert hashlib.sha256((HERE/'model_document.md').read_bytes()).hexdigest() == report['pricing']['model_document']['sha256']
    cases = [ToolCallCase.from_dict(json.loads(p.read_text())) for p in sorted(split.glob('*.json'))]
    ids = [c.case_id for c in cases]
    assert ids == report['expected_case_ids'] == report['completed_case_ids']
    assert len(report['case_results']) == len(set(ids)) == 120
    hashes = read('native_io_hashes.json')['files']
    events = journal['events']
    for key in ('request_id','response_id','provider_request_id'):
        assert len({e[key] for e in events if e.get(key)}) == 120
    results, mismatches = [], []
    cost = Decimal(0)
    with zipfile.ZipFile(HERE/'native_io.zip') as native:
        assert set(native.namelist()) == set(hashes) and len(hashes) == 240
        for name in native.namelist():
            assert hashlib.sha256(native.read(name)).hexdigest() == hashes[name]
        for index, (case, event, saved) in enumerate(zip(cases, events, report['case_results']), 1):
            assert event['case_id'] == saved['case_id'] == case.case_id
            assert event['request_number'] == index and event['role'] == 'r1-decision'
            req_name, res_name = (f'{kind}/{index:03d}-{case.case_id}.json' for kind in ('requests','responses'))
            request, response = json.loads(native.read(req_name)), json.loads(native.read(res_name))
            system, question = DecisionRunner.build_prompt(None, case)
            assert request == {'model':'gpt-4.1-mini-2025-04-14', 'messages':[
                {'role':'system','content':system},{'role':'user','content':question}],
                'tools':get_tool_schemas(),'temperature':0.0,'max_completion_tokens':1000}
            assert event['request_sha256'] == canonical_sha256(request)
            assert event['response_sha256'] == hashes[res_name]
            assert response['id'] == event['response_id'] and response['model'] == event['actual_model'] == request['model']
            choice = response['choices'][0]
            assert choice['finish_reason'] == event['finish_reason'] and choice['finish_reason'] in ('stop','tool_calls')
            usage = response['usage']
            expected_usage = {'input_tokens':usage['prompt_tokens'],'output_tokens':usage['completion_tokens'],
                              'cached_tokens':(usage.get('prompt_tokens_details') or {}).get('cached_tokens',0)}
            assert event['usage'] == expected_usage and usage['total_tokens'] == usage['prompt_tokens']+usage['completion_tokens']
            assert 0 <= expected_usage['cached_tokens'] <= expected_usage['input_tokens'] <= 1047576
            assert 0 <= expected_usage['output_tokens'] <= 1000 and math.isfinite(event['latency_seconds'])
            u = expected_usage
            amount = ((u['input_tokens']-u['cached_tokens'])*Decimal('.4')+u['cached_tokens']*Decimal('.1')+u['output_tokens']*Decimal('1.6'))/1000000
            assert abs(amount-Decimal(str(event['cost_usd']))) < Decimal('1e-12')
            cost += amount
            predicted = []
            for call in choice['message'].get('tool_calls') or []:
                function = call['function']; args = json.loads(function['arguments'])
                assert isinstance(args,dict)
                predicted.append(PredictedCall(function['name'], normalize_arguments(function['name'],args), args))
            metrics = compute_case_metrics(case,predicted)
            result = CaseResult(case.case_id,case.expected_calls,predicted)
            result.matches = metrics['matches']
            result.true_positives,result.false_positives,result.false_negatives = metrics['tp'],metrics['fp'],metrics['fn']
            result.forbidden_tool_violations = metrics['forbidden_violations']
            result.trajectory_success,result.exact_call_match,result.tool_set_match = metrics['trajectory_success'],metrics['exact_call_match'],metrics['tool_set_match']
            if result.forbidden_tool_violations: result.errors.append('FORBIDDEN_TOOL')
            if result.errors: result.trajectory_success = result.exact_call_match = result.tool_set_match = False
            assert result.to_dict() == saved
            if metrics['critical_arg_errors']:
                mismatches.append({'case_id':case.case_id,'critical_argument_mismatches_recomputed':metrics['critical_arg_errors'],
                                   'legacy_saved_critical_arg_errors':saved['critical_arg_errors'],
                                   'matches':saved['matches']})
            results.append(result)
    rebuilt = json.loads(json.dumps(build_generalization_report(cases,results,journal,gate)))
    # Legacy CaseResult.to_dict omits its per-case wall-clock latency. Keep the
    # original aggregate latency; the SDK latency distribution is independently
    # recomputed from the preserved native journal below.
    non_reconstructable = {'mean_latency_ms','p95_latency_ms'}
    assert {k:v for k,v in rebuilt['aggregate_observed_only'].items() if k not in non_reconstructable} == {
        k:v for k,v in report['aggregate_observed_only'].items() if k not in non_reconstructable}
    for key in rebuilt:
        if key != 'aggregate_observed_only': assert rebuilt[key] == report[key], key
    assert abs(cost-Decimal(str(journal['known_usd']))) < Decimal('1e-12')
    return {'status':'VERIFIED_OFFLINE','producer_sha':gate['git']['commit_sha'],'producer_ci':38698148403,
            'live_run':38699129318,'records':120,'responses':120,'native_io_files':240,
            'success':report['success'],'usage':report['usage'],'cost_usd':format(cost.quantize(Decimal('.00000001')),'f'),
            'cost_unknown':False,'pending_exposure_usd':0,'request_response_provider_ids_unique':True,
            'native_predictions_and_frozen_scorer_recomputed':True,'report_recomputed_equal_except_legacy_wall_clock_latency':True,
            'legacy_wall_clock_latency_fields_not_reconstructable_from_case_result':sorted(non_reconstructable),
            'sdk_latency_seconds_recomputed':report['latency_seconds'],
            'critical_argument_mismatches':mismatches,
            'legacy_error_summary_preserved':report['error_summary'],
            'interpretation':'119/120 decision-only; no production SOC tools executed; authored suite, correlated families, not a random held-out SOC population.',
            'new_model_calls':0,'new_tool_executions':0,'human_reviews_signed':0}


if __name__ == '__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--write-audit',action='store_true');args=parser.parse_args()
    result=verify()
    if args.write_audit: (HERE/'audit_summary.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
    else: assert result == json.loads((HERE/'audit_summary.json').read_text())
    print(json.dumps({k:result[k] for k in ('status','records','responses','success','cost_usd','new_model_calls')}))
