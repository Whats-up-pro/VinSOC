"""Identity regressions for the immutable CTU GPT-5 Mini E0 baseline."""

from __future__ import annotations

import copy
import hashlib
import importlib
import json
from pathlib import Path

import pytest


REPORT = Path("results/evaluation_v1/ctu_network_public/gpt5_e0/36520685612/ctu-r2-result.json")
DEV_LOCK = Path("evaluation/ctu_network_public/VERSION.lock")
REPORT_SHA256 = "33b35678171309c1a8958c1d9818499915986942e6936a03428df8fa0544bc15"


def _contract():
    try:
        return importlib.import_module("evaluation.dualsql_lite_ctu_gpt5.contract")
    except ModuleNotFoundError:
        pytest.fail("E0 compatibility contract is missing")


def _lock_payload():
    report = json.loads(REPORT.read_text(encoding="utf-8"))
    dev = json.loads(DEV_LOCK.read_text(encoding="utf-8"))
    return {
        "version": "dualsql_lite_ctu_gpt5_v1",
        "e0_report_sha256": REPORT_SHA256,
        "e0_run_id": "36520685612",
        "dev_version": "ctu_network_public_dev_v1",
        "case_ids": dev["case_ids"],
        "split_sha256": dev["split_sha256"],
        "logical_snapshot_sha256": dev["logical_snapshot_sha256"],
        "source_file_sha256": dev["source_file_sha256"],
        "builder_scorer_sha256": dev["builder_scorer_sha256"],
        "system_prompt_sha256": report["provenance"]["system_prompt_sha256"],
        "schema_context_sha256": report["provenance"]["schema_context_sha256"],
        "model_config_sha256": report["model_config_sha256"],
        "model": "gpt-5-mini-2025-08-07",
        "reasoning_effort": "low",
        "max_completion_tokens": 1000,
        "max_retries": 0,
        "pricing": {
            "input_usd_per_million": 0.25,
            "output_usd_per_million": 2.0,
            "source": "https://developers.openai.com/api/docs/models/gpt-5-mini",
            "verified_utc": "2026-09-29T10:33:37Z",
            "stop_if_current_official_price_differs": True,
        },
    }


def _write_variant(tmp_path, payload, lock, *, update_report_sha=True):
    report_path = tmp_path / "e0.json"
    report_path.write_text(json.dumps(payload, sort_keys=True) + "\n", encoding="utf-8")
    if update_report_sha:
        lock["e0_report_sha256"] = hashlib.sha256(report_path.read_bytes()).hexdigest()
    lock_path = tmp_path / "SERIES.lock"
    lock_path.write_text(json.dumps(lock) + "\n", encoding="utf-8")
    return report_path, lock_path


def test_exact_e0_report_is_accepted_without_provider(monkeypatch, tmp_path):
    monkeypatch.setattr("agent.provider.create_provider", lambda *a, **kw: pytest.fail("provider called"))
    contract = _contract()
    lock_path = tmp_path / "SERIES.lock"
    lock_path.write_text(json.dumps(_lock_payload()) + "\n", encoding="utf-8")
    result = contract.verify_e0_baseline(REPORT, lock_path)
    assert result.run_id == "36520685612"
    assert result.case_ids == tuple(f"ctu_sql_{index:03d}" for index in range(1, 9))
    assert result.execution_accurate == 0
    assert result.known_cost_usd == pytest.approx(0.00384725)
    assert result.report_sha256 == REPORT_SHA256


