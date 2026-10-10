"""Runtime identity validation, separate from immutable historical code locks."""
from __future__ import annotations

import json
import math
import re
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
    paths = set(RUNTIME_PATHS) | {'requirements.txt', '.github/workflows/ci.yml',
        '.github/workflows/query-demo-once.yml', 'scripts/run_query_demo_cloud.py',
        'scripts/run_query_real_data_checks.py', 'scripts/verify_query_preservation.py', 'scripts/prepare_query_budget.py',
        'results/evaluation_v1/text2sql_integration_v1/demo_selection.json'}
    # Bind the full local dependency closure, including lifecycle/evidence and SQL primitives.
    for package in ('agent', 'skills', 'vinsoc_data', 'vinsoc_text2sql', 'telemetry',
                    'evaluation/r2_cross_domain_v1', 'evaluation/finalization'):
        paths.update(p.relative_to(ROOT).as_posix() for p in (ROOT/package).glob('**/*.py'))
    return {path: file_hash(ROOT/path, portable=True) for path in sorted(paths)}


def window_id_for(scope, case_id=None, execution_id=None):
    if scope == 'demo':
        if not isinstance(case_id, str) or not case_id or any(c not in 'abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_-' for c in case_id):
            raise ValueError('FIXED_DEMO_SELECTION_REQUIRED')
        if execution_id is not None and not re.fullmatch(r'[a-z0-9-]{1,32}', execution_id):
            raise ValueError('INVALID_DEMO_EXECUTION_ID')
        return 'text2sql-integration-20261008-demo-'+case_id+('-'+execution_id if execution_id else '')
    if execution_id is not None:
        raise ValueError('INVALID_DEMO_EXECUTION_ID')
    if scope not in ('calibration', 'evaluation', 'pipeline'):
        raise ValueError('INVALID_RELEASE_SCOPE')
    return 'text2sql-integration-20261008-'+scope


def verify_scope_unused(scope, case_id=None, execution_id=None):
    root = Path.home()/'.vinsoc/live-windows'/window_id_for(scope, case_id, execution_id)
    if any((root/name).exists() for name in ('claim.json', 'ledger.json', 'migration.json')):
        raise ValueError('RELEASE_WINDOW_CONSUMED')


def verify_transmission_files(identities):
    if identities.get('runtime_source_sha256') != source_hashes():
        raise ValueError('RUNTIME_SOURCE_IDENTITY_MISMATCH')
    locked = identities.get('transmission_files_sha256')
    if not isinstance(locked, dict) or not locked:
        raise ValueError('TRANSMISSION_DATA_BINDING_REQUIRED')
    for relative, expected in locked.items():
        path = (ROOT/relative).resolve()
        if not path.is_relative_to(ROOT) or file_hash(path) != expected:
            raise ValueError('TRANSMISSION_DATA_IDENTITY_MISMATCH')


def transmission_files(contexts):
    """Recheck original binary/source/benchmark bytes before every transmission."""
    base = ROOT/'evaluation/r2_cross_domain_v1'
    lock = json.loads((base/'benchmark.lock.json').read_text())
    result = dict(lock['files'])
    result.update({c.snapshot_path.relative_to(ROOT).as_posix(): c.identity['duckdb_binary_sha256']
                   for c in contexts.values()})
    source = json.loads((ROOT/lock['source_manifest']).read_text())
    archive = ROOT/lock['external_source_root']/source['archive_filename']
    result[archive.relative_to(ROOT).as_posix()] = source['archive_sha256']
    result['evaluation/r2_cross_domain_v1/runtime_registry.json'] = lock['registry_sha256']
    return result


