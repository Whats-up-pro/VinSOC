"""One-condition CTU GPT-5 Mini runner with immutable, bounded evidence."""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
from dataclasses import asdict, dataclass
from pathlib import Path
from types import SimpleNamespace
from typing import Any

from evaluation.ctu_network_public.contract import (
    CASES, canonical_sha256, portable_text_sha256, split_data,
    validate as validate_dev_contract,
)
from evaluation.dualsql_lite_ctu_gpt5.agents import (
    CAP, MODEL, REASONING_EFFORT, ProviderCall, RoleResult, run_role,
)
from evaluation.dualsql_lite_ctu_gpt5.contract import SERIES_LOCK, verify_e0_baseline
from evaluation.dualsql_lite_ctu_gpt5.prompts import (
    GENERATOR_INSTRUCTIONS, GENERATOR_PROMPT_VERSION,
    LINKER_INSTRUCTIONS, LINKER_PROMPT_VERSION,
)
from evaluation.dualsql_lite_ctu_gpt5.tools import (
    CTUDatabaseTools, MAX_RESPONSE_BYTES, TOOL_SCHEMAS, TOOL_VERSION,
    SnapshotOnlyDuckDBSnapshot,
)
from evaluation.text_to_sql import (
    SQLBenchmarkCase, _extract_sql, _sql_error_category, evaluate_sql_case,
)

E0_REPORT = Path(
    "results/evaluation_v1/ctu_network_public/gpt5_e0/36520685612/ctu-r2-result.json"
)
CONDITIONS = ("E1", "E2", "E3")
INPUT_USD_PER_MILLION = 0.25
OUTPUT_USD_PER_MILLION = 2.0
SERIES_CEILING_USD = 0.75
KNOWN_PRIOR_USD = 0.01979725  # E0 plus the completed R1 dev run.


@dataclass(frozen=True)
class ConditionReport:
    path: Path
    payload: dict[str, Any]

    @property
    def execution_accurate(self) -> int:
        return int(self.payload["metrics"]["execution_accurate"])


def _sha_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _roles(condition: str) -> list[tuple[str, bool, int]]:
    if condition == "E1":
        return [("linker", True, 5), ("generator", False, 1)]
    if condition == "E2":
        return [("generator", True, 5)]
    if condition == "E3":
        return [("linker", True, 5), ("generator", True, 5)]
    raise ValueError("Invalid condition")


def conservative_preflight(schema_context: str) -> dict[str, dict[str, Any]]:
    """Bound all 168 possible calls using serialized requests and prior context."""
    raw_cases = split_data(CASES)
    questions = [item["question"] for item in raw_cases.values()]
    if len(questions) != 8:
        raise ValueError("Pinned CTU dev suite must contain eight cases")
    growth_tokens = MAX_RESPONSE_BYTES + CAP + 1024
    bounds: dict[str, dict[str, Any]] = {}
    for condition in CONDITIONS:
        slots: list[float] = []
        for question in questions:
            for role, enabled, turns in _roles(condition):
                if role == "linker":
                    system = LINKER_INSTRUCTIONS + "\nDatabase schema:\n" + schema_context
                elif condition == "E1":
                    system = GENERATOR_INSTRUCTIONS + "\nLinked schema supplied by controller."
                else:
                    system = GENERATOR_INSTRUCTIONS + "\nDatabase schema:\n" + schema_context
                request: dict[str, Any] = {
                    "model": MODEL, "reasoning_effort": REASONING_EFFORT,
                    "max_completion_tokens": CAP,
                    "messages": [{"role": "system", "content": system},
                                 {"role": "user", "content": question}],
                }
                if enabled:
                    request["tools"] = TOOL_SCHEMAS
                if role == "linker":
                    request["response_format"] = {"type": "json_object"}
                initial_tokens = len(json.dumps(request, ensure_ascii=True).encode("utf-8")) + 50
                for index in range(turns):
                    input_bound = initial_tokens + index * growth_tokens
                    slots.append((input_bound * INPUT_USD_PER_MILLION
                                  + CAP * OUTPUT_USD_PER_MILLION) / 1_000_000)
        bounds[condition] = {"max_calls": len(slots), "slot_bounds_usd": slots,
                             "ceiling_usd": sum(slots)}
    if ({condition: value["max_calls"] for condition, value in bounds.items()}
            != {"E1": 48, "E2": 40, "E3": 80}
            or sum(value["ceiling_usd"] for value in bounds.values()) >= SERIES_CEILING_USD):
        raise ValueError("Conservative series ceiling exceeds the locked limit")
    return bounds


