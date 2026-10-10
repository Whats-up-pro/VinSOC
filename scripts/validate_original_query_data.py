"""Validate original locked data/gold independently of the changed runtime adapter.

This is offline data validation, never model accuracy or worker acceptance.
Historical locks remain immutable; tools.py is bound separately by source hashes.
"""
from __future__ import annotations

import argparse
import json
import shutil
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path

from evaluation.r2_cross_domain_v1.benchmark import ReferenceCase, validate_gold_parity
from evaluation.r2_cross_domain_v1.benchmark_lock import FIELDS, file_hash
from evaluation.r2_cross_domain_v1.data import (
    DatabaseContext,
    inspect_sqlite,
    materialize_archive_member,
    verify_archive_member,
    verify_archive_sha256,
)
from evaluation.r2_cross_domain_v1.semantic_scoring import score_case
from scripts.prepare_r2_cross_domain import acquire_source_archive
from scripts.recover_vinsoc_spider_bundle import baseline, verify_closed_snapshot


def restore_sources(repo, archive=None):
    """Materialize only pinned source members, without DB selection or rebuild."""
    _base, lock, registry, _refs, _inventory, source, receipt, _changed = baseline(repo)
    root = repo / lock['external_source_root']
    root.mkdir(parents=True, exist_ok=True)
    target = root / source['archive_filename']
    if archive is not None and not target.exists():
        verify_archive_sha256(archive, source['archive_sha256'])
        with Path(archive).open('rb') as src, target.open('xb') as dst:
            shutil.copyfileobj(src, dst)
    acquire_source_archive(source, target)
    members = [source['split_member'], source['schema_member']]
    members += [e['source_sqlite_member'] for e in registry['databases'] if e['database_id'] != 'ctu_dev']
    for member in members:
        if materialize_archive_member(target, member, root) != receipt['verified_member_hashes'][member]:
            raise ValueError('ORIGINAL_SOURCE_MEMBER_MISMATCH')
    return {'archive_sha256': source['archive_sha256'], 'verified_members': len(members),
            'external_model_calls': 0, 'databases_rebuilt': 0}


def validate_original_data(repo):
    repo = Path(repo).resolve()
    base, lock, registry, refs, inventory, source, receipt, changed = baseline(repo)
    root = repo / lock['external_source_root']
    archive = root / source['archive_filename']
    verify_archive_sha256(archive, source['archive_sha256'])
    for member in (source['split_member'], source['schema_member']):
        if verify_archive_member(archive, member, root / member) != receipt['verified_member_hashes'][member]:
            raise ValueError('ORIGINAL_SOURCE_MEMBER_MISMATCH')
    contexts = {}
    for entry in registry['databases']:
        context = DatabaseContext.from_manifest(base / 'runtime_registry.json', entry['database_id'])
        verify_closed_snapshot(context.snapshot_path, entry['duckdb_binary_sha256'])
        contexts[context.database_id] = context
        if context.database_id == 'ctu_dev':
            from evaluation.ctu_network_public.contract import validate
            if validate(context.snapshot_path)['logical_snapshot_sha256'] != entry['origin_logical_sha256']:
                raise ValueError('CTU_ORIGIN_IDENTITY_MISMATCH')
        else:
            member = entry['source_sqlite_member']
            if verify_archive_member(archive, member, root / member) != receipt['verified_member_hashes'][member]:
                raise ValueError('ORIGINAL_SOURCE_MEMBER_MISMATCH')
            inspected = inspect_sqlite(root / member)
            for field in ('schema', 'relationships', 'row_counts', 'logical_sha256', 'source_sha256'):
                if inspected[field] != entry[field]:
                    raise ValueError('ORIGINAL_SOURCE_IDENTITY_MISMATCH:' + field)
            keys = {t['name']: [c['name'] for c in t['columns'] if c['primary_key_position']]
                    for t in inspected['schema']}
            if keys != entry['primary_keys']:
                raise ValueError('ORIGINAL_PRIMARY_KEY_MISMATCH')
    replay = []
    for ref in refs:
        audit = json.loads((repo / ref['semantic_audit_path']).read_text())
        if (audit['case_id'] != ref['case_id'] or audit['status'] != 'PASS'
                or len(audit['fixture_identities']) != 2
                or audit['semantic']['semantic_mutants_killed'] < 1
                or audit['semantic']['equivalent_controls_accepted'] < 1):
            raise ValueError('SEMANTIC_GATE_INCOMPLETE')
        if any(not r['parity'] or r['ordering_validation'] != 'PASS' for r in audit['fixture_sqlite_duckdb_parity']):
            raise ValueError('SEMANTIC_GOLD_PARITY_UNVERIFIED')
        context = contexts[ref['database_id']]
        if ref.get('source_gold_sql'):
            parity = validate_gold_parity(ref['source_gold_sql'], root / context.identity['source_sqlite_member'], context, ref['comparator'])
            if not parity['parity'] or parity['adapted_sql'] != ref['gold_sql']:
                raise ValueError('ORIGINAL_GOLD_PARITY_MISMATCH')
        reference = ReferenceCase(**{k: ref[k] for k in FIELDS})
        score = score_case(reference, {'final_sql': ref['gold_sql'], 'error_category': 'OK'},
                           [{'instance_id': 'original_base', 'context': context, 'fixture_only': False}])
        if score['execution_accurate'] is not True:
            raise ValueError('ORIGINAL_BASE_GOLD_FAILED:' + ref['case_id'])
        replay.append({'case_id': ref['case_id'], 'database_id': ref['database_id'],
                       'split': ref['split'], 'gold_execution_verified': True})
    baseline(repo)
    for context in contexts.values():
        verify_closed_snapshot(context.snapshot_path, context.identity['duckdb_binary_sha256'])
    return {'status': 'ALL_120_GOLD_VALIDATED_EXACT_ORIGINAL_BINARIES',
            'scope': 'offline_original_data_and_gold_validation_not_model_score',
            'created_at_utc': datetime.now(UTC).isoformat(),
            'original_databases_verified': len(contexts), 'inventory': inventory,
            'base_gold_replayed': len(replay), 'replayed_by_split': dict(Counter(r['split'] for r in replay)),
            'replayed_by_database': dict(Counter(r['database_id'] for r in replay)),
            'historical_data_files_verified': len(lock['files']),
            'historical_code_lock_pass': not changed, 'historical_runtime_changed_files': changed,
            'changed_runtime_source_sha256': {p: file_hash(repo / p, portable=True) for p in changed},
            'benchmark_lock_sha256': file_hash(base / 'benchmark.lock.json'),
            'registry_sha256': file_hash(base / 'runtime_registry.json'),
            'source_archive_sha256': source['archive_sha256'], 'external_model_calls': 0,
            'new_inference_cost_usd': 0, 'paid_authorized': False,
            'runtime_worker_gate_pass': False, 'gold_replay': replay}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--repo', type=Path, default=Path('.'))
    parser.add_argument('--restore-sources', action='store_true')
    parser.add_argument('--archive', type=Path)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    repo = args.repo.resolve()
    if args.restore_sources:
        restore_sources(repo, args.archive)
    result = validate_original_data(repo)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open('x', encoding='utf-8') as stream:
        json.dump(result, stream, indent=2, sort_keys=True)
        stream.write('\n')
    print(json.dumps({k: v for k, v in result.items() if k != 'gold_replay'}, sort_keys=True))


if __name__ == '__main__':
    main()
