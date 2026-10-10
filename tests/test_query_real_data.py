"""Required checks on exact original DBs and archived model SQL, without new calls."""
import hashlib
import importlib
import json
import os
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
REQUIRED = os.environ.get('VINSOC_QUERY_REAL_DATA_REQUIRED') == '1'
pytestmark = pytest.mark.skipif(not REQUIRED, reason='Required real-data CI job runs these acceptance checks')


def test_all_120_original_gold_queries_and_sources_validate():
    assert (ROOT / 'scripts/validate_original_query_data.py').is_file(), 'Original-data validator missing'
    module = importlib.import_module('scripts.validate_original_query_data')
    receipt = module.validate_original_data(ROOT)
    assert receipt['base_gold_replayed'] == 120
    assert receipt['replayed_by_split'] == {'calibration': 24, 'evaluation': 96}
    assert receipt['original_databases_verified'] == 13
    assert receipt['external_model_calls'] == 0
    assert receipt['historical_code_lock_pass'] is False


def test_saved_live_sql_runs_in_isolated_worker_on_locked_db():
    from evaluation.r2_cross_domain_v1.data import DatabaseContext
    from vinsoc_text2sql.executor import SqlExecutor
    artifact = ROOT / 'results/evaluation_v1/ctu_network_public/r2_phase2_live/20261001_3f9d72d/suite/report.json'
    assert hashlib.sha256(artifact.read_bytes()).hexdigest() == 'cb14da306ba0cd4bc92f0d239b037da976ef2867cde61e57395fa5f570dc039a'
    saved = next(c for c in json.loads(artifact.read_text())['case_results'] if c['case_id'] == 'ctu_sql_001')
    sql = saved['final_sql']
    assert hashlib.sha256(sql.encode()).hexdigest() == 'e6f8f0dfd72e80a5464a21b0546d9b92c67869da2e09b85869cd926cff76ce42'
    context = DatabaseContext.from_manifest(ROOT / 'evaluation/r2_cross_domain_v1/runtime_registry.json', 'ctu_dev')
    before = hashlib.sha256(context.snapshot_path.read_bytes()).hexdigest()
    result = SqlExecutor().query(context, sql, row_cap=10000, timeout_seconds=10)
    assert result['status'] == 'OK'
    assert result['truncated'] is False
    import duckdb
    with duckdb.connect(str(context.snapshot_path), read_only=True) as conn:
        cursor = conn.execute(sql)
        assert result['rows'] == [list(r) for r in cursor.fetchall()]
        assert result['columns'] == [{'name': c[0], 'type': str(c[1])} for c in cursor.description]
    identity = {k: result[k] for k in ('columns', 'rows', 'truncated')}
    encoded = json.dumps(identity, ensure_ascii=False, sort_keys=True, separators=(',', ':'), allow_nan=False)
    assert result['result_sha256'] == hashlib.sha256(encoded.encode()).hexdigest()
    assert hashlib.sha256(context.snapshot_path.read_bytes()).hexdigest() == before


def test_all_120_gold_queries_use_same_runtime_worker():
    from evaluation.finalization.query_runtime_validation import validate_data
    contexts, refs = validate_data()
    assert len(contexts) == 13
    assert len(refs) == 120