def _verified_inputs(snapshot: Path, series_lock: dict[str, Any]) -> tuple[list[SQLBenchmarkCase], dict[str, Any]]:
    """Verify data and immutable E0 before any client can be constructed."""
    if not snapshot.is_file():
        raise FileNotFoundError("Verified CTU dev snapshot is unavailable")
    locked = json.loads(SERIES_LOCK.read_text(encoding="utf-8"))
    for key in ("version", "model", "reasoning_effort", "max_completion_tokens",
                "max_retries", "pricing"):
        if series_lock.get(key) != locked.get(key):
            raise ValueError(f"Series identity mismatch: {key}")
    baseline = verify_e0_baseline(E0_REPORT, SERIES_LOCK)
    dev = validate_dev_contract(snapshot)
    if (dev["split_sha256"] != baseline.split_sha256
            or dev["logical_snapshot_sha256"] != baseline.logical_snapshot_sha256):
        raise ValueError("CTU dev and E0 snapshot identity mismatch")
    cases = [SQLBenchmarkCase.from_dict(item) for item in split_data(CASES).values()]
    if [case.case_id for case in cases] != list(baseline.case_ids):
        raise ValueError("CTU dev case identity mismatch")
    return cases, {**dev, "e0_report_sha256": baseline.report_sha256,
                   "e0_known_cost_usd": baseline.known_cost_usd}


def _runtime_gates(series_lock: dict[str, Any], total_ceiling: float,
                   condition_ceiling: float) -> dict[str, Any]:
    pricing = series_lock.get("pricing", {})
    gate = series_lock.get("runtime_gates", {})
    if (pricing.get("input_usd_per_million") != INPUT_USD_PER_MILLION
            or pricing.get("output_usd_per_million") != OUTPUT_USD_PER_MILLION
            or gate.get("current_input_usd_per_million") != INPUT_USD_PER_MILLION
            or gate.get("current_output_usd_per_million") != OUTPUT_USD_PER_MILLION
            or not gate.get("pricing_checked_utc")):
        raise ValueError("Current official pricing gate is unverified")
    if (not gate.get("credit_checked_utc")
            or not gate.get("organization_project_verified")
            or type(gate.get("usable_credit_usd")) not in {int, float}
            or type(gate.get("spend_limit_remaining_usd")) not in {int, float}
            or gate["usable_credit_usd"] < condition_ceiling
            or gate["spend_limit_remaining_usd"] < condition_ceiling):
        raise ValueError("Account, credit, or spend-limit gate is unverified")
    cumulative = gate.get("cumulative_known_usd")
    cap = gate.get("total_authorized_usd")
    if (type(cumulative) not in {int, float} or cumulative < KNOWN_PRIOR_USD
            or type(cap) not in {int, float} or cap > 2.0
            or cumulative + total_ceiling >= cap):
        raise ValueError("Cumulative series cost gate failed")
    return {"pricing_checked_utc": gate["pricing_checked_utc"],
            "credit_checked_utc": gate["credit_checked_utc"],
            "organization_project_verified": True,
            "usable_credit_usd": gate["usable_credit_usd"],
            "spend_limit_remaining_usd": gate["spend_limit_remaining_usd"],
            "cumulative_known_usd": cumulative,
            "total_authorized_usd": cap}


def _partial_path(output: Path) -> Path:
    return output.with_name(output.stem + ".partial" + output.suffix)


