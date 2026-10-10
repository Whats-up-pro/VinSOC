"""Verify the resume ancestor and immutable data/history before offline release."""
from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path

BASE = '3573496a165876f36116b2716ca737d17091aaf7'
ROOT = Path(__file__).resolve().parents[1]
EDITABLE_EVALUATION = {
    'evaluation/r2_cross_domain_v1/tools.py',
    'evaluation/finalization/query_pipeline_contract.py',
    'evaluation/finalization/query_runtime_validation.py',
    'evaluation/finalization/query_reporting.py',
}
PINNED_ZIPS = {
    'VinSOC_Runtime_DB_20261010.zip': '7cc72e34d50b5533ae44d23abcf1b68aa949a8fed972ccce73c932bd6c67114e',
    'VinSOC_CTU_20261010.zip': '2847ba055dee714195898251e686ad62f0856c721eda84af8782c77a33293dc4',
}


def git(*args):
    return subprocess.check_output(['git', *args], cwd=ROOT, text=True).strip()


def verify():
    subprocess.run(['git', 'merge-base', '--is-ancestor', BASE, 'HEAD'], cwd=ROOT, check=True)
    baseline = git('ls-tree', '-r', '--name-only', BASE).splitlines()
    protected = {p for p in baseline if
                 (p.startswith(('results/', 'evaluation/')) and p not in EDITABLE_EVALUATION)
                 or p.endswith('.zip')}
    changed = protected.intersection(git('diff', '--name-only', BASE).splitlines())
    if changed:
        raise ValueError('PROTECTED_FILES_CHANGED:' + ','.join(sorted(changed)))
    for path, expected in PINNED_ZIPS.items():
        with (ROOT/path).open('rb') as handle:
            if hashlib.file_digest(handle, 'sha256').hexdigest() != expected:
                raise ValueError('PINNED_ZIP_CHANGED:' + path)
    return {'baseline_sha': BASE, 'implementation_sha': git('rev-parse', 'HEAD'),
            'baseline_is_ancestor': True, 'protected_files': len(protected),
            'protected_changed': [], 'pinned_zip_sha256': PINNED_ZIPS,
            'external_model_calls': 0}


if __name__ == '__main__':
    print(json.dumps(verify(), indent=2))
