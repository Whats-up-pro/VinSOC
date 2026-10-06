"""Generic public-schema prompts; no CTU identifiers or question-specific rules."""
LINKER = """Link the analyst question to the supplied public database schema.
Use qualified table/column names and declared relationship edges for joins.
Use the database tools for stored string values; cite controller-issued evidence_id.
Small complete domain_witnesses may be cited directly even when matches is empty.
Thresholds and LIMIT quantities are typed constraints, not stored catalog values.
An incomplete/truncated domain cannot prove absence. Never invent witnesses.
Finish with one JSON object: tables (names), columns ({table,column}), relationships
(declared edges), grounded_values ({evidence_id,operator}); use = or !=,
constraints (typed predicates).
Numeric predicates use {table,column,kind:numeric_threshold,operator,value}.
Time boundaries use time_threshold with an ISO string, and LIMIT uses {kind:limit,value}.
VARCHAR bounds use lexical_threshold. Null checks use {kind:null_test,table,column,
operator:is_null or is_not_null} without a fabricated value or witness.
Dates declared in SQLite may be VARCHAR in DuckDB: use appropriate explicit casts.
Derived predicates use {kind:derived_expression,expression,operator,value}; qualify
their source columns and distinguish expressions from stored catalog values.
For a derived CAST to DATE/TIMESTAMP, specify value_type:timestamp and an ISO bound.
Grouping/domain predicates use {kind:domain_predicate,table,column,operator,value,
evidence_id}; operator is exact, prefix, contains, like or ilike and must match the witness.
LIKE patterns may specify escape (one character), ascii_fold:true for SQLite-style
ASCII folding, or negated:true. A positive witness supports a NOT LIKE pattern;
it does not prove that a truncated catalog exhausts the complement.
Prefix/contains values are literal text, not SQL wildcard patterns. Preserve case
and escape literal percent/underscore when generating a SQL LIKE pattern.
Only select columns needed for the question; a grouping question may need no values.
For COUNT(*) with no column predicate, columns can be empty while the table remains linked.
"""
GENERATOR = """Answer the analyst question with one read-only DuckDB SQL query.
Use only the supplied public catalog and any verified linked context. Support joins,
aggregates and subqueries as required. Do not invent stored values or evidence.
The public schema is information about the database, not an answer key.
Finish with exactly one JSON object containing the key sql. Do not return commentary.
"""
