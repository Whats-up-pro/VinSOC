"""Offline selection and manual-dispatch contract for the CTU comparison."""

from __future__ import annotations

import copy
from pathlib import Path

import pytest

from evaluation.dualsql_lite_ctu_gpt5.contract import BaselineEvidence
from evaluation.dualsql_lite_ctu_gpt5.runner import ConditionReport

WORKFLOW = Path(".github/workflows/r2-dualsql-ctu-gpt5.yml")


def _e0(*, score=2, cost=0.01, calls=8, latency=1000.0):
    return BaselineEvidence(
        run_id="36520685612",
        case_ids=tuple(f"ctu_sql_{index:03d}" for index in range(1, 9)),
        execution_accurate=score,
        known_cost_usd=cost,
        report_sha256="a" * 64,
        logical_snapshot_sha256="b" * 64,
        split_sha256="c" * 64,
        model_config_sha256="d" * 64,
        system_prompt_sha256="e" * 64,
        schema_context_sha256="f" * 64,
        model_calls=calls,
        latency_ms=latency,
        source_file_sha256={"ctu13_s5": "1" * 64, "ctu13_s7": "2" * 64},
        builder_scorer_sha256={"evaluation/text_to_sql.py": "3" * 64},
    )


def _condition(name, *, score=2, cost=0.02, calls=9, latency=1100.0):
    case_ids = [f"ctu_sql_{index:03d}" for index in range(1, 9)]
    provider_calls = [{
        "response_id": f"resp-{index}",
        "actual_model": "gpt-5-mini-2025-08-07",
        "input_tokens": 100,
        "output_tokens": 50,
        "cost_usd": cost / calls,
        "latency_ms": latency / calls,
    } for index in range(calls)]
    payload = {
        "run_status": "complete",
        "condition": name,
        "implementation_sha": "4" * 40,
        "case_ids": case_ids,
        "case_results": [{
            "case_id": case_id,
            "execution_accurate": index < score,
            "syntax_valid": True,
            "execution_success": True,
            "safety_rejected": False,
            "error_category": "NONE",
        } for index, case_id in enumerate(case_ids)],
        "metrics": {
            "execution_accurate": score,
            "syntax_valid": 8,
            "execution_success": 8,
            "safety_rejected": 0,
        },
        "known_cost_usd": cost,
        "cost_unknown": False,
        "attempted_calls": calls,
        "provider_calls": provider_calls,
        "model_contract": {
            "model": "gpt-5-mini-2025-08-07",
            "reasoning_effort": "low",
            "max_completion_tokens": 1000,
            "max_retries": 0,
        },
        "model_config_sha256": "d" * 64,
        "provenance": {
            "e0_report_sha256": "a" * 64,
            "logical_snapshot_sha256": "b" * 64,
            "split_sha256": "c" * 64,
            "schema_context_sha256": "f" * 64,
            "source_file_sha256": {"ctu13_s5": "1" * 64, "ctu13_s7": "2" * 64},
            "builder_scorer_sha256": {"evaluation/text_to_sql.py": "3" * 64},
            "model_config_sha256": "d" * 64,
            "linker_prompt_sha256": "6" * 64,
            "generator_prompt_sha256": "7" * 64,
            "tool_schema_sha256": "8" * 64,
            "tool_implementation_sha256": "9" * 64,
            "tool_version": "dualsql_lite_ctu_gpt5_tools_v2",
            "catalog_sha256": "0" * 64,
        },
    }
    return ConditionReport(Path(f"{name}.json"), payload)


@pytest.mark.parametrize("field,values,winner", [
    ("score", (3, 2, 2), "E1"),
    ("cost", (0.03, 0.01, 0.02), "E2"),
    ("calls", (10, 8, 9), "E2"),
    ("latency", (1300.0, 900.0, 1100.0), "E2"),
])
def test_selection_tiebreak_order(field, values, winner):
    from evaluation.dualsql_lite_ctu_gpt5.selection import build_selection

    options = {name: {field: value} for name, value in zip(("E1", "E2", "E3"), values)}
    conditions = [_condition(name, **options[name]) for name in ("E1", "E2", "E3")]
    result = build_selection(_e0(score=0, cost=0.5, calls=100, latency=10000), *conditions)
    assert result.winner == winner


def test_selection_simplest_condition_wins_exact_tie():
    from evaluation.dualsql_lite_ctu_gpt5.selection import build_selection

    result = build_selection(
        _e0(score=2, cost=0.02, calls=9, latency=1100),
        _condition("E1"), _condition("E2"), _condition("E3"),
    )
    assert result.winner == "E0"


