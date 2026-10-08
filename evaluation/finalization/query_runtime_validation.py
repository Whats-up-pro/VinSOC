"""Runtime identity validation, separate from immutable historical code locks."""
from __future__ import annotations

import json
import subprocess
import urllib.request
from pathlib import Path

from evaluation.r2_cross_domain_v1.benchmark_lock import (
    file_hash,
    validate_inventory,
    verify_runtime,
)
from evaluation.r2_cross_domain_v1.data import (
    DatabaseContext,
    verify_archive_member,
    verify_archive_sha256,
)
from vinsoc_text2sql.executor import SqlExecutor

ROOT = Path(__file__).resolve().parents[2]
RUNTIME_PATHS = ('cli/main.py', 'pyproject.toml', 'agent/orchestrator.py', 'agent/network_query_policy.py', 'skills/network_query_skill.py',
 'vinsoc_text2sql/service.py', 'vinsoc_text2sql/executor.py', 'vinsoc_text2sql/_worker.py',
 'vinsoc_text2sql/accounting.py', 'vinsoc_text2sql/provider.py',
 'evaluation/r2_cross_domain_v1/tools.py', 'evaluation/r2_cross_domain_v1/live.py',
 'evaluation/finalization/query_pipeline_contract.py', 'evaluation/finalization/query_runtime_validation.py',
 'evaluation/finalization/query_scoring.py', 'evaluation/finalization/query_reporting.py',
 'scripts/run_vinsoc_query_acceptance.py', 'scripts/review_vinsoc_query_case.py',
 'scripts/render_query_pipeline_report.py', 'schemas/query_investigation_case.json')


def source_hashes():
    return {path: file_hash(ROOT/path, portable=True) for path in RUNTIME_PATHS}


def validate_data():
    """Check locked data/scorer bytes; runtime adapters receive a new identity."""
    base = ROOT/'evaluation/r2_cross_domain_v1'
    lock = json.loads((base/'benchmark.lock.json').read_text())
    for path, expected in lock['files'].items():
        if file_hash(ROOT/path) != expected:
            raise ValueError('LOCKED_DATA_FILE_IDENTITY_MISMATCH')
    for path, expected in lock['source_files'].items():
        if path == 'evaluation/r2_cross_domain_v1/tools.py':
            continue  # Versioned executor injection, bound in new source_hashes().
        if file_hash(ROOT/path, portable=True) != expected:
            raise ValueError('LOCKED_SCORER_OR_PRIMITIVE_CHANGED')
    registry = base/'runtime_registry.json'
    if file_hash(registry) != lock['registry_sha256']:
        raise ValueError('REGISTRY_IDENTITY_MISMATCH')
    contexts = {e['database_id']: DatabaseContext.from_manifest(registry, e['database_id'])
                for e in json.loads(registry.read_text())['databases']}
    source = json.loads((ROOT/lock['source_manifest']).read_text())
    source_root = ROOT/lock['external_source_root']
    archive = source_root/source['archive_filename']
    verify_archive_sha256(archive, source['archive_sha256'])
    verify_archive_member(archive, source['split_member'], source_root/source['split_member'])
    for context in contexts.values():
        if context.database_id == 'ctu_dev':
            from evaluation.ctu_network_public.contract import validate
            observed = validate(context.snapshot_path)
            if observed['logical_snapshot_sha256'] != context.identity['origin_logical_sha256']:
                raise ValueError('CTU_ORIGIN_IDENTITY_MISMATCH')
        else:
            member = context.identity['source_sqlite_member']
            verify_archive_member(archive, member, source_root/member)
    refs = [json.loads(p.read_text()) for p in sorted((base/'benchmarks/references').glob('*/*.json'))]
    validate_inventory(refs)
    runtime = []
    for split in ('calibration', 'evaluation'):
        runtime += json.loads((base/f'benchmarks/{split}_runtime.json').read_text())
    verify_runtime(refs, runtime)
    # Every trusted gold query passes the same new worker before any client.
    executor = SqlExecutor()
    for ref in refs:
        receipt = executor.query(contexts[ref['database_id']], ref['gold_sql'], row_cap=10000, timeout_seconds=10)
        if receipt['truncated']:
            raise ValueError('GOLD_RESULT_LIMIT')
    return contexts, refs


def verify_code_and_ci(identities):
    def git(*args):
        return subprocess.check_output(['git', *args], cwd=ROOT, text=True).strip()
    head = git('rev-parse', 'HEAD')
    if git('branch', '--show-current') != 'master' or git('status', '--porcelain'):
        raise ValueError('GIT_NOT_EXACT_CLEAN_MASTER')
    if identities.get('implementation_sha') != head or identities.get('runtime_source_sha256') != source_hashes():
        raise ValueError('RUNTIME_SOURCE_IDENTITY_MISMATCH')
    run_id = identities.get('ci_run_id')
    if type(run_id) is not int or run_id <= 0:
        raise ValueError('EXACT_SHA_CI_REQUIRED')
    prefix = 'https://api.github.com/repos/Whats-up-pro/VinSOC'
    def fetch(path):
        with urllib.request.urlopen(prefix+path, timeout=30) as response:
            return json.load(response)
    if fetch('/git/ref/heads/master').get('object', {}).get('sha') != head:
        raise ValueError('REMOTE_MASTER_CHANGED')
    run = fetch('/actions/runs/'+str(run_id))
    jobs = fetch('/actions/runs/'+str(run_id)+'/jobs?per_page=100')['jobs']
    if (run.get('head_sha') != head or run.get('conclusion') != 'success'
        or run.get('path') != '.github/workflows/ci.yml'
        or not {'test (3.11)', 'test (3.12)'}.issubset(
            {j['name'] for j in jobs if j.get('conclusion') == 'success'})):
        raise ValueError('EXACT_SHA_CI_REQUIRED')
