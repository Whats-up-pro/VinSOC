"""Audit a genuine partial pipeline without SDK, SQL replay, or missing predictions."""
import argparse
import gzip
import hashlib
import json
import math
import sys
from collections import Counter
from decimal import Decimal
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = next(p for p in HERE.parents if (p/'.git').exists())
sys.path.insert(0,str(ROOT))


def same(left,right):
    """Python 3.12 sum() differs from producer 3.11 at float roundoff only."""
    if isinstance(left,float) and isinstance(right,float):
        return math.isclose(left,right,rel_tol=0,abs_tol=1e-12)
    if type(left) is not type(right): return False
    if isinstance(left,dict): return set(left)==set(right) and all(same(left[k],right[k]) for k in left)
    if isinstance(left,list): return len(left)==len(right) and all(same(a,b) for a,b in zip(left,right))
    return left==right


def verify():
    from scripts.run_vinsoc_query_acceptance import inventory_for
    from evaluation.finalization.query_reporting import build_query_report
    from evaluation.finalization.query_pipeline_reporting import build_pipeline_report
    from evaluation.finalization.query_record_normalization import result_hash_valid
    from evaluation.finalization.query_runtime_validation import selection_identities, verify_selection_lock
    from agent.evidence import Evidence,EvidenceStore
    from agent.network_query_policy import NetworkQueryPolicy

    read = lambda name: json.loads((HERE/name).read_text())
    report = json.loads(gzip.decompress((HERE/'live/report.json.gz').read_bytes()))
    native = json.loads(gzip.decompress((HERE/'native_responses.json.gz').read_bytes()))
    control = read('cloud_run.json'); rows=report['case_records']; events=report['cost_events']
    inventory=inventory_for('pipeline'); meta={r['case_id']:r for r in inventory}
    assert report['status']==control['status']=='partial' and report['failure_category']=='ValueError'
    assert report['planned']==report['planned_records']==32 and report['completed']==16
    assert len(rows)==17 and len({r['case_id'] for r in rows})==17
    assert [r['case_id'] for r in rows]==[r['case_id'] for r in inventory[:17]]
    missing=[r['case_id'] for r in inventory if r['case_id'] not in {x['case_id'] for x in rows}]
    assert len(missing)==15 and rows[-1]['status']=='partial' and 'score' not in rows[-1]
    assert report['attempted']==report['received']==report['valid_usage']==len(events)==len(native)==50
    assert report['cost_unknown'] is control['cost_unknown'] is False and report['pending_exposure_usd']==0
    identities={**selection_identities(),'implementation_sha':'ff37425719b3009d33d166ae3faa19ccc35a09e8'}
    assert all(row['identities']==identities for row in rows)
    lock=ROOT/'results/evaluation_v1/text2sql_integration_v1/selection_lock.json'
    locked=json.loads(lock.read_text());selected=verify_selection_lock(lock,identities={**identities,'selection_sha256':locked['selection_sha256']})
    assert selected['selected_condition']=='E0'
    files=list((HERE/'live').glob('E0_*.json'))
    assert len(files)==17
    assert {json.loads(p.read_text())['case_id']:json.loads(p.read_text()) for p in files}=={r['case_id']:r for r in rows}
    prices={'r2':('gpt-5-mini-2025-08-07',Decimal('.25'),Decimal('.025'),Decimal('2')),
            'routing':('gpt-4.1-mini-2025-04-14',Decimal('.4'),Decimal('.1'),Decimal('1.6')),
            'assessment':('gpt-4.1-mini-2025-04-14',Decimal('.4'),Decimal('.1'),Decimal('1.6'))}
    for key in ('request_id','response_id','provider_request_id'):
        assert len({e[key] for e in events if e.get(key)})==50
    cost=Decimal(0)
    for event,saved in zip(events,native):
        for key,value in saved.items():
            if key!='response': assert event[key]==value
        response=saved['response'];u=event['usage'];model,inp,cached,out=prices[event['role']]
        assert response['id']==event['response_id'] and response['model']==event['actual_model']==model
        usage=response['usage'];assert u['input_tokens']==usage['prompt_tokens'] and u['output_tokens']==usage['completion_tokens']
        assert u['cached_tokens']==(usage.get('prompt_tokens_details') or {}).get('cached_tokens',0)
        assert usage['total_tokens']==u['input_tokens']+u['output_tokens']
        assert 0<=u['cached_tokens']<=u['input_tokens'] and 0<=u['output_tokens']<=1000
        assert math.isfinite(event['latency_seconds']) and event['latency_seconds']>=0
        amount=((u['input_tokens']-u['cached_tokens'])*inp+u['cached_tokens']*cached+u['output_tokens']*out)/1000000
        assert abs(amount-Decimal(str(event['cost_usd'])))<Decimal('1e-12');cost+=amount
    parser_errors=Counter()
    for row in rows:
        cid=row['case_id'];g=row['generation'];assert g['question']==meta[cid]['question'] and g['runtime_version']=='shared_text2sql_v1'
        ev=[e for e in events if e['case_id']==cid];assert row['cost_events']==ev
        sql_events=[e for e in native if e['case_id']==cid and e['role']=='r2'];assert len(sql_events)==1
        content=json.loads(sql_events[0]['response']['choices'][0]['message']['content']);assert content['sql']==g['final_sql']
        execution=(row.get('metadata') or {}).get('query_execution',g.get('execution'))
        assert result_hash_valid(execution) and execution['sql_sha256']==hashlib.sha256(g['final_sql'].encode()).hexdigest()
        assert execution['snapshot_logical_sha256']==identities['snapshot_identities']['ctu_dev']
        if row.get('status')=='partial':
            assert len(ev)==2 and not any(e['role']=='assessment' for e in ev)
            continue
        assert row['metadata']['orchestration_mode']=='query_evidence_driven'
        assert row['score']['predicted_result_sha256']==execution['result_sha256']
        assessment=[e for e in native if e['case_id']==cid and e['role']=='assessment'];assert len(assessment)==1
        store=EvidenceStore();store.evidence=[Evidence(**item) for item in row['evidence']]
        try: NetworkQueryPolicy(meta[cid]['question']).parse_final_response(assessment[0]['response']['choices'][0]['message']['content'],store);error='OK'
        except ValueError as exc: error=str(exc)
        parser_errors[error]+=1
    assert abs(cost-Decimal(str(control['current_run_cost_usd'])))<Decimal('1e-12')
    assert same(build_query_report(rows,inventory,conditions=('E0',),identities=identities,journal={'events':events}),report['metrics'])
    pipeline=build_pipeline_report(rows,inventory,reviews=[],identities=identities,journal={'events':events})
    assert same(pipeline,report['pipeline_metrics'])
    assert all(v['denominator']==32 and v['rate'] is None for v in pipeline['metrics'].values())
    partial=rows[-1];execution=partial['generation']['execution'];subset={k:execution[k] for k in ('columns','rows','row_count','truncated','result_sha256')}
    payload=len(json.dumps(subset,ensure_ascii=False,separators=(',',':')).encode())
    assert payload==177205 and payload>NetworkQueryPolicy.MAX_RESPONSE_BYTES==32768
    assert len(execution['rows'])==execution['row_count']==9780 and execution['truncated'] is False
    return {'status':'VERIFIED_PARTIAL_NOT_COMPLETE','planned':32,'completed':16,'partial':1,'missing':15,
            'missing_case_ids':missing,'attempted':50,'received':50,'valid_usage':50,
            'usage':{k:sum(e['usage'][k] for e in events) for k in ('input_tokens','output_tokens','cached_tokens')},
            'current_run_cost_usd':format(cost.quantize(Decimal('.00000001')),'f'),
            'query_cumulative_cost_usd':'1.33381910','cost_unknown':False,'pending_exposure_usd':0,
            'selected_condition':'E0','selection_sha256':selected['selection_sha256'],'metrics_recomputed_equal':True,
            'floating_sum_comparison_absolute_tolerance':1e-12,
            'pipeline_metrics':pipeline,'native_assessment_parser_replay':dict(parser_errors),
            'stopping_payload_minimum_bytes':payload,'policy_limit_bytes':32768,
            'producer_exception_message_not_preserved':True,
            'interpretation':'Partial is not 32-case acceptance. Raw metrics treat unavailable partial stage checks as false; these are not observations of a wrong model assessment. All rates remain null and the denominator stays 32.',
            'new_model_calls':0,'new_sql_executions':0,'human_reviews_signed':0}


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--write-audit',action='store_true');args=parser.parse_args();result=verify()
    if args.write_audit:(HERE/'audit_summary.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
    else:assert result==json.loads((HERE/'audit_summary.json').read_text())
    print(json.dumps({k:result[k] for k in ('status','planned','completed','partial','missing','attempted','received','current_run_cost_usd','new_model_calls')}))
