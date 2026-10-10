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


def test_e3_reserves_last_turn_for_role_finalization(tmp_path):
    """A model cannot spend every bounded turn on tools and omit final JSON."""
    import duckdb
    from evaluation.r2_cross_domain_v1.data import DatabaseContext
    from evaluation.r2_cross_domain_v1.tools import DatabaseTools
    from vinsoc_text2sql.service import _generate

    snapshot = tmp_path/'shop.duckdb'
    with duckdb.connect(str(snapshot)) as connection:
        connection.execute('CREATE TABLE customers(id INTEGER)')
        connection.execute('INSERT INTO customers VALUES (1), (2)')
    context = DatabaseContext('shop', snapshot, {
        'database_id':'shop', 'schema':[{'name':'customers','columns':[
            {'name':'id','duckdb_type':'INTEGER','sqlite_type':'INTEGER'}]}],
        'primary_keys':{'customers':[]}, 'relationships':[],
        'logical_sha256':'fixture-logical-sha',
    })

    class Transport:
        contract = {'model':'fixture','reasoning_effort':'low',
                    'max_completion_tokens':1000,'service_tier':'default'}
        def __init__(self):
            self.requests = []
        def counters(self):
            count = len(self.requests)
            return {'attempted':count,'received':count,'valid_usage':count,'terminal':False}
        def request(self, payload):
            self.requests.append(payload)
            if 'tools' in payload:
                index = len(self.requests)
                return {'content':None,'tool_calls':[{'id':f'probe-{index}','function':{
                    'name':'database_profiler','arguments':{'table':'customers'}}}]}
            if len(self.requests) == 3:
                return {'content':json.dumps({'tables':['customers'],'columns':[],
                    'relationships':[],'grounded_values':[],'constraints':[]}), 'tool_calls':[]}
            return {'content':json.dumps({'sql':'SELECT COUNT(*) FROM customers'}), 'tool_calls':[]}

    transport = Transport()
    record = _generate(QueryRequest('case','shop','Count customers'), 'E3',
                       DatabaseTools(context), transport, lambda event: None)
    assert record['error_category'] == 'OK'
    assert record['final_sql'] == 'SELECT COUNT(*) FROM customers'
    assert len(transport.requests) == 6
    assert ['tools' in request for request in transport.requests] == [True, True, False, True, True, False]
