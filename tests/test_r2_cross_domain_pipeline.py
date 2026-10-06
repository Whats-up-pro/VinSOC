"""Synthetic multi-table pipeline evidence, never a live model benchmark."""
import json
import sqlite3
from contextlib import closing
from pathlib import Path

import duckdb
import pytest

from evaluation.r2_cross_domain_v1.data import DatabaseContext, build_duckdb_snapshot


@pytest.fixture
def context(tmp_path):
    source = tmp_path / "shop.sqlite"
    with closing(sqlite3.connect(source)) as conn, conn:
        conn.executescript("""
        CREATE TABLE customers (id INTEGER PRIMARY KEY, name TEXT);
        CREATE TABLE orders (id INTEGER PRIMARY KEY, customer_id INTEGER,
                             amount REAL, units INTEGER, occurred_at TIMESTAMP,
                             FOREIGN KEY(customer_id) REFERENCES customers(id));
        INSERT INTO customers VALUES (1, 'Ada'), (2, 'Lin');
        INSERT INTO orders VALUES (10, 1, 12.5, 9, '2024-01-01T00:00:00'),
                                  (11, 1, 30.0, 2, '2024-01-02T00:00:00'),
                                  (12, 2, 2.0, 3, '2024-01-03T00:00:00');
        """)
    receipt = build_duckdb_snapshot(source, tmp_path / "shop.duckdb", "shop")
    registry = tmp_path / "registry.json"
    registry.write_text(json.dumps({"databases": [{**receipt, "snapshot_path": "shop.duckdb"}]}))
    return DatabaseContext.from_manifest(registry, "shop")


@pytest.mark.parametrize("query", [
    "SELECT\nname FROM customers;",
    "SELECT ';' AS marker FROM customers -- comment ;\n LIMIT 1;",
    "WITH c AS (SELECT id, name FROM customers) SELECT c.name FROM c;",
    "SELECT c.name, SUM(o.amount) AS total FROM customers c JOIN orders o ON c.id=o.customer_id GROUP BY c.name;",
    "SELECT name FROM customers WHERE id IN (SELECT customer_id FROM orders)",
    "SELECT CASE WHEN EXISTS(SELECT 1 FROM orders) THEN 1 ELSE 0 END",
    "SELECT SUM(CASE WHEN amount > 10 THEN 1 ELSE 0 END) FROM orders",
])
def test_safe_select_cte_join_subquery_allowed(context, query):
    from evaluation.r2_cross_domain_v1.safety import validate_sql
    validate_sql(query, context)


@pytest.mark.parametrize("query", [
    "SELECT 1; SELECT 2", "INSERT INTO customers VALUES (9,'bad')", "DELETE FROM customers",
    "DROP TABLE customers", "ATTACH 'x.duckdb' AS x", "COPY customers TO 'x.csv'", "INSTALL httpfs", "LOAD httpfs",
    "SELECT * FROM read_csv('secret.csv')", "SELECT * FROM 'secret.parquet'", "SELECT getenv('API_KEY')",
    "SELECT * FROM other.customers", "SELECT * FROM sqlite_scan('secret.db','t')", "SELECT * FROM unregistered",
    "WITH t AS (DELETE FROM customers RETURNING *) SELECT * FROM t", "SELECT * INTO new_table FROM customers",
])
def test_unsafe_sql_rejected_before_execution(context, query):
    from evaluation.r2_cross_domain_v1.safety import SafetyError, validate_sql
    with pytest.raises(SafetyError):
        validate_sql(query, context)


def test_typed_threshold_is_not_fabricated_catalog_value(context):
    from evaluation.r2_cross_domain_v1.tools import DatabaseTools
    tools = DatabaseTools(context)
    result = tools.value_search({"table": "orders", "column": "amount", "query": "17"})
    assert result["resolution"] == "typed_constraint"
    assert result["matches"] == []
    assert result["type"] == "DOUBLE"
    assert result["domain_complete"] is False


def test_catalog_witness_has_verified_db_column_value_and_complete_domain(context):
    from evaluation.r2_cross_domain_v1.tools import DatabaseTools
    tools = DatabaseTools(context)
    result = tools.value_search({"table": "customers", "column": "name", "query": "Ada"})
    match = result["matches"][0]
    assert match["value"] == "Ada" and match["database_id"] == "shop"
    assert match["table"] == "customers" and match["column"] == "name"
    assert match["snapshot_identity"] == context.identity["logical_sha256"]
    assert match["evidence_id"] in tools.witnesses
    assert result["domain_complete"] is True


