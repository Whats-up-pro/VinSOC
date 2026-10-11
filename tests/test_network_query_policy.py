"""Query routing contract checks using locked questions; no model substitutes."""
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from agent.evidence import Evidence
from agent.network_query_policy import NetworkQueryPolicy
from agent.tools import get_tool_schemas

QUESTION = json.loads(Path('evaluation/r2_cross_domain_v1/benchmarks/evaluation_runtime.json').read_text())[0]['question']


def test_default_profile_unchanged():
    assert {x['function']['name'] for x in get_tool_schemas()} == {
        'cti_enrichment', 'network_investigation', 'endpoint_investigation'}
    schema = NetworkQueryPolicy(QUESTION).tool_schemas()[0]['function']
    assert schema['strict'] is True
    assert set(schema['parameters']['properties']) == {'question'}


@pytest.mark.parametrize('arguments', [
    {'question': QUESTION, 'sql': 'SELECT 1'},
    {'question': QUESTION.replace(' ', '  ', 1)},
    {'question': QUESTION, 'database_id': 'ctu_dev'},
    {'question': None},
])
def test_scope_and_literal_preservation(arguments):
    with pytest.raises(ValueError):
        NetworkQueryPolicy(QUESTION).validate_tool_call({'name': 'network_query', 'arguments': arguments})


def test_original_question_accepted_without_normalization():
    assert NetworkQueryPolicy(QUESTION).validate_tool_call(
        {'name': 'network_query', 'arguments': {'question': QUESTION}}) == {'question': QUESTION}


RUN3_FIXTURE = Path('tests/fixtures/query_run_38041048027_assessment.json')


def _paid_run3_fixture():
    return json.loads(RUN3_FIXTURE.read_text(encoding='utf-8'))


def _query_result_store(*, rows=None):
    fixture = _paid_run3_fixture()
    saved = fixture['query_result_evidence']
    data = dict(saved['data'])
    if rows is not None:
        data['rows'] = rows
        data['row_count'] = len(rows)
    result = Evidence(
        evidence_id=saved['evidence_id'], source_tool=saved['source_tool'],
        type=saved['type'], data=data, collected_at=saved['collected_at'],
        evidence_class=saved['evidence_class'], related_evidence_ids=saved['related_evidence_ids'],
    )
    saved_execution = fixture['query_execution_evidence']
    execution = Evidence(
        evidence_id=saved_execution['evidence_id'], source_tool=saved_execution['source_tool'],
        type=saved_execution['type'], data=saved_execution['data'],
        collected_at=saved_execution['collected_at'], evidence_class=saved_execution['evidence_class'],
        related_evidence_ids=saved_execution['related_evidence_ids'],
    )
    return SimpleNamespace(get_all_evidence=lambda: [execution, result])


def _run3_assessment():
    return _paid_run3_fixture()['assessment_response']


def test_single_row_query_columns_are_exact_typed_observations():
    """Regression for paid run 38041048027: model output must match stored SQL cells."""
    fixture = _paid_run3_fixture()
    assert fixture['workflow_run_id'] == 38041048027
    assert fixture['artifact_sha256'] == '0fea94b507c15e66099d73e813624e2150975384fb711622d17a83c258d3f3ac'
    assessment = NetworkQueryPolicy(QUESTION).parse_final_response(
        json.dumps(_run3_assessment()), _query_result_store())
    assert assessment.observations == _run3_assessment()['observations']
    assert assessment.limitations == [_run3_assessment()['limitations']]
    assert assessment.raw_json == _run3_assessment()


def test_query_column_observation_is_rejected_when_multiple_rows_make_it_ambiguous():
    with pytest.raises(ValueError, match='UNKNOWN_OR_DUPLICATE_QUERY_OBSERVATION'):
        NetworkQueryPolicy(QUESTION).parse_final_response(
            json.dumps(_run3_assessment()), _query_result_store(rows=[[1529, 1210], [1, 2]]))


def test_query_assessment_prompt_specifies_machine_checked_shapes():
    prompt = NetworkQueryPolicy(QUESTION).system_prompt()
    assert 'limitations must be an array of strings' in prompt
    assert 'single-row query result' in prompt
