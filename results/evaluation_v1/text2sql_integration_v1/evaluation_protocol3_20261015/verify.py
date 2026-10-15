"""Read-only verification of authentic evaluation artifacts. No SDK or SQL execution."""
from __future__ import annotations

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


def sha(data):
    return hashlib.sha256(data).hexdigest()


def canonical(value):
    return sha(json.dumps(value,sort_keys=True,separators=(',',':'),ensure_ascii=False).encode())


def verify():
    from scripts.run_vinsoc_query_acceptance import inventory_for
    from evaluation.finalization.query_runtime_validation import selection_identities, verify_selection_lock
    from evaluation.finalization.query_record_normalization import result_hash_valid
    from evaluation.finalization.query_reporting import build_query_report

    control=json.loads((HERE/'cloud_run.json').read_text())
    raw=gzip.decompress((HERE/'live/report.json.gz').read_bytes())
    report=json.loads(raw)
    rows=report['case_records'];events=report['cost_events'];inventory=inventory_for('evaluation')
    expected={(condition,row['case_id']) for condition in ('E0','E3') for row in inventory}
    indexed={(r['condition'],r['case_id']):r for r in rows}
    assert len(rows)==len(indexed)==len(expected)==192 and set(indexed)==expected
    files=sorted((HERE/'live').glob('E[03]_*.json'))
    bindings={}
    for path in files:
        row=json.loads(path.read_text())
        key=(row['condition'],row['case_id'])
        assert path.name==f'{key[0]}_{key[1]}.json' and key not in bindings
        bindings[key]=row
    assert bindings==indexed
    assert control['status']==report['status']=='completed'
    assert report['planned_records']==report['completed']==192 and report['planned']==96
    assert report['attempted']==report['received']==report['valid_usage']==len(events)==578
    assert control['attempted']==control['received']==578 and control['client_created'] is True
    assert control['window_claimed'] is True and control['cost_unknown'] is False
    assert report['cost_unknown'] is False and report['pending_exposure_usd']==0
    identities={**selection_identities(),'implementation_sha':'3c3ce816ed2f5dbf04c35433267b599b31d8c2bd'}
    assert all(row['identities']==identities for row in rows)
    lock_path=ROOT/'results/evaluation_v1/text2sql_integration_v1/selection_lock.json'
    locked=json.loads(lock_path.read_text())
    selected=verify_selection_lock(lock_path,identities={**identities,'selection_sha256':locked['selection_sha256']})
    assert selected['selected_condition']=='E0'
    metadata={row['case_id']:row for row in inventory}
    pricing=json.loads((HERE/'pricing_facts.json').read_text())
    by_condition={}
    for key in ('request_id','response_id','provider_request_id'):
        assert len({e.get(key) for e in events if e.get(key)})==578
    for row in rows:
        condition,cid=row['condition'],row['case_id']
        assert row['question']==metadata[cid]['question']
        assert row['database_id']==metadata[cid]['database_id']
        assert row['runtime_version']=='shared_text2sql_v1' and row['evidence_kind']=='openai_live'
        assert row['cost_unknown'] is False and row['generation']['final_sql']==row['final_sql']
        ev=[e for e in events if (e['condition'],e['case_id'])==(condition,cid)]
        assert ev==row['cost_events'] and 1<=len(ev)<=(1 if condition=='E0' else 6)
        assert len(row['responses'])==row['response_count']==row['attempted_calls']==len(ev)
        assert [r['response']['response_id'] for r in row['responses']]==[e['response_id'] for e in ev]
        if row['final_sql']:
            native=[]
            for item in row['responses']:
                try: content=json.loads(item['response'].get('content') or '')
                except ValueError: continue
                if item['role']=='generator' and isinstance(content,dict):native.append(content.get('sql'))
            assert row['final_sql'] in native
        if row['score']['execution_success']:
            execution=row['execution']
            assert result_hash_valid(execution)
            assert row['score']['predicted_result_sha256']==execution['result_sha256']
            assert execution['snapshot_logical_sha256']==identities['snapshot_identities'][row['database_id']]
            assert sha(execution['sql'].encode())==execution['sql_sha256']
        for e in ev:
            assert e['received'] is True and e['transmitted'] is True and e['role']=='r2'
            assert e['actual_model']=='gpt-5-mini-2025-08-07'
            usage=e['usage'];p=pricing[e['actual_model']]
            assert all(type(usage[k]) is int and usage[k]>=0 for k in ('input_tokens','output_tokens','cached_tokens'))
            assert usage['cached_tokens']<=usage['input_tokens']<=p['input_token_ceiling']
            assert usage['output_tokens']<=1000
            assert isinstance(e['latency_seconds'],(int,float)) and math.isfinite(e['latency_seconds']) and e['latency_seconds']>=0
            amount=((usage['input_tokens']-usage['cached_tokens'])*Decimal(str(p['input_usd_per_million']))
                +usage['cached_tokens']*Decimal(str(p['cached_input_usd_per_million']))
                +usage['output_tokens']*Decimal(str(p['output_usd_per_million'])))/1000000
            assert abs(amount-Decimal(str(e['cost_usd'])))<Decimal('0.000000000001')
    rebuilt=build_query_report(rows,inventory,identities=identities,journal={'events':events})
    assert rebuilt==report['metrics']
    for key in ('present','usage_valid','provenance_valid','scoring_valid'):
        assert all(row[key] is True for row in rebuilt['normalized_records'])
    for condition in ('E0','E3'):
        records=[r for r in rows if r['condition']==condition]
        ev=[e for e in events if e['condition']==condition]
        by_condition[condition]={
            'records':len(records),'correct':sum(r['score']['execution_accurate'] for r in records),
            'calls':len(ev),'cost_usd':format(sum(Decimal(str(e['cost_usd'])) for e in ev).quantize(Decimal('0.00000001')),'f'),
            'tokens':{k:sum(e['usage'][k] for e in ev) for k in ('input_tokens','output_tokens','cached_tokens')},
            'generation_errors':dict(Counter(r['error_category'] for r in records)),
            'scoring_errors':dict(Counter(r['score']['scoring_error_category'] for r in records))}
    total=sum(Decimal(str(e['cost_usd'])) for e in events)
    assert abs(total-Decimal(str(control['current_run_cost_usd'])))<Decimal('0.000000000001')
    return {'scope':'evaluation','records':192,'unique_cases':96,'paired_cases':96,
            'attempted':578,'received':578,'unique_provider_request_ids':578,'unique_response_ids':578,
            'cost_unknown':False,'pending_exposure_usd':0,'current_run_cost_usd':format(total.quantize(Decimal('0.00000001')),'f'),
            'query_cumulative_cost_usd':format((Decimal('0.60001675')+total).quantize(Decimal('0.00000001')),'f'),
            'input_tokens':sum(e['usage']['input_tokens'] for e in events),
            'output_tokens':sum(e['usage']['output_tokens'] for e in events),
            'cached_tokens':sum(e['usage']['cached_tokens'] for e in events),
            'conditions':by_condition,'paired_statistics':rebuilt['statistics']['paired'],
            'metrics_recomputed_equal':True,'producer_report_sha256':sha(raw),
            'producer_metrics_canonical_sha256':canonical(report['metrics']),
            'selected_condition':selected['selected_condition'],'selection_sha256':selected['selection_sha256'],
            'semantic_test_accuracy':'NOT_MEASURED; producer defaults are not a semantic test-suite result',
            'isolation_evidence':'Independent required real-data jobs from exact producer CI; executor isolation field is not used by this audit.',
            'new_model_calls_by_verifier':0,'sql_executions_by_verifier':0,
            'human_review_signed_by_verifier':False}


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--write-audit',action='store_true')
    args=parser.parse_args()
    result=verify()
    if args.write_audit:
        (HERE/'audit_summary.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
    else:
        assert result==json.loads((HERE/'audit_summary.json').read_text())
    print(json.dumps({'status':'VERIFIED_OFFLINE','records':result['records'],
                      'responses':result['received'],'cost_usd':result['current_run_cost_usd'],
                      'metrics_recomputed_equal':result['metrics_recomputed_equal'],
                      'new_model_calls':0},ensure_ascii=False))