def test_ambiguous_or_unknown_column_fails_closed(context):
    from evaluation.r2_cross_domain_v1.tools import DatabaseTools, ToolError
    tools = DatabaseTools(context)
    for args in ({"column": "id", "query": "1"}, {"table": "customers", "column": "secret", "query": "1"}):
        with pytest.raises(ToolError):
            tools.value_search(args)


def _link(evidence_id):
    return {"tables": ["customers"], "columns": [{"table": "customers", "column": "name"}],
            "relationships": [], "grounded_values": [{"evidence_id": evidence_id}], "constraints": []}


def test_missing_or_wrong_database_provenance_rejected(context):
    from evaluation.r2_cross_domain_v1.tools import DatabaseTools
    from evaluation.r2_cross_domain_v1.grounding import GroundingError, validate_link
    tools = DatabaseTools(context)
    result = tools.value_search({"table": "customers", "column": "name", "query": "Ada"})
    evidence_id = result["matches"][0]["evidence_id"]
    assert validate_link("Find Ada", _link(evidence_id), tools.trajectory, context)["grounded_values"][0]["value"] == "Ada"
    with pytest.raises(GroundingError):
        validate_link("Find Ada", _link("invented"), tools.trajectory, context)
    tools.trajectory[0]["result"]["matches"][0]["database_id"] = "different_db"
    with pytest.raises(GroundingError):
        validate_link("Find Ada", _link(evidence_id), tools.trajectory, context)


def test_join_probe_returns_real_fixture_rows_with_no_write(context):
    from evaluation.r2_cross_domain_v1.tools import DatabaseTools
    tools = DatabaseTools(context)
    result = tools.sql_probe({"sql": "SELECT c.name, SUM(o.amount) AS total FROM customers c JOIN orders o ON c.id=o.customer_id GROUP BY c.name ORDER BY c.name"})
    assert result["rows"] == [["Ada", 42.5], ["Lin", 2.0]]
    assert result["database_id"] == "shop"


def test_wrong_type_and_unregistered_join_path_rejected(context):
    from evaluation.r2_cross_domain_v1.grounding import GroundingError, validate_link
    link = {"tables": ["customers", "orders"], "columns": [{"table": "orders", "column": "amount"}],
            "relationships": [], "grounded_values": [],
            "constraints": [{"table": "orders", "column": "amount", "kind": "numeric_threshold", "operator": ">", "value": "Ada"}]}
    with pytest.raises(GroundingError):
        validate_link("Find orders over Ada", link, [], context)
    link["constraints"] = []
    link["relationships"] = [{"from_table": "orders", "from_column": "id", "to_table": "customers", "to_column": "id"}]
    with pytest.raises(GroundingError):
        validate_link("Find orders and customers", link, [], context)


def test_runtime_case_cannot_accept_gold_fields():
    from evaluation.r2_cross_domain_v1.models import RuntimeCase
    with pytest.raises(TypeError):
        RuntimeCase(case_id="fixture", database_id="shop", question="Find names", gold_sql="SECRET_SENTINEL_GOLD")


