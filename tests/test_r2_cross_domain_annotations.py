"""Reference-only annotations; fixtures do not represent model performance."""
from types import SimpleNamespace

import pytest


@pytest.fixture
def context():
    return SimpleNamespace(database_id="shop", identity={"schema": [
        {"name": "people", "columns": [{"name": "id", "duckdb_type": "BIGINT"}, {"name": "name", "duckdb_type": "VARCHAR"}]},
        {"name": "orders", "columns": [{"name": "id", "duckdb_type": "BIGINT"}, {"name": "person_id", "duckdb_type": "BIGINT"}, {"name": "amount", "duckdb_type": "DOUBLE"}]},
    ], "relationships": [{"from_table": "orders", "from_column": "person_id", "to_table": "people", "to_column": "id"}]})


def test_reference_annotations_resolve_aliases_and_join_path(context):
    from evaluation.r2_cross_domain_v1.annotations import annotate_reference
    alternative = annotate_reference("SELECT p.name, SUM(o.amount) FROM people p JOIN orders o ON p.id=o.person_id GROUP BY p.name", context)[0]
    assert alternative["tables"] == ["orders", "people"]
    assert {tuple(item.values()) for item in alternative["columns"]} == {("people", "name"), ("people", "id"), ("orders", "amount"), ("orders", "person_id")}
    assert alternative["relationships"] == context.identity["relationships"]


def test_annotations_separate_catalog_values_thresholds_and_limit(context):
    from evaluation.r2_cross_domain_v1.annotations import annotate_reference
    alternative = annotate_reference("SELECT p.name FROM people p JOIN orders o ON p.id=o.person_id WHERE p.name='Ada' AND o.amount>17 ORDER BY p.name, o.id LIMIT 3", context)[0]
    assert alternative["stored_values"] == [{"table": "people", "column": "name", "operator": "=", "value": "Ada"}]
    assert {entry["kind"] for entry in alternative["constraints"]} == {"numeric_threshold", "limit"}
    assert not any("evidence_id" in item for item in alternative["stored_values"])


def test_ambiguous_reference_column_is_not_guessed(context):
    from evaluation.r2_cross_domain_v1.annotations import annotate_reference, AnnotationError
    with pytest.raises(AnnotationError):
        annotate_reference("SELECT id FROM people JOIN orders ON people.id=orders.person_id", context)


def test_predicate_annotations_cover_patterns_null_membership_and_ranges(context):
    from evaluation.r2_cross_domain_v1.annotations import annotate_reference
    sql = """SELECT name FROM people WHERE name LIKE 'A\\_%' ESCAPE '\\'
             AND name IS NOT NULL AND id BETWEEN -3 AND 17 AND id IN (1, 9)"""
    alternative = annotate_reference(sql, context)[0]
    assert alternative["annotations_complete"]
    predicates = alternative["predicates"]
    assert {item["operator"] for item in predicates} >= {"like", "is", "between", "in"}
    pattern = next(item for item in predicates if item["operator"] == "like")
    assert pattern["escape"] == "\\"
    assert pattern["column_dependencies"] == [{"table": "people", "column": "name"}]
    assert pattern["negated"] is False
    assert next(item for item in predicates if item["operator"] == "is")["negated"]
    assert any(item["value"] == -3 for item in next(item for item in predicates if item["operator"] == "between")["literals"])


def test_annotations_include_aggregate_derived_and_reversed_constraints(context):
    from evaluation.r2_cross_domain_v1.annotations import annotate_reference
    alternative = annotate_reference("SELECT person_id, SUM(amount) FROM orders WHERE 12 < amount GROUP BY person_id HAVING SUM(amount)>19", context)[0]
    assert {item["stage"] for item in alternative["predicates"]} == {"where", "having"}
    assert {item["value"] for item in alternative["constraints"]} >= {12, 19}
    assert any(item["kind"] == "derived_expression" for item in alternative["constraints"])
    direct = next(item for item in alternative["constraints"] if item["kind"] == "numeric_threshold")
    assert direct["operator"] == ">" and direct["column"] == "amount"


def test_annotations_include_timestamp_cast_and_correlated_subquery(context):
    from evaluation.r2_cross_domain_v1.annotations import annotate_reference
    alternative = annotate_reference("""SELECT p.name FROM people p WHERE EXISTS
      (SELECT 1 FROM orders o WHERE o.person_id=p.id AND CAST(o.amount AS DOUBLE)>3)
      AND CAST(p.name AS TIMESTAMP)>=TIMESTAMP '2020-01-01 00:00:00'""", context)[0]
    assert alternative["annotations_complete"]
    assert any(item["kind"] == "derived_expression" and item.get("value_type") == "timestamp" for item in alternative["constraints"])
    assert any(item["operator"] == "exists" for item in alternative["predicates"])


def test_boolean_function_predicate_and_boolean_structure_are_annotated(context):
    from evaluation.r2_cross_domain_v1.annotations import annotate_reference
    alternative = annotate_reference("SELECT name FROM people WHERE starts_with(name,'A') OR (id=2 AND name IS NULL)", context)[0]
    assert "startswith" in {item["operator"] for item in alternative["predicates"]}
    assert alternative["boolean_structure"][0]["expression"].startswith("STARTS_WITH")


def test_mapping_annotations_include_pattern_membership_null_and_bounds(context):
    from evaluation.r2_cross_domain_v1.annotations import annotate_reference
    alt = annotate_reference("SELECT name FROM people WHERE starts_with(name,'A_') AND name IN ('Bo','Cy') AND id BETWEEN 2 AND 9 AND name IS NOT NULL", context)[0]
    assert {v['value'] for v in alt['stored_values']} == {'Bo', 'Cy'}
    assert any(v['kind'] == 'domain_predicate' and v['operator'] == 'prefix' and v['value'] == 'A_' for v in alt['constraints'])
    assert any(v['kind'] == 'null_test' and v['operator'] == 'is_not_null' for v in alt['constraints'])
    assert {(v['operator'], v['value']) for v in alt['constraints'] if v['kind'] == 'numeric_threshold'} == {('>=', 2), ('<=', 9)}
