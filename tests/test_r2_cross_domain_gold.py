"""Offline gold/dialect/scoring checks; no model results."""
import sqlite3
from contextlib import closing

import duckdb
import pytest


def test_sqlite_double_quoted_literal_converts_but_known_column_does_not():
    from evaluation.r2_cross_domain_v1.benchmark import adapt_sqlite_gold
    schema = [{"name": "people", "columns": [{"name": "name", "primary_key_position": 0}]}]
    result = adapt_sqlite_gold('SELECT "name" FROM people WHERE name="Ada"', schema)
    assert "'Ada'" in result["sql"] and '"name"' in result["sql"]
    assert result["transformations"]


def test_grouping_extension_requires_declared_functional_dependency():
    from evaluation.r2_cross_domain_v1.benchmark import adapt_sqlite_gold, BenchmarkError
    schema = [{"name": "people", "columns": [{"name": "id", "primary_key_position": 1}, {"name": "name", "primary_key_position": 0}]}]
    adapted = adapt_sqlite_gold("SELECT name, count(*) FROM people GROUP BY id", schema)["sql"]
    with duckdb.connect(":memory:") as conn:
        conn.execute("CREATE TABLE people(id BIGINT, name VARCHAR); INSERT INTO people VALUES(1,'Ada'),(2,'Lin')")
        assert sorted(conn.execute(adapted).fetchall()) == [("Ada", 1), ("Lin", 1)]
    with pytest.raises(BenchmarkError, match="UNPROVEN_BARE_GROUP_COLUMN"):
        adapt_sqlite_gold("SELECT id, count(*) FROM people GROUP BY name", schema)


def test_join_equality_propagates_key_dependency():
    from evaluation.r2_cross_domain_v1.benchmark import adapt_sqlite_gold
    schema = [
        {"name": "people", "columns": [{"name": "id", "primary_key_position": 1}, {"name": "name", "primary_key_position": 0}]},
        {"name": "visits", "columns": [{"name": "person_id", "primary_key_position": 0}]},
    ]
    adapted = adapt_sqlite_gold("SELECT p.name, COUNT(*) FROM visits v JOIN people p ON v.person_id=p.id GROUP BY v.person_id", schema)
    assert "p.name" in adapted["sql"].split("GROUP BY")[1]


def test_result_comparison_preserves_duplicates_order_null_and_numeric_types():
    from evaluation.r2_cross_domain_v1.semantic_scoring import compare_results
    assert compare_results([(1,), (1,), (None,)], [(None,), (1.0,), (1,)], "unordered_multiset")
    assert not compare_results([(1,), (None,)], [(None,), (1,), (1,)], "unordered_multiset")
    assert compare_results([(1,)], [(1,), (1,)], "unordered_set")
    assert not compare_results([(2,), (1,)], [(1,), (2,)], "ordered_rows")
    assert not compare_results([], [(0,)], "scalar")


def test_gold_sqlite_duckdb_parity_runs_real_engines(tmp_path):
    from evaluation.r2_cross_domain_v1.benchmark import validate_gold_parity
    from evaluation.r2_cross_domain_v1.data import DatabaseContext, build_duckdb_snapshot
    import json
    source = tmp_path / "people.sqlite"
    with closing(sqlite3.connect(source)) as conn, conn:
        conn.executescript("CREATE TABLE people(id INTEGER PRIMARY KEY, name TEXT); INSERT INTO people VALUES(1,'Ada'),(2,'Lin')")
    receipt = build_duckdb_snapshot(source, tmp_path / "people.duckdb", "people")
    registry = tmp_path / "registry.json"
    registry.write_text(json.dumps({"databases": [{**receipt, "snapshot_path": "people.duckdb"}]}))
    context = DatabaseContext.from_manifest(registry, "people")
    result = validate_gold_parity('SELECT name FROM people WHERE name="Ada"', source, context, "unordered_multiset")
    assert result["parity"] and result["sqlite_row_count"] == result["duckdb_row_count"] == 1
    assert result["original_sql"].endswith('name="Ada"')


def test_reference_dto_separates_gold_from_runtime():
    from evaluation.r2_cross_domain_v1.benchmark import ReferenceCase
    reference = ReferenceCase("fixture", "shop", "Count customers", "SELECT COUNT(*) FROM customers", "scalar", "basic", [], "family", [])
    runtime = reference.runtime()
    assert not hasattr(runtime, "gold_sql") and not hasattr(runtime, "accepted_links")


