"""Authoring and validation support for the R1 generalization split."""

from __future__ import annotations

import json
import re
import unicodedata
from argparse import ArgumentParser
from collections import Counter, defaultdict
from collections.abc import Sequence
from dataclasses import dataclass, replace
from hashlib import sha256
from itertools import pairwise
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator

from agent.tools import get_tool_schemas
from evaluation.tool_calling.models import CaseDifficulty, ToolCallCase
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
    manifest_path: str | None = None

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
            raise ValueError(
                f"candidate field difficulty is invalid: {data['difficulty']!r}"
            ) from exc

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


@dataclass(frozen=True)
class DistributionAudit:
    """Exact allocation receipt for a candidate pack."""

    passed: bool
    total: int
    main_group_counts: dict[str, int]
    single_tool_counts: dict[str, int]
    two_tool_counts: dict[str, int]
    robustness_count: int
    difficulties: dict[str, tuple[str, ...]]
    errors: tuple[str, ...]


@dataclass(frozen=True)
class CandidateAudit:
    """Fail-closed quality receipt produced before human gold review."""

    passed: bool
    case_count: int
    exact_duplicates: tuple[tuple[str, str], ...]
    pivot_duplicates: tuple[tuple[str, str], ...]
    near_duplicates: tuple[tuple[str, str, float], ...]
    leakage_case_ids: tuple[str, ...]
    schema_errors: tuple[str, ...]
    waiver_errors: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "format": "r1_generalization_candidate_audit_v1",
            "passed": self.passed,
            "case_count": self.case_count,
            "exact_duplicates": [list(item) for item in self.exact_duplicates],
            "pivot_duplicates": [list(item) for item in self.pivot_duplicates],
            "near_duplicates": [
                {"case_ids": [left, right], "jaccard": score}
                for left, right, score in self.near_duplicates
            ],
            "leakage_case_ids": list(self.leakage_case_ids),
            "schema_errors": list(self.schema_errors),
            "waiver_errors": list(self.waiver_errors),
            "provider_created": False,
        }


@dataclass(frozen=True)
class ReviewPackReceipt:
    """Receipt for two independently completed blind-review packs."""

    case_count: int
    pack_sha256: dict[str, str]


@dataclass(frozen=True)
class ReviewGate:
    """Status of the two-reviewer human gold gate."""

    passed: bool
    status: str
    reviewed_a: int
    reviewed_b: int
    disagreement_case_ids: tuple[str, ...]
    blocked_case_ids: tuple[str, ...]
    errors: tuple[str, ...]
    provider_created: bool = False
    final_expected_calls: tuple[tuple[str, tuple[dict[str, Any], ...]], ...] = ()
    reviewer_ids: tuple[str, ...] = ()
    review_file_paths: tuple[tuple[str, str], ...] = ()
    review_file_sha256: tuple[tuple[str, str], ...] = ()
    adjudication_path: str | None = None
    adjudication_sha256: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "format": "r1_generalization_review_gate_v1",
            "passed": self.passed,
            "status": self.status,
            "reviewed_a": self.reviewed_a,
            "reviewed_b": self.reviewed_b,
            "disagreement_case_ids": list(self.disagreement_case_ids),
            "blocked_case_ids": list(self.blocked_case_ids),
            "errors": list(self.errors),
            "provider_created": self.provider_created,
        }


@dataclass(frozen=True)
class GeneralizationLock:
    """Deterministic identity for an approved generalization split."""

    case_count: int
    case_ids: tuple[str, ...]
    distribution: dict[str, int]
    case_files_sha256: dict[str, str]
    split_sha256: str
    case_directory_sha256: str
    candidate_path: str
    candidate_sha256: str
    candidate_content_sha256: str
    review_file_paths: dict[str, str]
    review_file_sha256: dict[str, str]
    adjudication_path: str
    adjudication_sha256: str
    reviewer_ids: tuple[str, ...]
    review_status: str
    reviewed_a: int
    reviewed_b: int
    disagreement_case_ids: tuple[str, ...]
    scorer_files: tuple[str, ...]
    scorer_file_sha256: dict[str, str]
    scorer_sha256: str
    prompt_sha256: str
    production_schema_sha256: str
    model_calls: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "format": "r1_tool_calling_generalization_lock_v1",
            "case_count": self.case_count,
            "case_ids": list(self.case_ids),
            "distribution": self.distribution,
            "case_files_sha256": self.case_files_sha256,
            "split_sha256": self.split_sha256,
            "case_directory_sha256": self.case_directory_sha256,
            "candidate_path": self.candidate_path,
            "candidate_sha256": self.candidate_sha256,
            "candidate_content_sha256": self.candidate_content_sha256,
            "review_file_paths": self.review_file_paths,
            "review_file_sha256": self.review_file_sha256,
            "adjudication_path": self.adjudication_path,
            "adjudication_sha256": self.adjudication_sha256,
            "reviewer_ids": list(self.reviewer_ids),
            "review_status": self.review_status,
            "reviewed_a": self.reviewed_a,
            "reviewed_b": self.reviewed_b,
            "disagreement_case_ids": list(self.disagreement_case_ids),
            "scorer_files": list(self.scorer_files),
            "scorer_file_sha256": self.scorer_file_sha256,
            "scorer_sha256": self.scorer_sha256,
            "prompt_sha256": self.prompt_sha256,
            "production_schema_sha256": self.production_schema_sha256,
            "hash_canonicalization": (
                "UTF-8 JSON with sorted object keys and compact separators; "
                "scorer source line endings normalized to LF"
            ),
            "model_calls": self.model_calls,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> GeneralizationLock:
        if data.get("format") != "r1_tool_calling_generalization_lock_v1":
            raise ValueError("unsupported generalization lock format")
        return cls(
            case_count=data["case_count"],
            case_ids=tuple(data["case_ids"]),
            distribution=dict(data["distribution"]),
            case_files_sha256=dict(data["case_files_sha256"]),
            split_sha256=data["split_sha256"],
            case_directory_sha256=data["case_directory_sha256"],
            candidate_path=data["candidate_path"],
            candidate_sha256=data["candidate_sha256"],
            candidate_content_sha256=data["candidate_content_sha256"],
            review_file_paths=dict(data["review_file_paths"]),
            review_file_sha256=dict(data["review_file_sha256"]),
            adjudication_path=data["adjudication_path"],
            adjudication_sha256=data["adjudication_sha256"],
            reviewer_ids=tuple(data["reviewer_ids"]),
            review_status=data["review_status"],
            reviewed_a=data["reviewed_a"],
            reviewed_b=data["reviewed_b"],
            disagreement_case_ids=tuple(data["disagreement_case_ids"]),
            scorer_files=tuple(data["scorer_files"]),
            scorer_file_sha256=dict(data["scorer_file_sha256"]),
            scorer_sha256=data["scorer_sha256"],
            prompt_sha256=data["prompt_sha256"],
            production_schema_sha256=data["production_schema_sha256"],
            model_calls=data["model_calls"],
        )


