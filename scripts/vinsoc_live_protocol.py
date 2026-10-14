"""Bound live requests and append-only allocation reconciliation. No SDK clients."""
from __future__ import annotations

import hashlib
import json
import math
import re
import uuid
from datetime import datetime, timezone

from evaluation.finalization.cloud_window import REPOSITORY
from evaluation.finalization.query_pipeline_contract import role_caps
from evaluation.finalization.query_runtime_validation import ROOT
from evaluation.r2_cross_domain_v1.release import canonical_hash, fresh
from scripts.run_query_remaining_demo_cloud import verified_prior_receipts
from scripts.run_vinsoc_query_acceptance import inventory_for, verify_selected_question

VERSION = 'vinsoc_live_ui_v1'
LIMIT_USD = 3.0
SCOPE_LIMITS_USD = {
    'demo': LIMIT_USD,
    'pipeline': LIMIT_USD,
    'evaluation': LIMIT_USD,
    'calibration': 21.0,
}
BASE_USD = .0815592
REGISTRY_PREFIX = 'vinsoc-ui-allocation-'
WORKFLOW = 'query-live-ui.yml'


def catalog(scope):
    if scope not in ('demo','pipeline','calibration','evaluation'):
        raise ValueError('INVALID_RELEASE_SCOPE')
    if scope == 'demo':
        selection = json.loads((ROOT/'results/evaluation_v1/text2sql_integration_v1/demo_selection.json').read_text(encoding='utf-8'))
        return [verify_selected_question(r['case_id'], r['question'], require_demo=True) for r in selection['cases']]
    return inventory_for(scope)


def create_request(*, scope, case_id, question, head_sha, ci_run_id, live_consent=False):
    value = {'version':VERSION, 'scope':scope, 'case_id':case_id, 'question':question,
             'condition':'E3', 'head_sha':head_sha, 'ci_run_id':int(ci_run_id),
             'execution_id':'liveui-'+uuid.uuid4().hex[:24],
             'limit_usd':SCOPE_LIMITS_USD.get(scope),
             'confirmed_utc':datetime.now(timezone.utc).isoformat(), 'live_consent':live_consent}
    return validate_request(value)


def validate_request(value, *, mode='preflight'):
    keys = {'version','scope','case_id','question','condition','head_sha','ci_run_id',
            'execution_id','limit_usd','confirmed_utc','live_consent'}
    if (not isinstance(value,dict) or set(value) != keys or value['version'] != VERSION
            or value['scope'] not in ('demo','pipeline','calibration','evaluation')
            or value['condition'] not in ('E0','E3')
            or not isinstance(value['head_sha'],str) or not re.fullmatch(r'[a-f0-9]{40}',value['head_sha'])
            or type(value['ci_run_id']) is not int or value['ci_run_id'] <= 0
            or not isinstance(value['execution_id'],str) or not re.fullmatch(r'liveui-[a-f0-9]{24}',value['execution_id'])
            or type(value['limit_usd']) not in (int,float)
            or value['limit_usd'] != SCOPE_LIMITS_USD.get(value['scope'])
            or type(value['live_consent']) is not bool or not fresh(value['confirmed_utc'])):
        raise ValueError('LIVE_REQUEST_INVALID')
    if value['scope'] == 'demo':
        if value['condition'] != 'E3':
            raise ValueError('DEMO_REQUIRES_E3')
        verify_selected_question(value['case_id'], value['question'], require_demo=True)
    elif value['case_id'] is not None or value['question'] is not None:
        raise ValueError('FULL_SCOPE_INVENTORY_REQUIRED')
    if mode not in ('preflight','live'):
        raise ValueError('LIVE_MODE_INVALID')
    if mode == 'live' and value['live_consent'] is not True:
        raise ValueError('LIVE_CONSENT_REQUIRED')
    return value