def test_fake_pipeline_captures_all_responses_and_no_gold_leaks(context):
    from evaluation.r2_cross_domain_v1.models import RuntimeCase
    from evaluation.r2_cross_domain_v1.tools import DatabaseTools
    from evaluation.r2_cross_domain_v1.controller import run_case
    class FakeClient:
        transport_kind = "synthetic"
        def __init__(self):
            self.requests = []
        def request(self, request):
            self.requests.append(request)
            if len(self.requests) == 1:
                return {"content": json.dumps({"tables": ["customers", "orders"],
                    "columns": [{"table": "customers", "column": "id"}, {"table": "customers", "column": "name"}, {"table": "orders", "column": "customer_id"}, {"table": "orders", "column": "amount"}],
                    "relationships": context.identity["relationships"], "grounded_values": [], "constraints": []}),
                    "tool_calls": [], "response_id": "fake-link", "actual_model": "fake", "usage": {"prompt_tokens": 10, "completion_tokens": 10}}
            return {"content": json.dumps({"sql": "SELECT c.name, SUM(o.amount) FROM customers c JOIN orders o ON c.id=o.customer_id GROUP BY c.name ORDER BY c.name"}),
                    "tool_calls": [], "response_id": "fake-sql", "actual_model": "fake", "usage": {"prompt_tokens": 10, "completion_tokens": 10}}
    client, journal = FakeClient(), []
    record = run_case(RuntimeCase("fixture", "shop", "Return spending by customer, ordered by name"), "E3", DatabaseTools(context), client, journal.append)
    assert record["error_category"] == "OK"
    assert record["official_eligible"] is False and record["evidence_kind"] == "synthetic_transport"
    assert len(journal) == 2
    with duckdb.connect(str(context.snapshot_path), read_only=True) as conn:
        assert conn.execute(record["final_sql"]).fetchall() == [("Ada", 42.5), ("Lin", 2.0)]
    requests = json.dumps(client.requests)
    assert "SECRET_SENTINEL_GOLD" not in requests and "gold_sql" not in requests
    assert all(request["model"] == "gpt-5-mini-2025-08-07" and request["reasoning_effort"] == "low" and request["max_completion_tokens"] == 1000 and "temperature" not in request for request in client.requests)


def test_integer_top_k_and_time_threshold_do_not_query_literal_existence(context):
    from evaluation.r2_cross_domain_v1.tools import DatabaseTools
    from evaluation.r2_cross_domain_v1.grounding import validate_link
    tools = DatabaseTools(context)
    numeric = tools.value_search({"table": "orders", "column": "units", "query": "17"})
    timestamp = tools.value_search({"table": "orders", "column": "occurred_at", "query": "2024-02-01T00:00:00"})
    assert numeric["matches"] == timestamp["matches"] == []
    assert timestamp["resolution"] == "typed_constraint"
    assert tools.db_calls == 0
    link = {"tables": ["orders"], "columns": [{"table": "orders", "column": "units"}, {"table": "orders", "column": "occurred_at"}],
            "relationships": [], "grounded_values": [], "constraints": [
                {"kind": "numeric_threshold", "table": "orders", "column": "units", "operator": ">", "value": 17},
                {"kind": "time_threshold", "table": "orders", "column": "occurred_at", "operator": ">=", "value": "2024-02-01T00:00:00"},
                {"kind": "limit", "value": 3},
            ]}
    assert validate_link("Top 3 orders with units over 17 since February 1", link, tools.trajectory, context)["constraints"] == link["constraints"]


def test_derived_expression_and_duplicate_column_names_are_qualified(context):
    from evaluation.r2_cross_domain_v1.grounding import GroundingError, validate_link
    link = {"tables": ["customers", "orders"], "columns": [
        {"table": "customers", "column": "id"}, {"table": "orders", "column": "id"}, {"table": "orders", "column": "amount"}],
        "relationships": [], "grounded_values": [], "constraints": [
            {"kind": "derived_expression", "expression": "SUM(orders.amount)", "operator": ">", "value": 17}]}
    assert validate_link("Total above 17", link, [], context)["columns"] == link["columns"]
    link["constraints"][0]["expression"] = "SUM(id)"
    with pytest.raises(GroundingError):
        validate_link("Total above 17", link, [], context)


def test_truncated_catalog_is_never_closed_and_search_can_resolve_beyond_cap(context):
    from evaluation.r2_cross_domain_v1.tools import DatabaseTools
    tools = DatabaseTools(context, row_cap=1)
    result = tools.value_search({"table": "customers", "column": "name", "query": "Lin", "match_kind": "exact"})
    assert result["domain_complete"] is False and result["domain"] == []
    assert result["matches"][0]["value"] == "Lin"


def test_tool_cap_and_no_live_transport_bypass(context):
    from evaluation.r2_cross_domain_v1.tools import DatabaseTools, ToolError
    from evaluation.r2_cross_domain_v1.models import RuntimeCase
    from evaluation.r2_cross_domain_v1.controller import run_case
    tools = DatabaseTools(context, max_db_calls=1)
    tools.sql_probe({"sql": "SELECT name FROM customers"})
    with pytest.raises(ToolError, match="DB_TOOL_LIMIT"):
        tools.sql_probe({"sql": "SELECT name FROM customers"})
    class ForbiddenClient:
        def request(self, request):
            pytest.fail("live client called before release gate")
    with pytest.raises(ValueError, match="LIVE_RELEASE_GATE"):
        run_case(RuntimeCase("fixture", "shop", "Find names"), "E0", tools, ForbiddenClient(), lambda event: None)


