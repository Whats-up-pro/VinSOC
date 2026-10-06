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