@pytest.mark.parametrize("field", [
    "report_sha", "run_status", "case_ids", "case_result_ids", "usage_records",
    "actual_model", "requested_model", "reasoning_effort", "token_cap",
    "sdk_retries", "split_hash", "snapshot_hash", "source_hash",
    "scorer_hash", "system_prompt_hash", "schema_hash", "model_config_hash",
    "request_model", "request_reasoning", "request_cap", "request_temperature",
    "request_question", "pricing_rate",
])
def test_e0_identity_mutation_is_rejected(tmp_path, field):
    contract = _contract()
    payload = copy.deepcopy(json.loads(REPORT.read_text(encoding="utf-8")))
    lock = _lock_payload()
    if field == "report_sha":
        lock["e0_report_sha256"] = "0" * 64
    elif field == "run_status":
        payload["run_status"] = "partial"
    elif field == "case_ids":
        payload["case_ids"][7] = "ctu_sql_007"
    elif field == "case_result_ids":
        payload["case_results"][7]["case_id"] = "ctu_sql_007"
    elif field == "usage_records":
        payload["case_results"][0]["input_tokens"] = 0
    elif field == "actual_model":
        payload["case_results"][0]["actual_model"] = "different-model"
    elif field == "requested_model":
        payload["config"]["model"] = "different-model"
    elif field == "reasoning_effort":
        payload["config"]["reasoning_effort"] = "high"
    elif field == "token_cap":
        payload["config"]["max_completion_tokens"] = 999
    elif field == "sdk_retries":
        payload["config"]["max_retries"] = 1
    elif field == "split_hash":
        payload["provenance"]["split_sha256"] = "0" * 64
    elif field == "snapshot_hash":
        payload["provenance"]["logical_snapshot_sha256"] = "0" * 64
    elif field == "source_hash":
        payload["provenance"]["source_file_sha256"]["ctu13_s5"] = "0" * 64
    elif field == "scorer_hash":
        payload["provenance"]["builder_scorer_sha256"]["evaluation/text_to_sql.py"] = "0" * 64
    elif field == "system_prompt_hash":
        payload["provenance"]["system_prompt_sha256"] = "0" * 64
    elif field == "schema_hash":
        payload["provenance"]["schema_context_sha256"] = "0" * 64
    elif field == "model_config_hash":
        payload["model_config_sha256"] = "0" * 64
    elif field == "request_model":
        payload["serialized_requests"][0]["model"] = "different-model"
    elif field == "request_reasoning":
        payload["serialized_requests"][0]["reasoning_effort"] = "high"
    elif field == "request_cap":
        payload["serialized_requests"][0]["max_completion_tokens"] = 999
    elif field == "request_temperature":
        payload["serialized_requests"][0]["temperature"] = 0
    elif field == "request_question":
        payload["serialized_requests"][0]["messages"][1]["content"] = "changed"
    elif field == "pricing_rate":
        payload["pricing"]["input_usd_per_million"] = 0.15
    report_path, lock_path = _write_variant(
        tmp_path, payload, lock, update_report_sha=field != "report_sha"
    )
    expected_error = {
        "report_sha": "fixed report SHA-256",
        "run_status": "run status",
        "case_ids": "case IDs",
        "case_result_ids": "case result IDs",
        "usage_records": "case 1 usage",
        "actual_model": "case 1 response identity",
        "requested_model": "config model",
        "reasoning_effort": "config reasoning_effort",
        "token_cap": "config max_completion_tokens",
        "sdk_retries": "config max_retries",
        "split_hash": "split_sha256",
        "snapshot_hash": "logical_snapshot_sha256",
        "source_hash": "source_file_sha256",
        "scorer_hash": "builder_scorer_sha256",
        "system_prompt_hash": "system_prompt_sha256",
        "schema_hash": "schema_context_sha256",
        "model_config_hash": "model_config_sha256",
        "request_model": "request 1 model",
        "request_reasoning": "request 1 reasoning_effort",
        "request_cap": "request 1 max_completion_tokens",
        "request_temperature": "request 1 forbidden keys",
        "request_question": "request 1 question",
        "pricing_rate": "pricing rates",
    }[field]
    with pytest.raises(ValueError, match=expected_error):
        contract.verify_e0_baseline(report_path, lock_path)


def test_e0_descriptive_null_temperature_is_allowed(tmp_path):
    contract = _contract()
    payload = json.loads(REPORT.read_text(encoding="utf-8"))
    assert payload["config"]["temperature"] is None
    assert all("temperature" not in request for request in payload["serialized_requests"])
    lock_path = tmp_path / "SERIES.lock"
    lock_path.write_text(json.dumps(_lock_payload()), encoding="utf-8")
    assert contract.verify_e0_baseline(REPORT, lock_path).report_sha256 == REPORT_SHA256


