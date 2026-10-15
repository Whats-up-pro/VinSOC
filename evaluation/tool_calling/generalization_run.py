"""Gates for the added R1 split; historical scorer and prompt stay unchanged."""
from __future__ import annotations

import json
from dataclasses import asdict
from decimal import Decimal, InvalidOperation
from pathlib import Path

from evaluation.tool_calling.generalization import verify_generalization_lock
from evaluation.tool_calling.provenance import canonical_sha256, _git_identity

ROOT = Path(__file__).resolve().parents[2]
SPLIT = ROOT / 'evaluation/tool_calling/benchmarks/generalization_v1'
MODEL = 'gpt-4.1-mini-2025-04-14'


def validate_generalization_run_gate(split_dir, lock_path, authorization,
                                     requested_model, budget_limit_usd, git_identity):
    """Pure fail-closed check. No provider, SDK, network or write side effect."""
    verified = verify_generalization_lock(Path(split_dir), Path(lock_path))
    reasons = list(verified.errors)
    auth = authorization if isinstance(authorization, dict) else {}
    lock = {}
    if verified.passed:
        lock = json.loads(Path(lock_path).read_text(encoding='utf-8'))
    sha = git_identity.get('commit_sha')
    if (not isinstance(sha, str) or len(sha) != 40
            or git_identity.get('branch') != 'master'
            or git_identity.get('working_tree_clean') is not True
            or git_identity.get('remote_master_sha') != sha
            or git_identity.get('ci_sha') != sha
            or git_identity.get('ci_success') is not True):
        reasons.append('EXACT_CLEAN_MASTER_AND_CI_REQUIRED')
    if (auth.get('scope') != 'r1-generalization-v1' or auth.get('approved') is not True
            or not auth.get('authorized_by') or not auth.get('reference')
            or auth.get('implementation_sha') != sha
            or auth.get('split_sha256') != lock.get('split_sha256')
            or auth.get('model') != requested_model or requested_model != MODEL
            or auth.get('maximum_requests') != 120
            or auth.get('maximum_output_tokens') != 1000
            or auth.get('max_retries') != 0):
        reasons.append('EXPLICIT_SPLIT_MODEL_AUTHORIZATION_REQUIRED')
    try:
        budget, limit, ceiling = (Decimal(str(value)) for value in
            (budget_limit_usd, auth.get('limit_usd'), auth.get('cost_ceiling_usd')))
        if not all(x.is_finite() and x > 0 for x in (budget, limit, ceiling)):
            raise ValueError('nonfinite budget')
        if ceiling > budget or budget > limit:
            raise ValueError('insufficient budget')
    except (InvalidOperation, ValueError, TypeError):
        reasons.append('VERIFIED_FINITE_BUDGET_REQUIRED')
    return {'format': 'r1_generalization_run_gate_v1', 'passed': not reasons,
            'reasons': reasons, 'case_count': verified.case_count,
            'lock_verification': asdict(verified), 'git': dict(git_identity),
            'generalization_lock_sha256': verified.lock_sha256,
            'split_sha256': lock.get('split_sha256'),
            'candidate_sha256': lock.get('candidate_sha256'),
            'review_file_sha256': lock.get('review_file_sha256'),
            'reviewer_ids': lock.get('reviewer_ids'),
            'authorization_sha256': canonical_sha256(auth),
            'provider_created': False, 'model_calls': 0, 'cost_usd': 0}


def collect_git_identity(authorization, api=None):
    """Bind exact master and required CI independently of authorization contents."""
    identity = _git_identity()
    if api is None:
        return identity
    prefix = '/repos/Whats-up-pro/VinSOC'
    head = api.request('GET', prefix + '/git/ref/heads/master')
    ci_id = authorization.get('ci_run_id')
    if type(ci_id) is not int or ci_id <= 0:
        return identity
    run = api.request('GET', prefix + '/actions/runs/' + str(ci_id))
    jobs = api.request('GET', prefix + '/actions/runs/' + str(ci_id) + '/jobs?per_page=100')
    required = {'test (3.11)', 'test (3.12)', 'query-real-data (3.11)', 'query-real-data (3.12)'}
    identity.update(remote_master_sha=head.get('object', {}).get('sha'),
                    ci_sha=run.get('head_sha'),
                    ci_success=(run.get('path') == '.github/workflows/ci.yml'
                        and run.get('conclusion') == 'success'
                        and required.issubset({j['name'] for j in jobs['jobs']
                                              if j.get('conclusion') == 'success'})))
    return identity


def cli_generalization(args):
    """Route the added split before either legacy runner can be created."""
    if not getattr(args, 'authorization', None) or not getattr(args, 'budget_usd', None):
        raise ValueError('GENERALIZATION_AUTHORIZATION_AND_BUDGET_REQUIRED')
    if (getattr(args, 'mode', 'decision') != 'decision' or getattr(args, 'cases', None)
            or getattr(args, 'provider', 'openai') != 'openai'
            or getattr(args, 'temperature', 0.0) != 0.0):
        raise ValueError('GENERALIZATION_FULL_DECISION_ONLY_REQUIRED')
    from evaluation.finalization.cloud_window import GitHubAPI, atomic_json
    import os
    authorization = json.loads(Path(args.authorization).read_text(encoding='utf-8'))
    api = GitHubAPI(os.environ['GITHUB_TOKEN']) if os.environ.get('GITHUB_TOKEN') else None
    receipt = validate_generalization_run_gate(
        SPLIT, SPLIT / 'GENERALIZATION.lock', authorization, args.model,
        args.budget_usd, collect_git_identity(authorization, api))
    if receipt['passed'] and api is not None:
        if api.request('GET', '/repos/Whats-up-pro/VinSOC/git/ref/tags/vinsoc-r1-generalization-v1-once') is not None:
            receipt['passed'] = False
            receipt['reasons'].append('R1_WINDOW_ALREADY_CONSUMED')
    if getattr(args, 'output', None):
        atomic_json(args.output, receipt)
    if not receipt['passed']:
        raise ValueError('GENERALIZATION_GATE_BLOCKED:' + ','.join(receipt['reasons']))
    if getattr(args, 'command', None) == 'preflight':
        print(json.dumps(receipt, ensure_ascii=False))
        return receipt
    from evaluation.tool_calling.generalization_live import run_guarded
    return run_guarded(authorization, receipt, api, Path(args.output_dir))
