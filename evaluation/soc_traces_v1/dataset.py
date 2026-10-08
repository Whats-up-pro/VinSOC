"""Deterministic evaluator-only selection; never passed to the agent."""
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path
import json
import hashlib
import re
import duckdb
from vinsoc_data.soc_corpus import SOURCE_MANIFEST, verify_sources, digest, REVISION


def build_candidates(source_dir, repository):
    verify_sources(source_dir, SOURCE_MANIFEST)
    candidates=[]
    with duckdb.connect() as con:
        rows=con.execute('SELECT scenario_id,archetype,verdict FROM read_parquet(?)', [str(Path(source_dir)/'test.parquet')]).fetchall()
    inputs={s:json.loads(v) for s,v in repository._query("SELECT scenario_id,input_json FROM case_inputs WHERE split='test'")}
    observations=defaultdict(list)
    for scenario,record in repository._query("SELECT scenario_id,record_json FROM observations ORDER BY scenario_id,resource,source_record_id"):
        if scenario in inputs: observations[scenario].append(json.loads(record))
    for scenario,family,label in rows:
        records=observations[scenario]
        if not records or label not in ('malicious','benign'):continue
        payload={'input':inputs[scenario],'records':[r['data'] for r in records]}
        exact=digest(payload)
        normalized=re.sub(r'\d+','<number>', json.dumps(payload,sort_keys=True,ensure_ascii=False))
        candidates.append({'scenario_id':scenario,'family':family,'label':label,'payload_sha256':exact,
                           'near_duplicate_sha256':digest(normalized),'source_revision':REVISION})
    return candidates


def select_inventory(candidates, *, exclusions):
    excluded=set()
    for e in exclusions:
        if not e.get('analyst') or e.get('decision')!='exclude' or not e.get('rationale'):
            raise ValueError('EXCLUSION_HUMAN_REVIEW_REQUIRED')
        excluded.add(e['scenario_id'])
    selected=[];seen=set();near=Counter(c['near_duplicate_sha256'] for c in candidates)
    for label in ('malicious','benign'):
        groups=defaultdict(list)
        for c in candidates:
            if c['label']==label and c['scenario_id'] not in excluded:
                groups[c['family']].append(c)
        for group in groups.values():group.sort(key=lambda c:(hashlib.sha256(('20261008|'+c['scenario_id']).encode()).hexdigest(),c['scenario_id']))
        picked=[]
        while len(picked)<32:
            progress=False
            for family in sorted(groups):
                while groups[family]:
                    c=groups[family].pop(0)
                    if c['payload_sha256'] in seen:continue
                    seen.add(c['payload_sha256'])
                    picked.append({k:c[k] for k in ('scenario_id','family','label','payload_sha256','near_duplicate_sha256','source_revision')})
                    progress=True;break
                if len(picked)==32:break
            if not progress:raise ValueError('BLOCKED_DATASET_COVERAGE')
        selected.extend(picked)
    body={'protocol':'soc_selection_v1','algorithm':'label32_family_round_robin_sha256_20261008','cases':selected,
          'excluded_ids':sorted(excluded),'duplicate_profile':{'exact_groups':sum(n>1 for n in Counter(c['payload_sha256'] for c in candidates).values()),'near_groups':sum(n>1 for n in near.values())}}
    return {**body,'inventory_sha256':digest(body)}


def select_audit(inventory):
    return [c['scenario_id'] for label in ('malicious','benign') for c in [x for x in inventory['cases'] if x['label']==label][:6]]


def select_demo(inventory, repository):
    cases=inventory['cases'];chosen=[];families=set()
    for c in cases:
        if c['label']=='malicious' and c['family'] not in families:
            chosen.append(c['scenario_id']);families.add(c['family'])
            if len(chosen)==2:break
    chosen.append(next(c['scenario_id'] for c in cases if c['label']=='benign'))
    missing=next((c['scenario_id'] for c in cases if c['scenario_id'] not in chosen and any(not repository.available(c['scenario_id'],r) for r in ('asset','process_tree','related_alerts'))),None)
    if len(chosen)!=3 or missing is None:raise ValueError('BLOCKED_DEMO_COVERAGE')
    return chosen+[missing]


def validate_source_reviews(reviews, *, inventory):
    required=set(select_audit(inventory));approved=set();errors=[]
    cases={c['scenario_id']:c for c in inventory['cases']}
    for r in reviews:
        scenario=r.get('scenario_id');c=cases.get(scenario)
        try:
            stamp=datetime.fromisoformat(r['reviewed_at'].replace('Z','+00:00'))
            if stamp.utcoffset() is None:raise ValueError()
            if not c or not r.get('analyst') or not r.get('rationale') or r.get('source_sha256')!=c['payload_sha256'] or r.get('inventory_sha256')!=inventory['inventory_sha256']:raise ValueError()
            if r.get('decision')!='include' or r.get('label_supportability')!='supported':raise ValueError()
            if scenario in approved:raise ValueError()
            approved.add(scenario)
        except (KeyError,TypeError,ValueError):errors.append('INVALID_SOURCE_REVIEW:'+str(scenario))
    return {'status':'pass' if required<=approved and not errors else 'pending_human_review','reviewed':len(required&approved),'required':12,'missing':sorted(required-approved),'errors':errors}