@pytest.mark.parametrize("mutation", [
    "partial", "case_ids", "snapshot", "split", "sources", "scorer",
    "model", "model_config", "sha", "prompt", "tool", "catalog",
    "usage", "score",
])
def test_selection_rejects_incompatible_evidence(mutation):
    from evaluation.dualsql_lite_ctu_gpt5.selection import build_selection

    reports = [_condition(name) for name in ("E1", "E2", "E3")]
    changed = copy.deepcopy(reports[1].payload)
    if mutation == "partial":
        changed["run_status"] = "partial"
    elif mutation == "case_ids":
        changed["case_ids"][0] = "different"
    elif mutation == "snapshot":
        changed["provenance"]["logical_snapshot_sha256"] = "z" * 64
    elif mutation == "split":
        changed["provenance"]["split_sha256"] = "z" * 64
    elif mutation == "sources":
        changed["provenance"]["source_file_sha256"]["ctu13_s5"] = "z" * 64
    elif mutation == "scorer":
        changed["provenance"]["builder_scorer_sha256"]["evaluation/text_to_sql.py"] = "z" * 64
    elif mutation == "model":
        changed["model_contract"]["model"] = "wrong"
    elif mutation == "model_config":
        changed["model_config_sha256"] = "z" * 64
    elif mutation == "sha":
        changed["implementation_sha"] = "z" * 40
    elif mutation == "prompt":
        changed["provenance"]["generator_prompt_sha256"] = "z" * 64
    elif mutation == "tool":
        changed["provenance"]["tool_schema_sha256"] = "z" * 64
    elif mutation == "catalog":
        changed["provenance"]["catalog_sha256"] = "z" * 64
    elif mutation == "usage":
        changed["attempted_calls"] += 1
    elif mutation == "score":
        changed["metrics"]["execution_accurate"] += 1
    reports[1] = ConditionReport(Path("E2.json"), changed)
    with pytest.raises(ValueError, match="selection"):
        build_selection(_e0(), *reports)


def _workflow_text() -> str:
    return WORKFLOW.read_text(encoding="utf-8")


def _top_level_triggers(workflow: str) -> list[str]:
    lines = workflow.splitlines()
    start = lines.index("on:")
    triggers = []
    for line in lines[start + 1:]:
        if line and not line.startswith(" "):
            break
        if line.startswith("  ") and not line.startswith("    ") and line.strip():
            triggers.append(line.strip())
    return triggers


def test_workflow_is_manual_one_condition_only():
    workflow = _workflow_text()
    assert _top_level_triggers(workflow) == ["workflow_dispatch:"]
    assert "type: choice" in workflow
    assert workflow.count("- E1") == workflow.count("- E2") == workflow.count("- E3") == 1
    assert "- E0" not in workflow and "- all" not in workflow and "push:" not in workflow
    assert "permissions:\n  contents: read" in workflow
    assert "GITHUB_RUN_ATTEMPT" in workflow and "github.run_attempt == 1" in workflow


def test_workflow_reconstructs_and_verifies_exact_snapshot_twice():
    workflow = _workflow_text()
    assert "evaluation/ctu_network_public/dataset_manifest.json" in workflow
    assert "capture20110815-2.binetflow" in workflow
    assert "capture20110816-2.binetflow" in workflow
    assert "ef5c9ed6895d4ca5aec723449dae30054ccd1f6b091713a52ffcb681ff78a02c" in workflow
    assert "df0b5338190b967bd340a0d6c1bb3c34d1bbfb4b7ffa764c2dd26f77f1a26680" in workflow
    assert workflow.count("scripts.build_ctu_network_public_snapshot") == 2
    assert "evaluation.ctu_network_public.contract" in workflow and "VERSION.lock" in workflow
    assert "243906" in workflow and "logical_snapshot_sha256" in workflow
    assert "snapshot-a.duckdb" in workflow and "snapshot-b.duckdb" in workflow


def test_workflow_gates_client_and_scopes_secrets_to_paid_step():
    workflow = _workflow_text()
    assert "github.ref == 'refs/heads/master'" in workflow
    assert "git rev-parse HEAD" in workflow and "GITHUB_SHA" in workflow
    assert workflow.count("${{ secrets.OPENAI_API_KEY }}") == 1
    assert workflow.count("${{ secrets.VINSOC_EVAL_MODEL }}") == 1
    assert "OpenAI(max_retries=0)" in workflow
    assert workflow.index("Verify snapshot and all offline gates") < workflow.index("Run paid condition")
    paid = workflow.split("- name: Run paid condition", 1)[1].split("- name:", 1)[0]
    assert "OPENAI_API_KEY: ${{ secrets.OPENAI_API_KEY }}" in paid
    assert "VINSOC_EVAL_MODEL: ${{ secrets.VINSOC_EVAL_MODEL }}" in paid
    assert "OPENAI_BASE_URL" not in workflow


def test_workflow_uploads_only_json_and_always_cleans_sources():
    workflow = _workflow_text()
    upload = workflow.split("uses: actions/upload-artifact@v4", 1)[1]
    assert "*.json" in upload and "*.duckdb" not in upload and "sources/" not in upload
    assert "if: always()" in workflow
    cleanup = workflow.split("- name: Cleanup source bytes and snapshots", 1)[1]
    assert "snapshot-a.duckdb" in cleanup and "snapshot-b.duckdb" in cleanup
    assert "capture20110815-2.binetflow" in cleanup
    assert "capture20110816-2.binetflow" in cleanup
