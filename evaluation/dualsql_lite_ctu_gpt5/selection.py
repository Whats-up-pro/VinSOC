"""Deterministic selection across immutable CTU E0 and one-shot E1-E3 reports."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from evaluation.dualsql_lite_ctu_gpt5.contract import BaselineEvidence
from evaluation.dualsql_lite_ctu_gpt5.runner import ConditionReport

CONDITIONS = ("E0", "E1", "E2", "E3")
MODEL = "gpt-5-mini-2025-08-07"
DRIFT_FIELDS = (
    "linker_prompt_sha256", "generator_prompt_sha256", "tool_schema_sha256",
    "tool_implementation_sha256", "catalog_sha256", "schema_context_sha256",
)


@dataclass(frozen=True)
class SelectionResult:
    winner: str
    rows: tuple[dict[str, Any], ...]
    tiebreak_trace: tuple[str, ...]
    implementation_sha: str


def _verified_row(report: ConditionReport, e0: BaselineEvidence) -> dict[str, Any]:
    payload = report.payload
    condition = payload.get("condition")
    if condition not in CONDITIONS[1:] or payload.get("run_status") != "complete":
        raise ValueError("Condition report is partial or invalid")
    ids = list(e0.case_ids)
    results = payload.get("case_results", [])
    if (payload.get("case_ids") != ids or len(results) != 8
            or [item.get("case_id") for item in results] != ids
            or len(set(ids)) != 8):
        raise ValueError("Case identity or coverage differs")
    provenance = payload.get("provenance", {})
    expected = {"e0_report_sha256": e0.report_sha256,
                "split_sha256": e0.split_sha256,
                "logical_snapshot_sha256": e0.logical_snapshot_sha256,
                "source_file_sha256": e0.source_file_sha256,
                "builder_scorer_sha256": e0.builder_scorer_sha256}
    if any(provenance.get(key) != value for key, value in expected.items()):
        raise ValueError("Snapshot, split, source, scorer, or E0 identity differs")
    contract = payload.get("model_contract", {})
    if contract != {"model": MODEL, "reasoning_effort": "low",
                    "max_completion_tokens": 1000, "max_retries": 0}:
        raise ValueError("Model contract differs")
    calls = payload.get("provider_calls", [])
    if (payload.get("cost_unknown") is not False
            or not isinstance(calls, list) or not calls
            or payload.get("attempted_calls") != len(calls)):
        raise ValueError("Response or usage coverage is incomplete")
    for call in calls:
        if (call.get("actual_model") != MODEL or not call.get("response_id")
                or type(call.get("input_tokens")) is not int or call["input_tokens"] <= 0
                or type(call.get("output_tokens")) is not int
                or not 0 <= call["output_tokens"] <= 1000
                or type(call.get("cost_usd")) not in {int, float}
                or call["cost_usd"] < 0
                or type(call.get("latency_ms")) not in {int, float}
                or call["latency_ms"] < 0):
            raise ValueError("Provider call identity or usage differs")
    cost = sum(call["cost_usd"] for call in calls)
    if abs(cost - payload.get("known_cost_usd", -1)) > 1e-9:
        raise ValueError("Provider cost total differs")
    score = sum(item.get("execution_accurate") is True for item in results)
    if score != payload.get("metrics", {}).get("execution_accurate"):
        raise ValueError("Execution Accuracy total differs")
    sha = payload.get("implementation_sha")
    if not isinstance(sha, str) or len(sha) != 40:
        raise ValueError("Implementation SHA is absent")
    return {"condition": condition, "execution_accurate": score,
            "cost_usd": cost, "model_calls": len(calls),
            "latency_ms": sum(call["latency_ms"] for call in calls),
            "implementation_sha": sha,
            "model_config_sha256": payload.get("model_config_sha256"),
            "drift": {key: provenance.get(key) for key in DRIFT_FIELDS}}


def build_selection(e0: BaselineEvidence, e1: ConditionReport,
                    e2: ConditionReport, e3: ConditionReport) -> SelectionResult:
    """Reject identity drift, then apply the predeclared five-stage tie-break."""
    rows = [_verified_row(report, e0) for report in (e1, e2, e3)]
    if [row["condition"] for row in rows] != list(CONDITIONS[1:]):
        raise ValueError("E1, E2, E3 order is required")
    first = rows[0]
    for row in rows[1:]:
        for key in ("implementation_sha", "model_config_sha256", "drift"):
            if row[key] != first[key]:
                raise ValueError(f"E1-E3 implementation or prompt/tool/catalog drift: {key}")
    all_rows = [{"condition": "E0", "execution_accurate": e0.execution_accurate,
                 "cost_usd": e0.known_cost_usd, "model_calls": e0.model_calls,
                 "latency_ms": e0.latency_ms}] + [
                     {key: row[key] for key in ("condition", "execution_accurate",
                                               "cost_usd", "model_calls", "latency_ms")}
                     for row in rows]
    def key(row: dict[str, Any]) -> tuple[Any, ...]:
        return (-row["execution_accurate"], row["cost_usd"],
                row["model_calls"], row["latency_ms"],
                CONDITIONS.index(row["condition"]))
    ordered = sorted(all_rows, key=key)
    return SelectionResult(ordered[0]["condition"], tuple(all_rows),
                           tuple(row["condition"] for row in ordered),
                           first["implementation_sha"])
