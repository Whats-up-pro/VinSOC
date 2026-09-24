"""Canonical, inspectable provenance shared by the R1 A1 report entrypoints."""

from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path
from typing import Any

from evaluation.tool_calling.models import ToolCallCase


def canonical_sha256(value: Any) -> str:
    """Hash logical JSON, independent of object-key and file-reading order."""
    payload = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _git_identity() -> dict[str, Any]:
    root = Path(__file__).resolve().parents[2]
    try:
        def git(*args: str) -> str:
            return subprocess.run(
                ["git", *args], cwd=root, check=True, capture_output=True,
                text=True, timeout=10,
            ).stdout.strip()

        return {
            "commit_sha": git("rev-parse", "HEAD"),
            "branch": git("symbolic-ref", "--quiet", "--short", "HEAD"),
            "working_tree_clean": not bool(git("status", "--porcelain")),
        }
    except (OSError, subprocess.SubprocessError):
        return {"commit_sha": None, "branch": None, "working_tree_clean": None}


def build_a1_provenance(runner: Any, split: str, case_results: list[Any]) -> dict[str, Any]:
    """Use captured provider inputs and parsed split files, never reconstructed prompts."""
    reasons: list[str] = []
    git = _git_identity()
    if not git["commit_sha"] or git["working_tree_clean"] is not True:
        reasons.append("evaluator_git_identity_unavailable_or_dirty")
    if git["branch"] != "master":
        reasons.append("evaluation_not_on_master")

    split_path = Path(getattr(runner, "benchmarks_dir", "")) / split
    split_files: dict[str, Any] = {}
    if split_path.is_dir():
        for path in sorted(split_path.glob("*.json")):
            split_files[path.name] = json.loads(path.read_text(encoding="utf-8"))
    if not split_files:
        reasons.append("benchmark_split_unavailable")
    split_cases = {
        data["case_id"]: ToolCallCase.from_dict(data).to_dict()
        for data in split_files.values()
    }
    cases = getattr(runner, "_run_cases", None)
    evaluated = {case.case_id: case.to_dict() for case in cases} if cases is not None else {}
    if (not evaluated or evaluated != split_cases
            or len(split_cases) != len(split_files)
            or len(evaluated) != len(case_results)
            or len(case_results) != len(split_files)):
        reasons.append("evaluated_cases_do_not_match_full_split")

    # Each record was captured immediately before the matching provider call.
    records = getattr(runner, "_input_records", [])
    prompts = sorted(
        (record["prompt"] for record in records), key=lambda entry: entry["case_id"]
    )
    schemas_by_hash = {
        canonical_sha256(record["tool_schemas"]): record["tool_schemas"]
        for record in records
    }
    if (len(records) != len(case_results) or len(schemas_by_hash) != 1
            or sorted(record["prompt"]["case_id"] for record in records)
            != sorted(result.case_id for result in case_results)):
        reasons.append("provider_inputs_or_production_schemas_unavailable_or_inconsistent")

    metadata = runner.provider.get_run_metadata()
    calls = metadata.get("calls", [])
    if (len(calls) != len(case_results)
            or any(not call.get("actual_model") or not call.get("actual_provider")
                   or call.get("fallback_triggered") for call in calls)):
        reasons.append("actual_provider_model_or_fallback_not_verified")
    requested_model = getattr(getattr(runner, "config", None), "model", None)
    if not requested_model or any(
        call.get("actual_model") != requested_model for call in calls
    ):
        reasons.append("requested_model_not_pinned_to_actual_model")
    if any({"PROVIDER_ERROR", "EXECUTION_ERROR"}.intersection(result.errors)
           for result in case_results):
        reasons.append("provider_or_execution_errors_present")

    return {
        "format": "r1_a1_provenance_v1",
        "canonicalization": "UTF-8 JSON, sorted object keys, compact separators; split files sorted by filename; prompts sorted by case_id",
        "git": git,
        "benchmark_split": split,
        "benchmark_split_sha256": canonical_sha256(split_files) if split_files else None,
        "benchmark_files_sha256": {
            name: canonical_sha256(data) for name, data in split_files.items()
        },
        "evaluated_cases_sha256": canonical_sha256(evaluated) if evaluated else None,
        "prompt_sha256": canonical_sha256(prompts) if prompts else None,
        "prompts": prompts,
        "production_schema_sha256": next(iter(schemas_by_hash)) if len(schemas_by_hash) == 1 else None,
        "production_schemas_by_sha256": schemas_by_hash,
        "case_schema_sha256": {
            record["prompt"]["case_id"]: canonical_sha256(record["tool_schemas"])
            for record in records
        },
        "official_eligible": not reasons,
        "ineligible_reasons": reasons,
    }