def verify_canonical_reconciliation(account, *, required_scope=None):
    """An absent ledger is unknown, not an authoritative declaration of zero spend."""
    reference = account.get('reconciliation_reference') or {}
    canonical = Path.home()/'.vinsoc/live-windows'
    path = Path(reference.get('path', '')).resolve()
    if not path.is_relative_to(canonical.resolve()) or not path.is_file():
        raise ValueError('CANONICAL_RECONCILIATION_REQUIRED')
    if file_hash(path) != reference.get('sha256'):
        raise ValueError('CANONICAL_RECONCILIATION_HASH_MISMATCH')
    receipt = json.loads(path.read_text())
    from evaluation.r2_cross_domain_v1.release import fresh
    required_scopes = {'calibration','evaluation','pipeline'} | ({'demo'} if required_scope == 'demo' else set())
    if (not fresh(receipt.get('verified_utc')) or receipt.get('authoritative_host_verified') is not True
            or receipt.get('prior_hosts_sealed') is not True or receipt.get('unknown_exposure_usd') != 0
            or receipt.get('allocation_id') != account.get('allocation_id')
            or receipt.get('known_prior_cost_usd') != account.get('known_prior_cost_usd')
            or receipt.get('remaining_allocation_usd') != account.get('remaining_allocation_usd')
            or set(receipt.get('scope_states', {})) != required_scopes):
        raise ValueError('CANONICAL_RECONCILIATION_UNVERIFIED')
    ledgers = receipt.get('ledger_artifacts')
    if not isinstance(ledgers, list) or not ledgers:
        raise ValueError('CANONICAL_LEDGER_ARTIFACTS_REQUIRED')
    for artifact in ledgers:
        target = (canonical/artifact['path']).resolve()
        if not target.is_relative_to(canonical.resolve()) or file_hash(target) != artifact['sha256']:
            raise ValueError('CANONICAL_LEDGER_IDENTITY_MISMATCH')
    return receipt


def selection_identities():
    from evaluation.r2_cross_domain_v1.release import canonical_hash
    base = ROOT/'evaluation/r2_cross_domain_v1'
    registry = json.loads((base/'runtime_registry.json').read_text())
    return {'runtime_source_sha256': source_hashes(),
            'benchmark_identity': file_hash(base/'benchmark.lock.json'),
            'scorer_identity': file_hash(ROOT/'evaluation/finalization/query_scoring.py', portable=True),
            'snapshot_identities': {r['database_id']: r['logical_sha256'] for r in registry['databases']}}


def build_selection_lock(records, *, identities, artifacts):
    from evaluation.r2_cross_domain_v1.release import canonical_hash
    inventory = json.loads((ROOT/'evaluation/r2_cross_domain_v1/benchmarks/calibration_runtime.json').read_text())
    metadata = {r['case_id']: r for r in inventory}
    indexed = {}
    response_ids = set()
    for record in records:
        key = record.get('condition'), record.get('case_id')
        if key[0] not in ('E0', 'E3') or key[1] not in metadata or key in indexed:
            raise ValueError('CALIBRATION_RECORD_IDENTITY')
        indexed[key] = record
    if len(indexed) != 48:
        return {'version': 'query_selection_v2', 'status': 'pending', 'calibration_complete': False,
                'selected_condition': None, 'received_records': len(indexed), 'required_records': 48}
    required = selection_identities()
    if any(identities.get(k) != v for k, v in required.items()) or not identities.get('implementation_sha'):
        raise ValueError('CALIBRATION_PRODUCER_IDENTITY_MISMATCH')
    totals = {}
    for condition in ('E0', 'E3'):
        correct, cost, calls, latency = 0, 0., 0, 0.
        for row in inventory:
            record = indexed[(condition, row['case_id'])]
            generation = record.get('generation', record)
            events = record.get('cost_events', [])
            if (record.get('identities') != identities or generation.get('evidence_kind') != 'openai_live'
                    or generation.get('question') != row['question']
                    or generation.get('snapshot_identity') != required['snapshot_identities'][row['database_id']]
                    or type(record.get('score', {}).get('execution_accurate')) is not bool
                    or not events or record.get('cost_unknown') is not False
                    or len(events) != generation.get('attempted_calls')
                    or generation.get('response_count') != len(events)
                    or type(generation.get('wall_seconds')) not in (int, float)
                    or not math.isfinite(generation['wall_seconds']) or generation['wall_seconds'] < 0):
                raise ValueError('CALIBRATION_INCOMPLETE_SCORING_OR_USAGE')
            for e in events:
                u = e.get('usage') or {}
                if (e.get('case_id') != row['case_id'] or e.get('condition') != condition or e.get('role') != 'r2'
                        or e.get('received') is not True or not e.get('request_id') or not e.get('request_sha256')
                        or not e.get('response_id') or e['response_id'] in response_ids
                        or e.get('actual_model') != 'gpt-5-mini-2025-08-07'
                        or any(type(u.get(k)) is not int or u[k] < 0 for k in ('input_tokens', 'output_tokens', 'cached_tokens'))
                        or type(e.get('cost_usd')) not in (int, float) or not math.isfinite(e['cost_usd']) or e['cost_usd'] < 0):
                    raise ValueError('CALIBRATION_INCOMPLETE_SCORING_OR_USAGE')
                response_ids.add(e['response_id'])
                cost += e['cost_usd']
            correct += int(record['score']['execution_accurate'])
            calls += len(events)
            latency += generation['wall_seconds']
        totals[condition] = {'correct': correct, 'n': 24, 'cost_usd': cost, 'calls': calls, 'latency_seconds': latency}
    if not artifacts:
        raise ValueError('CALIBRATION_ARTIFACT_BINDING_REQUIRED')
    selected = min(totals, key=lambda c: (-totals[c]['correct'], totals[c]['cost_usd'], totals[c]['calls'], totals[c]['latency_seconds'], c))
    result = {'version': 'query_selection_v2', 'status': 'verified', 'calibration_complete': True,
              'selected_condition': selected, 'received_records': 48, 'required_records': 48,
              'identities': identities, 'artifacts': artifacts, 'records_sha256': canonical_hash(records),
              'totals': totals, 'rule': 'EX,cost,calls,latency,E0'}
    result['selection_sha256'] = canonical_hash(result)
    return result


