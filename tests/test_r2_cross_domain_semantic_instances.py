"""Synthetic counterexamples executed on DuckDB; no inference results."""
from copy import deepcopy
from types import SimpleNamespace

import pytest


@pytest.fixture
def spec():
    def column(name, kind, pk=False):
        return {"name": name, "duckdb_type": kind, "primary_key_position": int(pk), "not_null": pk}
    return {"fixture_only": True, "seed": 20261005, "database_id": "counterexample",
            "schema": [{"name": "parents", "columns": [column("id", "BIGINT", True), column("label", "VARCHAR")]},
                       {"name": "events", "columns": [column("id", "BIGINT", True), column("parent_id", "BIGINT"), column("source", "VARCHAR"),
                                                       column("label", "VARCHAR"), column("quantity", "BIGINT"), column("at", "TIMESTAMP")]}],
            "relationships": [{"from_table": "events", "from_column": "parent_id", "to_table": "parents", "to_column": "id"}],
            "rows": {"parents": [[1, "one"], [2, "two"], [3, "unmatched"]],
                     "events": [[1, 1, "A", "pre_one", 8, "2020-01-01 00:00:00"],
                                [2, 1, "A", "pre_one", 8, "2020-01-01 00:00:01"],
                                [3, 2, "B", "xpre_one", 9, "2019-12-31 23:59:59"],
                                [4, 2, "A", "Pre_two", None, "2020-01-02 00:00:00"],
                                [5, None, "B", "preXone", 3, "2020-01-03 00:00:00"]]}}


def test_fixture_builds_are_logically_identical_and_constraints_checked(tmp_path, spec):
    from evaluation.r2_cross_domain_v1.semantic_instances import build_fixture
    first = build_fixture(spec, tmp_path / "one.duckdb")
    second = build_fixture(spec, tmp_path / "two.duckdb")
    assert first["context"].identity["logical_sha256"] == second["context"].identity["logical_sha256"]
    assert first["fixture_only"] and first["constraints_verified"]
    with pytest.raises(ValueError, match="ALREADY_EXISTS"):
        build_fixture(spec, tmp_path / "one.duckdb")
    invalid = deepcopy(spec)
    invalid["rows"]["events"][0][1] = 999
    with pytest.raises(ValueError, match="FOREIGN_KEY"):
        build_fixture(invalid, tmp_path / "invalid.duckdb")


@pytest.mark.parametrize("gold,wrong,comparator", [
    ("SELECT COUNT(*) FROM events WHERE source='A'", "SELECT COUNT(*) FROM events", "scalar"),
    ("SELECT label FROM events WHERE starts_with(label,'pre_')", "SELECT label FROM events WHERE contains(label,'pre_')", "unordered_multiset"),
    ("SELECT label FROM events WHERE label LIKE 'pre\\_%' ESCAPE '\\'", "SELECT label FROM events WHERE label LIKE 'pre_%'", "unordered_multiset"),
    ("SELECT label FROM events WHERE label LIKE 'pre%'", "SELECT label FROM events WHERE label ILIKE 'pre%'", "unordered_multiset"),
    ("SELECT DISTINCT label FROM events", "SELECT label FROM events", "unordered_multiset"),
    ("SELECT id FROM events WHERE \"at\">=TIMESTAMP '2020-01-01'", "SELECT id FROM events WHERE \"at\">TIMESTAMP '2020-01-01'", "unordered_multiset"),
    ("SELECT id FROM events WHERE (source='A' OR source='B') AND quantity>7", "SELECT id FROM events WHERE source='A' OR source='B' AND quantity>7", "unordered_multiset"),
    ("SELECT p.id FROM parents p LEFT JOIN events e ON p.id=e.parent_id", "SELECT p.id FROM parents p INNER JOIN events e ON p.id=e.parent_id", "unordered_multiset"),
    ("SELECT COUNT(quantity) FROM events", "SELECT COUNT(*) FROM events", "scalar"),
    ("SELECT source FROM events GROUP BY source HAVING COUNT(*)>2", "SELECT source FROM events GROUP BY source HAVING COUNT(*)>=2", "unordered_multiset"),
    ("SELECT id FROM events ORDER BY quantity DESC NULLS LAST, id ASC LIMIT 2", "SELECT id FROM events ORDER BY quantity DESC NULLS LAST, id DESC LIMIT 2", "ordered_rows"),
])
def test_executable_wrong_sql_is_killed_on_counterexample(tmp_path, spec, gold, wrong, comparator):
    from evaluation.r2_cross_domain_v1.semantic_instances import build_fixture, audit_semantics
    one = build_fixture(spec, tmp_path / "one.duckdb")
    changed = deepcopy(spec)
    changed["seed"] += 1
    changed["rows"]["events"][4][4] = 4
    two = build_fixture(changed, tmp_path / "two.duckdb")
    reference = SimpleNamespace(database_id="counterexample", gold_sql=gold, comparator=comparator)
    report = audit_semantics(reference, [one, two], [{"family": "intentional_mutant", "sql": wrong}], [gold])
    assert report["semantic_mutants_killed"] == 1
    assert report["semantic_mutants_executable"] == 1
    assert report["equivalent_controls_accepted"] == 1
    assert report["external_model_calls"] == 0