@dataclass(frozen=True)
class LockVerification:
    """Offline verification result for a generalization lock."""

    passed: bool
    errors: tuple[str, ...]
    case_count: int
    distribution: dict[str, int]
    lock_sha256: str | None


def _stratum_tools(stratum: str) -> tuple[str, tuple[str, ...]]:
    if stratum == "no_tool":
        return "no_tool", ()
    prefix, separator, value = stratum.partition(":")
    expected_sizes = {"single": 1, "pair": 2, "triple": 3}
    if not separator or prefix not in expected_sizes:
        raise ValueError(f"invalid authoring_stratum {stratum!r}")
    tools = tuple(value.split("+"))
    if len(tools) != expected_sizes[prefix] or len(set(tools)) != len(tools):
        raise ValueError(f"invalid authoring_stratum {stratum!r}")
    group = {"single": "single_tool", "pair": "two_tool", "triple": "three_tool"}[prefix]
    return group, tools


def audit_candidate_distribution(cases: Sequence[CandidateCase]) -> DistributionAudit:
    """Validate the fixed 120-case allocation without altering the pack."""

    production_tools = tuple(schema["function"]["name"] for schema in get_tool_schemas())
    allowed_tools = set(production_tools)
    main_counts: Counter[str] = Counter()
    single_counts: Counter[str] = Counter()
    pair_counts: Counter[str] = Counter()
    difficulties: defaultdict[str, set[str]] = defaultdict(set)
    errors: list[str] = []
    robustness_count = 0

    for case in cases:
        try:
            group, tools = _stratum_tools(case.authoring_stratum)
        except ValueError as exc:
            errors.append(f"{case.case_id}: {exc}")
            continue
        unknown_tools = sorted(set(tools).difference(allowed_tools))
        if unknown_tools:
            errors.append(f"{case.case_id}: unknown tool(s): {', '.join(unknown_tools)}")
            continue
        main_counts[group] += 1
        difficulties[group].add(case.difficulty)
        if group == "single_tool":
            single_counts[tools[0]] += 1
        elif group == "two_tool":
            pair_counts["+".join(tools)] += 1
        elif group == "three_tool" and set(tools) != allowed_tools:
            errors.append(f"{case.case_id}: triple stratum must contain all production tools")
        if any(tag == "robustness" or tag.startswith("robustness:") for tag in case.coverage_tags):
            robustness_count += 1

    expected_main = {"no_tool": 24, "single_tool": 54, "two_tool": 30, "three_tool": 12}
    expected_single = {tool: 18 for tool in production_tools}
    expected_pairs = {
        "cti_enrichment+network_investigation": 10,
        "cti_enrichment+endpoint_investigation": 10,
        "network_investigation+endpoint_investigation": 10,
    }
    observed_main = {key: main_counts[key] for key in expected_main}
    observed_single = {key: single_counts[key] for key in expected_single}
    observed_pairs = {key: pair_counts[key] for key in expected_pairs}
    if len(cases) != 120:
        errors.append(f"expected 120 candidates, found {len(cases)}")
    if observed_main != expected_main:
        errors.append(f"main allocation mismatch: {observed_main}")
    if observed_single != expected_single:
        errors.append(f"single-tool allocation mismatch: {observed_single}")
    if observed_pairs != expected_pairs:
        errors.append(f"two-tool allocation mismatch: {observed_pairs}")
    if robustness_count < 30:
        errors.append(f"expected at least 30 robustness cases, found {robustness_count}")
    expected_difficulties = {difficulty.value for difficulty in CaseDifficulty}
    for group in expected_main:
        if difficulties[group] != expected_difficulties:
            errors.append(f"{group} difficulty coverage mismatch: {sorted(difficulties[group])}")

    return DistributionAudit(
        passed=not errors,
        total=len(cases),
        main_group_counts=observed_main,
        single_tool_counts=observed_single,
        two_tool_counts=observed_pairs,
        robustness_count=robustness_count,
        difficulties={key: tuple(sorted(difficulties[key])) for key in expected_main},
        errors=tuple(errors),
    )


def normalized_request(text: str) -> str:
    """Normalize request text for deterministic duplicate comparison."""

    normalized = unicodedata.normalize("NFKC", text).casefold()
    return re.sub(r"\s+", " ", normalized).strip()


def _token_bigrams(text: str) -> set[tuple[str, str]]:
    tokens = re.findall(r"[\w.-]+", normalized_request(text), flags=re.UNICODE)
    if len(tokens) == 1:
        return {(tokens[0], "")}
    return set(pairwise(tokens))


def token_bigram_jaccard(left: str, right: str) -> float:
    """Return Jaccard similarity over normalized token bigrams."""

    left_bigrams = _token_bigrams(left)
    right_bigrams = _token_bigrams(right)
    union = left_bigrams | right_bigrams
    if not union:
        return 1.0
    return len(left_bigrams & right_bigrams) / len(union)


_IPV4_RE = re.compile(r"(?<![\w.])(?:\d{1,3}\.){3}\d{1,3}(?!\w|\.\d)")
_DOMAIN_RE = re.compile(
    r"(?<![\w.-])(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+(?:test|com|net|org)(?![\w-]|\.[a-z0-9])",
    re.IGNORECASE,
)
_HASH_RE = re.compile(
    r"(?<![a-f0-9])(?:[a-f0-9]{64}|[a-f0-9]{40}|[a-f0-9]{32})(?![a-f0-9])", re.IGNORECASE
)
_HOST_RE = re.compile(r"(?<![A-Z0-9-])[A-Z]{2,}(?:-[A-Z0-9]+)+(?![A-Z0-9-])")
_GOLD_MARKERS = (
    "expected_calls",
    "forbidden_tools",
    "ordering_constraints",
    "acceptable_trajectories",
    "critical_arguments",
    "hidden answer",
    "gold answer",
)


def _valid_ipv4_values(text: str) -> tuple[str, ...]:
    values: list[str] = []
    for value in _IPV4_RE.findall(text):
        octets = value.split(".")
        if all(int(octet) <= 255 for octet in octets):
            values.append(value)
    return tuple(sorted(set(values)))


def _critical_pivots(text: str) -> tuple[str, ...]:
    values = {
        *(f"ipv4:{value}" for value in _valid_ipv4_values(text)),
        *(f"domain:{value.casefold()}" for value in _DOMAIN_RE.findall(text)),
        *(f"hash:{value.casefold()}" for value in _HASH_RE.findall(text)),
        *(f"host:{value.casefold()}" for value in _HOST_RE.findall(text)),
    }
    return tuple(sorted(values))


def _schema_errors_for_case(case: CandidateCase, schema_names: set[str]) -> list[str]:
    try:
        _, tools = _stratum_tools(case.authoring_stratum)
    except ValueError as exc:
        return [f"{case.case_id}: {exc}"]
    unknown = sorted(set(tools).difference(schema_names))
    if unknown:
        return [f"{case.case_id}: unknown production tool(s): {', '.join(unknown)}"]

    errors: list[str] = []
    if "network_investigation" in tools and not _valid_ipv4_values(case.request):
        errors.append(f"{case.case_id}: network_investigation requires an IPv4 pivot")
    if "endpoint_investigation" in tools and not _HOST_RE.search(case.request):
        errors.append(f"{case.case_id}: endpoint_investigation requires an endpoint host pivot")
    if "cti_enrichment" in tools and not (
        _valid_ipv4_values(case.request)
        or _DOMAIN_RE.search(case.request)
        or _HASH_RE.search(case.request)
    ):
        errors.append(f"{case.case_id}: cti_enrichment requires a supported IOC pivot")
    return errors


