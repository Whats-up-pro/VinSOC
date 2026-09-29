"""Offline structural and identity checks for the existing R1 frozen split."""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from evaluation.tool_calling.frozen_compatibility import (
    build_compatibility_lock,
    verify_compatibility_lock,
)

FROZEN = Path("evaluation/tool_calling/benchmarks/frozen")


def _copy_cases(tmp_path: Path) -> Path:
    target = tmp_path / "frozen"
    target.mkdir()
    for source in FROZEN.glob("frozen_*.json"):
        shutil.copyfile(source, target / source.name)
    return target


def test_existing_eight_cases_match_committed_lock_without_provider(monkeypatch):
    def forbidden_provider(*args, **kwargs):
        raise AssertionError("provider creation is forbidden in frozen compatibility")

    monkeypatch.setattr("agent.provider.create_provider", forbidden_provider)
    actual = build_compatibility_lock()
    assert actual["case_count"] == 8
    assert len(actual["case_ids"]) == 8
    assert actual["model_calls"] == 0
    assert verify_compatibility_lock() == actual


def test_unknown_tool_fails_before_lock(tmp_path):
    directory = _copy_cases(tmp_path)
    path = directory / "frozen_001.json"
    case = json.loads(path.read_text(encoding="utf-8"))
    case["expected_calls"][0]["tool"] = "nonexistent_tool"
    path.write_text(json.dumps(case), encoding="utf-8")
    with pytest.raises(ValueError, match="unknown tool"):
        build_compatibility_lock(directory)


def test_malformed_case_fails_before_lock(tmp_path):
    directory = _copy_cases(tmp_path)
    path = directory / "frozen_001.json"
    case = json.loads(path.read_text(encoding="utf-8"))
    del case["request"]
    path.write_text(json.dumps(case), encoding="utf-8")
    with pytest.raises(ValueError, match="request"):
        build_compatibility_lock(directory)


def test_duplicate_case_id_fails_before_lock(tmp_path):
    directory = _copy_cases(tmp_path)
    path = directory / "frozen_002.json"
    case = json.loads(path.read_text(encoding="utf-8"))
    case["case_id"] = "frozen_001"
    path.write_text(json.dumps(case), encoding="utf-8")
    with pytest.raises(ValueError, match="duplicate|filename"):
        build_compatibility_lock(directory)


def test_changed_case_file_fails_lock_verification(tmp_path):
    directory = _copy_cases(tmp_path)
    lock_path = tmp_path / "COMPATIBILITY.lock"
    lock_path.write_text(json.dumps(build_compatibility_lock(directory)), encoding="utf-8")
    path = directory / "frozen_008.json"
    case = json.loads(path.read_text(encoding="utf-8"))
    case["request"] += " "
    path.write_text(json.dumps(case), encoding="utf-8")
    with pytest.raises(ValueError, match="lock mismatch"):
        verify_compatibility_lock(directory, lock_path)