def test_parse_failure_preserves_response_usage_before_failure(context):
    from evaluation.r2_cross_domain_v1.tools import DatabaseTools
    from evaluation.r2_cross_domain_v1.models import RuntimeCase
    from evaluation.r2_cross_domain_v1.controller import run_case
    class FakeClient:
        transport_kind = "synthetic"
        def request(self, request):
            return {"content": "not JSON", "response_id": "fake-bad", "actual_model": "fake", "usage": {"prompt_tokens": 7, "completion_tokens": 3}}
    journal = []
    record = run_case(RuntimeCase("fixture", "shop", "Find names"), "E0", DatabaseTools(context), FakeClient(), journal.append)
    assert record["error_category"] == "TRANSPORT_OR_PARSE_FAILURE"
    assert record["attempted_calls"] == record["response_count"] == len(journal) == 1
    assert journal[0]["response"]["usage"] == {"prompt_tokens": 7, "completion_tokens": 3}


def test_linker_turn_limit_keeps_denominator_and_all_telemetry(context):
    from evaluation.r2_cross_domain_v1.tools import DatabaseTools
    from evaluation.r2_cross_domain_v1.models import RuntimeCase
    from evaluation.r2_cross_domain_v1.controller import run_case
    class FakeClient:
        transport_kind = "synthetic"
        def request(self, request):
            return {"content": None, "tool_calls": [{"id": "fake-profiler", "function": {"name": "database_profiler", "arguments": '{"table":"customers"}'}}],
                    "response_id": "fake-response", "actual_model": "fake", "usage": {"prompt_tokens": 7, "completion_tokens": 3}}
    journal = []
    record = run_case(RuntimeCase("fixture", "shop", "Find names"), "E3", DatabaseTools(context), FakeClient(), journal.append)
    assert record["error_category"] == "TOOL_LIMIT" and record["final_sql"] is None
    assert record["attempted_calls"] == record["response_count"] == len(journal) == 3
    assert record["db_calls"] == 3


def test_completed_linker_is_retained_when_generator_reaches_turn_limit(context):
    from evaluation.r2_cross_domain_v1.tools import DatabaseTools
    from evaluation.r2_cross_domain_v1.models import RuntimeCase
    from evaluation.r2_cross_domain_v1.controller import run_case
    class FakeClient:
        transport_kind = "synthetic"
        count = 0
        def request(self, request):
            self.count += 1
            if self.count == 1:
                return {"content": json.dumps({"tables": ["customers"], "columns": [], "relationships": [], "grounded_values": [], "constraints": []})}
            return {"tool_calls": [{"id": f"call-{self.count}", "function": {"name": "database_profiler", "arguments": {"table": "customers"}}}]}
    record = run_case(RuntimeCase("fixture", "shop", "Count customers"), "E3", DatabaseTools(context), FakeClient(), lambda event: None)
    assert record["error_category"] == "TOOL_LIMIT"
    assert record["linked_schema"]["tables"] == ["customers"]
    assert record["response_count"] == 4


def test_domain_prefix_is_witnessed_without_closed_domain_or_case_folding(context):
    from evaluation.r2_cross_domain_v1.tools import DatabaseTools
    from evaluation.r2_cross_domain_v1.grounding import GroundingError, validate_link
    tools = DatabaseTools(context, row_cap=1)
    found = tools.value_search({"table": "customers", "column": "name", "query": "A", "match_kind": "prefix"})
    evidence_id = found["matches"][0]["evidence_id"]
    link = _link(evidence_id)
    link["constraints"] = [{"kind": "domain_predicate", "table": "customers", "column": "name", "operator": "prefix", "value": "A", "evidence_id": evidence_id}]
    assert validate_link("Names starting with A", link, tools.trajectory, context)["constraints"] == link["constraints"]
    link["constraints"][0]["value"] = "a"
    with pytest.raises(GroundingError):
        validate_link("Names starting with a", link, tools.trajectory, context)


