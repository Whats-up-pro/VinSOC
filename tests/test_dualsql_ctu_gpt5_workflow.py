"""Offline selection and manual-dispatch contract for the CTU comparison."""

from __future__ import annotations

import copy
import hashlib
import io
from pathlib import Path

import pytest

from evaluation.dualsql_lite_ctu_gpt5.contract import BaselineEvidence
from evaluation.dualsql_lite_ctu_gpt5.runner import ConditionReport


def _e0(*, score=2, cost=0.01, calls=8, latency=1000.0):
    return BaselineEvidence(
        run_id="36520685612", case_ids=tuple(f"ctu_sql_{index:03d}" for index in range(1, 9)),
        execution_accurate=score, known_cost_usd=cost,
        report_sha256="a" * 64, logical_snapshot_sha256="b" * 64,
        split_sha256="c" * 64, model_config_sha256="d" * 64,
        system_prompt_sha256="e" * 64, schema_context_sha256="f" * 64,
        model_calls=calls, latency_ms=latency,
        source_file_sha256={"ctu13_s5": "1" * 64, "ctu13_s7": "2" * 64},
        builder_scorer_sha256={"evaluation/text_to_sql.py": "3" * 64},
    )


def _condition(name, *, score=2, cost=0.02, calls=9, latency=1100.0):
    case_ids = [f"ctu_sql_{index:03d}" for index in range(1, 9)]
    provider_calls = [{"response_id": f"resp-{index}",
                       "actual_model": "gpt-5-mini-2025-08-07",
                       "input_tokens": 100, "output_tokens": 50,
                       "cost_usd": cost / calls, "latency_ms": latency / calls}
                      for index in range(calls)]
    payload = {"run_status": "complete", "condition": name,
        "implementation_sha": "4" * 40,
        "case_ids": case_ids,
        "case_results": [{"case_id": case_id, "execution_accurate": index < score,
                          "syntax_valid": True, "execution_success": True,
                          "safety_rejected": False, "error_category": "NONE"}
                         for index, case_id in enumerate(case_ids)],
        "metrics": {"execution_accurate": score},
        "known_cost_usd": cost, "cost_unknown": False,
        "attempted_calls": calls, "provider_calls": provider_calls,
        "model_contract": {"model": "gpt-5-mini-2025-08-07",
                           "reasoning_effort": "low", "max_completion_tokens": 1000,
                           "max_retries": 0},
        "model_config_sha256": "5" * 64,
        "provenance": {"e0_report_sha256": "a" * 64,
            "logical_snapshot_sha256": "b" * 64, "split_sha256": "c" * 64,
            "schema_context_sha256": "f" * 64,
            "source_file_sha256": {"ctu13_s5": "1" * 64, "ctu13_s7": "2" * 64},
            "builder_scorer_sha256": {"evaluation/text_to_sql.py": "3" * 64},
            "linker_prompt_sha256": "6" * 64, "generator_prompt_sha256": "7" * 64,
            "tool_schema_sha256": "8" * 64,
            "tool_implementation_sha256": "9" * 64,
            "catalog_sha256": "0" * 64},
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

    result = build_selection(_e0(score=2, cost=0.02, calls=9, latency=1100),
                             _condition("E1"), _condition("E2"), _condition("E3"))
    assert result.winner == "E0"


@pytest.mark.parametrize("mutation", [
    "partial", "case_ids", "snapshot", "split", "sources", "scorer",
    "model", "sha", "prompt", "tool", "catalog", "usage", "score",
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
    with pytest.raises(ValueError):
        build_selection(_e0(), *reports)


WORKFLOW = Path(".github/workflows/r2-dualsql-ctu-gpt5.yml")


def test_manual_workflow_has_one_condition_choice_and_no_rerun():
    workflow = WORKFLOW.read_text(encoding="utf-8")
    dispatch = workflow.split("on:", 1)[1].split("permissions:", 1)[0]
    assert "workflow_dispatch:" in dispatch
    assert "push:" not in dispatch and "pull_request:" not in dispatch
    assert "condition:" in dispatch and dispatch.count("type: choice") == 1
    assert all(f"- {condition}" in dispatch for condition in ("E1", "E2", "E3"))
    assert "- E0" not in dispatch and "- all" not in dispatch
    assert "GITHUB_RUN_ATTEMPT" in workflow and '"1"' in workflow
    assert "contents: read" in workflow


def test_manual_workflow_reconstructs_two_verified_snapshots_before_provider():
    workflow = WORKFLOW.read_text(encoding="utf-8")
    assert "evaluation/ctu_network_public/dataset_manifest.json" in workflow
    assert "python -m evaluation.dualsql_lite_ctu_gpt5.workflow prepare" in workflow
    assert "python -m evaluation.dualsql_lite_ctu_gpt5.workflow run" in workflow
    assert workflow.index("workflow prepare") < workflow.index("workflow run")
    assert "Verify exact-SHA CI" in workflow
    assert workflow.index("Verify exact-SHA CI") < workflow.index("workflow run")
    assert "if: always()" in workflow
    assert "workflow cleanup" in workflow
    assert "dualsql_evidence/*.json" in workflow
    assert "*.duckdb" not in workflow.split("uses: actions/upload-artifact@", 1)[1]
    assert "OPENAI_EVAL_MODEL" in workflow and "OPENAI_API_KEY" in workflow


def test_prepare_contract_uses_only_official_pinned_s5_s7_and_two_builds():
    from evaluation.dualsql_lite_ctu_gpt5 import workflow
    import inspect

    source = inspect.getsource(workflow)
    assert "ctu13_s5" in source and "ctu13_s7" in source
    assert "mcfp.felk.cvut.cz" in source
    assert "file_sha256" in source
    assert source.count("build_ctu_network_snapshot") >= 1
    assert "validate_dev_contract" in source
    assert "logical_snapshot_sha256" in source
    assert "243906" in source


def test_prepare_performs_two_independent_builds_and_rejects_hash_drift(tmp_path, monkeypatch):
    from evaluation.dualsql_lite_ctu_gpt5 import workflow

    sources = [{"dataset_id": "ctu13_s5", "file_sha256": "1" * 64},
               {"dataset_id": "ctu13_s7", "file_sha256": "2" * 64}]
    downloaded = []
    built = []
    monkeypatch.setattr(workflow, "_sources", lambda *_: sources)
    monkeypatch.setattr(workflow, "_download_pinned", lambda source: downloaded.append(source["dataset_id"]))

    def fake_build(manifest, snapshot):
        built.append(snapshot.name)
        return {"content_sha256": "a" * 64}

    monkeypatch.setattr(workflow, "build_ctu_network_snapshot", fake_build)
    monkeypatch.setattr(workflow, "validate_dev_contract", lambda snapshot: {
        "logical_snapshot_sha256": "a" * 64,
        "row_counts": {"network_flows": 243906},
        "source_row_counts": {"ctu13_s5": 129831, "ctu13_s7": 114075},
    })
    result = workflow.prepare(tmp_path / "first", tmp_path / "evidence")
    assert downloaded == ["ctu13_s5", "ctu13_s7"]
    assert built == ["ctu-dev-a.duckdb", "ctu-dev-b.duckdb"]
    assert result["logical_snapshot_sha256"] == "a" * 64
    assert sorted(path.name for path in (tmp_path / "evidence").glob("*.json")) == [
        "build-a.json", "build-b.json"]

    count = 0
    def drifting_validate(snapshot):
        nonlocal count
        count += 1
        return {"logical_snapshot_sha256": "a" * 64 if count == 1 else "b" * 64,
                "row_counts": {"network_flows": 243906},
                "source_row_counts": {"ctu13_s5": 129831, "ctu13_s7": 114075}}

    monkeypatch.setattr(workflow, "validate_dev_contract", drifting_validate)
    with pytest.raises(ValueError, match="logical hash mismatch"):
        workflow.prepare(tmp_path / "second", tmp_path / "other_evidence")


def test_pinned_download_rejects_source_checksum_mismatch(tmp_path, monkeypatch):
    from evaluation.dualsql_lite_ctu_gpt5 import workflow

    payload = b"fixture source bytes"
    monkeypatch.setattr(workflow.urllib.request, "urlopen",
                        lambda *_args, **_kwargs: io.BytesIO(payload))
    valid = {"dataset_id": "ctu13_s5", "path": str(tmp_path / "valid.bin"),
             "source_url": "https://mcfp.felk.cvut.cz/example",
             "file_sha256": hashlib.sha256(payload).hexdigest()}
    workflow._download_pinned(valid)
    assert (tmp_path / "valid.bin").read_bytes() == payload
    invalid = {**valid, "path": str(tmp_path / "invalid.bin"),
               "file_sha256": "0" * 64}
    with pytest.raises(ValueError, match="checksum mismatch"):
        workflow._download_pinned(invalid)
