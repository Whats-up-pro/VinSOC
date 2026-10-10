"""Evaluator/report adapter. Missing slots carry no inferred score or model output."""
from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path

import sqlglot

ROOT = Path(__file__).resolve().parents[2]
META = ('case_id', 'database_id', 'question', 'domain', 'family_id', 'difficulty', 'features')


def inventory_metadata(inventory):
    annotations = {}
    for split in ('calibration', 'evaluation'):
        for path in (ROOT/'evaluation/r2_cross_domain_v1/benchmarks/references'/split).glob('*.json'):
            reference = json.loads(path.read_text())
            annotations[reference['case_id']] = {k: reference[k] for k in META}
    result = []
    seen = set()
    for row in inventory:
        if row.get('case_id') in seen:
            raise ValueError('DUPLICATE_PLANNED_CASE')
        seen.add(row.get('case_id'))
        saved = annotations.get(row['case_id'], row)
        if saved.get('question') != row.get('question') or saved.get('database_id') != row.get('database_id'):
            raise ValueError('INVENTORY_QUESTION_OR_DATABASE_MISMATCH')
        result.append({k: saved.get(k) for k in META})
    return result


def finite(value):
    return type(value) in (int, float) and math.isfinite(value) and value >= 0


def result_hash_valid(receipt):
    if not isinstance(receipt, dict) or any(k not in receipt for k in ('columns','rows','truncated')):
        return False
    data = {k:receipt[k] for k in ('columns','rows','truncated')}
    encoded = json.dumps(data, ensure_ascii=False, sort_keys=True, separators=(',', ':'), allow_nan=False)
    return hashlib.sha256(encoded.encode()).hexdigest() == receipt.get('result_sha256')


def normalize_query_records(records, inventory, *, identities, journal):
    metadata = inventory_metadata(inventory)
    ids = {r['case_id'] for r in metadata}
    indexed = {}
    for record in records:
        key = record.get('condition'), record.get('case_id')
        if key in indexed or key[0] not in ('E0','E3') or key[1] not in ids:
            raise ValueError('DUPLICATE_OR_FOREIGN_CASE_RECORD')
        indexed[key] = record
    normalized = []
    for condition in ('E0','E3'):
        for meta in metadata:
            record = indexed.get((condition,meta['case_id']))
            row = {**meta, 'condition':condition, 'present':record is not None,
                   'planned_case_count':len(metadata), 'record_status':'missing' if record is None else 'incomplete',
                   'execution_accurate':None, 'execution_success':None, 'syntax_valid':None,
                   'usage_valid':False, 'provenance_valid':False, 'scoring_valid':False}
            if record is None:
                normalized.append(row)
                continue
            generation = record.get('generation', record)
            score = record.get('score', {})
            events = record.get('cost_events', [])
            journal_events = [e for e in journal.get('events', journal.get('cost_events', []))
                              if e.get('case_id') == meta['case_id'] and e.get('condition') == condition]
            usage_valid = bool(events) and events == journal_events
            for event in events:
                usage = event.get('usage') or {}
                usage_valid &= (event.get('received') is True and bool(event.get('response_id'))
                    and bool(event.get('request_id')) and bool(event.get('request_sha256'))
                    and all(type(usage.get(k)) is int and usage[k] >= 0 for k in ('input_tokens','output_tokens','cached_tokens'))
                    and finite(event.get('cost_usd')))
            if len({e.get('response_id') for e in events}) != len(events):
                usage_valid = False
            expected = identities.get('snapshot_identities', {}).get(meta['database_id'])
            provenance = (bool(identities.get('runtime_source_sha256')) and bool(identities.get('benchmark_identity'))
                and bool(identities.get('scorer_identity')) and record.get('identities') == identities
                and expected is not None and generation.get('snapshot_identity') == expected
                and generation.get('question') == meta['question'] and generation.get('evidence_kind') == 'openai_live')
            valid_score = provenance and usage_valid and type(score.get('execution_accurate')) is bool
            sql = generation.get('final_sql')
            syntax = None
            if sql:
                try:
                    syntax = len(sqlglot.parse(sql, read='duckdb')) == 1
                except sqlglot.errors.ParseError:
                    syntax = False
            row.update(final_sql=sql, error_category=generation.get('error_category'),
                       scoring_error_category=score.get('scoring_error_category'),
                       syntax_valid=syntax, execution_accurate=score.get('execution_accurate') if valid_score else None,
                       execution_success=score.get('execution_success') if valid_score else None,
                       safety_rejected=generation.get('error_category') == 'SAFETY_REJECTION',
                       scoring_valid=bool(valid_score), usage_valid=bool(usage_valid), provenance_valid=bool(provenance),
                       record_status='scored' if valid_score else 'incomplete',
                       snapshot_identity=expected, scorer_identity=identities.get('scorer_identity'),
                       benchmark_identity=identities.get('benchmark_identity'),
                       runtime_identity=identities.get('runtime_source_sha256'),
                       modules=record.get('modules') if condition == 'E3' else {'schema_linker':None,'value_grounding':None},
                       trajectory=generation.get('trajectory', []), db_calls=generation.get('db_calls'),
                       wall_seconds=generation.get('wall_seconds'), evidence_kind=generation.get('evidence_kind'),
                       attempted_calls=len(events), response_count=sum(e.get('received') is True for e in events),
                       cost_unknown=not usage_valid,
                       responses=[{'role':e['role'], 'response':{'usage':e.get('usage'), 'cost_usd':e.get('cost_usd')}} for e in events])
            normalized.append(row)
    return normalized