def base_receipts():
    prior = verified_prior_receipts()
    package = ROOT/'results/evaluation_v1/text2sql_integration_v1/mentor_four_case_demo_20261013'
    manifest = json.loads((package/'artifact_manifest.json').read_text(encoding='utf-8'))
    relative = 'cloud_public/cloud_run.json'
    raw = (package/relative).read_bytes()
    if hashlib.sha256(raw).hexdigest() != manifest['files'][relative]:
        raise ValueError('BASE_ALLOCATION_ARTIFACT_CHANGED')
    report = json.loads(raw)
    if (report.get('attempted') != 23 or report.get('received') != 23
            or report.get('cost_unknown') is not False
            or not math.isclose(report.get('known_usd',-1), BASE_USD, abs_tol=1e-12)):
        raise ValueError('BASE_ALLOCATION_UNVERIFIED')
    prior.append({'workflow_run_id':38369416643, 'known_cost_usd':report['current_run_cost_usd'],
                  'report_sha256':hashlib.sha256(raw).hexdigest()})
    if not math.isclose(sum(r['known_cost_usd'] for r in prior), BASE_USD, abs_tol=1e-12):
        raise ValueError('BASE_ALLOCATION_UNVERIFIED')
    return prior


def reconcile_allocation(entries, *, limit_usd=LIMIT_USD):
    if type(limit_usd) not in (int,float) or limit_usd not in set(SCOPE_LIMITS_USD.values()):
        raise ValueError('ALLOCATION_LIMIT_UNAUTHORIZED')
    prior = base_receipts()
    grouped = {}
    for entry in entries:
        key, phase = entry.get('execution_id'), entry.get('phase')
        if not isinstance(key,str) or not re.fullmatch(r'liveui-[a-f0-9]{24}',key) or phase not in ('begin','end'):
            raise ValueError('ALLOCATION_RECEIPT_INVALID')
        group = grouped.setdefault(key,{})
        if phase in group:
            raise ValueError('DUPLICATE_ALLOCATION_RECEIPT')
        group[phase] = entry
    known = BASE_USD
    ends = []
    for key, pair in grouped.items():
        if set(pair) != {'begin','end'} or pair['end'].get('cost_unknown') is not False:
            raise ValueError('ALLOCATION_EXPOSURE_UNKNOWN')
        begin,end = pair['begin'],pair['end']
        cost = end.get('current_run_cost_usd')
        if (end.get('request_sha256') != begin.get('request_sha256')
                or type(cost) not in (int,float) or not math.isfinite(cost) or cost < 0
                or type(end.get('attempted')) is not int or end['attempted'] != end.get('received')
                or not isinstance(end.get('report_sha256'),str) or not re.fullmatch(r'[a-f0-9]{64}',end['report_sha256'])):
            raise ValueError('ALLOCATION_RECEIPT_INVALID')
        ends.append((begin.get('prior_cost_usd'),key,end))
    for prior_cost,key,end in sorted(ends, key=lambda item:(item[0] if isinstance(item[0],(int,float)) else -1,item[1])):
        if type(prior_cost) not in (int,float) or not math.isclose(prior_cost,known,abs_tol=1e-12):
            raise ValueError('ALLOCATION_CHAIN_MISMATCH')
        known += end['current_run_cost_usd']
        prior.append({'execution_id':key,'known_cost_usd':end['current_run_cost_usd'],
                      'report_sha256':end['report_sha256']})
    if known > limit_usd:
        raise ValueError('ALLOCATION_CAP_EXCEEDED')
    return {'known_usd':known,'remaining_usd':limit_usd-known,'cost_unknown':False,'receipts':prior}


class AllocationRegistry:
    def __init__(self, api, *, sha, run_id):
        self.api,self.sha,self.run_id = api,sha,str(run_id)
        self.prefix = '/repos/'+REPOSITORY

    def entries(self):
        refs = self.api.request('GET',self.prefix+'/git/matching-refs/tags/'+REGISTRY_PREFIX)
        if not isinstance(refs,list) or len(refs) > 2000:
            raise ValueError('REMOTE_ALLOCATION_UNVERIFIED')
        entries = []
        for ref in refs:
            obj = self.api.request('GET',self.prefix+'/git/tags/'+ref['object']['sha'])
            entries.append(json.loads(obj['message']))
        return entries

    def append(self, request, phase, data):
        name = REGISTRY_PREFIX+request['execution_id']+('-end' if phase == 'end' else '')
        payload = {'phase':phase,'execution_id':request['execution_id'],
                   'request_sha256':canonical_hash(request),'run_id':self.run_id,**data}
        from evaluation.finalization.query_cloud import QueryDemoGitHubStore
        store = QueryDemoGitHubStore(self.api,implementation_sha=self.sha,run_id=self.run_id)
        store._tag(name,payload)


def request_limit(request):
    return sum(role_caps(request['scope'],request['condition']).values())
