"""Pipeline EX, facts, runtime and human decisions have independent gates."""
from __future__ import annotations

import json
import hashlib
from collections import Counter, defaultdict
from datetime import datetime

from .query_record_normalization import inventory_metadata, normalize_query_records, result_hash_valid, finite


def query_observations_verified(assessment, evidence):
    """Match cited facts to metadata or an unambiguous single-row result cell."""
    if not isinstance(assessment, dict) or not isinstance(evidence, list):
        return False
    by_id = {}
    for item in evidence:
        if not isinstance(item, dict) or not isinstance(item.get('evidence_id'), str):
            return False
        if item['evidence_id'] in by_id:
            return False
        by_id[item['evidence_id']] = item
    observations, citations = assessment.get('observations'), assessment.get('evidence_ids')
    if (not isinstance(observations, list) or not observations
            or not isinstance(citations, list) or not citations
            or any(not isinstance(i, str) or i not in by_id for i in citations)
            or not any(by_id[i].get('type') == 'query_result' for i in citations)):
        return False
    seen = set()
    for observation in observations:
        if (not isinstance(observation, dict) or set(observation) != {'evidence_id', 'field', 'value'}
                or not isinstance(observation['evidence_id'], str)
                or not isinstance(observation['field'], str)):
            return False
        key = observation['evidence_id'], observation['field']
        if key in seen or key[0] not in by_id:
            return False
        seen.add(key)
        item = by_id[key[0]]
        data = item.get('data')
        if not isinstance(data, dict):
            return False
        columns, rows = data.get('columns'), data.get('rows')
        matches = ([i for i, column in enumerate(columns)
                    if isinstance(column, dict) and column.get('name') == key[1]]
                   if item.get('type') == 'query_result' and isinstance(columns, list) else [])
        if key[1] in data and matches:
            return False  # The same field names metadata and a result column.
        if key[1] in data:
            expected = data[key[1]]
        elif item.get('type') == 'query_result':
            if (not isinstance(rows, list) or len(rows) != 1 or len(matches) != 1
                    or not isinstance(rows[0], list) or len(rows[0]) != len(columns)):
                return False
            expected = rows[0][matches[0]]
        else:
            return False
        if type(expected) is not type(observation['value']) or expected != observation['value']:
            return False
    return True


def query_execution_verified(record):
    """Bind displayed execution, result evidence, SQL and execution lineage."""
    metadata = record.get('metadata', {})
    generation = record.get('generation', {})
    execution = metadata.get('query_execution', record.get('execution'))
    results = [e for e in record.get('evidence', []) if e.get('type') == 'query_result']
    observed = [e for e in record.get('evidence', []) if e.get('type') == 'query_execution']
    sql = generation.get('final_sql')
    if not isinstance(sql, str) or not sql or len(results) != 1 or len(observed) != 1:
        return False
    result, observed_data = results[0].get('data'), observed[0].get('data')
    if not isinstance(result, dict) or not isinstance(observed_data, dict):
        return False
    try:
        if not result_hash_valid(execution) or not result_hash_valid(result):
            return False
    except (ValueError, TypeError):
        return False
    identity_fields = ('database_id', 'snapshot_binary_sha256', 'snapshot_logical_sha256',
                       'sql_sha256', 'result_sha256', 'executor_version')
    return (execution.get('truncated') is False
            and bool(observed[0].get('evidence_id'))
            and results[0].get('related_evidence_ids') == [observed[0]['evidence_id']]
            and result.get('result_sha256') == execution.get('result_sha256')
            and all(isinstance(execution.get(k), str) and bool(execution[k])
                    and observed_data.get(k) == execution[k] for k in identity_fields)
            and execution.get('sql_sha256') == hashlib.sha256(sql.encode()).hexdigest()
            and execution.get('snapshot_logical_sha256') == generation.get('snapshot_identity')
            and metadata.get('query_policy', {}).get('validation', {}).get('independent_query_replay') is True)


def validate_review(review, record):
    expected = record.get('case_receipt_sha256')
    if not isinstance(review.get('utc'), str):
        return False
    try:
        utc = datetime.fromisoformat(review.get('utc','').replace('Z','+00:00'))
        time_valid = utc.tzinfo is not None and utc.utcoffset().total_seconds() == 0
    except (ValueError, TypeError):
        time_valid = False
    return (bool(expected) and review.get('scope') == 'actual_human_review'
            and review.get('case_id') == record.get('case_id')
            and review.get('case_receipt_sha256') == expected
            and review.get('decision') in ('approved','rejected','escalated')
            and isinstance(review.get('analyst'), str) and bool(review['analyst'].strip())
            and isinstance(review.get('rationale'), str) and bool(review['rationale'].strip()) and time_valid)


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
            assessment = policy.get('assessment') or {}
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
            evidence = record.get('evidence', [])
            provenance = norm['provenance_valid'] and query_execution_verified(record)
            facts = query_observations_verified(assessment, evidence)
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
    completed = sum(r.get('status') != 'partial' for r in records)
    return {'scope':'pipeline32_saved_artifact_metrics', 'planned':32, 'completed':completed,
            'recorded':len(indexed), 'partial':len(indexed)-completed,
            'status':'recorded_awaiting_human' if completed==32 else 'incomplete', 'cases':cases,
            'metrics':{m:{'correct_observed':metrics[m], 'denominator':32, 'measured':known[m],
                          'missing_or_incomplete':32-known[m], 'rate':metrics[m]/32 if known[m]==32 else None} for m in values},
            'human_review':{d:decisions[d] for d in ('approved','rejected','escalated','pending')},
            'role_overhead':overhead, 'official_eligible':False,
            'positive_new_pipeline_trace_validation':'pending_authentic_pipeline_records'}