def test_boolean_combinations_are_safe_read_only_sql():
    from evaluation.r2_cross_domain_v1.safety import validate_sql
    from types import SimpleNamespace
    context = SimpleNamespace(identity={"schema": [{"name": "people"}]})
    validate_sql("SELECT name FROM people WHERE (id=1 OR id=2) AND name!='bad'", context)


def test_sqlite_affinity_is_explicit_in_mixed_type_predicates():
    from evaluation.r2_cross_domain_v1.benchmark import adapt_sqlite_gold, BenchmarkError
    schema = [{"name": "t", "columns": [
        {"name": "number", "duckdb_type": "BIGINT", "sqlite_type": "INTEGER", "primary_key_position": 0},
        {"name": "text", "duckdb_type": "VARCHAR", "sqlite_type": "TEXT", "primary_key_position": 0},
    ]}]
    # Blind TRY_CAST would turn 'bad' into NULL and corrupt NOT IN semantics.
    # Without a proved affinity adapter, this conversion must fail closed.
    with pytest.raises(BenchmarkError, match="UNSUPPORTED_MIXED_AFFINITY"):
        adapt_sqlite_gold("SELECT text FROM t WHERE number IN(SELECT text FROM t)", schema)
    adapted = adapt_sqlite_gold("SELECT text FROM t WHERE text > 9", schema)["sql"]
    with duckdb.connect(":memory:") as conn:
        conn.execute("CREATE TABLE t(number BIGINT,text VARCHAR); INSERT INTO t VALUES(1,'12'),(2,'a')")
        assert conn.execute(adapted).fetchall() == [("a",)]


def test_top_k_tie_is_rejected_even_if_both_engines_choose_same_row(tmp_path):
    from evaluation.r2_cross_domain_v1.benchmark import validate_gold_parity, BenchmarkError
    from evaluation.r2_cross_domain_v1.data import DatabaseContext, build_duckdb_snapshot
    import json
    source = tmp_path / "items.sqlite"
    with closing(sqlite3.connect(source)) as conn, conn:
        conn.executescript("CREATE TABLE items(id INTEGER PRIMARY KEY, name TEXT, score INTEGER); INSERT INTO items VALUES(1,'A',10),(2,'B',10)")
    receipt = build_duckdb_snapshot(source, tmp_path / "items.duckdb", "items")
    registry = tmp_path / "registry.json"
    registry.write_text(json.dumps({"databases": [{**receipt, "snapshot_path": "items.duckdb"}]}))
    context = DatabaseContext.from_manifest(registry, "items")
    with pytest.raises(BenchmarkError, match="AMBIGUOUS_LIMIT_TIE"):
        validate_gold_parity("SELECT name FROM items ORDER BY score DESC LIMIT 1", source, context, "ordered_rows")
    assert validate_gold_parity("SELECT name FROM items ORDER BY score DESC, id LIMIT 1", source, context, "ordered_rows")["parity"]


def test_generation_ok_is_not_execution_accuracy(tmp_path):
    from evaluation.r2_cross_domain_v1.benchmark import ReferenceCase
    from evaluation.r2_cross_domain_v1.semantic_scoring import score_case
    from evaluation.r2_cross_domain_v1.data import DatabaseContext, build_duckdb_snapshot
    import json
    source = tmp_path / "items.sqlite"
    with closing(sqlite3.connect(source)) as conn, conn:
        conn.executescript("CREATE TABLE items(id INTEGER PRIMARY KEY); INSERT INTO items VALUES(1),(2)")
    receipt = build_duckdb_snapshot(source, tmp_path / "items.duckdb", "items")
    registry = tmp_path / "registry.json"
    registry.write_text(json.dumps({"databases": [{**receipt, "snapshot_path": "items.duckdb"}]}))
    context = DatabaseContext.from_manifest(registry, "items")
    reference = ReferenceCase("fixture", "items", "Count all items", "SELECT COUNT(*) FROM items", "scalar", "basic", [], "family", [])
    record = {"error_category": "OK", "final_sql": "SELECT COUNT(*) FROM items WHERE id=1"}
    scored = score_case(reference, record, [{"instance_id": "base", "context": context, "fixture_only": False}])
    assert scored["syntax_valid"] and scored["execution_success"]
    assert not scored["execution_accurate"] and scored["scoring_error_category"] == "RESULT_MISMATCH"
    assert scored["pipeline_error_category"] == "OK" and "execution_accurate" not in record
    missing = score_case(reference, {"error_category": "TOOL_LIMIT", "final_sql": None}, [{"instance_id": "base", "context": context, "fixture_only": False}])
    assert missing["pipeline_error_category"] == "TOOL_LIMIT" and not missing["execution_accurate"]
    assert missing["semantic_instances_correct"] == 0 and missing["semantic_instances_total"] == 1
    correct = score_case(reference, {"error_category": "OK", "final_sql": "SELECT COUNT(id) FROM items"}, [{"instance_id": "base", "context": context, "fixture_only": False}])
    assert correct["execution_accurate"]


