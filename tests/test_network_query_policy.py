"""Query routing contract checks using locked questions; no model substitutes."""
import json
from pathlib import Path

import pytest

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
