"""Offline scoring fixtures: DuckDB is real; provider creation is forbidden."""
from __future__ import annotations

import copy
import importlib
import importlib.util
import json
import runpy
import sys
from pathlib import Path

import duckdb
import pytest

from evaluation.r2_phase2.safety import Phase2Snapshot
from evaluation.text_to_sql import SQLBenchmarkCase


def scoring():
    assert importlib.util.find_spec('evaluation.r2_phase2.scoring') is not None, 'offline scoring helper missing'
    return importlib.import_module('evaluation.r2_phase2.scoring')


def audit_module():
    assert importlib.util.find_spec('scripts.audit_r2_saved_outputs') is not None, 'offline audit entrypoint missing'
    return importlib.import_module('scripts.audit_r2_saved_outputs')


@pytest.fixture
def sample(tmp_path):
    snapshot = tmp_path / 'synthetic.duckdb'
    with duckdb.connect(str(snapshot)) as conn:
        conn.execute('CREATE TABLE network_flows (amount INTEGER)')
        conn.execute('INSERT INTO network_flows VALUES (2), (3), (7)')
    cases = tmp_path / 'cases'
    cases.mkdir()
    raw = {'case_id': 'synthetic_total', 'question': 'How many fixture rows?',
           'database_snapshot': str(snapshot), 'gold_sql': ['SELECT COUNT(*) FROM network_flows'],
           'category': 'aggregation', 'difficulty': 'basic', 'result_comparator': 'scalar'}
    (cases / 'synthetic_total.json').write_text(json.dumps(raw), encoding='utf-8')
    return SQLBenchmarkCase.from_dict(raw), snapshot, cases


def test_pipeline_ok_wrong_result_is_not_execution_accuracy(sample):
    case, path, _ = sample
    record = {'case_id': case.case_id, 'error_category': 'OK', 'final_sql': 'SELECT 1'}
    original = copy.deepcopy(record)
    result = scoring().score_prediction(case, record, Phase2Snapshot(path))
    assert result['syntax_valid'] is True and result['execution_success'] is True
    assert result['execution_accurate'] is False
    assert result['pipeline_error_category'] == 'OK'
    assert result['scoring_error_category'] == 'RESULT_MISMATCH'
    assert record == original


def test_correct_sql_passes_real_evaluator(sample):
    case, path, _ = sample
    result = scoring().score_prediction(case, {'case_id': case.case_id, 'error_category': 'OK',
                                              'final_sql': 'SELECT COUNT(*) AS n FROM network_flows;'}, Phase2Snapshot(path))
    assert result['execution_accurate'] is True and result['execution_success'] is True
    assert result['syntax_valid'] is True and result['safety_rejected'] is False
    assert result['scoring_status'] == 'scored'


def test_no_final_sql_preserves_tool_limit(sample):
    case, path, _ = sample
    result = scoring().score_prediction(case, {'case_id': case.case_id, 'error_category': 'TOOL_LIMIT',
                                              'final_sql': None}, Phase2Snapshot(path))
    assert result['error_category'] == result['pipeline_error_category'] == 'TOOL_LIMIT'
    assert result['scoring_error_category'] == 'NO_FINAL_SQL'
    assert result['execution_accurate'] is False and result['scoring_status'] == 'scored'


def test_missing_snapshot_is_unscored_not_zero_or_pass(sample):
    case, path, _ = sample
    result = scoring().score_prediction(case, {'case_id': case.case_id, 'error_category': 'OK',
                                              'final_sql': 'SELECT 3'}, Phase2Snapshot(path.with_name('missing.duckdb')))
    assert result['scoring_status'] == 'unscored' and result['validation_passed'] is False
    assert result['scoring_error_category'] == 'SNAPSHOT_MISSING'
    assert all(result[name] is None for name in ('syntax_valid', 'execution_success', 'execution_accurate', 'safety_rejected'))


