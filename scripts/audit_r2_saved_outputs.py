"""Offline replay receipts for saved predictions. No provider/client creation."""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
from datetime import datetime, timezone
from pathlib import Path

from evaluation.r2_phase2.scoring import SCORE_FIELDS, score_prediction, unscored_prediction
from evaluation.r2_phase2.safety import Phase2Snapshot
from evaluation.text_to_sql import SQLBenchmarkCase


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _load(path: Path):
    return json.loads(path.read_text(encoding='utf-8'))


def _write_new(path: Path, value: dict):
    with path.open('x', encoding='utf-8', newline='\n') as stream:
        json.dump(value, stream, ensure_ascii=False, default=str, indent=2, sort_keys=True)
        stream.write('\n')


def _current_source_identity() -> dict:
    paths = ['evaluation/r2_phase2/scoring.py', 'evaluation/r2_phase2/safety.py',
             'scripts/audit_r2_saved_outputs.py', 'scripts/test_case006_integer_fix.py',
             'evaluation/text_to_sql.py']
    try:
        git_sha = subprocess.check_output(['git', 'rev-parse', 'HEAD'], text=True).strip()
    except (OSError, subprocess.SubprocessError):
        git_sha = None
    return {'implementation_sha': git_sha, 'source_portable_sha256': {
        p: hashlib.sha256(Path(p).read_bytes().replace(b'\r\n', b'\n').replace(b'\r', b'\n')).hexdigest()
        for p in paths}, 'scope': 'current offline replay only; never historical provenance backfill'}


def _archived_identity_matches(identity: dict, verified: dict, snapshot: Path, manifest: Path, cases_dir: Path) -> bool:
    return (identity.get('snapshot_sha256') == sha256(snapshot)
            and identity.get('logical_snapshot_sha256') == verified['logical_snapshot_sha256']
            and identity.get('manifest_sha256') == sha256(manifest)
            and identity.get('case_file_sha256') == {p.name: sha256(p) for p in sorted(cases_dir.glob('*.json'))})


