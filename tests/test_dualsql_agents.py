"""Inference roles use one model, strict limits, and no gold at inference time."""

import json
from types import SimpleNamespace

import duckdb
import pytest

from evaluation.text_to_sql import SQLBenchmarkCase


@pytest.fixture
def snapshot(tmp_path):
    path = tmp_path / "public.duckdb"
    with duckdb.connect(str(path)) as con:
        con.execute("CREATE TABLE network_flows(source_dataset VARCHAR, label VARCHAR)")
        con.execute("INSERT INTO network_flows VALUES ('ctu13_s5', 'flow=From-Botnet-TCP')")
        con.execute("CREATE TABLE dataset_provenance(secret VARCHAR)")
        con.execute("INSERT INTO dataset_provenance VALUES ('GOLD_ONLY_SENTINEL')")
    return path


def response(content="", calls=(), model="gpt-4.1-mini-2025-04-14"):
    tool_calls = [SimpleNamespace(id=f"tc_{i}", type="function",
                  function=SimpleNamespace(name=name, arguments=json.dumps(arguments)))
                  for i, (name, arguments) in enumerate(calls, 1)]
    return SimpleNamespace(model=model, usage=SimpleNamespace(prompt_tokens=100,
                           completion_tokens=50), choices=[SimpleNamespace(
                           message=SimpleNamespace(content=content, tool_calls=tool_calls))])


class FakeClient:
    def __init__(self, *responses):
        self.responses = iter(responses)
        self.requests = []
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self.create))

    def create(self, **kwargs):
        self.requests.append(kwargs)
        return next(self.responses)


def case():
    return SQLBenchmarkCase(
        case_id="public_sql_001", question="Count botnet flows in scenario 5",
        database_snapshot="public.duckdb",
        gold_sql=("SELECT COUNT(*) FROM network_flows WHERE source_dataset='GOLD_ONLY_SENTINEL'",),
        category="network", difficulty="basic", result_comparator="scalar")


def test_e0_one_shot_never_receives_gold(snapshot):
    from evaluation.dualsql_lite.agents import DualSQLCaseRunner

    client = FakeClient(response("SELECT count(*) FROM network_flows"))
    result = DualSQLCaseRunner(snapshot, client).run_case(case(), "E0")
    assert result["final_sql"] == "SELECT count(*) FROM network_flows"
    assert result["linker_turns"] == 0 and result["generator_turns"] == 1
    assert result["generator_tool_calls"] == 0
    assert len(client.requests) == 1 and client.requests[0]["tools"] is None
    assert "GOLD_ONLY_SENTINEL" not in json.dumps(client.requests)


def test_e1_linker_grounding_then_static_generator(snapshot):
    from evaluation.dualsql_lite.agents import DualSQLCaseRunner

    linked = {"tables": [{"table": "network_flows", "columns": ["source_dataset", "label"]}],
              "grounded_values": [{"table": "network_flows", "column": "source_dataset",
                                   "value": "ctu13_s5", "tool_call_id": "tc_1"}]}
    client = FakeClient(response(calls=[("value_search", {"query": "scenario 5"})]),
                        response(json.dumps(linked)),
                        response("SELECT count(*) FROM network_flows"))
    result = DualSQLCaseRunner(snapshot, client).run_case(case(), "E1")
    assert result["linked_schema"] == linked
    assert result["linker_tool_calls"] == 1 and result["generator_tool_calls"] == 0
    assert client.requests[0]["tools"] and client.requests[1]["tools"]
    assert client.requests[2]["tools"] is None
    assert all(r["model"] == "gpt-4.1-mini-2025-04-14" for r in client.requests)
    assert "GOLD_ONLY_SENTINEL" not in json.dumps(client.requests + result["trajectory"])


