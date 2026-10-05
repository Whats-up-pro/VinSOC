"""Evaluation-only typed tools; production investigation schemas are unchanged."""

TOOL_VERSION = 'r2_phase2_typed_tools_v4'

TOOL_SCHEMAS = [
    {'type': 'function', 'function': {
        'name': 'database_profiler',
        'description': 'Inspect verified column types and bounded text domains. Completeness is explicit.',
        'parameters': {'type': 'object', 'properties': {'table': {'type': 'string'}},
                       'additionalProperties': False}}},
    {'type': 'function', 'function': {
        'name': 'value_search',
        'description': 'Text retrieval with literal matching modes; numeric/time columns return only schema type hints, not value witnesses.',
        'parameters': {'type': 'object', 'properties': {
            'query': {'type': 'string', 'minLength': 1, 'maxLength': 200},
            'table': {'type': 'string'}, 'column': {'type': 'string'},
            'match_mode': {'type': 'string', 'enum': ['exact', 'prefix', 'contains']},
            'case_sensitive': {'type': 'boolean'}}, 'required': ['query'],
            'additionalProperties': False}}},
    {'type': 'function', 'function': {
        'name': 'sql_probe', 'description': 'Bounded read-only SELECT; computed expressions do not certify catalog literals.',
        'parameters': {'type': 'object', 'properties': {'sql': {'type': 'string', 'maxLength': 4000}},
                       'required': ['sql'], 'additionalProperties': False}}},
]
