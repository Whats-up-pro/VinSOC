"""Budget and immutable evidence series behavior with a tiny real snapshot."""

import json
from types import SimpleNamespace

import duckdb
import pytest

from evaluation.text_to_sql import SQLBenchmarkCase


@pytest.fixture
def snapshot(tmp_path):
    path = tmp_path / "snapshot.duckdb"
    with duckdb.connect(str(path)) as con:
        con.execute("CREATE TABLE network_flows(source_dataset VARCHAR, label VARCHAR)")
        con.execute("INSERT INTO network_flows VALUES ('ctu13_s5','flow=From-Botnet')")
    return path


def test_preflight_rejects_small_budget_before_first_paid_call(snapshot, tmp_path):
    from evaluation.dualsql_lite.experiment import ExperimentSeries

    class NoCallClient:
        def __init__(self):
            self.chat = SimpleNamespace(completions=SimpleNamespace(create=self.create))
            self.calls = 0

        def create(self, **kwargs):
            self.calls += 1
            raise AssertionError("Budget gate must block before API")

    client = NoCallClient()
    case = SQLBenchmarkCase("x", "Count flows", str(snapshot),
                            ("SELECT count(*) FROM network_flows",),
                            "aggregation", "basic", "scalar")
    with pytest.raises(ValueError, match="preflight.*budget"):
        ExperimentSeries(snapshot, [case], tmp_path / "artifacts", client,
                         identity={"benchmark_hash": "a", "scorer_hash": "b",
                                   "snapshot_content_hash": "c"}, budget_usd=0.00001).run()
    assert client.calls == 0


def test_append_only_e0_e3_reports_and_selection(snapshot, tmp_path):
    from evaluation.dualsql_lite.experiment import ExperimentSeries, select_winner

    linked = json.dumps({"tables": [{"table": "network_flows",
                                     "columns": ["source_dataset", "label"]}],
                         "grounded_values": []})
    sql = "SELECT count(*) FROM network_flows"
    contents = iter([sql, linked, sql, sql, linked, sql])

    class Client:
        def __init__(self):
            self.chat = SimpleNamespace(completions=SimpleNamespace(create=self.create))

        def create(self, **kwargs):
            return SimpleNamespace(model=kwargs["model"], usage=SimpleNamespace(
                prompt_tokens=100, completion_tokens=25),
                choices=[SimpleNamespace(message=SimpleNamespace(
                    content=next(contents), tool_calls=[]))])

    case = SQLBenchmarkCase("x", "Count flows", str(snapshot),
                            ("SELECT count(*) FROM network_flows",),
                            "aggregation", "basic", "scalar")
    output = tmp_path / "reports"
    reports = ExperimentSeries(snapshot, [case], output, Client(),
                               identity={"benchmark_hash": "a", "scorer_hash": "b",
                                         "snapshot_content_hash": "c"}, budget_usd=2).run()
    assert [r["experiment_id"] for r in reports] == ["E0", "E1", "E2", "E3"]
    assert all(r["metrics"]["execution_accuracy"] == 1 for r in reports)
    assert select_winner(reports)["experiment_id"] in {"E0", "E2"}
    assert len(list(output.glob("*.json"))) == 4
    with pytest.raises(FileExistsError):
        ExperimentSeries(snapshot, [case], output, Client(),
                         identity={"benchmark_hash": "a", "scorer_hash": "b",
                                   "snapshot_content_hash": "c"}, budget_usd=2).run()


def test_selection_prioritizes_accuracy_then_cost_calls_latency():
    from evaluation.dualsql_lite.experiment import select_winner

    reports = [
        {"experiment_id": name, "metrics": {"execution_accuracy": acc},
         "total_cost_usd": cost, "model_calls": calls, "latency_ms": latency}
        for name, acc, cost, calls, latency in [
            ("E0", .25, .1, 1, 10), ("E1", .5, .2, 3, 30),
            ("E2", .5, .1, 2, 20), ("E3", .5, .1, 2, 21)]
    ]
    assert select_winner(reports)["experiment_id"] == "E2"
    tied = [{**r, "latency_ms": 20, "model_calls": 2,
             "total_cost_usd": .1, "metrics": {"execution_accuracy": .5}}
            for r in reports]
    assert select_winner(tied)["experiment_id"] == "E0"


def test_budget_reservations_follow_role_turns_when_linker_finishes_early(snapshot):
    from evaluation.dualsql_lite.experiment import BudgetGate
    from evaluation.dualsql_lite.agents import GENERATOR_INSTRUCTIONS, LINKER_INSTRUCTIONS

    case = SQLBenchmarkCase("x", "Count flows", str(snapshot),
                            ("SELECT count(*) FROM network_flows",),
                            "aggregation", "basic", "scalar")
    gate = BudgetGate([case], "network_flows(source_dataset VARCHAR)", 2)
    gate.begin_case("E3", "x")
    for system, turn in [(LINKER_INSTRUCTIONS, 1)] + [(GENERATOR_INSTRUCTIONS, n)
                                                       for n in range(1, 6)]:
        request = {"model": "gpt-4.1-mini-2025-04-14", "temperature": 0,
                   "max_completion_tokens": 1000, "tools": [],
                   "messages": [{"role": "system", "content": system},
                                {"role": "user", "content": "Count flows"}] +
                               ([{"role": "assistant", "content": "x" * 6000},
                                 {"role": "tool", "content": "x" * 1650}] * (turn - 1))}
        gate.before_call(request)
        gate.after_call(request, {"input_tokens": 100, "cost_usd": .0001})
    gate.finish_case()
    assert gate.current is None