def _valid_near_duplicate_waivers(
    waivers: Sequence[dict[str, Any]], known_ids: set[str]
) -> tuple[set[frozenset[str]], tuple[str, ...]]:
    accepted: set[frozenset[str]] = set()
    errors: list[str] = []
    for index, waiver in enumerate(waivers, 1):
        case_ids = waiver.get("case_ids")
        reason = waiver.get("reason")
        reviewed_by = waiver.get("reviewed_by")
        if (
            not isinstance(case_ids, list)
            or len(case_ids) != 2
            or len(set(case_ids)) != 2
            or any(case_id not in known_ids for case_id in case_ids)
            or not isinstance(reason, str)
            or not reason.strip()
            or not isinstance(reviewed_by, str)
            or not reviewed_by.strip()
        ):
            errors.append(f"waiver {index}: case_ids, reason, and reviewed_by are required")
            continue
        accepted.add(frozenset(case_ids))
    return accepted, tuple(errors)


def audit_candidates(
    cases: Sequence[CandidateCase],
    existing_cases: Sequence[ToolCallCase],
    schemas: Sequence[dict[str, Any]],
    waivers: Sequence[dict[str, Any]],
) -> CandidateAudit:
    """Audit candidate independence, leakage and production-schema compatibility."""

    new_items = [(case.case_id, case.request) for case in cases]
    existing_items = [(case.case_id, case.request) for case in existing_cases]
    all_items = new_items + existing_items
    known_ids = {case_id for case_id, _ in all_items}
    new_ids = {case.case_id for case in cases}
    accepted_waivers, waiver_errors = _valid_near_duplicate_waivers(waivers, known_ids)

    exact: list[tuple[str, str]] = []
    pivot: list[tuple[str, str]] = []
    near: list[tuple[str, str, float]] = []
    for left_index, (left_id, left_request) in enumerate(all_items):
        for right_id, right_request in all_items[left_index + 1 :]:
            if left_id not in new_ids and right_id not in new_ids:
                continue
            left_normalized = normalized_request(left_request)
            right_normalized = normalized_request(right_request)
            if left_normalized == right_normalized:
                exact.append((left_id, right_id))
            left_pivots = _critical_pivots(left_request)
            right_pivots = _critical_pivots(right_request)
            if left_pivots and left_pivots == right_pivots:
                pivot.append((left_id, right_id))
            if left_normalized != right_normalized:
                similarity = token_bigram_jaccard(left_request, right_request)
                pair = frozenset((left_id, right_id))
                if similarity >= 0.80 and pair not in accepted_waivers:
                    near.append((left_id, right_id, round(similarity, 6)))

    leakage = tuple(
        case.case_id
        for case in cases
        if any(marker in normalized_request(case.request) for marker in _GOLD_MARKERS)
    )
    schema_names = {schema.get("function", {}).get("name") for schema in schemas} - {None}
    schema_errors: list[str] = []
    if schemas:
        for case in cases:
            schema_errors.extend(_schema_errors_for_case(case, schema_names))

    passed = not (exact or pivot or near or leakage or schema_errors or waiver_errors)
    return CandidateAudit(
        passed=passed,
        case_count=len(cases),
        exact_duplicates=tuple(exact),
        pivot_duplicates=tuple(pivot),
        near_duplicates=tuple(near),
        leakage_case_ids=leakage,
        schema_errors=tuple(schema_errors),
        waiver_errors=waiver_errors,
    )


def _blind_review_row(case: CandidateCase) -> dict[str, str]:
    return {
        "case_id": case.case_id,
        "request": case.request,
        "difficulty": case.difficulty,
        "production_schema_reference": "agent.tools.get_tool_schemas()",
    }


def write_blind_review_packs(cases: Sequence[CandidateCase], output_dir: Path) -> ReviewPackReceipt:
    """Write blind inputs without source metadata or authoring strata."""

    output_dir.mkdir(parents=True, exist_ok=True)
    payload = (
        "\n".join(json.dumps(_blind_review_row(case), ensure_ascii=False) for case in cases) + "\n"
    )
    hashes: dict[str, str] = {}
    for name in ("reviewer_a.jsonl", "reviewer_b.jsonl"):
        path = output_dir / name
        path.write_text(payload, encoding="utf-8")
        hashes[name] = _raw_sha256(path)
    return ReviewPackReceipt(case_count=len(cases), pack_sha256=hashes)