DEV_SNAPSHOT = Path("data/ctu_network_public/snapshots/ctu_dev.duckdb")


def _tools():
    module = importlib.import_module("evaluation.dualsql_lite_ctu_gpt5.tools")
    try:
        return module.CTUDatabaseTools(DEV_SNAPSHOT)
    except AttributeError:
        pytest.fail("CTUDatabaseTools boundary is missing")


def test_ctu_tools_expose_only_network_flows_and_real_dev_values():
    tools = _tools()
    profile = tools.database_profiler({})
    assert profile["ok"] is True
    assert [table["name"] for table in profile["tables"]] == ["network_flows"]
    assert all("type" in column for column in profile["tables"][0]["columns"])
    sources = tools.value_search({"query": "ctu13_s5", "column": "source_dataset"})
    labels = tools.value_search({"query": "From-Botnet", "column": "label"})
    protocols = tools.value_search({"query": "TCP", "column": "protocol"})
    assert any(item["value"] == "ctu13_s5" for item in sources["matches"])
    assert any("flow=From-Botnet" in item["value"] for item in labels["matches"])
    assert any(item["value"] == "TCP" for item in protocols["matches"])
    assert all(item["table"] == "network_flows" for result in
               (sources, labels, protocols) for item in result["matches"])
    assert len({profile["evidence_id"], sources["evidence_id"],
                labels["evidence_id"], protocols["evidence_id"]}) == 4
    assert all(item["evidence_id"] == result["evidence_id"] for result in
               (sources, labels, protocols) for item in result["matches"])


def test_ctu_catalog_hash_is_deterministic_and_schema_has_no_frozen_hints():
    first, second = _tools(), _tools()
    assert first.catalog_sha256 == second.catalog_sha256
    assert len(first.catalog_sha256) == 64
    module = importlib.import_module("evaluation.dualsql_lite_ctu_gpt5.tools")
    schema_text = json.dumps(module.TOOL_SCHEMAS)
    assert "ctu13_s1" not in schema_text and "ctu13_s4" not in schema_text
    assert {item["function"]["name"] for item in module.TOOL_SCHEMAS} == {
        "database_profiler", "value_search", "sql_probe"
    }


def test_ctu_sql_probe_limits_rows_and_response_bytes():
    tools = _tools()
    result = tools.sql_probe({"sql": "SELECT source_row_id FROM network_flows ORDER BY source_row_id"})
    assert result["ok"] is True
    assert len(result["rows"]) == 20
    assert result["truncated"] is True
    assert len(json.dumps(result, default=str).encode("utf-8")) <= 1650
    oversized = tools.sql_probe({"sql": "SELECT repeat('x', 3000) AS payload FROM network_flows LIMIT 1"})
    assert oversized == {"ok": False, "error_type": "OUTPUT_LIMIT"}


@pytest.mark.parametrize("sql", [
    "DELETE FROM network_flows",
    "SELECT * FROM dataset_provenance",
    "SELECT * FROM information_schema.tables",
    "SELECT * FROM read_csv('https://example.com/data.csv')",
    "SELECT * FROM cti_indicators",
])
def test_ctu_sql_probe_rejects_non_snapshot_or_mutating_sql(sql):
    result = _tools().sql_probe({"sql": sql})
    assert result == {"ok": False, "error_type": "SAFETY_REJECTION"}


def test_ctu_tool_execution_error_suppresses_duckdb_details():
    result = _tools().sql_probe({"sql": "SELECT nonexistent_column FROM network_flows"})
    assert result == {"ok": False, "error_type": "EXECUTION_ERROR"}


