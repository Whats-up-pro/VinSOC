"""Check that the selected CTU config is traceable to immutable run bytes."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from evaluation.ctu_network_public.contract import portable_text_sha256
from evaluation.dualsql_lite_ctu_gpt5.contract import verify_e0_baseline
from evaluation.dualsql_lite_ctu_gpt5.runner import ConditionReport, E0_REPORT
from evaluation.dualsql_lite_ctu_gpt5.selection import DRIFT_FIELDS, build_selection


ROOT = Path("results/evaluation_v1/ctu_network_public/dualsql_lite_ctu_gpt5_v1")
LOCK = Path("evaluation/dualsql_lite_ctu_gpt5/SELECTED_CONFIG.lock")
RUNS = {"E1": "36662231091", "E2": "36662683274", "E3": "36662943266"}


def test_selected_config_lock_is_derived_from_immutable_evidence():
    selected = json.loads(LOCK.read_text(encoding="utf-8"))
    baseline = verify_e0_baseline(E0_REPORT)
    reports = {}
    expected_hashes = {"E0": baseline.report_sha256}
    for condition, run_id in RUNS.items():
        path = ROOT / run_id / f"{condition}.json"
        raw = path.read_bytes()
        receipt = json.loads((path.parent / "receipt.json").read_text(encoding="utf-8"))
        digest = hashlib.sha256(raw).hexdigest()
        assert receipt["report_sha256"] == digest
        assert receipt["condition"] == condition
        assert receipt["run_id"] == run_id
        assert receipt["artifact_id"] > 0
        assert receipt["artifact_digest"].startswith("sha256:")
        assert receipt["implementation_sha"] == selected["implementation_sha"]
        assert selected["artifacts"][condition]["artifact_id"] == receipt["artifact_id"]
        assert selected["artifacts"][condition]["artifact_digest"] == receipt["artifact_digest"]
        expected_hashes[condition] = digest
        reports[condition] = ConditionReport(path, json.loads(raw))

    comparison = build_selection(baseline, reports["E1"], reports["E2"], reports["E3"])
    assert selected["report_sha256"] == expected_hashes
    assert selected["winner"] == comparison.winner == "E0"
    assert selected["implementation_sha"] == comparison.implementation_sha
    assert selected["selection_inputs"] == list(comparison.rows)
    assert selected["tie_break_trace"] == list(comparison.tiebreak_trace)
    assert selected["selection_order"] == comparison.payload["selection_order"]
    assert selected["comparison_identity"] == comparison.payload["identity"]
    assert selected["comparison_prompt_tool_catalog_identity"] == {
        key: reports["E1"].payload["provenance"][key] for key in DRIFT_FIELDS
    }

    config = selected["selected_config"]
    assert config["architecture"] == "one_shot_generator_no_tools"
    assert config["model"] == "gpt-5-mini-2025-08-07"
    assert config["reasoning_effort"] == "low"
    assert config["max_completion_tokens"] == 1000
    assert config["max_retries"] == 0
    assert config["temperature_parameter"] == "omitted"
    assert config["tool_access"] is False
    assert config["model_config_sha256"] == baseline.model_config_sha256
    assert config["system_prompt_sha256"] == baseline.system_prompt_sha256
    assert config["schema_context_sha256"] == baseline.schema_context_sha256
    assert config["runner_sha256"] == portable_text_sha256(
        Path("evaluation/ctu_network_public/run_model.py")
    )
    assert selected["frozen_status"] == "not_run"
