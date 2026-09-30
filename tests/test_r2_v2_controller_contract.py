"""Exercise actual runner gates and every response-preservation return path."""
import json

import pytest

from evaluation.dualsql_lite_ctu_gpt5_v2.runner import run_case, run_role
from tests.r2_remediation_fixtures import FakeClient, call, case, make_tools, response


@pytest.mark.parametrize("content,question,error", [
    ("broken", "Return totals", "LINKER_FORMAT_ERROR"),
    ('{"tables":[],"grounded_values":[]}', "Return totals", "INVALID_LINKED_SCHEMA"),
    ('{"tables":[{"table":"network_flows","columns":[]}],"grounded_values":[]}', "Return totals", "INVALID_LINKED_SCHEMA"),
    ('{"tables":[{"table":"network_flows","columns":["missing"]}],"grounded_values":[]}', "Return totals", "INVALID_LINKED_SCHEMA"),
    ('{"tables":[{"table":"other","columns":["label"]}],"grounded_values":[]}', "Return totals", "INVALID_LINKED_SCHEMA"),
    ('{"tables":[{"table":"network_flows","columns":["source_dataset"]}],"grounded_values":[]}', "Count Group 5 flows", "UNRESOLVED_LITERAL"),
    ('{"tables":[{"table":"network_flows","columns":["label"]}],"grounded_values":[{"table":"network_flows","column":"label","value":"invented"}]}', "Return totals", "INVALID_TOOL_PROVENANCE"),
])
def test_linker_failure_stops_generator_and_retains_usage(tmp_path, content, question, error):
    tools, _ = make_tools(tmp_path)
    client = FakeClient([response(content)])
    result = run_case(case(question), "E3", tools, client, tools.schema_context())
    assert len(client.requests) == 1
    assert result["error_category"] == error
    assert len(result["usage"]) == 1
    assert result["roles"]["generator"] is None


@pytest.mark.parametrize("reply,error", [
    (RuntimeError("credential-secret"), "PROVIDER_ERROR"),
    (response(), "EMPTY_RESPONSE"),
    (response("partial", finish="length"), "COMPLETION_LIMIT"),
    (response(calls=[call(arguments="invalid-json")]), "MALFORMED_TOOL_ARGUMENTS"),
    (response("SELECT 1", model="other"), "MODEL_IDENTITY_MISMATCH"),
    (response("SELECT 1", tokens=False), "USAGE_INCOMPLETE"),
])
def test_role_safe_failures_keep_observed_response(tmp_path, reply, error):
    tools, _ = make_tools(tmp_path)
    client = FakeClient([reply]); sink = []
    result = run_role("generator", "question", "prompt", tools, client, 5, lambda r,t: sink.append(t))
    assert result.error == error
    assert result.attempted_calls == 1
    assert result.response_count == (0 if isinstance(reply, Exception) else 1)
    assert len(sink) == result.response_count
    assert "credential-secret" not in json.dumps(result.__dict__)
    if error == "MALFORMED_TOOL_ARGUMENTS":
        assert result.usage[0]["response"]["tool_calls"][0]["function"]["arguments"] == "invalid-json"


def test_generator_failure_retains_linker_usage_and_no_gold(tmp_path):
    tools, _ = make_tools(tmp_path)
    client = FakeClient([response('{"tables":[{"table":"network_flows","columns":["source_dataset"]}],"grounded_values":[]}'), RuntimeError("secret")])
    result = run_case(case(gold="GOLD_SENTINEL"), "E1", tools, client, tools.schema_context())
    assert len(result["usage"]) == 1 and result["cost_unknown"]
    assert result["roles"]["linker"]["response_count"] == 1
    assert "tools" not in client.requests[1]
    assert "GOLD_SENTINEL" not in json.dumps(client.requests)


def test_turn_and_total_database_call_caps(tmp_path):
    tools, _ = make_tools(tmp_path)
    client = FakeClient([response(calls=[call("database_profiler", "{}", str(i))]) for i in range(6)])
    result = run_role("generator", "q", "p", tools, client, 99)
    assert result.error == "TURN_LIMIT" and len(client.requests) == 5
    assert result.tool_count == 5 and len(result.usage) == 5
    client = FakeClient([response(calls=[call("database_profiler", "{}", str(i)) for i in range(6)])])
    result = run_role("generator", "q", "p", tools, client, 5)
    assert result.error == "TOOL_LIMIT" and result.tool_count == 5
    assert len(result.trajectory) == 5 and len(result.usage) == 1


def test_actual_linker_gate_and_large_schema_without_column_heuristic(tmp_path):
    tools, _ = make_tools(tmp_path)
    selected = [{"table": "network_flows", "columns": ["source_dataset", "label", "protocol", "n"]}]
    client = FakeClient([response(calls=[call()]), response(json.dumps({"tables": selected, "grounded_values": [{"table":"network_flows","column":"source_dataset","value":"alpha"}]})), response("SELECT count(*) FROM network_flows")])
    result = run_case(case("Count Group 5 flows"), "E1", tools, client, tools.schema_context())
    assert result["error_category"] == "OK"
    assert len(result["usage"]) == 3
    assert result["linked_schema"]["grounded_values"][0]["evidence_id"]
    assert "syntax_valid" not in result


def test_live_client_boundary_closed_before_constructor(monkeypatch):
    from evaluation.dualsql_lite_ctu_gpt5_v2.experiment import create_client
    def forbidden(*a, **k):
        pytest.fail("created provider during offline remediation")
    monkeypatch.setattr("openai.OpenAI", forbidden)
    with pytest.raises(RuntimeError, match="PAID_EXECUTION_DISABLED"):
        create_client()


def test_linker_extra_fields_cannot_cross_validated_handoff(tmp_path):
    tools, _ = make_tools(tmp_path)
    payload = {"tables": [{"table": "network_flows", "columns": ["label"],
                           "final_sql": "SELECT 999", "unverified_value": "invented"}],
               "grounded_values": []}
    client = FakeClient([response(json.dumps(payload)), response("SELECT 1")])
    result = run_case(case(), "E1", tools, client, tools.schema_context())
    assert result["error_category"] == "INVALID_LINKED_SCHEMA"
    assert len(client.requests) == 1
    assert result["roles"]["generator"] is None
