from __future__ import annotations

import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


def _candidate(**overrides):
    data = {
        "case_id": "gen_001",
        "request": "Investigate IPv4 198.51.100.10 in network telemetry.",
        "difficulty": "basic",
        "source_kind": "public_documentation",
        "source_reference": "RFC 5737",
        "source_record_id": "rfc5737-example-1",
        "scenario_family": "ipv4_network_triage",
        "template_family": "single_network_explicit",
        "authoring_stratum": "single:network_investigation",
        "coverage_tags": ["single_tool", "network"],
    }
    data.update(overrides)
    return data


def test_historical_r1_bytes_match_committed_identities():
    from evaluation.tool_calling.generalization import historical_identity

    assert historical_identity(ROOT) == {
        "dev_split_sha256": "d8e68968a390a09d502a3da01319611f546a6d0189a30e0fe0c316550d0aa259",
        "frozen_split_sha256": "eb46a6d42aeced2f6f676fb5a04a670a49351d4516c5582cb61dcb39e2b61ae4",
        "historical_result_raw_sha256": "60a87c2502ea6d664b883e147bfdfb1be014df813c001225ec0a05839f7e421b",
        "winner_lock_raw_sha256": "dd520c4d9da7430d55d083cc66246f4de4a432aaf536108565bae070745269e9",
    }


@pytest.mark.parametrize(
    "gold_field",
    [
        "expected_calls",
        "forbidden_tools",
        "ordering_constraints",
        "acceptable_trajectories",
        "category",
        "reference_time",
        "notes",
    ],
)
def test_candidate_rejects_expected_calls_and_other_gold_fields(gold_field):
    from evaluation.tool_calling.generalization import CandidateCase

    with pytest.raises(ValueError, match="gold field"):
        CandidateCase.from_dict(_candidate(**{gold_field: []}))


@pytest.mark.parametrize(
    "field",
    [
        "case_id",
        "request",
        "difficulty",
        "source_kind",
        "source_reference",
        "source_record_id",
        "scenario_family",
        "template_family",
        "authoring_stratum",
        "coverage_tags",
    ],
)
def test_candidate_requires_source_and_unique_identity(field):
    from evaluation.tool_calling.generalization import CandidateCase

    data = _candidate()
    data.pop(field)
    with pytest.raises(ValueError, match=field):
        CandidateCase.from_dict(data)


def test_candidate_loader_rejects_duplicate_case_and_source_identities(tmp_path):
    from evaluation.tool_calling.generalization import load_candidates

    duplicate_case = [_candidate(), _candidate(source_record_id="different")]
    path = tmp_path / "duplicate-case.jsonl"
    path.write_text("\n".join(json.dumps(row) for row in duplicate_case) + "\n")
    with pytest.raises(ValueError, match="duplicate case_id"):
        load_candidates(path)

    duplicate_source = [_candidate(), _candidate(case_id="gen_002")]
    path = tmp_path / "duplicate-source.jsonl"
    path.write_text("\n".join(json.dumps(row) for row in duplicate_source) + "\n")
    with pytest.raises(ValueError, match="duplicate source identity"):
        load_candidates(path)


def test_candidate_loader_reports_invalid_jsonl_line(tmp_path):
    from evaluation.tool_calling.generalization import load_candidates

    path = tmp_path / "broken.jsonl"
    path.write_text(json.dumps(_candidate()) + "\n{broken\n", encoding="utf-8")
    with pytest.raises(ValueError, match=r"broken\.jsonl:2"):
        load_candidates(path)