def test_ctu_tool_rejects_unknown_arguments_and_tables():
    tools = _tools()
    assert tools.invoke("value_search", {"query": "TCP", "extra": True}) == {
        "ok": False, "error_type": "INVALID_ARGUMENTS"
    }
    assert tools.database_profiler({"table": "dataset_provenance"}) == {
        "ok": False, "error_type": "INVALID_ARGUMENTS"
    }


class _RoleClient:
    def __init__(self, *messages):
        from types import SimpleNamespace

        self.messages = iter(messages)
        self.max_retries = 0
        self.requests = []
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self.create))

    def create(self, **request):
        from types import SimpleNamespace

        self.requests.append(request)
        message = next(self.messages)
        return SimpleNamespace(id=f"chatcmpl-{len(self.requests)}", model="gpt-5-mini-2025-08-07",
                               usage=SimpleNamespace(prompt_tokens=100, completion_tokens=50),
                               choices=[SimpleNamespace(message=message)])


def _role_message(content=None, calls=()):
    from types import SimpleNamespace

    tool_calls = [SimpleNamespace(id=f"tool-{index}", type="function",
                                  function=SimpleNamespace(name=name, arguments=arguments))
                  for index, (name, arguments) in enumerate(calls, 1)]
    return SimpleNamespace(content=content, tool_calls=tool_calls)


def _run_test_role(client, *, role="generator", tools=None, question="Count TCP flows", max_turns=5):
    from evaluation.dualsql_lite_ctu_gpt5.agents import run_role

    charged = []
    result = run_role(role=role, question=question, system_prompt="Use network_flows.",
                      tools=tools, client=client, telemetry_sink=charged.append,
                      max_turns=max_turns)
    return result, charged


def test_ctu_role_two_native_tool_calls_in_one_turn_and_fixed_request():
    client = _RoleClient(
        _role_message(calls=[("database_profiler", "{}"),
                             ("value_search", '{"query":"TCP","column":"protocol"}')]),
        _role_message(content="SELECT count(*) FROM network_flows"),
    )
    result, charged = _run_test_role(client, tools=_tools())
    assert result.content == "SELECT count(*) FROM network_flows"
    assert result.model_turns == 2 and result.db_tool_calls == 2
    assert len(result.trajectory) == 2 and len(charged) == 2
    assert all(call.response_id and call.cost_usd > 0 for call in charged)
    assert all(request["model"] == "gpt-5-mini-2025-08-07" and
               request["reasoning_effort"] == "low" and
               request["max_completion_tokens"] == 1000 and
               "temperature" not in request for request in client.requests)


def test_ctu_role_sixth_tool_call_is_blocked_after_charged_response():
    five = [("sql_probe", '{"sql":"SELECT 1"}')] * 5
    client = _RoleClient(_role_message(calls=five),
                         _role_message(calls=[("database_profiler", "{}")]))
    result, charged = _run_test_role(client, tools=_tools())
    assert result.error == "TOOL_LIMIT" and result.db_tool_calls == 5
    assert len(charged) == 2


def test_ctu_role_sixth_model_turn_is_blocked():
    client = _RoleClient(*[_role_message(calls=[("database_profiler", "{}")]) for _ in range(5)])
    result, charged = _run_test_role(client, tools=_tools())
    assert result.error == "TURN_LIMIT"
    assert result.model_turns == 5 and len(charged) == 5 and len(client.requests) == 5


def test_ctu_linker_grounding_is_controller_owned_and_question_literals_are_separate():
    tools = _tools()
    link = '{"tables":[{"table":"network_flows","columns":["source_dataset","protocol"]}]}'
    client = _RoleClient(
        _role_message(calls=[("value_search", '{"query":"ctu13_s5","column":"source_dataset"}')]),
        _role_message(content=link),
    )
    result, _ = _run_test_role(client, role="linker", tools=tools,
                               question="Count flows where protocol is 'TCP'")
    assert result.error is None and result.selected_schema == [
        {"table": "network_flows", "columns": ["source_dataset", "protocol"]}
    ]
    assert result.question_literals == [{"value": "TCP", "evidence_class": "question"}]
    assert any(value["value"] == "ctu13_s5" and value["evidence_id"].startswith("ev-")
               for value in result.grounded_values)
    assert "GOLD_ONLY_SENTINEL" not in json.dumps(client.requests)
    assert all("grounded_values" not in request["messages"][-1].get("content", "")
               for request in client.requests[:1])


