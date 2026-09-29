"""Offline integrity checks for the CTU S1/S4 frozen contract."""

from __future__ import annotations

import importlib
import json
from pathlib import Path

import duckdb
import pytest

from scripts.build_ctu_network_frozen_snapshot import build_ctu_network_frozen_snapshot
from tests.test_ctu_network_frozen_builder import _sources


def _contract():
    try:
        return importlib.import_module("evaluation.ctu_network_frozen.contract")
    except ModuleNotFoundError:
        pytest.fail("The offline frozen contract module is missing")


@pytest.fixture
def frozen_fixture(tmp_path):
    manifest, receipt = _sources(tmp_path)
    snapshot = tmp_path / "frozen.duckdb"
    build_ctu_network_frozen_snapshot(manifest, receipt, snapshot, tmp_path / "work")
    cases_dir = tmp_path / "cases"
    cases_dir.mkdir()
    for index in range(1, 9):
        tags = (
            ["scalar_filter", "stored_value_grounding"], ["distinct"],
            ["boolean_precedence"], ["bounded_time_interval"],
            ["aggregation_group_by"], ["order_by_limit"],
            ["multi_row_comparison"], ["stored_value_grounding"],
        )
        payload = {
            "case_id": f"frozen_sql_{index:03d}",
            "question": f"Count S1 flows for offline fixture {index}.",
            "database_snapshot": str(snapshot),
            "gold_sql": ["SELECT count(*) AS n FROM network_flows WHERE source_dataset = 'ctu13_s1'"],
            "category": "filter",
            "difficulty": "basic",
            "result_comparator": "scalar",
            "semantic_tags": tags[index - 1],
            "counterexample_sql": "SELECT -1 AS n",
        }
        (cases_dir / f"frozen_{index:03d}.json").write_text(
            json.dumps(payload) + "\n", encoding="utf-8"
        )
    return manifest, receipt, snapshot, cases_dir


def _lock(tmp_path, frozen_fixture, monkeypatch):
    manifest, receipt, snapshot, cases_dir = frozen_fixture
    monkeypatch.setattr("agent.provider.create_provider", lambda *a, **kw: pytest.fail("provider called"))
    contract = _contract()
    lock = contract.build_frozen_lock(
        snapshot, cases_dir, manifest_path=manifest, receipt_path=receipt
    )
    lock_path = tmp_path / "VERSION.lock"
    lock_path.write_text(json.dumps(lock, sort_keys=True) + "\n", encoding="utf-8")
    return contract, lock, lock_path


def test_offline_lock_captures_sources_cases_gold_and_comparators(tmp_path, frozen_fixture, monkeypatch):
    contract, lock, lock_path = _lock(tmp_path, frozen_fixture, monkeypatch)
    manifest, receipt, snapshot, cases_dir = frozen_fixture
    assert lock["source_row_counts"] == {"ctu13_s1": 1, "ctu13_s4": 1}
    assert lock["distinct_source_row_id"] == 2
    assert len(lock["case_file_sha256"]) == 8
    assert len(lock["gold_results"]) == 8
    assert set(lock["comparator_contract"]["cases"].values()) == {"scalar"}
    assert len(lock["semantic_counterexamples"]) == 8
    assert contract.validate_frozen_contract(
        snapshot, lock_path, cases_dir, manifest_path=manifest, receipt_path=receipt
    )["logical_snapshot_sha256"] == lock["logical_snapshot_sha256"]


@pytest.mark.parametrize("changed_field", [
    "source_url", "source_hash", "logical_snapshot", "distinct_count",
    "case_file", "gold_result", "comparator",
])
def test_changed_frozen_identity_is_rejected(tmp_path, frozen_fixture, monkeypatch, changed_field):
    contract, lock, lock_path = _lock(tmp_path, frozen_fixture, monkeypatch)
    manifest, receipt, snapshot, cases_dir = frozen_fixture
    if changed_field in {"source_url", "source_hash"}:
        payload = json.loads(manifest.read_text(encoding="utf-8"))
        field = "source_url" if changed_field == "source_url" else "file_sha256"
        payload["sources"][0][field] = "changed"
        manifest.write_text(json.dumps(payload), encoding="utf-8")
    elif changed_field == "logical_snapshot":
        with duckdb.connect(str(snapshot)) as conn:
            conn.execute("UPDATE network_flows SET label = 'changed' WHERE source_dataset = 'ctu13_s1'")
    elif changed_field == "distinct_count":
        lock["distinct_source_row_id"] += 1
        lock_path.write_text(json.dumps(lock), encoding="utf-8")
    elif changed_field in {"case_file", "comparator"}:
        path = cases_dir / "frozen_001.json"
        payload = json.loads(path.read_text(encoding="utf-8"))
        if changed_field == "case_file":
            payload["question"] = "Changed question"
        else:
            payload["result_comparator"] = "ordered_rows"
        path.write_text(json.dumps(payload), encoding="utf-8")
    else:
        lock["gold_results"]["frozen_sql_001"]["result_sha256"] = "0" * 64
        lock_path.write_text(json.dumps(lock), encoding="utf-8")
    with pytest.raises(ValueError):
        contract.validate_frozen_contract(
            snapshot, lock_path, cases_dir, manifest_path=manifest, receipt_path=receipt
        )


@pytest.mark.parametrize("case_change", ["duplicate", "missing"])
def test_duplicate_or_missing_case_id_is_rejected(tmp_path, frozen_fixture, monkeypatch, case_change):
    contract, _lock_data, _lock_path = _lock(tmp_path, frozen_fixture, monkeypatch)
    manifest, receipt, snapshot, cases_dir = frozen_fixture
    path = cases_dir / "frozen_008.json"
    if case_change == "duplicate":
        payload = json.loads(path.read_text(encoding="utf-8"))
        payload["case_id"] = "frozen_sql_007"
        path.write_text(json.dumps(payload), encoding="utf-8")
    else:
        path.unlink()
    with pytest.raises(ValueError, match="case|ID|eight"):
        contract.build_frozen_lock(
            snapshot, cases_dir, manifest_path=manifest, receipt_path=receipt
        )


def test_semantic_counterexample_must_differ_from_gold(tmp_path, frozen_fixture, monkeypatch):
    contract, _lock_data, _lock_path = _lock(tmp_path, frozen_fixture, monkeypatch)
    manifest, receipt, snapshot, cases_dir = frozen_fixture
    path = cases_dir / "frozen_001.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["counterexample_sql"] = payload["gold_sql"][0]
    path.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(ValueError, match="counterexample"):
        contract.build_frozen_lock(
            snapshot, cases_dir, manifest_path=manifest, receipt_path=receipt
        )
