"""Restore the user-delivered real DB bundle, preserving existing data."""
import importlib
from pathlib import Path

import pytest

from scripts.export_vinsoc_db_bundle import FILES, digest

ROOT = Path(__file__).resolve().parents[1]
BUNDLE = ROOT / 'VinSOC_Runtime_DB_20261010.zip'
BUNDLE_SHA256 = '7cc72e34d50b5533ae44d23abcf1b68aa949a8fed972ccce73c932bd6c67114e'


def restore(destination, expected=BUNDLE_SHA256):
    assert (ROOT / 'scripts/restore_query_data_bundle.py').is_file(), 'Approved bundle restore is missing'
    module = importlib.import_module('scripts.restore_query_data_bundle')
    return module.restore_bundle(BUNDLE, expected_sha256=expected, destination=destination)


def test_restores_all_13_exact_original_databases(tmp_path):
    receipt = restore(tmp_path)
    assert receipt['database_count'] == 13
    assert receipt['model_calls'] == 0
    for entry in FILES:
        assert digest(tmp_path / entry['path']) == entry['sha256']


def test_repeat_restore_preserves_identical_existing_files(tmp_path):
    restore(tmp_path)
    before = {e['path']: (tmp_path / e['path']).stat().st_mtime_ns for e in FILES}
    receipt = restore(tmp_path)
    assert receipt['restored_count'] == 0
    assert before == {e['path']: (tmp_path / e['path']).stat().st_mtime_ns for e in FILES}


def test_wrong_archive_hash_writes_nothing(tmp_path):
    with pytest.raises(ValueError, match='BUNDLE_CHECKSUM_MISMATCH'):
        restore(tmp_path, '0' * 64)
    assert list(tmp_path.iterdir()) == []


def test_different_existing_database_is_preserved_before_any_restore(tmp_path):
    path = tmp_path / FILES[-1]['path']
    path.parent.mkdir(parents=True)
    path.write_bytes(b'existing data must survive')
    with pytest.raises(ValueError, match='EXISTING_DATABASE_MISMATCH'):
        restore(tmp_path)
    assert path.read_bytes() == b'existing data must survive'
    assert not (tmp_path / FILES[0]['path']).exists()


def test_existing_wal_blocks_before_any_restore(tmp_path):
    path = tmp_path / (FILES[-1]['path'] + '.wal')
    path.parent.mkdir(parents=True)
    path.write_bytes(b'active writer')
    with pytest.raises(ValueError, match='WAL_PRESENT'):
        restore(tmp_path)
    assert path.read_bytes() == b'active writer'
    assert not (tmp_path / FILES[0]['path']).exists()


def test_symlinked_parent_cannot_escape_destination(tmp_path):
    destination = tmp_path / 'repo'
    outside = tmp_path / 'outside'
    destination.mkdir()
    outside.mkdir()
    (destination / 'data').symlink_to(outside, target_is_directory=True)
    with pytest.raises(ValueError, match='UNSAFE_DESTINATION'):
        restore(destination)
    assert list(outside.iterdir()) == []


def test_second_ctu_archive_contains_same_locked_runtime_snapshot():
    assert (ROOT / 'scripts/restore_query_data_bundle.py').is_file()
    module = importlib.import_module('scripts.restore_query_data_bundle')
    assert hasattr(module, 'verify_ctu_bundle'), 'Second archive verifier missing'
    receipt = module.verify_ctu_bundle(ROOT / 'VinSOC_CTU_20261010.zip')
    assert receipt['snapshot_sha256'] == FILES[-1]['sha256']
    assert receipt['network_e2e_v1_compatible'] is False
