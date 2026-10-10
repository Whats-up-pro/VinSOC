import json
from pathlib import Path

import pytest


def test_selection_stays_pending_without_48_real_records():
    from evaluation.finalization.query_runtime_validation import build_selection_lock
    result = build_selection_lock([], identities={}, artifacts=[])
    assert result['status'] == 'pending'
    assert result['calibration_complete'] is False
    assert result['selected_condition'] is None
    assert result['received_records'] == 0


def test_historical_records_cannot_be_relabelled_calibration(tmp_path):
    from evaluation.finalization.query_runtime_validation import build_selection_lock
    real = json.loads(Path('results/evaluation_v1/ctu_network_public/r2_phase2_live/20261001_3f9d72d/suite/report.json').read_text())
    with pytest.raises(ValueError, match='CALIBRATION_RECORD_IDENTITY'):
        build_selection_lock(real['case_results'], identities={}, artifacts=[])


def test_missing_or_self_declared_selection_is_rejected(tmp_path):
    from evaluation.finalization.query_runtime_validation import verify_selection_lock
    with pytest.raises(ValueError, match='CALIBRATION_SELECTION_LOCK_REQUIRED'):
        verify_selection_lock(tmp_path/'missing.json', identities={})
    path = tmp_path/'invalid.json'
    path.write_text(json.dumps({'calibration_complete': True, 'selected_condition': 'E3'}))
    with pytest.raises(ValueError):
        verify_selection_lock(path, identities={})


def test_altered_real_artifact_is_rejected_by_binding(tmp_path):
    import hashlib
    from evaluation.finalization.query_runtime_validation import load_calibration_artifacts
    source = Path('results/evaluation_v1/text2sql_integration_v1/original_data_20261010/ci_verification.json')
    path = tmp_path/'real-receipt.json'
    path.write_bytes(source.read_bytes()+b' ')
    binding = [{'path': path.name, 'sha256': hashlib.sha256(source.read_bytes()).hexdigest()}]
    with pytest.raises(ValueError, match='CALIBRATION_ARTIFACT_HASH_MISMATCH'):
        load_calibration_artifacts(tmp_path, binding)