def _schema_by_tool(schemas: Sequence[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    return {schema["function"]["name"]: schema["function"]["parameters"] for schema in schemas}


def _project_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _path_for_lock(path: Path) -> str:
    resolved = path.resolve()
    try:
        return resolved.relative_to(_project_root()).as_posix()
    except ValueError:
        return resolved.as_posix()


def _validate_review_calls(
    case_id: str,
    calls: Any,
    schemas_by_tool: dict[str, dict[str, Any]],
    label: str,
) -> tuple[tuple[dict[str, Any], ...] | None, list[str]]:
    errors: list[str] = []
    if not isinstance(calls, list):
        return None, [f"{label} {case_id}: expected_calls must be a list"]
    normalized_calls: list[dict[str, Any]] = []
    for index, call in enumerate(calls, 1):
        prefix = f"{label} {case_id} call {index}"
        if not isinstance(call, dict):
            errors.append(f"{prefix}: call must be an object")
            continue
        allowed_fields = {"tool", "required_arguments", "critical_arguments"}
        unknown_fields = sorted(set(call).difference(allowed_fields))
        if unknown_fields:
            errors.append(f"{prefix}: unknown field(s): {', '.join(unknown_fields)}")
        tool = call.get("tool")
        if tool not in schemas_by_tool:
            errors.append(f"{prefix}: invalid tool {tool!r}")
            continue
        arguments = call.get("required_arguments")
        critical = call.get("critical_arguments")
        if not isinstance(arguments, dict):
            errors.append(f"{prefix}: required_arguments must be an object")
            continue
        if (
            not isinstance(critical, list)
            or any(not isinstance(name, str) for name in critical)
            or len(critical) != len(set(critical))
        ):
            errors.append(f"{prefix}: critical_arguments must be a unique string list")
            continue
        properties = schemas_by_tool[tool].get("properties", {})
        for argument, value in arguments.items():
            if argument not in properties:
                errors.append(f"{prefix}: unknown argument {argument!r} for {tool}")
                continue
            validation_errors = list(Draft202012Validator(properties[argument]).iter_errors(value))
            if validation_errors:
                errors.append(
                    f"{prefix}: invalid value for {argument!r}: " f"{validation_errors[0].message}"
                )
        missing_critical = sorted(set(critical).difference(arguments))
        if missing_critical:
            errors.append(
                f"{prefix}: critical argument(s) absent from required_arguments: "
                f"{', '.join(missing_critical)}"
            )
        normalized_calls.append(
            {
                "tool": tool,
                "required_arguments": arguments,
                "critical_arguments": critical,
            }
        )
    if errors:
        return None, errors
    return tuple(sorted(normalized_calls, key=canonical_sha256)), []


def _read_reviewer_pack(
    path: Path,
    label: str,
    cases_by_id: dict[str, CandidateCase],
    schemas_by_tool: dict[str, dict[str, Any]],
) -> tuple[dict[str, tuple[dict[str, Any], ...]], int, set[str], list[str], set[str]]:
    errors: list[str] = []
    blocked: set[str] = set()
    indexed: dict[str, dict[str, Any]] = {}
    for row in _load_jsonl_objects(path):
        case_id = row.get("case_id")
        if not isinstance(case_id, str):
            errors.append(f"{label}: record without a valid case_id")
            continue
        if case_id in indexed:
            errors.append(f"{label} {case_id}: duplicate record")
            blocked.add(case_id)
            continue
        indexed[case_id] = row

    expected_ids = set(cases_by_id)
    for case_id in sorted(expected_ids.difference(indexed)):
        errors.append(f"{label} {case_id}: missing case")
        blocked.add(case_id)
    for case_id in sorted(set(indexed).difference(expected_ids)):
        errors.append(f"{label} {case_id}: unexpected case")
        blocked.add(case_id)

    decisions: dict[str, tuple[dict[str, Any], ...]] = {}
    reviewer_ids: set[str] = set()
    for case_id in sorted(expected_ids.intersection(indexed)):
        row = indexed[case_id]
        if any(
            row.get(key) != value for key, value in _blind_review_row(cases_by_id[case_id]).items()
        ):
            errors.append(f"{label} {case_id}: prefilled fields changed")
            blocked.add(case_id)
            continue
        review_fields = {"reviewer_id", "reviewer_signature", "expected_calls"}
        present = review_fields.intersection(row)
        if not present:
            continue
        if present != review_fields:
            errors.append(f"{label} {case_id}: incomplete review fields")
            blocked.add(case_id)
            continue
        reviewer_id = row["reviewer_id"]
        signature = row["reviewer_signature"]
        if not isinstance(reviewer_id, str) or not reviewer_id.strip():
            errors.append(f"{label} {case_id}: blank reviewer_id")
            blocked.add(case_id)
        else:
            reviewer_ids.add(reviewer_id.strip())
        if not isinstance(signature, str) or not signature.strip():
            errors.append(f"{label} {case_id}: blank reviewer_signature")
            blocked.add(case_id)
        decision, decision_errors = _validate_review_calls(
            case_id, row["expected_calls"], schemas_by_tool, label
        )
        errors.extend(decision_errors)
        if decision_errors:
            blocked.add(case_id)
        if (
            decision is not None
            and isinstance(reviewer_id, str)
            and reviewer_id.strip()
            and isinstance(signature, str)
            and signature.strip()
        ):
            decisions[case_id] = decision
    if len(reviewer_ids) > 1:
        errors.append(f"{label}: one pack must use one reviewer_id")
        blocked.update(decisions)
    return decisions, len(decisions), reviewer_ids, errors, blocked


def _read_adjudications(
    path: Path | None,
    disagreements: set[str],
    reviewer_ids: set[str],
    schemas_by_tool: dict[str, dict[str, Any]],
) -> tuple[dict[str, tuple[dict[str, Any], ...]], list[str], set[str]]:
    if not disagreements:
        if path is None or not path.exists():
            return {}, [], set()
        records = _load_jsonl_objects(path)
        if not records:
            return {}, [], set()
        blocked = {row["case_id"] for row in records if isinstance(row.get("case_id"), str)}
        return (
            {},
            [
                f"adjudication {row.get('case_id', '<unknown>')}: "
                "case has no reviewer disagreement"
                for row in records
            ],
            blocked,
        )
    if path is None or not path.exists():
        return {}, [], set(disagreements)
    errors: list[str] = []
    decisions: dict[str, tuple[dict[str, Any], ...]] = {}
    blocked: set[str] = set()
    indexed: dict[str, dict[str, Any]] = {}
    for row in _load_jsonl_objects(path):
        case_id = row.get("case_id")
        if not isinstance(case_id, str):
            errors.append("adjudication: record without a valid case_id")
            continue
        if case_id in indexed:
            errors.append(f"adjudication {case_id}: duplicate record")
            blocked.add(case_id)
            continue
        indexed[case_id] = row
    for case_id in sorted(disagreements.difference(indexed)):
        blocked.add(case_id)
    for case_id, row in indexed.items():
        if case_id not in disagreements:
            errors.append(f"adjudication {case_id}: case has no reviewer disagreement")
            blocked.add(case_id)
            continue
        adjudicator = row.get("adjudicator_id")
        signature = row.get("adjudicator_signature")
        reason = row.get("reason")
        if not isinstance(adjudicator, str) or not adjudicator.strip():
            errors.append(f"adjudication {case_id}: blank adjudicator_id")
        elif adjudicator.strip() in reviewer_ids:
            errors.append(f"adjudication {case_id}: adjudicator must be distinct from reviewers")
        if not isinstance(signature, str) or not signature.strip():
            errors.append(f"adjudication {case_id}: blank adjudicator_signature")
        if not isinstance(reason, str) or not reason.strip():
            errors.append(f"adjudication {case_id}: reason is required")
        decision, decision_errors = _validate_review_calls(
            case_id, row.get("expected_calls"), schemas_by_tool, "adjudication"
        )
        errors.extend(decision_errors)
        if (
            decision is not None
            and isinstance(adjudicator, str)
            and adjudicator.strip()
            and adjudicator.strip() not in reviewer_ids
            and isinstance(signature, str)
            and signature.strip()
            and isinstance(reason, str)
            and reason.strip()
            and not decision_errors
        ):
            decisions[case_id] = decision
        else:
            blocked.add(case_id)
    return decisions, errors, blocked


def evaluate_review_gate(
    cases: Sequence[CandidateCase],
    review_a_path: Path,
    review_b_path: Path,
    adjudication_path: Path | None,
    schemas: Sequence[dict[str, Any]],
) -> ReviewGate:
    """Require complete, independent and schema-valid human gold decisions."""

    cases_by_id = {case.case_id: case for case in cases}
    schemas_by_tool = _schema_by_tool(schemas)
    decisions_a, count_a, ids_a, errors_a, blocked_a = _read_reviewer_pack(
        review_a_path, "reviewer_a", cases_by_id, schemas_by_tool
    )
    decisions_b, count_b, ids_b, errors_b, blocked_b = _read_reviewer_pack(
        review_b_path, "reviewer_b", cases_by_id, schemas_by_tool
    )
    errors = errors_a + errors_b
    blocked = blocked_a | blocked_b
    if ids_a.intersection(ids_b):
        errors.append("reviewer_a and reviewer_b must use distinct reviewers")
        blocked.update(cases_by_id)

    total = len(cases_by_id)
    if errors:
        return ReviewGate(
            False,
            "blocked_review_validation",
            count_a,
            count_b,
            (),
            tuple(sorted(blocked)),
            tuple(errors),
        )
    if count_a < total or count_b < total:
        pending = (
            set(cases_by_id).difference(decisions_a).union(set(cases_by_id).difference(decisions_b))
        )
        return ReviewGate(
            False,
            "pending_human_review",
            count_a,
            count_b,
            (),
            tuple(sorted(pending)),
            (),
        )

    disagreements = {
        case_id for case_id in cases_by_id if decisions_a[case_id] != decisions_b[case_id]
    }
    adjudicated, adjudication_errors, adjudication_blocked = _read_adjudications(
        adjudication_path, disagreements, ids_a | ids_b, schemas_by_tool
    )
    errors.extend(adjudication_errors)
    unresolved = disagreements.difference(adjudicated)
    blocked.update(adjudication_blocked)
    if errors:
        return ReviewGate(
            False,
            "blocked_adjudication_validation",
            count_a,
            count_b,
            tuple(sorted(disagreements)),
            tuple(sorted(blocked | unresolved)),
            tuple(errors),
        )
    if unresolved:
        return ReviewGate(
            False,
            "pending_adjudication",
            count_a,
            count_b,
            tuple(sorted(disagreements)),
            tuple(sorted(unresolved)),
            (),
        )
    final_decisions = {
        case_id: adjudicated.get(case_id, decisions_a[case_id]) for case_id in sorted(cases_by_id)
    }
    review_paths = {
        "reviewer_a.jsonl": _path_for_lock(review_a_path),
        "reviewer_b.jsonl": _path_for_lock(review_b_path),
    }
    review_hashes = {
        "reviewer_a.jsonl": _raw_sha256(review_a_path),
        "reviewer_b.jsonl": _raw_sha256(review_b_path),
    }
    return ReviewGate(
        True,
        "approved",
        count_a,
        count_b,
        tuple(sorted(disagreements)),
        (),
        (),
        final_expected_calls=tuple(final_decisions.items()),
        reviewer_ids=tuple(sorted(ids_a | ids_b)),
        review_file_paths=tuple(sorted(review_paths.items())),
        review_file_sha256=tuple(sorted(review_hashes.items())),
        adjudication_path=(
            _path_for_lock(adjudication_path)
            if adjudication_path is not None and adjudication_path.exists()
            else None
        ),
        adjudication_sha256=(
            _raw_sha256(adjudication_path)
            if adjudication_path is not None and adjudication_path.exists()
            else None
        ),
    )


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
        cases.append(replace(case, manifest_path=_path_for_lock(path)))
    return cases


def _canonical_split_hash(path: Path) -> str:
    files = {
        item.name: json.loads(item.read_text(encoding="utf-8"))
        for item in sorted(path.glob("*.json"))
    }
    return canonical_sha256(files)


def _raw_sha256(path: Path) -> str:
    return sha256(path.read_bytes()).hexdigest()


def _source_sha256(path: Path) -> str:
    normalized = path.read_bytes().replace(b"\r\n", b"\n").replace(b"\r", b"\n")
    return sha256(normalized).hexdigest()


def _resolve_locked_path(value: str) -> Path:
    path = Path(value)
    return path if path.is_absolute() else _project_root() / path


def _production_prompt_sha256() -> str:
    from evaluation.tool_calling.decision_runner import DecisionRunner

    probe = ToolCallCase.from_dict(
        {
            "case_id": "prompt_hash_probe",
            "category": "no_tool",
            "difficulty": "basic",
            "request": "prompt hash probe",
            "reference_time": "2026-10-09T00:00:00Z",
            "expected_calls": [],
            "forbidden_tools": [],
            "ordering_constraints": [],
        }
    )
    system_prompt, _ = DecisionRunner.build_prompt(None, probe, None)
    return canonical_sha256(system_prompt)


_CATEGORY_BY_TOOLS = {
    frozenset(): "no_tool",
    frozenset({"cti_enrichment"}): "cti_only",
    frozenset({"network_investigation"}): "network_only",
    frozenset({"endpoint_investigation"}): "endpoint_only",
    frozenset({"cti_enrichment", "network_investigation"}): "cti_network",
    frozenset({"cti_enrichment", "endpoint_investigation"}): "cti_endpoint",
    frozenset({"network_investigation", "endpoint_investigation"}): "network_endpoint",
    frozenset(
        {"cti_enrichment", "network_investigation", "endpoint_investigation"}
    ): "cti_network_endpoint",
}


def _gold_distribution(
    decisions: dict[str, tuple[dict[str, Any], ...]],
) -> dict[str, int]:
    labels = {0: "no_tool", 1: "single_tool", 2: "two_tool", 3: "three_tool"}
    counts: Counter[str] = Counter()
    for case_id, calls in decisions.items():
        if len(calls) not in labels:
            raise ValueError(f"{case_id}: expected at most three production tool calls")
        counts[labels[len(calls)]] += 1
    return {label: counts[label] for label in labels.values()}


def _case_payload(
    case: CandidateCase,
    calls: tuple[dict[str, Any], ...],
    production_tools: tuple[str, ...],
) -> dict[str, Any]:
    tool_set = frozenset(call["tool"] for call in calls)
    if len(tool_set) != len(calls):
        raise ValueError(f"{case.case_id}: duplicate expected tool call")
    category = _CATEGORY_BY_TOOLS.get(tool_set)
    if category is None:
        raise ValueError(f"{case.case_id}: unsupported final tool set {sorted(tool_set)}")
    for call in calls:
        for argument, value in call["required_arguments"].items():
            if isinstance(value, str) and value not in case.request:
                raise ValueError(
                    f"{case.case_id}: {argument} value {value!r} is absent from request"
                )

    expected_calls = [
        {
            "call_id": f"call_{index}",
            "tool": call["tool"],
            "required_arguments": call["required_arguments"],
            "critical_arguments": call["critical_arguments"],
            "optional": False,
        }
        for index, call in enumerate(calls, 1)
    ]
    source_metadata = {
        "source_kind": case.source_kind,
        "source_reference": case.source_reference,
        "source_record_id": case.source_record_id,
        "scenario_family": case.scenario_family,
        "template_family": case.template_family,
        "authoring_stratum": case.authoring_stratum,
        "coverage_tags": list(case.coverage_tags),
    }
    return {
        "case_id": case.case_id,
        "category": category,
        "difficulty": case.difficulty,
        "request": case.request,
        "reference_time": "2026-10-09T00:00:00Z",
        "expected_calls": expected_calls,
        "forbidden_tools": [tool for tool in production_tools if tool not in tool_set],
        "ordering_constraints": [],
        "acceptable_trajectories": [],
        "notes": json.dumps(
            source_metadata, sort_keys=True, separators=(",", ":"), ensure_ascii=False
        ),
    }


def _candidate_from_case_payload(data: dict[str, Any]) -> dict[str, Any]:
    metadata = json.loads(data["notes"])
    return {
        "case_id": data["case_id"],
        "request": data["request"],
        "difficulty": data["difficulty"],
        **metadata,
    }


def build_locked_split(
    cases: Sequence[CandidateCase],
    review_gate: ReviewGate,
    output_dir: Path,
    scorer_files: Sequence[Path],
    schemas: Sequence[dict[str, Any]],
) -> GeneralizationLock:
    """Build an immutable split only from a complete approved review gate."""

    output_dir = Path(output_dir)
    if not review_gate.passed or review_gate.status != "approved":
        raise ValueError("review gate must be approved before building a split")
    if output_dir.exists():
        raise FileExistsError(f"output directory already exists: {output_dir}")
    if review_gate.reviewed_a != 120 or review_gate.reviewed_b != 120:
        raise ValueError("approved review gate must contain 120 decisions from each reviewer")
    if len(review_gate.reviewer_ids) != 2 or len(set(review_gate.reviewer_ids)) != 2:
        raise ValueError("approved review gate must contain two distinct reviewer IDs")
    if review_gate.adjudication_path is None or review_gate.adjudication_sha256 is None:
        raise ValueError("an adjudication artifact is required, including when it is empty")

    case_list = sorted(cases, key=lambda item: item.case_id)
    expected_ids = [f"gen_{number:03d}" for number in range(1, 121)]
    if [case.case_id for case in case_list] != expected_ids:
        raise ValueError("locked split requires exactly gen_001 through gen_120")
    candidate_paths = {case.manifest_path for case in case_list}
    if len(candidate_paths) != 1 or None in candidate_paths:
        raise ValueError("all candidates must come from one recorded candidate manifest")
    candidate_path = next(iter(candidate_paths))
    assert candidate_path is not None
    candidate_file = _resolve_locked_path(candidate_path)
    if not candidate_file.is_file():
        raise ValueError("recorded candidate manifest does not exist")
    candidate_audit = audit_candidate_distribution(case_list)
    if not candidate_audit.passed:
        raise ValueError("candidate distribution is invalid: " + "; ".join(candidate_audit.errors))

    decisions = dict(review_gate.final_expected_calls)
    if set(decisions) != set(expected_ids):
        raise ValueError("approved review gate does not contain all final gold decisions")
    schemas_by_tool = _schema_by_tool(schemas)
    production_tools = tuple(schema["function"]["name"] for schema in schemas)
    normalized_decisions: dict[str, tuple[dict[str, Any], ...]] = {}
    for case in case_list:
        normalized, errors = _validate_review_calls(
            case.case_id, list(decisions[case.case_id]), schemas_by_tool, "locked gold"
        )
        if errors or normalized is None:
            raise ValueError("; ".join(errors))
        normalized_decisions[case.case_id] = normalized

    distribution = _gold_distribution(normalized_decisions)
    required_distribution = {
        "no_tool": 24,
        "single_tool": 54,
        "two_tool": 30,
        "three_tool": 12,
    }
    if distribution != required_distribution:
        raise ValueError(f"final gold distribution mismatch: {distribution}")

    contents = {
        f"{case.case_id}.json": _case_payload(
            case, normalized_decisions[case.case_id], production_tools
        )
        for case in case_list
    }
    for filename, data in contents.items():
        try:
            ToolCallCase.from_dict(data)
        except (KeyError, TypeError, ValueError) as exc:
            raise ValueError(f"{filename}: cannot load through production case model") from exc

    scorer_paths = [Path(path) for path in scorer_files]
    if not scorer_paths or any(not path.is_file() for path in scorer_paths):
        raise ValueError("every scorer file must exist")
    scorer_labels = tuple(_path_for_lock(path) for path in scorer_paths)
    scorer_hashes = {
        label: _source_sha256(path) for label, path in zip(scorer_labels, scorer_paths, strict=True)
    }
    case_hashes = {filename: canonical_sha256(data) for filename, data in contents.items()}
    review_paths = dict(review_gate.review_file_paths)
    review_hashes = dict(review_gate.review_file_sha256)
    if set(review_paths) != {"reviewer_a.jsonl", "reviewer_b.jsonl"}:
        raise ValueError("approved review gate is missing review artifact paths")
    if set(review_hashes) != set(review_paths):
        raise ValueError("approved review gate is missing review artifact hashes")

    lock = GeneralizationLock(
        case_count=len(contents),
        case_ids=tuple(expected_ids),
        distribution=distribution,
        case_files_sha256=case_hashes,
        split_sha256=canonical_sha256(contents),
        case_directory_sha256=canonical_sha256(case_hashes),
        candidate_path=candidate_path,
        candidate_sha256=_raw_sha256(candidate_file),
        candidate_content_sha256=canonical_sha256([case.to_dict() for case in case_list]),
        review_file_paths=review_paths,
        review_file_sha256=review_hashes,
        adjudication_path=review_gate.adjudication_path,
        adjudication_sha256=review_gate.adjudication_sha256,
        reviewer_ids=review_gate.reviewer_ids,
        review_status=review_gate.status,
        reviewed_a=review_gate.reviewed_a,
        reviewed_b=review_gate.reviewed_b,
        disagreement_case_ids=review_gate.disagreement_case_ids,
        scorer_files=scorer_labels,
        scorer_file_sha256=scorer_hashes,
        scorer_sha256=canonical_sha256(scorer_hashes),
        prompt_sha256=_production_prompt_sha256(),
        production_schema_sha256=canonical_sha256(list(schemas)),
    )

    output_dir.mkdir(parents=True)
    for filename, data in contents.items():
        (output_dir / filename).write_text(
            json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
        )
    (output_dir / "GENERALIZATION.lock").write_text(
        json.dumps(lock.to_dict(), indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    return lock


def verify_generalization_lock(split_dir: Path, lock_path: Path) -> LockVerification:
    """Verify split, authoring inputs, scorer, prompt and schema hashes offline."""

    split_dir = Path(split_dir)
    lock_path = Path(lock_path)
    errors: list[str] = []
    distribution = {label: 0 for label in ("no_tool", "single_tool", "two_tool", "three_tool")}
    lock_hash = _raw_sha256(lock_path) if lock_path.is_file() else None
    try:
        lock_data = json.loads(lock_path.read_text(encoding="utf-8"))
        lock = GeneralizationLock.from_dict(lock_data)
    except (OSError, KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
        return LockVerification(False, (f"invalid lock: {exc}",), 0, distribution, lock_hash)

    all_json_paths = sorted(split_dir.glob("*.json"))
    case_paths = [path for path in all_json_paths if path.name.startswith("gen_")]
    unexpected_json = [path.name for path in all_json_paths if not path.name.startswith("gen_")]
    if unexpected_json:
        errors.append(f"unexpected JSON files: {', '.join(unexpected_json)}")
    contents: dict[str, Any] = {}
    candidate_rows: list[dict[str, Any]] = []
    production_schemas = get_tool_schemas()
    production_tools = tuple(schema["function"]["name"] for schema in production_schemas)
    schema_by_tool = _schema_by_tool(production_schemas)
    actual_decisions: dict[str, tuple[dict[str, Any], ...]] = {}
    for path in case_paths:
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            case = ToolCallCase.from_dict(data)
            if case.case_id != path.stem:
                errors.append(f"{path.name}: case ID does not match filename")
            calls = [
                {
                    "tool": call.tool,
                    "required_arguments": call.required_arguments,
                    "critical_arguments": call.critical_arguments,
                }
                for call in case.expected_calls
            ]
            normalized_calls, call_errors = _validate_review_calls(
                case.case_id, calls, schema_by_tool, "locked case"
            )
            errors.extend(call_errors)
            if normalized_calls is not None:
                actual_decisions[case.case_id] = normalized_calls
            tool_set = frozenset(call.tool for call in case.expected_calls)
            if len(tool_set) != len(case.expected_calls):
                errors.append(f"{path.name}: duplicate expected tool call")
            expected_category = _CATEGORY_BY_TOOLS.get(tool_set)
            if expected_category is None or case.category.value != expected_category:
                errors.append(f"{path.name}: category does not match expected tools")
            expected_forbidden = [tool for tool in production_tools if tool not in tool_set]
            if case.forbidden_tools != expected_forbidden:
                errors.append(f"{path.name}: forbidden tools do not match final gold")
            candidate_rows.append(_candidate_from_case_payload(data))
            contents[path.name] = data
        except (OSError, KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
            errors.append(f"{path.name}: invalid locked case: {exc}")

    try:
        distribution = _gold_distribution(actual_decisions)
    except ValueError as exc:
        errors.append(str(exc))
    required_ids = tuple(f"gen_{number:03d}" for number in range(1, 121))
    required_distribution = {
        "no_tool": 24,
        "single_tool": 54,
        "two_tool": 30,
        "three_tool": 12,
    }
    if lock.case_ids != required_ids:
        errors.append("lock must contain exactly gen_001 through gen_120")
    expected_names = {f"{case_id}.json" for case_id in required_ids}
    if set(contents) != expected_names:
        errors.append("case IDs/files do not match lock")
    if len(contents) != lock.case_count or lock.case_count != 120:
        errors.append("case count does not match locked 120-case contract")
    actual_case_hashes = {filename: canonical_sha256(data) for filename, data in contents.items()}
    if actual_case_hashes != lock.case_files_sha256:
        errors.append("case hash mismatch")
    if canonical_sha256(contents) != lock.split_sha256:
        errors.append("split hash mismatch")
    if canonical_sha256(actual_case_hashes) != lock.case_directory_sha256:
        errors.append("case directory hash mismatch")
    if distribution != lock.distribution:
        errors.append("final gold distribution does not match lock")
    if distribution != required_distribution or lock.distribution != required_distribution:
        errors.append("final gold does not match required distribution 24/54/30/12")

    candidate_cases: list[CandidateCase] = []
    candidate_path = _resolve_locked_path(lock.candidate_path)
    if not candidate_path.is_file():
        errors.append("candidate artifact is missing")
    elif _raw_sha256(candidate_path) != lock.candidate_sha256:
        errors.append("candidate artifact hash mismatch")
    else:
        try:
            candidate_cases = load_candidates(candidate_path)
        except (OSError, TypeError, ValueError) as exc:
            errors.append(f"candidate artifact is invalid: {exc}")
    candidate_content = [case.to_dict() for case in candidate_cases]
    if canonical_sha256(candidate_content) != lock.candidate_content_sha256:
        errors.append("candidate content hash mismatch")
    if sorted(candidate_rows, key=lambda row: row["case_id"]) != candidate_content:
        errors.append("locked case metadata does not match candidate artifact")

    if lock.review_status != "approved" or lock.reviewed_a != 120 or lock.reviewed_b != 120:
        errors.append("review approval receipt is incomplete")
    if len(lock.reviewer_ids) != 2 or len(set(lock.reviewer_ids)) != 2:
        errors.append("reviewer identities are not distinct")
    required_review_names = {"reviewer_a.jsonl", "reviewer_b.jsonl"}
    if set(lock.review_file_paths) != required_review_names:
        errors.append("review artifact paths must contain reviewer A and reviewer B")
    if set(lock.review_file_sha256) != required_review_names:
        errors.append("review artifact hashes must contain reviewer A and reviewer B")
    resolved_reviews: dict[str, Path] = {}
    for name in required_review_names:
        value = lock.review_file_paths.get(name)
        if value is None:
            continue
        path = _resolve_locked_path(value)
        resolved_reviews[name] = path
        if not path.is_file() or _raw_sha256(path) != lock.review_file_sha256.get(name):
            errors.append(f"review hash mismatch: {name}")
    adjudication_path = _resolve_locked_path(lock.adjudication_path)
    if (
        not adjudication_path.is_file()
        or _raw_sha256(adjudication_path) != lock.adjudication_sha256
    ):
        errors.append("adjudication hash mismatch")

    if candidate_cases and set(resolved_reviews) == required_review_names:
        try:
            approved_gate = evaluate_review_gate(
                candidate_cases,
                resolved_reviews["reviewer_a.jsonl"],
                resolved_reviews["reviewer_b.jsonl"],
                adjudication_path,
                production_schemas,
            )
        except (OSError, TypeError, ValueError) as exc:
            errors.append(f"approved review artifacts are invalid: {exc}")
        else:
            if not approved_gate.passed or approved_gate.status != "approved":
                errors.append("approved review artifacts no longer pass the review gate")
            if approved_gate.reviewer_ids != lock.reviewer_ids:
                errors.append("reviewer identities do not match approved review artifacts")
            if approved_gate.disagreement_case_ids != lock.disagreement_case_ids:
                errors.append("disagreement receipt does not match approved review artifacts")
            approved_decisions = dict(approved_gate.final_expected_calls)
            if approved_decisions != actual_decisions:
                errors.append("locked gold does not match approved review decisions")
            approved_payloads = {
                f"{case.case_id}.json": _case_payload(
                    case, approved_decisions[case.case_id], production_tools
                )
                for case in candidate_cases
                if case.case_id in approved_decisions
            }
            if approved_payloads != contents:
                errors.append("locked split does not match approved case payloads")

    expected_scorer_files = tuple(_path_for_lock(path) for path in _default_scorer_files())
    if lock.scorer_files != expected_scorer_files:
        errors.append("scorer files do not match the required scorer set")
    if set(lock.scorer_file_sha256) != set(expected_scorer_files):
        errors.append("scorer hashes do not cover the required scorer set")
    actual_scorer_hashes = {}
    for value in expected_scorer_files:
        path = _resolve_locked_path(value)
        if not path.is_file():
            errors.append(f"missing scorer file: {value}")
            continue
        actual_scorer_hashes[value] = _source_sha256(path)
    if actual_scorer_hashes != lock.scorer_file_sha256:
        errors.append("scorer file hash mismatch")
    if canonical_sha256(actual_scorer_hashes) != lock.scorer_sha256:
        errors.append("scorer aggregate hash mismatch")
    if _production_prompt_sha256() != lock.prompt_sha256:
        errors.append("prompt hash mismatch")
    if canonical_sha256(production_schemas) != lock.production_schema_sha256:
        errors.append("production schema hash mismatch")
    if lock.model_calls != 0:
        errors.append("lock must record zero model calls")

    return LockVerification(
        passed=not errors,
        errors=tuple(errors),
        case_count=len(contents),
        distribution=distribution,
        lock_sha256=lock_hash,
    )


def historical_identity(root: Path = Path(".")) -> dict[str, str]:
    """Return the immutable R1 identities that new work must preserve."""

    return {
        "dev_split_sha256": _canonical_split_hash(root / "evaluation/tool_calling/benchmarks/dev"),
        "frozen_split_sha256": _canonical_split_hash(
            root / "evaluation/tool_calling/benchmarks/frozen"
        ),
        "historical_result_raw_sha256": _raw_sha256(
            root / "results/evaluation_v1/r1/r1_a1_dev_v2_852e543.json"
        ),
        "winner_lock_raw_sha256": _raw_sha256(root / "evaluation/tool_calling/winner_lock.json"),
    }


def _load_jsonl_objects(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    records: list[dict[str, Any]] = []
    for line_number, raw_line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not raw_line.strip():
            continue
        try:
            record = json.loads(raw_line)
        except json.JSONDecodeError as exc:
            raise ValueError(f"{path.name}:{line_number}: invalid JSON: {exc.msg}") from exc
        if not isinstance(record, dict):
            raise TypeError(f"{path.name}:{line_number}: record must be a JSON object")
        records.append(record)
    return records


def _load_existing_cases(benchmarks_dir: Path) -> list[ToolCallCase]:
    cases: list[ToolCallCase] = []
    for split in ("dev", "frozen"):
        for path in sorted((benchmarks_dir / split).glob("*.json")):
            cases.append(ToolCallCase.from_dict(json.loads(path.read_text(encoding="utf-8"))))
    return cases


def _audit_command(args: Any) -> int:
    cases = load_candidates(args.candidates)
    distribution = audit_candidate_distribution(cases)
    audit = audit_candidates(
        cases,
        _load_existing_cases(args.benchmarks),
        get_tool_schemas(),
        _load_jsonl_objects(args.waivers),
    )
    receipt = audit.to_dict()
    receipt["distribution"] = {
        "passed": distribution.passed,
        "total": distribution.total,
        "main_group_counts": distribution.main_group_counts,
        "single_tool_counts": distribution.single_tool_counts,
        "two_tool_counts": distribution.two_tool_counts,
        "robustness_count": distribution.robustness_count,
        "difficulties": distribution.difficulties,
        "errors": list(distribution.errors),
    }
    receipt["passed"] = audit.passed and distribution.passed
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(receipt, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    print(json.dumps(receipt, ensure_ascii=False))
    return 0 if receipt["passed"] else 1


def _review_gate_command(args: Any) -> int:
    adjudication = args.adjudication
    if adjudication is None:
        default_adjudication = args.reviews / "adjudication.jsonl"
        adjudication = default_adjudication if default_adjudication.exists() else None
    gate = evaluate_review_gate(
        load_candidates(args.candidates),
        args.reviews / "reviewer_a.jsonl",
        args.reviews / "reviewer_b.jsonl",
        adjudication,
        get_tool_schemas(),
    )
    print(json.dumps(gate.to_dict(), ensure_ascii=False))
    return 0 if gate.passed else 1


def _default_scorer_files() -> list[Path]:
    lock_path = _project_root() / "evaluation/tool_calling/benchmarks/dev/VERSION.lock"
    data = json.loads(lock_path.read_text(encoding="utf-8"))
    return [_project_root() / value for value in data["scorer_files"]]


def _build_lock_command(args: Any) -> int:
    cases = load_candidates(args.candidates)
    adjudication = args.adjudication
    if adjudication is None:
        adjudication = args.reviews / "adjudication.jsonl"
    gate = evaluate_review_gate(
        cases,
        args.reviews / "reviewer_a.jsonl",
        args.reviews / "reviewer_b.jsonl",
        adjudication,
        get_tool_schemas(),
    )
    if not gate.passed:
        print(json.dumps(gate.to_dict(), ensure_ascii=False))
        return 1
    try:
        lock = build_locked_split(
            cases,
            gate,
            args.output,
            _default_scorer_files(),
            get_tool_schemas(),
        )
        verification = verify_generalization_lock(args.output, args.output / "GENERALIZATION.lock")
    except (OSError, TypeError, ValueError) as exc:
        print(
            json.dumps(
                {
                    "status": "blocked_lock_build",
                    "error": str(exc),
                    "provider_created": False,
                    "model_calls": 0,
                },
                ensure_ascii=False,
            )
        )
        return 1
    receipt = {
        "status": gate.status,
        "case_count": lock.case_count,
        "distribution": lock.distribution,
        "lock_sha256": verification.lock_sha256,
        "lock_verification": "PASS" if verification.passed else "FAIL",
        "errors": list(verification.errors),
        "provider_created": False,
        "model_calls": 0,
    }
    print(json.dumps(receipt, ensure_ascii=False))
    return 0 if verification.passed else 1


def main(argv: Sequence[str] | None = None) -> int:
    """Run offline authoring commands; no command constructs a model provider."""

    parser = ArgumentParser(prog="python -m evaluation.tool_calling.generalization")
    subparsers = parser.add_subparsers(dest="command", required=True)
    audit_parser = subparsers.add_parser("audit", help="audit candidate pack offline")
    audit_parser.add_argument("--candidates", type=Path, required=True)
    audit_parser.add_argument(
        "--benchmarks", type=Path, default=Path("evaluation/tool_calling/benchmarks")
    )
    audit_parser.add_argument(
        "--waivers",
        type=Path,
        default=Path(
            "evaluation/tool_calling/authoring/generalization_v1/near_duplicate_waivers.jsonl"
        ),
    )
    audit_parser.add_argument("--output", type=Path, required=True)
    audit_parser.set_defaults(handler=_audit_command)
    review_parser = subparsers.add_parser(
        "review-gate", help="check two blind human review packs offline"
    )
    review_parser.add_argument("--candidates", type=Path, required=True)
    review_parser.add_argument("--reviews", type=Path, required=True)
    review_parser.add_argument("--adjudication", type=Path)
    review_parser.set_defaults(handler=_review_gate_command)
    build_parser = subparsers.add_parser(
        "build-lock", help="build and verify an approved locked split offline"
    )
    build_parser.add_argument("--candidates", type=Path, required=True)
    build_parser.add_argument("--reviews", type=Path, required=True)
    build_parser.add_argument("--adjudication", type=Path)
    build_parser.add_argument("--output", type=Path, required=True)
    build_parser.set_defaults(handler=_build_lock_command)
    args = parser.parse_args(argv)
    return args.handler(args)


if __name__ == "__main__":  # pragma: no cover - exercised through main()
    raise SystemExit(main())
