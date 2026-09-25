"""Public_dev cases are distinct from legacy dev/frozen and keep source evidence."""

import json
from pathlib import Path

import duckdb

from evaluation.tool_calling.matching import compute_case_metrics
from evaluation.tool_calling.models import PredictedCall, ToolCallCase
from evaluation.tool_calling.metrics import compute_exact_call_prf
from evaluation.text_to_sql import SQLBenchmarkCase, _equivalent, evaluate_sql_case
from vinsoc_data.duckdb_store import DuckDBSnapshot


R1 = Path("evaluation/public_pilot/r1/public_dev")
R2 = Path("evaluation/public_pilot/r2/public_dev")


def _r1_cases():
    return [json.loads(path.read_text()) for path in sorted(R1.glob("*.json"))]


def test_public_r1_has_eight_network_eight_endpoint_four_no_tool():
    cases = _r1_cases()
    assert [c["case_id"] for c in cases] == [f"public_r1_{i:03d}" for i in range(1, 21)]
    assert [sum(c["category"] == category for c in cases) for category in (
        "network_only", "endpoint_only", "no_tool")] == [8, 8, 4]
    for case in cases:
        ToolCallCase.from_dict(case)
        assert all(call["tool"] != "cti_enrichment" for call in case["expected_calls"])
        if case["expected_calls"]:
            assert len(case["expected_calls"]) == 1
            assert len(case["evidence"]["normalized_row_sha256"]) == 64
            assert case["expected_calls"][0]["required_arguments"]["time_range"]


def test_public_r1_scorer_penalizes_extra_missing_wrong_arg_and_no_tool():
    first, no_tool = [ToolCallCase.from_dict(c) for c in (_r1_cases()[0], _r1_cases()[-1])]
    expected = first.expected_calls[0]
    correct = PredictedCall(expected.tool, expected.required_arguments)
    good = compute_case_metrics(first, [correct])
    assert good["trajectory_success"]
    for predictions in (
        [correct, PredictedCall("endpoint_investigation", {"host": "EXTRA"})],
        [],
        [PredictedCall(expected.tool, {**expected.required_arguments, "indicator": "8.8.8.8"})],
    ):
        bad = compute_case_metrics(first, predictions)
        assert not bad["trajectory_success"]
    abstain = compute_case_metrics(no_tool, [])
    wrong_abstain = compute_case_metrics(no_tool, [correct])
    assert abstain["trajectory_success"] and not wrong_abstain["trajectory_success"]


def test_public_r2_has_eight_unique_cases_and_comparators():
    cases = [SQLBenchmarkCase.from_dict(json.loads(p.read_text())) for p in sorted(R2.glob("*.json"))]
    assert [c.case_id for c in cases] == [f"public_sql_{i:03d}" for i in range(1, 9)]
    assert {c.result_comparator for c in cases} == {"scalar", "ordered_rows", "unordered_rows", "boolean"}
    assert all(c.database_snapshot == "data/public_pilot/snapshot.duckdb" for c in cases)
    assert not any(c.category == "cti" for c in cases)


def test_sql_semantic_traps_distinct_time_boolean_and_order(tmp_path):
    path = tmp_path / "trap.duckdb"
    with duckdb.connect(str(path)) as conn:
        conn.execute("CREATE TABLE events (id INT, item VARCHAR, time TIMESTAMP, a BOOLEAN, b BOOLEAN)")
        conn.execute("INSERT INTO events VALUES (1,'beta','2020-01-01 00:00:00',true,false),"
                     "(2,'alpha','2020-01-02 00:00:00',true,true),"
                     "(3,'alpha','2020-01-01 12:00:00',false,true)")
    snapshot = DuckDBSnapshot(path)
    traps = (
        ("SELECT DISTINCT item FROM events ORDER BY item", "SELECT item FROM events ORDER BY item", "ordered_rows"),
        ("SELECT count(*) FROM events WHERE time >= '2020-01-01' AND time < '2020-01-02'",
         "SELECT count(*) FROM events WHERE time >= '2020-01-01' AND time <= '2020-01-02'", "scalar"),
        ("SELECT count(*) FROM events WHERE a AND b", "SELECT count(*) FROM events WHERE a OR b", "scalar"),
        ("SELECT item FROM events ORDER BY item LIMIT 1", "SELECT item FROM events ORDER BY item DESC LIMIT 1", "ordered_rows"),
    )
    for index, (gold, wrong, comparator) in enumerate(traps):
        case = SQLBenchmarkCase(f"trap_{index}", "fixture", str(path), (gold,), "filter", "basic", comparator)
        assert evaluate_sql_case(case, gold, snapshot).execution_accurate
        assert not evaluate_sql_case(case, wrong, snapshot).execution_accurate