def test_replay_has_zero_provider_calls_and_preserves_source_bytes(sample, tmp_path, monkeypatch):
    import openai
    import agent.provider
    constructor_calls = []
    def forbidden(*args, **kwargs):
        constructor_calls.append(1)
        raise AssertionError('offline audit tried creating provider')
    monkeypatch.setattr(openai, 'OpenAI', forbidden)
    monkeypatch.setattr(openai, 'AsyncOpenAI', forbidden)
    monkeypatch.setattr(agent.provider, 'create_provider', forbidden)
    case, snapshot, cases = sample
    inputs = tmp_path / 'saved'
    inputs.mkdir()
    raw = b'{"case_id":"synthetic_total","error_category":"OK","final_sql":"SELECT 1"}\r\n'
    source = inputs / 'synthetic_total.json'
    source.write_bytes(raw)
    report = audit_module().audit_saved_outputs(inputs, cases, snapshot, tmp_path / 'replay')
    assert source.read_bytes() == raw
    assert report['model_calls'] == 0 and report['new_cost_usd'] == 0
    assert report['source_hashes_before'] == report['source_hashes_after']
    assert report['counts']['execution_accurate'] == 0
    assert constructor_calls == []


def test_broken_gold_is_validation_failure_even_without_final_sql(sample):
    case, snapshot, _ = sample
    broken = SQLBenchmarkCase(case.case_id, case.question, case.database_snapshot,
                              ('SELECT absent_column FROM network_flows',), case.category, case.difficulty, 'scalar')
    result = scoring().score_prediction(broken, {'case_id': case.case_id, 'error_category': 'TOOL_LIMIT',
                                               'final_sql': None}, Phase2Snapshot(snapshot))
    assert result['scoring_status'] == 'unscored'
    assert result['scoring_error_category'] == 'GOLD_VALIDATION_FAILED'
    assert result['execution_accurate'] is None
    assert result['pipeline_error_category'] == 'TOOL_LIMIT'


def test_unverified_consumed_frozen_outputs_remain_unscored(tmp_path):
    # This fixture exercises the verified-vs-missing identity boundary, without loading holdout gold.
    inputs = tmp_path / 'saved'
    inputs.mkdir()
    (inputs / 'frozen_sql_001.json').write_text(json.dumps({'case_id': 'frozen_sql_001',
        'error_category': 'OK', 'final_sql': 'SELECT 1'}), encoding='utf-8')
    # Registered frozen split must require its run snapshot identity before any SQL query.
    report = audit_module().audit_saved_outputs(inputs, Path('evaluation/ctu_network_frozen/frozen'),
                                               tmp_path / 'missing.duckdb', tmp_path / 'replay')
    assert report['scope'] == 'consumed_frozen_offline_diagnostic'
    assert report['protocol_eligible'] is False
    assert report['counts']['execution_accurate'] is None
    assert 'SNAPSHOT_IDENTITY_UNVERIFIED' in report['validation_errors']


def test_case006_wrapper_missing_input_never_creates_provider(tmp_path, monkeypatch, capsys):
    import openai
    def forbidden(*args, **kwargs):
        pytest.fail('case006 wrapper created a live client instead of reporting INPUT_MISSING')
    monkeypatch.setattr(openai, 'OpenAI', forbidden)
    monkeypatch.setattr(sys, 'argv', ['test_case006_integer_fix', '--input', str(tmp_path / 'missing.json'),
                                    '--snapshot', str(tmp_path / 'missing.duckdb'), '--output', str(tmp_path / 'out')])
    with pytest.raises(SystemExit) as exited:
        runpy.run_path('scripts/test_case006_integer_fix.py', run_name='__main__')
    assert exited.value.code != 0
    assert 'INPUT_MISSING' in capsys.readouterr().out