def test_ctu_linker_rejects_invented_value_in_final_submission():
    client = _RoleClient(_role_message(content=json.dumps({
        "tables": [{"table": "network_flows", "columns": ["label"]}],
        "grounded_values": [{"table": "network_flows", "column": "label", "value": "invented"}],
    })))
    result, charged = _run_test_role(client, role="linker", tools=_tools())
    assert result.error == "INVALID_LINKED_SCHEMA" and len(charged) == 1


def test_ctu_role_persists_usage_before_malformed_tool_arguments():
    client = _RoleClient(_role_message(calls=[("value_search", "{bad json")]),
                         _role_message(content="SELECT 1"))
    result, charged = _run_test_role(client, tools=_tools())
    assert len(charged) == 2 and charged[0].response_id == "chatcmpl-1"
    assert charged[0].input_tokens == 100 and charged[0].output_tokens == 50
    assert result.error is None and result.malformed == 1
    assert result.trajectory[0]["result"]["error_type"] == "INVALID_ARGUMENTS"


def test_ctu_role_omits_tools_for_no_tool_generator():
    client = _RoleClient(_role_message(content="SELECT 1"))
    result, _ = _run_test_role(client, tools=None, max_turns=1)
    assert result.content == "SELECT 1"
    assert "tools" not in client.requests[0]


def test_ctu_runner_rejects_invalid_condition_and_existing_output_before_provider(tmp_path):
    from evaluation.dualsql_lite_ctu_gpt5.runner import run_condition

    created = []
    factory = lambda: created.append(True)
    output = tmp_path / "result.json"
    with pytest.raises(ValueError, match="condition"):
        run_condition("E0", tmp_path / "missing.duckdb", output, factory, {})
    output.write_text("immutable", encoding="utf-8")
    with pytest.raises(FileExistsError):
        run_condition("E1", tmp_path / "missing.duckdb", output, factory, {})
    assert output.read_text(encoding="utf-8") == "immutable" and not created


def test_ctu_runner_preflight_covers_all_call_slots_under_series_ceiling():
    from evaluation.dualsql_lite_ctu_gpt5.runner import conservative_preflight

    bounds = conservative_preflight("network_flows(source_dataset VARCHAR, label VARCHAR)")
    assert {name: item["max_calls"] for name, item in bounds.items()} == {
        "E1": 48, "E2": 40, "E3": 80
    }
    assert sum(item["ceiling_usd"] for item in bounds.values()) < 0.75
    assert all(item["ceiling_usd"] > 0 for item in bounds.values())


def test_ctu_runner_preflight_blocks_provider_creation_on_bad_snapshot(tmp_path):
    from evaluation.dualsql_lite_ctu_gpt5.runner import run_condition

    created = []
    with pytest.raises((ValueError, FileNotFoundError)):
        run_condition("E1", tmp_path / "missing.duckdb", tmp_path / "result.json",
                      lambda: created.append(True), {})
    assert not created and not (tmp_path / "result.json").exists()