def load_calibration_artifacts(directory, artifacts):
    directory = Path(directory).resolve()
    records = []
    for artifact in artifacts:
        target = (directory/artifact['path']).resolve()
        if not target.is_relative_to(directory) or file_hash(target) != artifact['sha256']:
            raise ValueError('CALIBRATION_ARTIFACT_HASH_MISMATCH')
        loaded = json.loads(target.read_text(encoding='utf-8'))
        if not isinstance(loaded.get('case_records'), list):
            raise ValueError('CALIBRATION_RECORD_ARTIFACT_REQUIRED')
        records.extend(loaded['case_records'])
    return records


def verify_selection_lock(path, *, identities):
    from evaluation.r2_cross_domain_v1.release import canonical_hash
    path = Path(path)
    if not path.is_file():
        raise ValueError('CALIBRATION_SELECTION_LOCK_REQUIRED')
    lock = json.loads(path.read_text(encoding='utf-8'))
    if lock.get('version') != 'query_selection_v2' or lock.get('calibration_complete') is not True:
        raise ValueError('CALIBRATION_SELECTION_LOCK_REQUIRED')
    unsigned = {k: v for k, v in lock.items() if k != 'selection_sha256'}
    if canonical_hash(unsigned) != lock.get('selection_sha256') or identities.get('selection_sha256') != lock['selection_sha256']:
        raise ValueError('CALIBRATION_SELECTION_HASH_MISMATCH')
    records = load_calibration_artifacts(path.parent, lock.get('artifacts', []))
    expected = build_selection_lock(records, identities=lock['identities'], artifacts=lock['artifacts'])
    if expected != lock:
        raise ValueError('CALIBRATION_SELECTION_RECOMPUTE_MISMATCH')
    # Producer commit exists and its source bytes match the calibrated runtime.
    producer = lock['identities']['implementation_sha']
    for source, expected_hash in lock['identities']['runtime_source_sha256'].items():
        import hashlib
        content = subprocess.check_output(['git', 'show', producer+':'+source], cwd=ROOT)
        if hashlib.sha256(content.replace(b'\r\n', b'\n')).hexdigest() != expected_hash:
            raise ValueError('CALIBRATION_PRODUCER_IDENTITY_MISMATCH')
    return lock


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
        or not {'test (3.11)', 'test (3.12)', 'query-real-data (3.11)', 'query-real-data (3.12)'}.issubset(
            {j['name'] for j in jobs if j.get('conclusion') == 'success'})):
        raise ValueError('EXACT_SHA_CI_REQUIRED')
