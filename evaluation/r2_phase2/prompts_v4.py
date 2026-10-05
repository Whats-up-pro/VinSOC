"""Typed/operator contract instructions, without benchmark mappings or example SQL."""

LINKER_PROMPT_VERSION = 'r2_phase2_typed_linker_v4'
GENERATOR_PROMPT_VERSION = 'r2_phase2_typed_generator_v4'

LINKER_INSTRUCTIONS = (
    'Map the question to the verified database schema. Inspect column types with database_profiler. '
    'Select only columns needed for projection, filtering, grouping and ordering. '
    'Source identifiers and their aliases are controller-owned metadata. '
    'Numeric and timestamp constraints are question literals, not catalog strings: '
    'confirm the column type and proceed; do not search for or probe their existence. '
    'A typed_constraint_not_catalog_value response is a type hint, never a stored-value witness. '
    'For text, use value_search with explicit match_mode (exact, prefix or contains) and case_sensitive '
    'matching the question. A literal percent, underscore or backslash is escaped in the returned predicate. '
    'Samples and truncated results are not complete domains. '
    'Return exactly one JSON object with tables and grounded_values arrays. '
    'Each table is {table: string, columns: [string]}. '
    'Each grounded value is {table: string, column: string, value: string, evidence_id: string (optional)} '
    'backed by observed text catalog evidence. Do not submit numeric/time values in grounded_values. '
    'No SQL or prose.'
)

GENERATOR_INSTRUCTIONS = (
    'Write one read-only DuckDB SELECT for the question; return SQL only. '
    'Use verified schema types, controller source metadata, observed text values and grouping predicates. '
    'Keep question numeric/time constraints separate from stored catalog values; do not probe their existence. '
    'Use numeric or timestamp expressions with the appropriate type, never fabricated catalog strings. '
    'Honor the question source filters, exact/prefix/contains semantics and case sensitivity. '
    'When using an observed grouping predicate preserve its operator, pattern and escape. '
    'Do not treat truncated catalog samples as the whole domain. '
    'Respect requested DISTINCT, inclusive/exclusive time bounds, Boolean parentheses, grouping, '
    'top-k quantity, tie-breaking and output order. A matching result on one snapshot is not universal correctness. '
    'Do not invent stored values, consult gold, write data, access external relations, or return commentary.'
)
