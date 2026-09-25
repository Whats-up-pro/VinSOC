"""Configuration selection requires complete, comparable, immutable evidence."""

import json

import pytest


def test_selection_rejects_mixed_identity_and_incomplete_runs(tmp_path):
    from evaluation.dualsql_lite.selection import build_selection

    for name in ("E0", "E1", "E2", "E3"):
        (tmp_path / f"{name}.json").write_text(json.dumps({
            "experiment_id": name, "eligible": True, "run_status": "completed",
            "identity": {"benchmark_hash": "same", "git_commit": "abc"},
            "case_count": 8, "correct_cases": 5,
            "metrics": {"execution_accuracy": 5 / 8},
            "total_cost_usd": .01, "model_calls": 8, "latency_ms": 100,
        }))
    selected = build_selection(tmp_path)
    assert selected["selected_experiment"] == "E0"
    assert len(selected["artifact_sha256"]) == 4
    p = tmp_path / "E3.json"
    raw = json.loads(p.read_text())
    raw["identity"]["benchmark_hash"] = "different"
    p.write_text(json.dumps(raw))
    with pytest.raises(ValueError, match="identity"):
        build_selection(tmp_path)
    raw["identity"]["benchmark_hash"] = "same"
    raw["run_status"] = "invalid"
    p.write_text(json.dumps(raw))
    with pytest.raises(ValueError, match="completed"):
        build_selection(tmp_path)