def test_syntax_failures_are_not_semantic_kills(tmp_path, spec):
    from evaluation.r2_cross_domain_v1.semantic_instances import build_fixture, audit_semantics
    one = build_fixture(spec, tmp_path / "one.duckdb")
    changed = deepcopy(spec)
    changed["rows"]["events"][4][4] = 4
    two = build_fixture(changed, tmp_path / "two.duckdb")
    reference = SimpleNamespace(database_id="counterexample", gold_sql="SELECT id FROM events", comparator="unordered_multiset")
    report = audit_semantics(reference, [one, two], [{"family": "broken", "sql": "SELECT FROM"}], [])
    assert report["semantic_mutants_killed"] == report["semantic_mutants_executable"] == 0
    assert report["mutant_results"][0]["status"] == "NONEXECUTABLE"


def test_mutation_candidates_and_equivalent_controls_are_generic():
    from evaluation.r2_cross_domain_v1.semantic_instances import generate_mutants, equivalent_controls
    query = "SELECT DISTINCT code FROM arbitrary_table WHERE quantity>=12 AND flag='X' ORDER BY code LIMIT 3"
    mutants = generate_mutants(query)
    assert {item["family"] for item in mutants} >= {"distinct", "missing_filter", "boolean", "boundary", "ordering", "limit"}
    assert all(item["sql"] != query for item in mutants)
    assert equivalent_controls(query)


def test_root_set_operation_and_simple_count_projection_can_be_mutated():
    from evaluation.r2_cross_domain_v1.semantic_instances import generate_mutants
    assert any(item["family"] == "set_operation" and "UNION" in item["sql"] for item in generate_mutants("SELECT code FROM a EXCEPT SELECT code FROM b"))
    assert any(item["family"] == "null_count" for item in generate_mutants("SELECT COUNT(*) FROM arbitrary_table"))
    assert any(item["family"] == "projection" for item in generate_mutants("SELECT a,b FROM arbitrary_table"))
    assert any("EXCEPT" in item["sql"] for item in generate_mutants("SELECT code FROM a INTERSECT SELECT code FROM b"))


def test_generic_fixture_generator_uses_typed_constants_and_declared_keys(tmp_path, spec):
    from evaluation.r2_cross_domain_v1.semantic_instances import build_fixture
    from evaluation.r2_cross_domain_v1.fixture_generation import generate_fixture_spec
    context = SimpleNamespace(database_id=spec["database_id"], identity={"schema": spec["schema"], "relationships": spec["relationships"]})
    sql = "SELECT e.label FROM events e JOIN parents p ON e.parent_id=p.id WHERE e.quantity>=17 AND e.source='A'"
    first = generate_fixture_spec(context, sql, variant=0)
    second = generate_fixture_spec(context, sql, variant=1)
    assert first["fixture_only"] and first["seed"] != second["seed"]
    amounts = [row[4] for row in first["rows"]["events"]]
    assert {16, 17, 18} <= set(amounts)
    one = build_fixture(first, tmp_path / "one.duckdb")
    two = build_fixture(second, tmp_path / "two.duckdb")
    assert one["context"].identity["logical_sha256"] != two["context"].identity["logical_sha256"]