def test_ctu_runner_records_charged_partial_on_provider_failure(tmp_path, monkeypatch):
    from evaluation.dualsql_lite_ctu_gpt5 import runner
    import duckdb

    snapshot = tmp_path / "small.duckdb"
    with duckdb.connect(str(snapshot)) as connection:
        connection.execute("CREATE TABLE network_flows(source_dataset VARCHAR, label VARCHAR)")
        connection.execute("INSERT INTO network_flows VALUES ('ctu13_s5', 'flow=Normal')")
    case = _runner_case()
    monkeypatch.setattr(runner, "_verified_inputs", lambda *_: ([case], _runner_identity()))

    class FailingClient:
        def __init__(self):
            from types import SimpleNamespace

            self.calls = 0
            self.max_retries = 0
            self.chat = SimpleNamespace(completions=SimpleNamespace(create=self.create))

        def create(self, **request):
            from types import SimpleNamespace

            self.calls += 1
            if self.calls == 1:
                return SimpleNamespace(
                    id="chatcmpl-test", model="gpt-5-mini-2025-08-07",
                    usage=SimpleNamespace(prompt_tokens=100, completion_tokens=50),
                    choices=[SimpleNamespace(message=_role_message(
                        calls=[("value_search", "{malformed")]))],
                )
            raise RuntimeError("simulated provider outage")

    client = FailingClient()
    output = tmp_path / "result.json"
    with pytest.raises(RuntimeError, match="simulated provider outage"):
        runner.run_condition("E2", snapshot, output, lambda: client, _runner_lock())
    partial = json.loads((tmp_path / "result.partial.json").read_text(encoding="utf-8"))
    assert partial["run_status"] == "partial"
    assert partial["provider_calls"][0]["response_id"] == "chatcmpl-test"
    assert partial["known_cost_usd"] == pytest.approx(0.000125)
    assert client.calls == 2 and not output.exists()


def _runner_case():
    from evaluation.text_to_sql import SQLBenchmarkCase

    return SQLBenchmarkCase(case_id="ctu_sql_001", question="Count rows",
                            database_snapshot="small.duckdb",
                            gold_sql=("SELECT count(*) FROM network_flows",),
                            category="network", difficulty="basic",
                            result_comparator="scalar")


def _runner_identity():
    return {"split_sha256": "a" * 64, "logical_snapshot_sha256": "b" * 64,
            "source_file_sha256": {"ctu13_s5": "c" * 64},
            "builder_scorer_sha256": {"evaluation/text_to_sql.py": "d" * 64},
            "case_ids": ["ctu_sql_001"], "e0_report_sha256": "e" * 64}


def _runner_lock():
    return {"model": "gpt-5-mini-2025-08-07", "reasoning_effort": "low",
            "max_completion_tokens": 1000, "max_retries": 0,
            "pricing": {"input_usd_per_million": 0.25,
                        "output_usd_per_million": 2.0,
                        "source": "https://developers.openai.com/api/docs/models/gpt-5-mini",
                        "verified_utc": "2026-09-29T10:33:37Z"},
            "runtime_gates": {"current_input_usd_per_million": 0.25,
                              "current_output_usd_per_million": 2.0,
                              "pricing_checked_utc": "2026-09-30T00:00:00Z",
                              "credit_checked_utc": "2026-09-30T00:00:00Z",
                              "organization_project_verified": True,
                              "usable_credit_usd": 2.0,
                              "spend_limit_remaining_usd": 2.0,
                              "cumulative_known_usd": 0.01979725,
                              "total_authorized_usd": 2.0}}


