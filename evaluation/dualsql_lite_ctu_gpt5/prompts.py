"""Versioned CTU dev prompts; no case answers or frozen-source literals."""

LINKER_PROMPT_VERSION = "dualsql_lite_ctu_gpt5_linker_v2"
GENERATOR_PROMPT_VERSION = "dualsql_lite_ctu_gpt5_generator_v2"

LINKER_INSTRUCTIONS = (
    "You link a network-flow question to the verified database schema. "
    "Use database_profiler and value_search when column meaning or stored values are uncertain. "
    "Return one JSON object with exactly a tables array. Each table entry has only table and "
    "columns; use real names observed in the supplied schema. Do not include values in the "
    "final JSON: the controller attaches verified database values and their evidence IDs. "
    "A literal explicitly quoted in the question is question evidence and needs no database lookup. "
    "Return no SQL or prose."
)

GENERATOR_INSTRUCTIONS = (
    "Write one read-only DuckDB SELECT over the supplied network_flows schema. "
    "Use tools to inspect uncertain stored values when tools are available. "
    "Respect exact filters, Boolean grouping, time boundaries, aggregation, ordering, and limits. "
    "Use only verified database values or literals explicitly supplied in the question. "
    "Return only SQL, without Markdown or commentary."
)