def audit_saved_outputs(input_dir: Path, cases_dir: Path, snapshot_path: Path, output_dir: Path) -> dict:
    """Write exclusive replay outputs; leave input/snapshot/gold bytes untouched."""
    input_dir, cases_dir, snapshot_path, output_dir = map(Path, (input_dir, cases_dir, snapshot_path, output_dir))
    if not input_dir.exists():
        raise FileNotFoundError('INPUT_MISSING')
    if output_dir.exists():
        raise FileExistsError('OUTPUT_EXISTS')
    single = input_dir.is_file()
    source_root = input_dir if not single else input_dir.parent
    if not single and output_dir.resolve().is_relative_to(source_root.resolve()):
        raise ValueError('OUTPUT_MUST_BE_SEPARATE')
    source_files = [input_dir] if single else sorted(p for p in input_dir.iterdir() if p.is_file())
    before = {p.as_posix(): sha256(p) for p in source_files}
    report_path = source_root / 'report.json'
    archived_report = _load(report_path) if not single and report_path.is_file() else {}
    records = []
    for path in source_files:
        if path.suffix != '.json' or (not single and path.name == 'report.json'):
            continue
        data = _load(path)
        if not isinstance(data, dict) or not isinstance(data.get('case_id'), str):
            raise ValueError('PREDICTION_RECORD_INVALID')
        records.append(data)
    if not records:
        raise ValueError('NO_PREDICTIONS')
    ids = [record['case_id'] for record in records]
    if any(re.fullmatch(r'[A-Za-z0-9_-]+', case_id) is None for case_id in ids):
        raise ValueError('UNSAFE_CASE_ID')
    if len(set(ids)) != len(ids):
        raise ValueError('DUPLICATE_CASE_ID')
    if 'case_results' in archived_report:
        archived_cases = archived_report['case_results']
        if (not isinstance(archived_cases, list) or len(archived_cases) != len(records)
                or any(not isinstance(r, dict) or 'case_id' not in r for r in archived_cases)
                or {r['case_id']: r for r in archived_cases} != {r['case_id']: r for r in records}):
            raise ValueError('SOURCE_CASE_REPORT_MISMATCH')

    from evaluation.ctu_network_public.contract import CASES, MANIFEST, validate
    frozen_root = Path('evaluation/ctu_network_frozen')
    frozen = cases_dir.resolve() == (frozen_root / 'frozen').resolve()
    registered_dev = cases_dir.resolve() == CASES.resolve()
    scope = ('consumed_frozen_offline_diagnostic' if frozen else
             'single_saved_prediction_diagnostic' if single else 'offline_saved_prediction_replay')
    validation_errors = []
    verified = None
    archived_identity = archived_report.get('identity') or {}
    # Missing frozen run identity must not trigger snapshot/gold inspection.
    if frozen:
        lock = _load(frozen_root / 'VERSION.lock')
        expected_ids = lock['case_ids']
        # File/lock comparisons precede the validator, which queries gold and snapshot facts.
        try:
            files_match = (isinstance(archived_identity, dict) and snapshot_path.is_file()
                           and _archived_identity_matches(archived_identity, lock, snapshot_path,
                                                          frozen_root / 'dataset_manifest.json', cases_dir))
        except (OSError, KeyError, TypeError):
            files_match = False
        if not files_match:
            validation_errors.append('SNAPSHOT_IDENTITY_UNVERIFIED')
        else:
            from evaluation.ctu_network_frozen.contract import validate_frozen_contract
            try:
                verified = validate_frozen_contract(snapshot_path)
                if not _archived_identity_matches(archived_identity, verified, snapshot_path,
                                                 frozen_root / 'dataset_manifest.json', cases_dir):
                    validation_errors.append('SNAPSHOT_IDENTITY_UNVERIFIED')
            except Exception:
                validation_errors.append('SNAPSHOT_IDENTITY_UNVERIFIED')
    else:
        raw_cases = {p.name: _load(p) for p in sorted(cases_dir.glob('*.json'))}
        cases = {data['case_id']: SQLBenchmarkCase.from_dict(data) for data in raw_cases.values()}
        if len(cases) != len(raw_cases):
            raise ValueError('DUPLICATE_BENCHMARK_ID')
        expected_ids = sorted(cases)
        if not snapshot_path.is_file():
            validation_errors.append('SNAPSHOT_MISSING')
        elif registered_dev:
            try:
                verified = validate(snapshot_path, cases_dir=cases_dir)
            except Exception:
                validation_errors.append('SNAPSHOT_IDENTITY_UNVERIFIED')
            if verified and archived_identity and not _archived_identity_matches(
                    archived_identity, verified, snapshot_path, MANIFEST, cases_dir):
                validation_errors.append('SNAPSHOT_IDENTITY_UNVERIFIED')
        if single:
            expected_ids = ids
    if any(case_id not in expected_ids for case_id in ids):
        raise ValueError('CASE_SET_MISMATCH')
    missing = sorted(set(expected_ids) - set(ids))
    if missing:
        validation_errors.append('CASE_SET_INCOMPLETE')
    reason = next((e for e in validation_errors if e != 'CASE_SET_INCOMPLETE'), None)
    if frozen and reason is None:
        cases = {data['case_id']: SQLBenchmarkCase.from_dict(data)
                 for data in (_load(p) for p in sorted(cases_dir.glob('*.json')))}
    reader = Phase2Snapshot(snapshot_path) if reason is None else None
    results = [unscored_prediction(record, reason) if reason else
               score_prediction(cases[record['case_id']], record, reader) for record in records]
    validation_errors.extend(r['scoring_error_category'] for r in results if not r['validation_passed'])
    validation_errors = sorted(set(validation_errors))
    scored = [r for r in results if r['scoring_status'] == 'scored']
    complete = len(scored) == len(expected_ids) and not validation_errors
    after = {p.as_posix(): sha256(p) for p in source_files}
    if before != after:
        raise ValueError('INPUT_BYTES_CHANGED')
    counts = {field: sum(r[field] for r in scored) if complete else None for field in SCORE_FIELDS}
    report = {'version': 'r2_saved_output_audit_v1', 'scope': scope,
              'protocol_eligible': False, 'is_new_model_run': False, 'model_calls': 0, 'new_cost_usd': 0,
              'created_utc': datetime.now(timezone.utc).isoformat(), 'replay_implementation': _current_source_identity(),
              'source_report_path': report_path.as_posix() if archived_report else None,
              'archived_run_identity': archived_identity or None,
              'archived_snapshot_identity_verified': bool(verified and archived_identity and reason is None),
              'current_snapshot_validation': verified, 'snapshot_path': snapshot_path.as_posix(),
              'snapshot_raw_sha256': sha256(snapshot_path) if verified else None,
              'case_count': len(expected_ids), 'scored_case_count': len(scored),
              'unscored_case_count': len(expected_ids) - len(scored), 'missing_case_ids': missing,
              'validation_passed': complete, 'validation_errors': validation_errors,
              'status': 'scored' if complete else 'unscored' if not scored else 'partial',
              'counts': counts, 'rates': {field: n / len(expected_ids) if n is not None else None for field, n in counts.items()},
              'source_hashes_before': before, 'source_hashes_after': after, 'case_results': results}
    output_dir.mkdir(parents=True, exist_ok=False)
    for record in results:
        _write_new(output_dir / (record['case_id'] + '.json'), record)
    _write_new(output_dir / 'report.json', report)
    return report


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input', type=Path, required=True)
    parser.add_argument('--cases-dir', type=Path, default=Path('evaluation/ctu_network_public/dev'))
    parser.add_argument('--snapshot', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        report = audit_saved_outputs(args.input, args.cases_dir, args.snapshot, args.output)
    except FileNotFoundError:
        print(json.dumps({'error': 'INPUT_MISSING', 'model_calls': 0}))
        return 2
    except (ValueError, FileExistsError) as error:
        allowed = {'OUTPUT_EXISTS', 'OUTPUT_MUST_BE_SEPARATE', 'NO_PREDICTIONS', 'DUPLICATE_CASE_ID',
                   'DUPLICATE_BENCHMARK_ID', 'CASE_SET_MISMATCH', 'PREDICTION_RECORD_INVALID', 'INPUT_BYTES_CHANGED',
                   'UNSAFE_CASE_ID', 'SOURCE_CASE_REPORT_MISMATCH'}
        print(json.dumps({'error': str(error) if str(error) in allowed else 'VALIDATION_FAILED', 'model_calls': 0}))
        return 2
    print(json.dumps({key: report[key] for key in ('status', 'scope', 'counts', 'validation_errors', 'model_calls', 'new_cost_usd')}))
    return 0 if report['validation_passed'] else 2


if __name__ == '__main__':
    raise SystemExit(main())