def test_time_expression_does_not_require_stored_timestamp_catalog_match(context):
    from evaluation.r2_cross_domain_v1.grounding import validate_link
    link = {"tables": ["orders"], "columns": [{"table": "orders", "column": "occurred_at"}],
            "relationships": [], "grounded_values": [], "constraints": [{"kind": "derived_expression",
                "expression": "CAST(orders.occurred_at AS TIMESTAMP)", "operator": ">=", "value": "2025-01-01T00:00:00", "value_type": "timestamp"}]}
    assert validate_link("Orders since 2025", link, [], context)["constraints"] == link["constraints"]


def test_context_rejects_catalog_type_tampering_even_with_unchanged_binary(context):
    from copy import deepcopy
    from evaluation.r2_cross_domain_v1.data import RegistryError
    registry = context.snapshot_path.parent / "tampered_registry.json"
    identity = deepcopy(context.identity)
    next(column for table in identity["schema"] if table["name"] == "customers" for column in table["columns"] if column["name"] == "name")["duckdb_type"] = "BIGINT"
    registry.write_text(json.dumps({"databases": [identity]}))
    with pytest.raises(RegistryError, match="CATALOG_SCHEMA_MISMATCH"):
        DatabaseContext.from_manifest(registry, "shop")


def test_e0_has_no_db_tools_and_generation_ok_is_not_an_ex_score(context):
    from evaluation.r2_cross_domain_v1.tools import DatabaseTools
    from evaluation.r2_cross_domain_v1.models import RuntimeCase
    from evaluation.r2_cross_domain_v1.controller import run_case
    class FakeClient:
        transport_kind = "synthetic"
        def request(self, request):
            assert "tools" not in request
            return {"content": '{"sql":"SELECT 999 AS wrong_answer"}', "response_id": "fake", "actual_model": "fake", "usage": {}}
    record = run_case(RuntimeCase("fixture", "shop", "Count customers"), "E0", DatabaseTools(context), FakeClient(), lambda event: None)
    assert record["error_category"] == "OK" and record["db_calls"] == 0
    assert "execution_accurate" not in record


def test_full_fake_profiler_typed_hint_link_generator_flow(context):
    from evaluation.r2_cross_domain_v1.tools import DatabaseTools
    from evaluation.r2_cross_domain_v1.models import RuntimeCase
    from evaluation.r2_cross_domain_v1.controller import run_case
    class FakeClient:
        transport_kind = "synthetic"
        def __init__(self):
            self.count = 0
        def request(self, request):
            self.count += 1
            response = {"response_id": f"fake-{self.count}", "actual_model": "fake", "usage": {"prompt_tokens": 10, "completion_tokens": 10}}
            if self.count <= 2:
                name, args = ("database_profiler", {"table": "orders"}) if self.count == 1 else ("value_search", {"table": "orders", "column": "units", "query": "1"})
                return {**response, "tool_calls": [{"id": f"tool-{self.count}", "function": {"name": name, "arguments": json.dumps(args)}}], "content": None}
            if self.count == 3:
                return {**response, "content": json.dumps({"tables": ["orders"], "columns": [{"table": "orders", "column": "id"}, {"table": "orders", "column": "units"}], "relationships": [], "grounded_values": [],
                    "constraints": [{"kind": "numeric_threshold", "table": "orders", "column": "units", "operator": ">", "value": 1}, {"kind": "limit", "value": 2}]})}
            return {**response, "content": '{"sql":"SELECT id, units FROM orders WHERE units > 1 ORDER BY units DESC, id LIMIT 2"}'}
    journal = []
    record = run_case(RuntimeCase("fixture", "shop", "Top 2 orders by units above 1"), "E3", DatabaseTools(context), FakeClient(), journal.append)
    assert record["error_category"] == "OK" and len(journal) == 4 and record["db_calls"] == 1
    assert [event["tool"] for event in record["trajectory"]] == ["database_profiler", "value_search"]
    with duckdb.connect(str(context.snapshot_path), read_only=True) as conn:
        assert conn.execute(record["final_sql"]).fetchall() == [(10, 9), (12, 3)]