def test_incomplete_frozen_identity_never_queries_existing_snapshot(tmp_path, monkeypatch):
    import evaluation.ctu_network_frozen.contract as frozen_contract
    def forbidden(*args, **kwargs):
        pytest.fail('incomplete archived identity triggered frozen snapshot/gold queries')
    monkeypatch.setattr(frozen_contract, 'validate_frozen_contract', forbidden)
    inputs = tmp_path / 'saved'
    inputs.mkdir()
    (inputs / 'frozen_sql_001.json').write_text(json.dumps({'case_id': 'frozen_sql_001',
        'error_category': 'OK', 'final_sql': 'SELECT 1'}), encoding='utf-8')
    (inputs / 'report.json').write_text(json.dumps({'identity': {'git_sha': 'historical'}}), encoding='utf-8')
    snapshot = tmp_path / 'existing.duckdb'
    snapshot.write_bytes(b'synthetic placeholder, must never be queried')
    report = audit_module().audit_saved_outputs(inputs, Path('evaluation/ctu_network_frozen/frozen'),
                                               snapshot, tmp_path / 'replay')
    assert report['counts']['execution_accurate'] is None
    assert 'SNAPSHOT_IDENTITY_UNVERIFIED' in report['validation_errors']


def test_source_report_cannot_be_spliced_with_another_prediction(sample, tmp_path):
    case, snapshot, cases = sample
    inputs = tmp_path / 'saved'
    inputs.mkdir()
    original = {'case_id': case.case_id, 'error_category': 'OK', 'final_sql': 'SELECT 1'}
    different = {**original, 'final_sql': 'SELECT COUNT(*) FROM network_flows'}
    (inputs / (case.case_id + '.json')).write_text(json.dumps(different), encoding='utf-8')
    (inputs / 'report.json').write_text(json.dumps({'case_results': [original]}), encoding='utf-8')
    with pytest.raises(ValueError, match='SOURCE_CASE_REPORT_MISMATCH'):
        audit_module().audit_saved_outputs(inputs, cases, snapshot, tmp_path / 'replay')
    assert not (tmp_path / 'replay').exists()


def test_single_saved_prediction_wrapper_scores_wrong_result(sample, tmp_path, monkeypatch, capsys):
    case, snapshot, _ = sample
    source = tmp_path / 'saved.json'
    source.write_text(json.dumps({'case_id': case.case_id, 'error_category': 'OK', 'final_sql': 'SELECT 1'}), encoding='utf-8')
    monkeypatch.setattr(sys, 'argv', ['case006', '--input', str(source), '--cases-dir', str(tmp_path / 'cases'),
                                    '--snapshot', str(snapshot), '--output', str(tmp_path / 'out')])
    with pytest.raises(SystemExit) as exited:
        runpy.run_path('scripts/test_case006_integer_fix.py', run_name='__main__')
    assert exited.value.code == 0
    report = json.loads((tmp_path / 'out/report.json').read_text(encoding='utf-8'))
    assert report['scope'] == 'single_saved_prediction_diagnostic'
    assert report['case_count'] == 1 and report['counts']['execution_accurate'] == 0
    assert report['case_results'][0]['scoring_error_category'] == 'RESULT_MISMATCH'


def test_case_identifier_cannot_escape_output_directory(sample, tmp_path):
    _, snapshot, cases = sample
    data = json.loads((cases / 'synthetic_total.json').read_text(encoding='utf-8'))
    data['case_id'] = '../escape'
    (cases / 'synthetic_total.json').write_text(json.dumps(data), encoding='utf-8')
    inputs = tmp_path / 'saved'
    inputs.mkdir()
    (inputs / 'prediction.json').write_text(json.dumps({'case_id': '../escape', 'error_category': 'OK',
                                                      'final_sql': 'SELECT 3'}), encoding='utf-8')
    with pytest.raises(ValueError, match='UNSAFE_CASE_ID'):
        audit_module().audit_saved_outputs(inputs, cases, snapshot, tmp_path / 'replay')
    assert not (tmp_path / 'escape.json').exists()
