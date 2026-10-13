"""Real saved traces stay truthful when displayed or reviewed."""
import importlib
import importlib.util
import json
import shutil
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
PACKAGE = Path('results/evaluation_v1/text2sql_integration_v1/mentor_four_case_demo_20261013')
AVG = 'ctu_cross_bce6d3679ade4cd6'
UDP = 'ctu_cross_66b8e92a76c3359b'
NULL = 'ctu_cross_3f659571f998adb0'


def module():
    assert importlib.util.find_spec('scripts.vinsoc_demo_data') is not None, 'Authentic demo adapter is missing'
    return importlib.import_module('scripts.vinsoc_demo_data')


def test_four_cases_keep_actual_success_failed_and_partial_states():
    data = module().load_demo(ROOT)
    assert len(data['cases']) == 4
    cases = {c['case_id']: c for c in data['cases']}
    assert cases[AVG]['status'] == 'awaiting_human'
    assert cases[AVG]['view']['typed_result']['rows'] == [['TCP']]
    assert cases[NULL]['metrics']['integrated_ex'] is False
    assert cases[UDP]['status'] == 'incomplete'
    assert cases[UDP]['metrics']['integrated_ex'] is None
    assert cases[UDP]['view']['typed_result']['row_count'] == 9780
    assert data['summary']['new_run_received'] == 23


def test_invalid_assessment_is_kept_separate_from_accepted_assessment():
    case = next(c for c in module().load_demo(ROOT)['cases'] if c['case_id'] == NULL)
    assert not case['view']['assessment']
    assert case['raw_assessment']
    assert case['metrics']['factual_verification'] is False


def test_missing_package_keeps_all_fixed_ids_visible(tmp_path):
    data = module().load_demo(ROOT, package=tmp_path / 'absent')
    assert len(data['cases']) == 4
    assert all(c['status'] == 'missing' and c['record'] is None for c in data['cases'])


def test_changed_case_cannot_keep_a_success_badge(tmp_path):
    package = tmp_path / 'package'
    shutil.copytree(ROOT / PACKAGE, package)
    case_file = package / f'cloud_public/{AVG}/live/E3_{AVG}.json'
    case_file.write_bytes(case_file.read_bytes() + b' ')
    case = next(c for c in module().load_demo(ROOT, package=package)['cases'] if c['case_id'] == AVG)
    assert case['status'] == 'integrity_failed'
    assert case['record'] is None


def test_review_requires_human_fields_and_utc(tmp_path):
    data = module().load_demo(ROOT)
    case = next(c for c in data['cases'] if c['case_id'] == AVG)
    with pytest.raises(ValueError, match='HUMAN_FIELDS_REQUIRED'):
        module().save_review(case, tmp_path, analyst='', decision='approved', rationale='', utc='')
    with pytest.raises(ValueError, match='ACTUAL_UTC_REQUIRED'):
        module().save_review(case, tmp_path, analyst='test-only', decision='approved', rationale='validation fixture', utc='2026-10-13T12:00:00')
    assert not list(tmp_path.glob('*.json'))


def test_failed_case_cannot_be_approved(tmp_path):
    case = next(c for c in module().load_demo(ROOT)['cases'] if c['case_id'] == NULL)
    with pytest.raises(ValueError, match='TECHNICAL_APPROVAL_FORBIDDEN'):
        module().save_review(case, tmp_path, analyst='test-only', decision='approved', rationale='validation fixture', utc='2026-10-13T12:00:00Z')
    assert not list(tmp_path.glob('*.json'))


def test_review_hash_mismatch_remains_visible_and_unapproved(tmp_path):
    (tmp_path / 'mismatch.json').write_text(json.dumps({'scope':'actual_human_review', 'case_id':AVG,
        'case_receipt_sha256':'wrong', 'analyst':'test-only', 'decision':'approved',
        'rationale':'negative validation fixture', 'utc':'2026-10-13T12:00:00Z'}), encoding='utf-8')
    case = next(c for c in module().load_demo(ROOT, review_dir=tmp_path)['cases'] if c['case_id'] == AVG)
    assert case['review_status'] == 'hash_or_identity_mismatch'
    assert case['status'] == 'awaiting_human'
    assert case['metrics']['human_approved_completion'] is False


def test_duplicate_case_checkpoint_cannot_hide_behind_a_valid_report(tmp_path):
    package = tmp_path / 'package'
    shutil.copytree(ROOT / PACKAGE, package)
    live = package / f'cloud_public/{AVG}/live'
    shutil.copyfile(live / f'E3_{AVG}.json', live / f'E0_{AVG}.json')
    case = next(c for c in module().load_demo(ROOT, package=package)['cases'] if c['case_id'] == AVG)
    assert case['status'] == 'integrity_failed'
    assert 'DUPLICATE' in case['error']


def test_non_object_review_does_not_crash_or_approve(tmp_path):
    (tmp_path / 'not-a-review.json').write_text('[]', encoding='utf-8')
    data = module().load_demo(ROOT, review_dir=tmp_path)
    assert data['errors']
    assert not any(c['metrics'].get('human_approved_completion') for c in data['cases'])


def test_routing_covers_main_branches_and_real_error():
    result = module().load_routing(ROOT)
    cases = {c['case_id']: c for c in result['cases']}
    assert {'case_001','case_002','case_003','case_004','case_005','case_007','case_022'} <= cases.keys()
    assert cases['case_002']['result']['trajectory_success'] is False
    assert cases['case_022']['result']['predicted_calls'] == []


def test_soc_keeps_synthetic_origin_and_insufficient_evidence():
    data = module().load_soc(ROOT)
    assert data['receipt']['data_origin'] == 'synthetic'
    assert data['receipt']['responses_received'] == 3
    assert data['receipt']['verdict'] == 'insufficient_evidence'
