"""Restore exact original Text-to-SQL snapshots; never rebuild or overwrite data.

python -m scripts.restore_query_data_bundle --repo . --bundle VinSOC_Runtime_DB_20261010.zip
"""
from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import stat
import sys
import zipfile
from pathlib import Path

if __package__ in (None, ''):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.export_vinsoc_db_bundle import FILES, SOURCES, digest

RUNTIME_BUNDLE_SHA256 = '7cc72e34d50b5533ae44d23abcf1b68aa949a8fed972ccce73c932bd6c67114e'
CTU_BUNDLE_SHA256 = '2847ba055dee714195898251e686ad62f0856c721eda84af8782c77a33293dc4'


def verify_ctu_bundle(bundle: Path) -> dict:
    if digest(bundle) != CTU_BUNDLE_SHA256:
        raise ValueError('CTU_BUNDLE_CHECKSUM_MISMATCH')
    with zipfile.ZipFile(bundle) as archive:
        if archive.namelist() != ['ctu_dev.duckdb']:
            raise ValueError('CTU_BUNDLE_MEMBER_SET_MISMATCH')
        with archive.open('ctu_dev.duckdb') as stream:
            observed = hashlib.file_digest(stream, 'sha256').hexdigest()
        if observed != FILES[-1]['sha256']:
            raise ValueError('CTU_SNAPSHOT_CHECKSUM_MISMATCH')
    return {'bundle_sha256': CTU_BUNDLE_SHA256, 'snapshot_sha256': observed,
            'same_snapshot_as_runtime_bundle': True, 'network_e2e_v1_compatible': False}


def restore_bundle(bundle: Path, *, expected_sha256: str, destination: Path) -> dict:
    """Validate the entire archive and all destinations before writing any DB."""
    bundle, root = Path(bundle), Path(destination).resolve(strict=True)
    if digest(bundle) != expected_sha256:
        raise ValueError('BUNDLE_CHECKSUM_MISMATCH')
    expected_manifest = {
        'schema_version': 1, 'scope': 'r2_cross_domain_v1_locked_runtime_13',
        'lock_baseline_commit': '791184cbc0346c3c6331dab63b603facfeb4005a',
        'files': FILES, 'source_attribution': SOURCES, 'model_calls': 0,
    }
    with zipfile.ZipFile(bundle) as archive:
        infos = archive.infolist()
        allowed = {e['path'] for e in FILES} | {'bundle_manifest.json'}
        if len(infos) != len(allowed) or {i.filename for i in infos} != allowed:
            raise ValueError('BUNDLE_MEMBER_SET_MISMATCH')
        if any(i.is_dir() or stat.S_ISLNK(i.external_attr >> 16) for i in infos):
            raise ValueError('UNSAFE_BUNDLE_MEMBER')
        if json.loads(archive.read('bundle_manifest.json')) != expected_manifest:
            raise ValueError('BUNDLE_MANIFEST_MISMATCH')
        targets = []
        for entry in FILES:
            with archive.open(entry['path']) as stream:
                if hashlib.file_digest(stream, 'sha256').hexdigest() != entry['sha256']:
                    raise ValueError('BUNDLE_DATABASE_CHECKSUM_MISMATCH')
            target = root / entry['path']
            if target.resolve() != target or not target.resolve().is_relative_to(root):
                raise ValueError('UNSAFE_DESTINATION')
            wal = Path(str(target) + '.wal')
            if wal.exists() or wal.is_symlink():
                raise ValueError('WAL_PRESENT_CLOSE_WRITER_FIRST')
            if target.exists() and (not target.is_file() or digest(target) != entry['sha256']):
                raise ValueError('EXISTING_DATABASE_MISMATCH')
            targets.append((entry, target))
        restored = 0
        for entry, target in targets:
            if not target.exists():
                target.parent.mkdir(parents=True, exist_ok=True)
                with archive.open(entry['path']) as source, target.open('xb') as output:
                    shutil.copyfileobj(source, output)
                restored += 1
            if digest(target) != entry['sha256'] or Path(str(target) + '.wal').exists():
                raise ValueError('RESTORED_DATABASE_CHANGED')
    return {'status': 'ALL_13_EXACT_ORIGINAL_BINARIES_RESTORED',
            'bundle_sha256': expected_sha256, 'database_count': 13,
            'restored_count': restored, 'preserved_count': 13 - restored,
            'model_calls': 0, 'files': FILES}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--repo', required=True, type=Path)
    parser.add_argument('--bundle', required=True, type=Path)
    parser.add_argument('--expected-sha256', default=RUNTIME_BUNDLE_SHA256)
    args = parser.parse_args()
    receipt = restore_bundle(args.bundle, expected_sha256=args.expected_sha256, destination=args.repo)
    print(json.dumps(receipt, indent=2))


if __name__ == '__main__':
    main()
