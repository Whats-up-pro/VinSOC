"""Authoring and validation support for the R1 generalization split."""

from __future__ import annotations

import json
from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path
from typing import Any

from evaluation.tool_calling.models import CaseDifficulty
from evaluation.tool_calling.provenance import canonical_sha256

_CANDIDATE_FIELDS = {
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
}
_GOLD_FIELDS = {
    "expected_calls",
    "forbidden_tools",
    "ordering_constraints",
    "acceptable_trajectories",
    "category",
    "reference_time",
    "notes",
}


@dataclass(frozen=True)
class CandidateCase:
    """A request and source metadata before any gold decision exists."""

    case_id: str
    request: str
    difficulty: str
    source_kind: str
    source_reference: str
    source_record_id: str
    scenario_family: str
    template_family: str
    authoring_stratum: str
    coverage_tags: tuple[str, ...]

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> CandidateCase:
        gold_fields = sorted(_GOLD_FIELDS.intersection(data))
        if gold_fields:
            raise ValueError(f"candidate contains gold field(s): {', '.join(gold_fields)}")

        missing = sorted(_CANDIDATE_FIELDS.difference(data))
        if missing:
            raise ValueError(f"candidate missing required field(s): {', '.join(missing)}")
        unknown = sorted(set(data).difference(_CANDIDATE_FIELDS))
        if unknown:
            raise ValueError(f"candidate contains unknown field(s): {', '.join(unknown)}")

        scalar_fields = sorted(_CANDIDATE_FIELDS.difference({"coverage_tags"}))
        for field_name in scalar_fields:
            if not isinstance(data[field_name], str) or not data[field_name].strip():
                raise ValueError(f"candidate field {field_name} must be a non-empty string")
        try:
            CaseDifficulty(data["difficulty"])
        except ValueError as exc:
            raise ValueError(f"candidate field difficulty is invalid: {data['difficulty']!r}") from exc

        tags = data["coverage_tags"]
        if (
            not isinstance(tags, list)
            or not tags
            or any(not isinstance(tag, str) or not tag.strip() for tag in tags)
        ):
            raise ValueError("candidate field coverage_tags must be a non-empty string list")
        if len(tags) != len(set(tags)):
            raise ValueError("candidate field coverage_tags contains duplicates")

        return cls(
            case_id=data["case_id"].strip(),
            request=data["request"].strip(),
            difficulty=data["difficulty"],
            source_kind=data["source_kind"].strip(),
            source_reference=data["source_reference"].strip(),
            source_record_id=data["source_record_id"].strip(),
            scenario_family=data["scenario_family"].strip(),
            template_family=data["template_family"].strip(),
            authoring_stratum=data["authoring_stratum"].strip(),
            coverage_tags=tuple(tags),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "case_id": self.case_id,
            "request": self.request,
            "difficulty": self.difficulty,
            "source_kind": self.source_kind,
            "source_reference": self.source_reference,
            "source_record_id": self.source_record_id,
            "scenario_family": self.scenario_family,
            "template_family": self.template_family,
            "authoring_stratum": self.authoring_stratum,
            "coverage_tags": list(self.coverage_tags),
        }


def load_candidates(path: Path) -> list[CandidateCase]:
    """Load a UTF-8 JSONL pack and reject ambiguous identities."""

    cases: list[CandidateCase] = []
    case_ids: set[str] = set()
    source_ids: set[tuple[str, str, str]] = set()
    for line_number, raw_line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not raw_line.strip():
            continue
        try:
            data = json.loads(raw_line)
        except json.JSONDecodeError as exc:
            raise ValueError(f"{path.name}:{line_number}: invalid JSON: {exc.msg}") from exc
        if not isinstance(data, dict):
            raise TypeError(f"{path.name}:{line_number}: candidate must be a JSON object")
        try:
            case = CandidateCase.from_dict(data)
        except ValueError as exc:
            raise ValueError(f"{path.name}:{line_number}: {exc}") from exc

        if case.case_id in case_ids:
            raise ValueError(f"{path.name}:{line_number}: duplicate case_id {case.case_id}")
        source_identity = (case.source_kind, case.source_reference, case.source_record_id)
        if source_identity in source_ids:
            raise ValueError(
                f"{path.name}:{line_number}: duplicate source identity {source_identity!r}"
            )
        case_ids.add(case.case_id)
        source_ids.add(source_identity)
        cases.append(case)
    return cases


def _canonical_split_hash(path: Path) -> str:
    files = {
        item.name: json.loads(item.read_text(encoding="utf-8"))
        for item in sorted(path.glob("*.json"))
    }
    return canonical_sha256(files)


def _raw_sha256(path: Path) -> str:
    return sha256(path.read_bytes()).hexdigest()


def historical_identity(root: Path = Path(".")) -> dict[str, str]:
    """Return the immutable R1 identities that new work must preserve."""

    return {
        "dev_split_sha256": _canonical_split_hash(
            root / "evaluation/tool_calling/benchmarks/dev"
        ),
        "frozen_split_sha256": _canonical_split_hash(
            root / "evaluation/tool_calling/benchmarks/frozen"
        ),
        "historical_result_raw_sha256": _raw_sha256(
            root / "results/evaluation_v1/r1/r1_a1_dev_v2_852e543.json"
        ),
        "winner_lock_raw_sha256": _raw_sha256(
            root / "evaluation/tool_calling/winner_lock.json"
        ),
    }