def test_all_order_ties_must_be_deterministic_not_only_limit(tmp_path):
    from evaluation.r2_cross_domain_v1.benchmark import validate_gold_parity, BenchmarkError
    from evaluation.r2_cross_domain_v1.data import DatabaseContext, build_duckdb_snapshot
    import json
    source = tmp_path / "items.sqlite"
    with closing(sqlite3.connect(source)) as conn, conn:
        conn.executescript("CREATE TABLE items(id INTEGER PRIMARY KEY, name TEXT, score INTEGER); INSERT INTO items VALUES(1,'A',10),(2,'B',10)")
    receipt = build_duckdb_snapshot(source, tmp_path / "items.duckdb", "items")
    registry = tmp_path / "registry.json"
    registry.write_text(json.dumps({"databases": [{**receipt, "snapshot_path": "items.duckdb"}]}))
    context = DatabaseContext.from_manifest(registry, "items")
    with pytest.raises(BenchmarkError, match="AMBIGUOUS_ORDER_TIE"):
        validate_gold_parity("SELECT name FROM items ORDER BY score", source, context, "ordered_rows")


def test_scoring_preserves_decimal_and_duplicate_select_column_positions(tmp_path):
    from evaluation.r2_cross_domain_v1.benchmark import ReferenceCase
    from evaluation.r2_cross_domain_v1.semantic_scoring import score_case
    from evaluation.r2_cross_domain_v1.data import DatabaseContext, build_duckdb_snapshot
    import json
    source = tmp_path / "items.sqlite"
    with closing(sqlite3.connect(source)) as conn, conn:
        conn.executescript("CREATE TABLE items(id INTEGER PRIMARY KEY, amount NUMERIC); INSERT INTO items VALUES(1,1.1),(2,2.4)")
    receipt = build_duckdb_snapshot(source, tmp_path / "items.duckdb", "items")
    registry = tmp_path / "registry.json"
    registry.write_text(json.dumps({"databases": [{**receipt, "snapshot_path": "items.duckdb"}]}))
    context = DatabaseContext.from_manifest(registry, "items")
    instances = [{"instance_id": "base", "context": context, "fixture_only": False}]
    reference = ReferenceCase("fixture", "items", "Sum amounts", "SELECT SUM(amount) FROM items", "scalar", "basic", [], "family", [])
    assert score_case(reference, {"final_sql": "SELECT SUM(CAST(amount AS DOUBLE)) FROM items"}, instances)["execution_accurate"]
    reference = ReferenceCase("fixture", "items", "Two values", "SELECT id, amount FROM items", "unordered_multiset", "basic", [], "family", [])
    assert not score_case(reference, {"final_sql": "SELECT id AS x, id AS x FROM items"}, instances)["execution_accurate"]
@pytest.mark.parametrize("predicate,expected", [("name LIKE '%Hey%'", 3), ("name LIKE 'Ä'", 1), ("name LIKE 'a\\_b' ESCAPE '\\'", 2)])
def test_sqlite_like_adapter_preserves_ascii_nocase_without_unicode_casefold(tmp_path, predicate, expected):
    import sqlite3
    from contextlib import closing
    from evaluation.r2_cross_domain_v1.data import build_duckdb_snapshot, DatabaseContext
    from evaluation.r2_cross_domain_v1.benchmark import validate_gold_parity
    source = tmp_path / "like.sqlite"
    with closing(sqlite3.connect(source)) as connection, connection:
        connection.execute("CREATE TABLE words (id INTEGER PRIMARY KEY, name TEXT)")
        connection.executemany("INSERT INTO words VALUES (?,?)", [(1,"Hey"),(2,"hey"),(3,"HEY"),(4,"Ä"),(5,"ä"),(6,"a_b"),(7,"A_B"),(8,None)])
    identity = build_duckdb_snapshot(source, tmp_path / "like.duckdb", "like_fixture")
    context = DatabaseContext("like_fixture", tmp_path / "like.duckdb", identity)
    report = validate_gold_parity("SELECT COUNT(*) FROM words WHERE " + predicate, source, context, "scalar")
    assert report["parity"]
    assert report["sample_adapted_rows"] == [[expected]]