@pytest.mark.parametrize("condition,expected_calls", [("E1", 2), ("E2", 1), ("E3", 2)])
def test_ctu_runner_condition_semantics_and_complete_identity(
    tmp_path, monkeypatch, condition, expected_calls
):
    from evaluation.dualsql_lite_ctu_gpt5 import runner
    import duckdb

    snapshot = tmp_path / "small.duckdb"
    with duckdb.connect(str(snapshot)) as connection:
        connection.execute("CREATE TABLE network_flows(source_dataset VARCHAR, label VARCHAR)")
        connection.execute("INSERT INTO network_flows VALUES ('ctu13_s5', 'flow=Normal')")
    monkeypatch.setattr(runner, "_verified_inputs", lambda *_: ([_runner_case()], _runner_identity()))
    messages = []
    if condition in {"E1", "E3"}:
        messages.append(_role_message(content='{"tables":[{"table":"network_flows","columns":["label"]}]}'))
    messages.append(_role_message(content="SELECT count(*) FROM network_flows"))
    client = _RoleClient(*messages)
    output = tmp_path / "result.json"
    result = runner.run_condition(condition, snapshot, output, lambda: client, _runner_lock())
    payload = json.loads(output.read_text(encoding="utf-8"))
    assert result.execution_accurate == 1 and payload["run_status"] == "complete"
    assert payload["metrics"]["execution_accurate"] == 1
    assert len(payload["provider_calls"]) == expected_calls == len(client.requests)
    assert payload["case_ids"] == ["ctu_sql_001"]
    assert payload["provenance"]["catalog_sha256"]
    assert payload["provenance"]["tool_implementation_sha256"]
    assert payload["provenance"]["schema_context_sha256"]
    assert payload["provenance"]["split_sha256"] == "a" * 64
    assert payload["model_contract"]["max_retries"] == 0
    assert payload["known_cost_usd"] == pytest.approx(expected_calls * 0.000125)
    assert len(payload["serialized_requests"]) == expected_calls
    assert all("temperature" not in request for request in payload["serialized_requests"])
    assert all("gold_sql" not in json.dumps(request) for request in payload["serialized_requests"])
    if condition == "E1":
        assert "tools" in client.requests[0] and "tools" not in client.requests[1]
    elif condition == "E2":
        assert "tools" in client.requests[0]
    else:
        assert all("tools" in request for request in client.requests)
    with pytest.raises(FileExistsError):
        runner.run_condition(condition, snapshot, output, lambda: client, _runner_lock())


@pytest.mark.parametrize("failure", ["wrong_model", "usage_mismatch"])
def test_ctu_runner_keeps_charged_identity_error_in_partial(tmp_path, monkeypatch, failure):
    from evaluation.dualsql_lite_ctu_gpt5 import runner
    from types import SimpleNamespace
    import duckdb

    snapshot = tmp_path / "small.duckdb"
    with duckdb.connect(str(snapshot)) as connection:
        connection.execute("CREATE TABLE network_flows(source_dataset VARCHAR, label VARCHAR)")
        connection.execute("INSERT INTO network_flows VALUES ('ctu13_s5', 'flow=Normal')")
    monkeypatch.setattr(runner, "_verified_inputs", lambda *_: ([_runner_case()], _runner_identity()))

    class BadClient:
        def __init__(self):
            self.max_retries = 0
            self.chat = SimpleNamespace(completions=SimpleNamespace(create=self.create))

        def create(self, **request):
            usage = SimpleNamespace(prompt_tokens=100, completion_tokens=50,
                                    total_tokens=151 if failure == "usage_mismatch" else 150)
            return SimpleNamespace(id="chatcmpl-bad",
                model="wrong-model" if failure == "wrong_model" else "gpt-5-mini-2025-08-07",
                usage=usage,
                choices=[SimpleNamespace(message=_role_message(content="SELECT 1"))])

    output = tmp_path / "result.json"
    with pytest.raises(ValueError):
        runner.run_condition("E2", snapshot, output, lambda: BadClient(), _runner_lock())
    partial = json.loads((tmp_path / "result.partial.json").read_text(encoding="utf-8"))
    assert partial["run_status"] == "partial" and not output.exists()
    if failure == "wrong_model":
        assert partial["provider_calls"][0]["actual_model"] == "wrong-model"
        assert partial["known_cost_usd"] == pytest.approx(0.000125)
    else:
        assert partial["cost_unknown"] is True


def test_ctu_runner_rejects_sdk_retries_before_first_model_call(tmp_path, monkeypatch):
    from evaluation.dualsql_lite_ctu_gpt5 import runner
    import duckdb

    snapshot = tmp_path / "small.duckdb"
    with duckdb.connect(str(snapshot)) as connection:
        connection.execute("CREATE TABLE network_flows(source_dataset VARCHAR, label VARCHAR)")
    monkeypatch.setattr(runner, "_verified_inputs", lambda *_: ([_runner_case()], _runner_identity()))
    client = _RoleClient(_role_message(content="SELECT 1"))
    client.max_retries = 2
    with pytest.raises(ValueError, match="SDK retries"):
        runner.run_condition("E2", snapshot, tmp_path / "result.json", lambda: client, _runner_lock())
    assert client.requests == []
