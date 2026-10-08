"""Offline, scope-specific gates for new real query-runtime releases."""
from __future__ import annotations

import math

from evaluation.r2_cross_domain_v1.release import canonical_hash, fresh

VERSION = 'query_pipeline_release_v1'
CONTRACTS = {
 'r2': {'model': 'gpt-5-mini-2025-08-07', 'reasoning_effort': 'low',
        'max_completion_tokens': 1000, 'service_tier': 'default', 'max_retries': 0,
        'max_request_bytes': 32768, 'frame_reserve_tokens': 512, 'max_messages': 20},
 'routing': {'model': 'gpt-4.1-mini-2025-04-14', 'temperature': 0,
        'max_completion_tokens': 1000, 'service_tier': 'default', 'max_retries': 0,
        'max_request_bytes': 32768, 'frame_reserve_tokens': 512, 'max_messages': 20},
 'assessment': {'model': 'gpt-4.1-mini-2025-04-14', 'temperature': 0,
        'max_completion_tokens': 1000, 'service_tier': 'default', 'max_retries': 0,
        'max_request_bytes': 65536, 'frame_reserve_tokens': 512, 'max_messages': 20}}


def role_caps(scope, condition):
    if condition not in ('E0', 'E3'):
        raise ValueError('INVALID_CONDITION')
    if scope in ('calibration', 'evaluation'):
        return {'routing': 0, 'r2': (24 if scope == 'calibration' else 96)*7, 'assessment': 0}
    if scope == 'pipeline':
        return {'routing': 32, 'r2': 32*(6 if condition == 'E3' else 1), 'assessment': 32}
    raise ValueError('INVALID_RELEASE_SCOPE')


def number(value):
    return type(value) in (int, float) and math.isfinite(value) and value >= 0


def preflight(scope, condition, *, inventory, identities, account, pricing, budget):
    caps = role_caps(scope, condition)
    planned = {'calibration': 24, 'evaluation': 96, 'pipeline': 32}[scope]
    reasons = []
    ids = [row.get('case_id') for row in inventory if isinstance(row, dict)]
    if (len(inventory) != planned or len(ids) != planned or len(set(ids)) != planned
            or any(not isinstance(i, str) or not i for i in ids)
            or identities.get('data_verified') is not True):
        reasons.append('FULL_LOCKED_INVENTORY_UNVERIFIED')
    if (identities.get('source_verified') is not True or identities.get('ci_verified') is not True
            or identities.get('worker_verified') is not True):
        reasons.append('RUNTIME_CODE_CI_OR_ISOLATION_UNVERIFIED')
    if (not fresh(account.get('confirmed_utc')) or account.get('project_verified') is not True
            or not number(account.get('remaining_allocation_usd'))
            or not number(account.get('known_prior_cost_usd'))
            or account.get('unresolved_cost_unknown') is not False):
        reasons.append('ACCOUNT_OR_RECONCILIATION_UNVERIFIED')
    reserves = {}
    for role, cap in caps.items():
        if not cap:
            continue
        p = pricing.get(CONTRACTS[role]['model'], {})
        if (not fresh(p.get('checked_utc')) or p.get('input_bound_verified') is not True
                or p.get('source_url') not in ('https://openai.com/api/pricing/',
                    'https://developers.openai.com/api/docs/pricing', 'https://platform.openai.com/docs/pricing')
                or any(not number(p.get(k)) or p[k] <= 0 for k in
                       ('input_usd_per_million', 'output_usd_per_million'))):
            reasons.append('PRICING_OR_TOKEN_BOUND_UNVERIFIED_'+role.upper())
            continue
        c = CONTRACTS[role]
        reserves[role] = ((c['max_request_bytes']+c['frame_reserve_tokens'])*p['input_usd_per_million']
                         + c['max_completion_tokens']*p['output_usd_per_million'])/1_000_000
    new_ceiling = sum(caps[r]*reserves[r] for r in reserves) if all(r in reserves for r in caps if caps[r]) else None
    if (budget.get('paid_authorized') is not True or budget.get('authorization_scope') != scope
            or not budget.get('decision_reference') or not number(budget.get('limit_usd'))):
        reasons.append('PAID_RELEASE_NOT_AUTHORIZED')
    if new_ceiling is not None and (not number(budget.get('limit_usd'))
            or not number(account.get('known_prior_cost_usd'))
            or account.get('known_prior_cost_usd', 0)+new_ceiling > budget.get('limit_usd', 0)
            or new_ceiling > account.get('remaining_allocation_usd', 0)):
        reasons.append('FULL_RUN_BUDGET_INSUFFICIENT')
    result = {'version': VERSION, 'scope': scope, 'condition': condition,
              'window_id': 'text2sql-integration-20261008-'+scope,
              'authorized': not reasons, 'status': 'preflight_pass' if not reasons else 'blocked',
              'reasons': reasons, 'attempted': 0, 'received': 0, 'client_created': False,
              'planned': planned, 'case_ids': ids, 'role_caps': caps, 'contracts': CONTRACTS,
              'reserves_usd': reserves, 'new_cost_ceiling_usd': new_ceiling,
              'gate_inputs': {'inventory': inventory, 'identities': identities, 'account': account,
                              'pricing': pricing, 'budget': budget}}
    result['release_sha256'] = canonical_hash(result)
    return result


def validate_release(release):
    if not isinstance(release, dict) or release.get('version') != VERSION:
        raise ValueError('RELEASE_NOT_AUTHORIZED')
    inputs = release['gate_inputs']
    expected = preflight(release['scope'], release['condition'], **inputs)
    if not expected['authorized'] or release != expected:
        raise ValueError('RELEASE_NOT_AUTHORIZED')
    return expected
