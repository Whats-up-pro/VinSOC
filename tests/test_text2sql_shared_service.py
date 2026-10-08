"""Deterministic boundary checks; no invented model responses or datasets."""
import json
from dataclasses import fields
from pathlib import Path

import pytest

from evaluation.r2_cross_domain_v1.data import DatabaseContext
from evaluation.r2_cross_domain_v1.safety import SafetyError
from vinsoc_text2sql.executor import ExecutorError, SqlExecutor
from vinsoc_text2sql.service import QueryRequest, TextToSQLService

REGISTRY = Path('evaluation/r2_cross_domain_v1/runtime_registry.json')


def catalog_context():
    # Published metadata only, deliberately no claim that missing bytes verified.
    entry = json.loads(REGISTRY.read_text())['databases'][-1]
    return DatabaseContext(entry['database_id'], REGISTRY.parent/entry['snapshot_path'], entry)


def test_request_has_no_evaluator_fields():
    assert [f.name for f in fields(QueryRequest)] == ['request_id', 'database_id', 'question']
    with pytest.raises(TypeError):
        QueryRequest('x', 'ctu_dev', 'question', gold_sql='SELECT 1')


def test_wrong_database_rejected_before_transport_or_database():
    request = QueryRequest('x', 'other', 'question')
    with pytest.raises(ValueError, match='INVALID_RUNTIME_CONTRACT'):
        TextToSQLService().generate(request, condition='E0', context=catalog_context(),
                                   transport=None, telemetry_sink=lambda record: None)


@pytest.mark.parametrize('sql', [
    'DROP TABLE network_flows', 'SELECT 1; SELECT 2',
    "SELECT * FROM read_csv_auto('/etc/passwd')",
    'SELECT * FROM dataset_not_in_scope',
])
def test_unsafe_sql_rejected_before_worker(sql):
    with pytest.raises(SafetyError):
        SqlExecutor().query(catalog_context(), sql, row_cap=20, timeout_seconds=2)


def test_missing_snapshot_fails_closed(tmp_path):
    catalog = catalog_context()
    missing = DatabaseContext(catalog.database_id, tmp_path/'absent.duckdb', catalog.identity)
    with pytest.raises(ExecutorError, match='REAL_DATA_REQUIRED'):
        SqlExecutor().query(missing, 'SELECT COUNT(*) FROM network_flows',
                            row_cap=20, timeout_seconds=2)


def test_worker_startup_timeout_is_infrastructure_not_model_failure():
    assert SqlExecutor.timeout_category('') == 'WORKER_ISOLATION_OR_STARTUP_FAILED'