def test_e2_generator_can_probe_but_e3_can_recover_after_link(snapshot):
    from evaluation.dualsql_lite.agents import DualSQLCaseRunner

    sql = "SELECT count(*) FROM network_flows"
    e2 = FakeClient(response(calls=[("sql_probe", {"sql": sql})]), response(sql))
    r2 = DualSQLCaseRunner(snapshot, e2).run_case(case(), "E2")
    assert r2["linker_turns"] == 0 and r2["generator_tool_calls"] == 1
    incomplete = {"tables": [{"table": "network_flows", "columns": ["label"]}],
                  "grounded_values": []}
    e3 = FakeClient(response(json.dumps(incomplete)),
                    response(calls=[("database_profiler", {"table": "network_flows"})]),
                    response(sql))
    r3 = DualSQLCaseRunner(snapshot, e3).run_case(case(), "E3")
    assert r3["generator_tool_calls"] == 1
    assert r3["generator_recovery_events"] == 1


@pytest.mark.parametrize("bad_link", [
    {"tables": [{"table": "dataset_provenance", "columns": ["secret"]}], "grounded_values": []},
    {"tables": [{"table": "network_flows", "columns": ["invented"]}], "grounded_values": []},
    {"tables": [{"table": "network_flows", "columns": ["label"]}],
     "grounded_values": [{"table": "network_flows", "column": "label",
                          "value": "GOLD_ONLY_SENTINEL", "tool_call_id": "tc_1"}]},
])
def test_invalid_link_is_model_failure_without_generator(snapshot, bad_link):
    from evaluation.dualsql_lite.agents import DualSQLCaseRunner

    client = FakeClient(response(json.dumps(bad_link)))
    result = DualSQLCaseRunner(snapshot, client).run_case(case(), "E1")
    assert result["error_category"] == "LINKER_FORMAT_OR_LIMIT_FAILURE"
    assert result["final_sql"] is None and len(client.requests) == 1


def test_turn_limit_and_malformed_tool_calls_are_model_failures(snapshot):
    from evaluation.dualsql_lite.agents import DualSQLCaseRunner

    sql = "SELECT count(*) FROM network_flows"
    client = FakeClient(*(response(calls=[("sql_probe", {"sql": sql})]) for _ in range(5)))
    result = DualSQLCaseRunner(snapshot, client).run_case(case(), "E2")
    assert result["final_sql"] is None
    assert result["error_category"] == "GENERATOR_FORMAT_OR_LIMIT_FAILURE"
    assert len(client.requests) == 5
    malformed = FakeClient(response(calls=[("value_search", {"query": 5})]),
                           response(sql))
    result = DualSQLCaseRunner(snapshot, malformed).run_case(case(), "E2")
    assert result["trajectory"][0]["result"]["error_type"] == "INVALID_ARGUMENTS"


def test_parallel_tool_calls_do_not_bypass_per_turn_budget_bound(snapshot):
    from evaluation.dualsql_lite.agents import DualSQLCaseRunner

    client = FakeClient(response(calls=[("sql_probe", {"sql": "SELECT 1"})] * 5))
    result = DualSQLCaseRunner(snapshot, client).run_case(case(), "E2")
    assert result["error_category"] == "GENERATOR_FORMAT_OR_LIMIT_FAILURE"
    assert result["generator_tool_calls"] == 0
    assert len(client.requests) == 1


def test_wrong_actual_model_invalidates_run(snapshot):
    from evaluation.dualsql_lite.agents import InvalidEvidenceRun, DualSQLCaseRunner

    with pytest.raises(InvalidEvidenceRun, match="actual model"):
        DualSQLCaseRunner(snapshot, FakeClient(response("SELECT 1", model="wrong"))).run_case(case(), "E0")


def test_final_sql_cannot_read_external_file_or_internal_provenance(snapshot):
    from evaluation.dualsql_lite.agents import DualSQLCaseRunner

    for sql in ("SELECT * FROM read_csv('/etc/passwd')",
                "SELECT * FROM dataset_provenance"):
        result = DualSQLCaseRunner(snapshot, FakeClient(response(sql))).run_case(case(), "E0")
        assert result["safety_rejected"] is True
        assert result["error_category"] == "SAFETY_REJECTION"