def test_composite_key_allows_repeated_filter_component_with_unique_tuple(tmp_path):
    from evaluation.r2_cross_domain_v1.fixture_generation import generate_fixture_spec
    from evaluation.r2_cross_domain_v1.semantic_instances import build_fixture
    context = SimpleNamespace(database_id="tenants", identity={"schema": [{"name": "entries", "columns": [
        {"name": "tenant", "duckdb_type": "VARCHAR", "primary_key_position": 1, "not_null": False},
        {"name": "receipt_id", "duckdb_type": "BIGINT", "primary_key_position": 2, "not_null": True}]}], "relationships": []})
    spec = generate_fixture_spec(context, "SELECT COUNT(*) FROM entries WHERE tenant='branch_B'", variant=0)
    assert any(row[0] == "branch_B" for row in spec["rows"]["entries"])
    assert all(row[0] is not None for row in spec["rows"]["entries"])
    instance = build_fixture(spec, tmp_path / "fixture.duckdb")
    assert instance["constraints_verified"]


def test_reordered_rows_pass_multiset_but_fail_ordered(tmp_path, spec):
    from evaluation.r2_cross_domain_v1.semantic_instances import build_fixture, audit_semantics
    one = build_fixture(spec, tmp_path / "one.duckdb")
    changed = deepcopy(spec)
    changed["rows"]["events"][4][4] = 4
    two = build_fixture(changed, tmp_path / "two.duckdb")
    wrong = [{"family": "order", "sql": "SELECT id FROM events ORDER BY id DESC"}]
    for comparator, killed in (("ordered_rows", 1), ("unordered_multiset", 0)):
        reference = SimpleNamespace(database_id="counterexample", gold_sql="SELECT id FROM events ORDER BY id ASC", comparator=comparator)
        assert audit_semantics(reference, [one, two], wrong, [reference.gold_sql])["semantic_mutants_killed"] == killed


def test_audit_receipt_keeps_decimal_sample_and_never_overwrites(tmp_path):
    from decimal import Decimal
    import json
    from scripts.audit_r2_cross_domain_semantics import write_record
    path = tmp_path / "receipt.json"
    write_record(path, {"sample": [[Decimal("123.456789")]]})
    assert json.loads(path.read_text(encoding="utf-8"))["sample"] == [["123.456789"]]
    with pytest.raises(FileExistsError):
        write_record(path, {})


def test_conjunctive_cross_source_time_constraints_receive_positive_rows(tmp_path):
    from evaluation.r2_cross_domain_v1.fixture_generation import generate_fixture_spec
    from evaluation.r2_cross_domain_v1.semantic_instances import build_fixture
    from evaluation.r2_cross_domain_v1.tools import DatabaseTools
    context = SimpleNamespace(database_id="branches", identity={"schema": [{"name": "records", "columns": [
        {"name": "branch", "duckdb_type": "VARCHAR", "primary_key_position": 1},
        {"name": "id", "duckdb_type": "BIGINT", "primary_key_position": 2},
        {"name": "kind", "duckdb_type": "VARCHAR"}, {"name": "stamp", "duckdb_type": "TIMESTAMP"},
        {"name": "destination", "duckdb_type": "VARCHAR"}]}], "relationships": []})
    sql = """SELECT COUNT(*) FROM (SELECT destination FROM records WHERE branch='east' AND kind='K'
       AND stamp>TIMESTAMP '2022-02-01' INTERSECT SELECT destination FROM records WHERE branch='west'
       AND kind='K' AND stamp>TIMESTAMP '2023-03-01') shared"""
    spec = generate_fixture_spec(context, sql, variant=0)
    instance = build_fixture(spec, tmp_path / "fixture.duckdb")
    _, rows, _ = DatabaseTools(instance["context"])._execute(sql)
    assert rows[0][0] > 0


def test_positive_row_expansion_preserves_primary_foreign_key_uniqueness(tmp_path):
    from evaluation.r2_cross_domain_v1.fixture_generation import generate_fixture_spec
    from evaluation.r2_cross_domain_v1.semantic_instances import build_fixture
    key = {"name": "id", "duckdb_type": "BIGINT", "primary_key_position": 1}
    context = SimpleNamespace(database_id="extension", identity={"schema": [
        {"name": "base", "columns": [key]},
        {"name": "detail", "columns": [key, {"name": "quantity", "duckdb_type": "BIGINT"}]}],
        "relationships": [{"from_table": "detail", "from_column": "id", "to_table": "base", "to_column": "id"}]})
    spec = generate_fixture_spec(context, "SELECT id FROM detail WHERE quantity>17", variant=0)
    assert build_fixture(spec, tmp_path / "fixture.duckdb")["constraints_verified"]
