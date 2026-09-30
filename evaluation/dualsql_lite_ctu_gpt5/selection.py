"""Deterministic selection across immutable CTU E0 and E1-E3 evidence."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from evaluation.dualsql_lite_ctu_gpt5.contract import BaselineEvidence, SERIES_LOCK
from evaluation.dualsql_lite_ctu_gpt5.runner import ConditionReport

CONDITIONS = ("E0", "E1", "E2", "E3")
MODEL_CONTRACT = {
    "model": "gpt-5-mini-2025-08-07",
    "reasoning_effort": "low",
    "max_completion_tokens": 1000,
    "max_retries": 0,
}
DRIFT_FIELDS = (
    "linker_prompt_sha256",
    "generator_prompt_sha256",
    "tool_schema_sha256",
    "tool_implementation_sha256",
    "tool_version",
    "catalog_sha256",
    "schema_context_sha256",
)


@dataclass(frozen=True)
class SelectionResult:
    winner: str
    rows: tuple[dict[str, Any], ...]
    tiebreak_trace: tuple[str, ...]
    implementation_sha: str
    payload: dict[str, Any]

    @property
    def ranking(self) -> tuple[str, ...]:
        return self.tiebreak_trace


def _fail(field: str) -> None:
    raise ValueError(f"R2 selection compatibility failed: {field}")


def _verified_row(expected_condition: str, report: ConditionReport,
                  e0: BaselineEvidence) -> dict[str, Any]:
    payload = report.payload
    if (payload.get("condition") != expected_condition
            or payload.get("run_status") != "complete"):
        _fail(f"{expected_condition} completion")
    ids = list(e0.case_ids)
    results = payload.get("case_results", [])
    if (payload.get("case_ids") != ids or len(results) != 8
            or [item.get("case_id") for item in results] != ids
            or len(set(ids)) != 8):
        _fail(f"{expected_condition} case identity or coverage")
    provenance = payload.get("provenance", {})
    fixed_identity = {
        "e0_report_sha256": e0.report_sha256,
        "split_sha256": e0.split_sha256,
        "logical_snapshot_sha256": e0.logical_snapshot_sha256,
        "source_file_sha256": e0.source_file_sha256,
        "builder_scorer_sha256": e0.builder_scorer_sha256,
        "model_config_sha256": e0.model_config_sha256,
    }
    if any(provenance.get(key) != value for key, value in fixed_identity.items()):
        _fail(f"{expected_condition} benchmark or model identity")
    if (payload.get("model_contract") != MODEL_CONTRACT
            or payload.get("model_config_sha256") != e0.model_config_sha256):
        _fail(f"{expected_condition} model contract")

    calls = payload.get("provider_calls", [])
    if (payload.get("cost_unknown") is not False
            or not isinstance(calls, list) or not calls
            or payload.get("attempted_calls") != len(calls)):
        _fail(f"{expected_condition} response or usage coverage")
    for call in calls:
        if (call.get("actual_model") != MODEL_CONTRACT["model"]
                or not call.get("response_id")
                or type(call.get("input_tokens")) is not int
                or call["input_tokens"] <= 0
                or type(call.get("output_tokens")) is not int
                or not 0 <= call["output_tokens"] <= 1000
                or type(call.get("cost_usd")) not in {int, float}
                or call["cost_usd"] < 0
                or type(call.get("latency_ms")) not in {int, float}
                or call["latency_ms"] < 0):
            _fail(f"{expected_condition} provider identity or usage")
    cost = sum(float(call["cost_usd"]) for call in calls)
    reported_cost = float(payload.get("known_cost_usd", -1))
    if abs(cost - reported_cost) > 1e-9:
        _fail(f"{expected_condition} provider cost total")

    derived = {
        "execution_accurate": sum(item.get("execution_accurate") is True
                                   for item in results),
        "syntax_valid": sum(item.get("syntax_valid") is True for item in results),
        "execution_success": sum(item.get("execution_success") is True
                                 for item in results),
        "safety_rejected": sum(item.get("safety_rejected") is True
                               for item in results),
    }
    metrics = payload.get("metrics", {})
    if any(metrics.get(key) != value for key, value in derived.items()):
        _fail(f"{expected_condition} metric totals")
    implementation_sha = payload.get("implementation_sha")
    if not isinstance(implementation_sha, str) or len(implementation_sha) != 40:
        _fail(f"{expected_condition} implementation SHA")
    return {
        "condition": expected_condition,
        **derived,
        "cost_usd": reported_cost,
        "model_calls": len(calls),
        "latency_ms": sum(float(call["latency_ms"]) for call in calls),
        "implementation_sha": implementation_sha,
        "model_config_sha256": payload["model_config_sha256"],
        "drift": {key: provenance.get(key) for key in DRIFT_FIELDS},
    }


def build_selection(e0: BaselineEvidence, e1: ConditionReport,
                    e2: ConditionReport, e3: ConditionReport) -> SelectionResult:
    """Reject identity drift, then apply the predeclared five-stage tie-break."""
    rows = [_verified_row(name, report, e0)
            for name, report in zip(CONDITIONS[1:], (e1, e2, e3))]
    first = rows[0]
    for row in rows[1:]:
        for key in ("implementation_sha", "model_config_sha256", "drift"):
            if row[key] != first[key]:
                _fail(f"E1-E3 implementation or prompt/tool/catalog drift: {key}")

    public_rows = ({
        "condition": "E0",
        "execution_accurate": e0.execution_accurate,
        "syntax_valid": e0.syntax_valid,
        "execution_success": e0.execution_success,
        "safety_rejected": e0.safety_rejected,
        "cost_usd": e0.known_cost_usd,
        "model_calls": e0.model_calls,
        "latency_ms": e0.latency_ms,
    },) + tuple({
        key: row[key] for key in (
            "condition", "execution_accurate", "syntax_valid",
            "execution_success", "safety_rejected", "cost_usd",
            "model_calls", "latency_ms",
        )
    } for row in rows)

    def selection_key(row: dict[str, Any]) -> tuple[Any, ...]:
        return (
            -row["execution_accurate"],
            row["cost_usd"],
            row["model_calls"],
            row["latency_ms"],
            CONDITIONS.index(row["condition"]),
        )

    ordered = tuple(row["condition"] for row in sorted(public_rows, key=selection_key))
    lock = json.loads(SERIES_LOCK.read_text(encoding="utf-8"))
    result_payload = {
        "series_version": lock["version"],
        "headline_metric": "execution_accuracy",
        "winner": ordered[0],
        "ranking": list(ordered),
        "conditions": list(public_rows),
        "selection_order": [
            "higher_execution_accuracy",
            "lower_known_cost_usd",
            "fewer_model_calls",
            "lower_latency_ms",
            "simpler_architecture_E0_E1_E2_E3",
        ],
        "identity": {
            "case_ids": list(e0.case_ids),
            "split_sha256": e0.split_sha256,
            "logical_snapshot_sha256": e0.logical_snapshot_sha256,
            "source_file_sha256": e0.source_file_sha256,
            "builder_scorer_sha256": e0.builder_scorer_sha256,
            "model_config_sha256": e0.model_config_sha256,
            "e0_report_sha256": e0.report_sha256,
            "e1_e3_implementation_sha": first["implementation_sha"],
        },
    }
    return SelectionResult(
        ordered[0], public_rows, ordered, first["implementation_sha"], result_payload,
    )
