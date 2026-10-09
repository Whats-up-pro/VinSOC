"""Authoring and validation support for the R1 generalization split."""

from __future__ import annotations

import json
import re
import unicodedata
from argparse import ArgumentParser
from collections import Counter, defaultdict
from collections.abc import Sequence
from dataclasses import dataclass
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

    production_tools = tuple(
        schema["function"]["name"] for schema in get_tool_schemas()
    )
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
            errors.append(
                f"{group} difficulty coverage mismatch: {sorted(difficulties[group])}"
            )

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
_HASH_RE = re.compile(r"(?<![a-f0-9])(?:[a-f0-9]{64}|[a-f0-9]{40}|[a-f0-9]{32})(?![a-f0-9])", re.IGNORECASE)
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


def _schema_errors_for_case(
    case: CandidateCase, schema_names: set[str]
) -> list[str]:
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
    schema_names = {
        schema.get("function", {}).get("name") for schema in schemas
    } - {None}
    schema_errors: list[str] = []
    if schemas:
        for case in cases:
            schema_errors.extend(_schema_errors_for_case(case, schema_names))

    passed = not (
        exact or pivot or near or leakage or schema_errors or waiver_errors
    )
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


def write_blind_review_packs(
    cases: Sequence[CandidateCase], output_dir: Path
) -> ReviewPackReceipt:
    """Write blind inputs without source metadata or authoring strata."""

    output_dir.mkdir(parents=True, exist_ok=True)
    payload = "\n".join(
        json.dumps(_blind_review_row(case), ensure_ascii=False) for case in cases
    ) + "\n"
    hashes: dict[str, str] = {}
    for name in ("reviewer_a.jsonl", "reviewer_b.jsonl"):
        path = output_dir / name
        path.write_text(payload, encoding="utf-8")
        hashes[name] = _raw_sha256(path)
    return ReviewPackReceipt(case_count=len(cases), pack_sha256=hashes)


def _schema_by_tool(schemas: Sequence[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    return {
        schema["function"]["name"]: schema["function"]["parameters"]
        for schema in schemas
    }


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
            validation_errors = list(
                Draft202012Validator(properties[argument]).iter_errors(value)
            )
            if validation_errors:
                errors.append(
                    f"{prefix}: invalid value for {argument!r}: "
                    f"{validation_errors[0].message}"
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
            row.get(key) != value
            for key, value in _blind_review_row(cases_by_id[case_id]).items()
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
) -> tuple[set[str], list[str], set[str]]:
    if not disagreements:
        return set(), [], set()
    if path is None or not path.exists():
        return set(), [], set(disagreements)
    errors: list[str] = []
    resolved: set[str] = set()
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
            resolved.add(case_id)
        else:
            blocked.add(case_id)
    return resolved, errors, blocked


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
        pending = set(cases_by_id).difference(decisions_a).union(
            set(cases_by_id).difference(decisions_b)
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
    resolved, adjudication_errors, adjudication_blocked = _read_adjudications(
        adjudication_path, disagreements, ids_a | ids_b, schemas_by_tool
    )
    errors.extend(adjudication_errors)
    unresolved = disagreements.difference(resolved)
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
    return ReviewGate(
        True,
        "approved",
        count_a,
        count_b,
        tuple(sorted(disagreements)),
        (),
        (),
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
    args = parser.parse_args(argv)
    return args.handler(args)


if __name__ == "__main__":  # pragma: no cover - exercised through main()
    raise SystemExit(main())
