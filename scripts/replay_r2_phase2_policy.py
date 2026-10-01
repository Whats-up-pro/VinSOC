"""Offline-only replay of saved predictions, never re-generation or rescoring in place."""
from __future__ import annotations
import argparse
import hashlib
import json
from dataclasses import asdict
from pathlib import Path

from evaluation.ctu_network_public.contract import CASES, MANIFEST, validate, portable_text_sha256
from evaluation.dualsql_lite_ctu_gpt5_v2.experiment import load_cases
from evaluation.r2_phase2.safety import Phase2Snapshot, POLICY_IDENTITY
from evaluation.text_to_sql import evaluate_sql_case

SOURCE = Path('results/evaluation_v1/ctu_network_public/dualsql_v2_remediation_live/20260930_90acf451/suite')
SNAPSHOT = Path('data/ctu_network_public/snapshots/ctu_dev.duckdb')


def replay(output: Path, source: Path = SOURCE, snapshot: Path = SNAPSHOT):
    if output.exists():
        raise FileExistsError('OUTPUT_EXISTS')
    verified = validate(snapshot, manifest_path=MANIFEST)
    paths = sorted(source.glob('*.json')) + [source / 'partial.jsonl']
    before = {str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}
    records = []
    adapter = Phase2Snapshot(snapshot)
    for case in load_cases(CASES):
        original = json.loads((source / f'{case.case_id}.json').read_text(encoding='utf-8'))
        scored = evaluate_sql_case(case, original.get('final_sql') or '', adapter)
        records.append({'case_id': case.case_id, 'prediction': original.get('final_sql'),
                        'original_error_category': original['error_category'],
                        'original_flags': {k: original[k] for k in
                            ('syntax_valid', 'execution_success', 'execution_accurate', 'safety_rejected')},
                        'replay': {k: v for k, v in asdict(scored).items() if k != 'error'}})
    after = {str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}
    if before != after:
        raise RuntimeError('SOURCE_MUTATED')
    result = {'scope': 'offline_prediction_replay_not_live_benchmark', 'api_calls': 0,
              'policy_identity': POLICY_IDENTITY,
              'policy_sha256': portable_text_sha256(Path('evaluation/r2_phase2/safety.py')),
              'source_hashes_before': before, 'source_hashes_after': after,
              'snapshot': verified, 'records': records,
              'counts': {field: sum(r['replay'][field] for r in records) for field in
                         ('syntax_valid', 'execution_success', 'execution_accurate', 'safety_rejected')}}
    output.mkdir(parents=True, exist_ok=False)
    (output / 'report.json').write_text(json.dumps(result, indent=2, sort_keys=True) + '\n', encoding='utf-8')
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(replay(args.output)['counts']))
