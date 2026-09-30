"""The actual v2 integration must preserve locked evaluator/comparator semantics."""
import pytest

from evaluation.dualsql_lite_ctu_gpt5_v2 import experiment
from evaluation.dualsql_lite_ctu_gpt5.tools import SnapshotOnlyDuckDBSnapshot
from evaluation.text_to_sql import evaluate_sql_case
from tests.r2_remediation_fixtures import FakeClient, case, make_tools, response


@pytest.mark.parametrize("sql,flags", [
    ("SELECT FROM", (False, False, False, False)),
    ("SELECT absent FROM network_flows", (True, False, False, False)),
    ("SELECT * FROM unknown_table", (True, False, False, True)),
    ("", (False, False, False, False)),
    ("SELECT 9", (True, True, False, False)),
    ("SELECT count(*) FROM network_flows", (True, True, True, False)),
    ("DELETE FROM network_flows", (True, False, False, True)),
])
def test_actual_score_record_uses_locked_evaluator(tmp_path, sql, flags):
    tools, _ = make_tools(tmp_path)
    record = {"case_id": "synthetic", "final_sql": sql, "error_category": "OK"}
    experiment.score_record(case(), record, SnapshotOnlyDuckDBSnapshot(tools.snapshot_path))
    assert tuple(record[k] for k in ("syntax_valid", "execution_success", "execution_accurate", "safety_rejected")) == flags


@pytest.mark.parametrize("sql", [
    "SELECT 1; SELECT 2", "DELETE FROM network_flows", "SELECT * FROM read_csv('external.csv')",
    "SELECT * FROM dataset_provenance", "SELECT * FROM information_schema.tables",
])
def test_probe_and_final_share_safety_boundary(tmp_path, sql, monkeypatch):
    tools, _ = make_tools(tmp_path)
    def forbidden(*a, **k):
        pytest.fail("unsafe SQL reached a DB execution")
    monkeypatch.setattr(tools, "_connect", forbidden)
    assert tools.sql_probe({"sql": sql})["error_type"] == "SAFETY_REJECTION"
    snapshot = SnapshotOnlyDuckDBSnapshot(tools.snapshot_path)
    monkeypatch.setattr(snapshot, "_connect", forbidden)
    result = evaluate_sql_case(case(), sql, snapshot)
    assert not result.execution_success
    assert result.safety_rejected or not result.syntax_valid


def test_order_duplicate_and_column_semantics_unchanged(tmp_path):
    tools, _ = make_tools(tmp_path)
    snapshot = SnapshotOnlyDuckDBSnapshot(tools.snapshot_path)
    gold = "SELECT n FROM network_flows ORDER BY n"
    ordered = case(gold=gold, comparator="ordered_rows")
    unordered = case(gold=gold, comparator="unordered_rows")
    assert not evaluate_sql_case(ordered, "SELECT n FROM network_flows ORDER BY n DESC", snapshot).execution_accurate
    assert evaluate_sql_case(unordered, "SELECT n FROM network_flows ORDER BY n DESC", snapshot).execution_accurate
    assert not evaluate_sql_case(unordered, "SELECT DISTINCT n FROM network_flows", snapshot).execution_accurate
    assert evaluate_sql_case(case(gold="SELECT count(*) AS a FROM network_flows"), "SELECT count(*) AS different FROM network_flows", snapshot).execution_accurate


def test_run_condition_scores_final_without_gold_in_request(tmp_path, monkeypatch):
    tools, manifest = make_tools(tmp_path)
    client = FakeClient([response("SELECT 9")])
    monkeypatch.setattr(experiment, "verify_dev_inputs", lambda *a: {"logical_snapshot_sha256": "fixture", "source_file_sha256": {"alpha": "fixture"}})
    report = experiment.run_condition("E0", [case(gold="SELECT 3 AS GOLD_SENTINEL")], tools.snapshot_path, client, tmp_path / "output", manifest)
    assert report["counts"]["execution_accurate"] == 0
    assert report["counts"]["execution_success"] == 1
    assert "GOLD_SENTINEL" not in str(client.requests)