def test_count_star_can_link_table_without_inventing_a_required_column(context):
    from evaluation.r2_cross_domain_v1.grounding import validate_link
    link = {"tables": ["customers"], "columns": [], "relationships": [], "grounded_values": [], "constraints": []}
    assert validate_link("How many customers are there?", link, [], context)["columns"] == []


def test_unknown_tool_arguments_rejected_and_recorded_before_any_db_execution(context):
    from evaluation.r2_cross_domain_v1.tools import DatabaseTools, ToolError
    tools = DatabaseTools(context)
    with pytest.raises(ToolError, match="INVALID_TOOL_ARGUMENTS"):
        tools.call("value_search", {"table": "customers", "column": "name", "query": "Ada", "database_id": "other_db"})
    assert tools.db_calls == 0
    assert tools.trajectory[-1]["error_code"] == "INVALID_TOOL_ARGUMENTS"


def test_sqlite_source_reader_explicitly_closes_its_connection(context, monkeypatch):
    from evaluation.r2_cross_domain_v1.data import inspect_sqlite
    import evaluation.r2_cross_domain_v1.data as data
    original_connect = sqlite3.connect
    opened = []
    class TrackedConnection(sqlite3.Connection):
        explicitly_closed = False
        def close(self):
            self.explicitly_closed = True
            return super().close()
    def connect(*args, **kwargs):
        kwargs["factory"] = TrackedConnection
        connection = original_connect(*args, **kwargs)
        opened.append(connection)
        return connection
    monkeypatch.setattr(data.sqlite3, "connect", connect)
    inspect_sqlite(context.snapshot_path.with_suffix(".sqlite"))
    assert opened and all(connection.explicitly_closed for connection in opened)


def test_low_cardinality_domain_values_have_controller_owned_witnesses(context):
    from evaluation.r2_cross_domain_v1.tools import DatabaseTools
    from evaluation.r2_cross_domain_v1.grounding import validate_link
    tools = DatabaseTools(context)
    result = tools.value_search({"table": "customers", "column": "name", "query": "unmatched concept"})
    assert result["matches"] == [] and result["domain_complete"] is True
    witnesses = result["domain_witnesses"]
    assert {witness["value"] for witness in witnesses} == {"Ada", "Lin"}
    linked = validate_link("Find Ada", _link(witnesses[0]["evidence_id"]), tools.trajectory, context)
    assert linked["grounded_values"][0]["value"] == witnesses[0]["value"]


def test_inequality_operator_is_preserved_and_invalid_operator_rejected(context):
    from evaluation.r2_cross_domain_v1.tools import DatabaseTools
    from evaluation.r2_cross_domain_v1.grounding import validate_link, GroundingError
    tools = DatabaseTools(context)
    result = tools.value_search({'table':'customers','column':'name','query':'Ada'})
    submitted = _link(result['matches'][0]['evidence_id'])
    submitted['grounded_values'][0]['operator'] = '!='
    assert validate_link('Exclude Ada', submitted, tools.trajectory, context)['grounded_values'][0]['operator'] == '!='
    submitted['grounded_values'][0]['operator'] = 'DROP'
    with pytest.raises(GroundingError):
        validate_link('Exclude Ada', submitted, tools.trajectory, context)


def test_lexical_null_and_like_constraints_are_typed_not_catalog_fabrication(context):
    from evaluation.r2_cross_domain_v1.tools import DatabaseTools
    from evaluation.r2_cross_domain_v1.grounding import validate_link, GroundingError
    tools = DatabaseTools(context)
    result = tools.value_search({'table':'customers','column':'name','query':'Ada'})
    submitted = _link(result['matches'][0]['evidence_id'])
    submitted['constraints'] = [
        {'kind':'lexical_threshold','table':'customers','column':'name','operator':'>','value':'B'},
        {'kind':'null_test','table':'customers','column':'name','operator':'is_not_null'},
        {'kind':'domain_predicate','table':'customers','column':'name','operator':'like','value':'A_a','evidence_id':result['matches'][0]['evidence_id']},
    ]
    assert validate_link('Names after B matching A_a', submitted, tools.trajectory, context)['constraints'] == submitted['constraints']
    submitted['constraints'][2]['value'] = 'A\\_a'
    submitted['constraints'][2]['escape'] = '\\'
    with pytest.raises(GroundingError, match='DOMAIN'):
        validate_link('Literal underscore', submitted, tools.trajectory, context)