def _write_partial(path: Path, payload: dict[str, Any]) -> None:
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(json.dumps(payload, sort_keys=True, indent=2, default=str) + "\n",
                         encoding="utf-8")
    os.replace(temporary, path)


def run_condition(
    condition: str,
    snapshot_path: Path,
    output_path: Path,
    client: Any,
    series_lock: dict[str, Any],
) -> ConditionReport:
    """Run only one paid condition after all offline and runtime gates pass."""
    if condition not in CONDITIONS:
        raise ValueError("Invalid condition")
    output = Path(output_path)
    partial = _partial_path(output)
    if output.exists() or partial.exists():
        raise FileExistsError("Result or partial artifact already exists")
    snapshot = Path(snapshot_path)
    cases, identity = _verified_inputs(snapshot, series_lock)
    tools = CTUDatabaseTools(snapshot)
    schema_context = tools.schema_context()
    bounds = conservative_preflight(schema_context)
    total_ceiling = sum(value["ceiling_usd"] for value in bounds.values())
    condition_bound = bounds[condition]
    gate = _runtime_gates(series_lock, total_ceiling, condition_bound["ceiling_usd"])
    git_sha = subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip()
    if len(git_sha) != 40:
        raise ValueError("Implementation SHA is unavailable")
    output.parent.mkdir(parents=True, exist_ok=True)
    report: dict[str, Any] = {
        "run_status": "partial", "condition": condition,
        "implementation_sha": git_sha,
        "case_ids": [case.case_id for case in cases],
        "case_results": [], "provider_calls": [], "serialized_requests": [],
        "known_cost_usd": 0.0, "cost_unknown": False,
        "model_contract": {"model": MODEL, "reasoning_effort": REASONING_EFFORT,
                           "max_completion_tokens": CAP, "max_retries": 0},
        "model_config_sha256": canonical_sha256({"model": MODEL,
            "reasoning_effort": REASONING_EFFORT, "max_completion_tokens": CAP,
            "max_retries": 0}),
        "provenance": {
            "split_sha256": identity["split_sha256"],
            "logical_snapshot_sha256": identity["logical_snapshot_sha256"],
            "source_file_sha256": identity["source_file_sha256"],
            "builder_scorer_sha256": identity["builder_scorer_sha256"],
            "e0_report_sha256": identity["e0_report_sha256"],
            "linker_prompt_sha256": _sha_text(LINKER_INSTRUCTIONS),
            "generator_prompt_sha256": _sha_text(GENERATOR_INSTRUCTIONS),
            "linker_prompt_version": LINKER_PROMPT_VERSION,
            "generator_prompt_version": GENERATOR_PROMPT_VERSION,
            "tool_schema_sha256": canonical_sha256(TOOL_SCHEMAS),
            "tool_implementation_sha256": portable_text_sha256(
                Path("evaluation/dualsql_lite_ctu_gpt5/tools.py")),
            "tool_version": TOOL_VERSION,
            "catalog_sha256": tools.catalog_sha256,
            "schema_context_sha256": _sha_text(schema_context),
        },
        "pricing": {**series_lock["pricing"],
                    "current_check_utc": gate["pricing_checked_utc"]},
        "account_gate": gate,
        "preflight": {"condition_ceiling_usd": condition_bound["ceiling_usd"],
                       "series_ceiling_usd": total_ceiling,
                       "max_condition_calls": condition_bound["max_calls"]},
    }
    _write_partial(partial, report)

    actual_client = client() if callable(client) else client
    if getattr(actual_client, "max_retries", None) != 0:
        raise ValueError("SDK retries must be zero")
    slots = condition_bound["slot_bounds_usd"]
    attempted = 0
    budget = condition_bound["ceiling_usd"] * 1.01

    def before_create(**request: Any) -> Any:
        nonlocal attempted
        if attempted >= len(slots):
            raise ValueError("Condition call cap reached")
        remaining = sum(slots[attempted:])
        if report["known_cost_usd"] + remaining >= budget:
            raise ValueError("Per-call cost gate failed")
        attempted += 1
        report["attempted_calls"] = attempted
        report["serialized_requests"].append(json.loads(json.dumps(request, default=str)))
        _write_partial(partial, report)
        return actual_client.chat.completions.create(**request)

    proxy = SimpleNamespace(chat=SimpleNamespace(
        completions=SimpleNamespace(create=before_create)))

    def persist_call(call: ProviderCall) -> None:
        report["provider_calls"].append(asdict(call))
        report["known_cost_usd"] += call.cost_usd
        _write_partial(partial, report)

    reader = SnapshotOnlyDuckDBSnapshot(snapshot)
    try:
        for case in cases:
            linked: RoleResult | None = None
            if condition in {"E1", "E3"}:
                linked = run_role(role="linker", question=case.question,
                    system_prompt=LINKER_INSTRUCTIONS + "\nDatabase schema:\n" + schema_context,
                    tools=tools, client=proxy, telemetry_sink=persist_call)
            generator: RoleResult | None = None
            if linked is None or linked.error is None:
                generator_tools = tools if condition in {"E2", "E3"} else None
                context = ("\nLinked schema:\n" + json.dumps(linked.linked_schema)
                           if linked is not None else "\nDatabase schema:\n" + schema_context)
                generator = run_role(role="generator", question=case.question,
                    system_prompt=GENERATOR_INSTRUCTIONS + context,
                    tools=generator_tools, client=proxy,
                    telemetry_sink=persist_call,
                    max_turns=1 if condition == "E1" else 5)
            sql = _extract_sql(generator.content) if generator and generator.content else None
            evaluation = evaluate_sql_case(case, sql, reader) if sql else None
            category = (_sql_error_category(evaluation) if evaluation else
                        (linked.error if linked and linked.error else
                         generator.error if generator else "NO_SQL"))
            events = (linked.trajectory if linked else []) + (generator.trajectory if generator else [])
            report["case_results"].append({
                "case_id": case.case_id, "question_sha256": _sha_text(case.question),
                "category": case.category, "difficulty": case.difficulty,
                "linked_schema": linked.linked_schema if linked else None,
                "linker_error": linked.error if linked else None,
                "generator_error": generator.error if generator else None,
                "linker_turns": linked.turns if linked else 0,
                "generator_turns": generator.turns if generator else 0,
                "linker_tool_calls": linked.tool_count if linked else 0,
                "generator_tool_calls": generator.tool_count if generator else 0,
                "trajectory": events, "final_sql": sql, "error_category": category,
                "syntax_valid": evaluation.syntax_valid if evaluation else False,
                "execution_success": evaluation.execution_success if evaluation else False,
                "execution_accurate": evaluation.execution_accurate if evaluation else False,
                "safety_rejected": evaluation.safety_rejected if evaluation else False,
            })
            _write_partial(partial, report)
    except Exception as exc:
        report["run_status"] = "partial"
        report["fatal_error_type"] = type(exc).__name__
        if attempted > len(report["provider_calls"]):
            report["cost_unknown"] = True
        _write_partial(partial, report)
        raise

    report["run_status"] = "complete"
    report["provenance"]["serialized_requests_sha256"] = canonical_sha256(
        report["serialized_requests"])
    report["metrics"] = {
        "execution_accurate": sum(bool(item["execution_accurate"])
                                  for item in report["case_results"]),
        "syntax_valid": sum(bool(item["syntax_valid"]) for item in report["case_results"]),
        "execution_success": sum(bool(item["execution_success"])
                                 for item in report["case_results"]),
        "safety_rejected": sum(bool(item["safety_rejected"])
                               for item in report["case_results"]),
    }
    if len(report["case_results"]) != len(cases) or report["cost_unknown"]:
        raise ValueError("Incomplete condition report")
    with output.open("x", encoding="utf-8") as destination:
        destination.write(json.dumps(report, sort_keys=True, indent=2, default=str) + "\n")
    _write_partial(partial, report)
    return ConditionReport(output, report)
