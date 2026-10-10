"""Pipeline EX, facts, runtime and human decisions have independent gates."""
from __future__ import annotations

import json
from collections import Counter, defaultdict
from datetime import datetime

from .query_record_normalization import inventory_metadata, normalize_query_records, result_hash_valid, finite


def validate_review(review, record):
    expected = record.get('case_receipt_sha256')
    try:
        utc = datetime.fromisoformat(review.get('utc','').replace('Z','+00:00'))
        time_valid = utc.tzinfo is not None and utc.utcoffset().total_seconds() == 0
    except (ValueError, TypeError):
        time_valid = False
    return (bool(expected) and review.get('scope') == 'actual_human_review'
            and review.get('case_id') == record.get('case_id')
            and review.get('case_receipt_sha256') == expected
            and review.get('decision') in ('approved','rejected','escalated')
            and bool(str(review.get('analyst','')).strip()) and bool(str(review.get('rationale','')).strip()) and time_valid)


def build_pipeline_report(records, inventory, *, reviews, identities, journal):
    inventory = inventory_metadata(inventory)
    if len(inventory) != 32 or any(r['database_id'] != 'ctu_dev' for r in inventory):
        raise ValueError('FULL_CTU32_INVENTORY_REQUIRED')
    indexed = {}
    ids = {r['case_id'] for r in inventory}
    for record in records:
        if record.get('case_id') not in ids or record['case_id'] in indexed:
            raise ValueError('DUPLICATE_OR_FOREIGN_PIPELINE_RECORD')
        indexed[record['case_id']] = record
    review_map = {}
    for review in reviews:
        if review.get('case_id') not in ids or review['case_id'] in review_map:
            raise ValueError('DUPLICATE_OR_FOREIGN_HUMAN_REVIEW')
        review_map[review['case_id']] = review
    normalized = {(r['condition'],r['case_id']):r for r in normalize_query_records(records, inventory, identities=identities, journal=journal)}
    cases = []
    metrics = Counter()
    known = Counter()
    role_events = defaultdict(list)
    for meta in inventory:
        record = indexed.get(meta['case_id'])
        values = {k:None for k in ('routing','runtime','integrated_ex','provenance','factual_verification','technical_workflow','human_review_coverage','human_approved_completion')}
        decision = 'pending'
        review_status = 'missing'
        if record:
            generation = record.get('generation', {})
            meta_case = record.get('metadata', {})
            policy = meta_case.get('query_policy', {})
            trace = record.get('tool_trace', [])
            events = record.get('cost_events', [])
            native = [c for e in events if e.get('role') == 'routing' for c in e.get('native_tool_calls', [])]
            routing = (len(native) == 1 and bool(native[0].get('id')) and len(trace) == 1)
            if routing:
                try:
                    args = native[0]['function']['arguments']
                    args = json.loads(args) if isinstance(args,str) else args
                    routing = (native[0]['function']['name'] == 'network_query' and args == {'question':meta['question']}
                               and trace[0].get('tool') == 'network_query' and trace[0].get('arguments') == args)
                except (ValueError,KeyError,TypeError):
                    routing = False
            norm = normalized[(record['condition'],meta['case_id'])]
            execution = meta_case.get('query_execution', record.get('execution'))
            evidence = record.get('evidence', [])
            by_id = {e['evidence_id']:e for e in evidence}
            results = [e for e in evidence if e.get('type') == 'query_result']
            observed = [e for e in evidence if e.get('type') == 'query_execution']
            provenance = (norm['provenance_valid'] and result_hash_valid(execution)
                and execution.get('truncated') is False and len(results) == len(observed) == 1
                and results[0].get('related_evidence_ids') == [observed[0]['evidence_id']]
                and results[0].get('data', {}).get('result_sha256') == execution.get('result_sha256')
                and policy.get('validation', {}).get('independent_query_replay') is True)
            facts = bool(record.get('observations')) and bool(record.get('assessment_evidence_ids'))
            for observation in record.get('observations', []):
                data = by_id.get(observation.get('evidence_id'), {}).get('data', {})
                value = data.get(observation.get('field'))
                facts &= (observation.get('field') in data and type(value) is type(observation.get('value')) and value == observation.get('value'))
            facts &= all(i in by_id for i in record.get('assessment_evidence_ids', []))
            runtime = generation.get('runtime_version') == 'shared_text2sql_v1' and generation.get('question') == meta['question']
            integrated = norm['execution_accurate']
            technical = (routing and runtime and integrated is True and provenance and facts
                         and meta_case.get('schema_valid') is True and policy.get('termination') == 'FINAL_ASSESSMENT')
            review = review_map.get(meta['case_id'])
            if review:
                if validate_review(review, record):
                    decision, review_status = review['decision'], 'valid'
                else:
                    review_status = 'hash_or_identity_mismatch'
            values.update(routing=bool(routing), runtime=bool(runtime), integrated_ex=integrated,
                          provenance=bool(provenance), factual_verification=bool(facts), technical_workflow=bool(technical),
                          human_review_coverage=review_status == 'valid',
                          human_approved_completion=bool(technical and decision == 'approved'))
            for event in events:
                role_events[event['role']].append(event)
        for metric, value in values.items():
            if type(value) is bool:
                known[metric] += 1
                metrics[metric] += int(value)
        status = 'missing' if not record else ('awaiting_human' if values['technical_workflow'] else
                  'incomplete' if values['integrated_ex'] is None else 'technical_failed')
        if record and values['technical_workflow'] and review_status == 'valid':
            status = decision
        cases.append({'case_id':meta['case_id'], 'question':meta['question'], 'status':status,
                      'metrics':values, 'human_decision':decision, 'review_status':review_status})
    overhead = {}
    for role in ('routing','r2','assessment'):
        events = role_events[role]
        overhead[role] = {'calls':len(events), 'received':sum(e.get('received') is True for e in events),
                         'input_tokens':sum((e.get('usage') or {}).get('input_tokens',0) for e in events),
                         'output_tokens':sum((e.get('usage') or {}).get('output_tokens',0) for e in events),
                         'latency_seconds_known':sum(e['latency_seconds'] for e in events if finite(e.get('latency_seconds'))),
                         'known_cost_usd':sum(e['cost_usd'] for e in events if finite(e.get('cost_usd'))),
                         'unknown_cost_calls':sum(not finite(e.get('cost_usd')) for e in events)}
    decisions = Counter(c['human_decision'] for c in cases)
    return {'scope':'pipeline32_saved_artifact_metrics', 'planned':32, 'completed':len(indexed),
            'status':'recorded_awaiting_human' if len(indexed)==32 else 'incomplete', 'cases':cases,
            'metrics':{m:{'correct_observed':metrics[m], 'denominator':32, 'measured':known[m],
                          'missing_or_incomplete':32-known[m], 'rate':metrics[m]/32 if known[m]==32 else None} for m in values},
            'human_review':{d:decisions[d] for d in ('approved','rejected','escalated','pending')},
            'role_overhead':overhead, 'official_eligible':False,
            'positive_new_pipeline_trace_validation':'pending_authentic_pipeline_records'}
