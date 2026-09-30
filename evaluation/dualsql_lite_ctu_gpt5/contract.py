"""Offline E0 compatibility gate for the CTU GPT-5 Mini comparison."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from evaluation.ctu_network_public.contract import canonical_sha256, split_data


MODEL = "gpt-5-mini-2025-08-07"
E0_REPORT_SHA256 = "33b35678171309c1a8958c1d9818499915986942e6936a03428df8fa0544bc15"
DEV_LOCK = Path("evaluation/ctu_network_public/VERSION.lock")
DEV_CASES = Path("evaluation/ctu_network_public/dev")
SERIES_LOCK = Path("evaluation/dualsql_lite_ctu_gpt5/SERIES.lock")
EXPECTED_CASE_IDS = tuple(f"ctu_sql_{index:03d}" for index in range(1, 9))


@dataclass(frozen=True)
class BaselineEvidence:
    run_id: str
    case_ids: tuple[str, ...]
    execution_accurate: int
    known_cost_usd: float
    report_sha256: str
    logical_snapshot_sha256: str
    split_sha256: str
    model_config_sha256: str
    system_prompt_sha256: str
    schema_context_sha256: str
    model_calls: int = 8
    latency_ms: float = 0.0
    source_file_sha256: dict[str, str] | None = None
    builder_scorer_sha256: dict[str, str] | None = None


def _require(condition: bool, field: str) -> None:
    if not condition:
        raise ValueError(f"E0 compatibility failed: {field}")


def _sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def verify_e0_baseline(
    report_path: Path,
    series_lock_path: Path = SERIES_LOCK,
) -> BaselineEvidence:
    """Validate stored E0 responses and requests without constructing a client."""
    report_path = Path(report_path)
    lock = json.loads(Path(series_lock_path).read_text(encoding="utf-8"))
    report = json.loads(report_path.read_text(encoding="utf-8"))
    dev_lock = json.loads(DEV_LOCK.read_text(encoding="utf-8"))
    raw_cases = split_data(DEV_CASES)
    _require(canonical_sha256(raw_cases) == dev_lock["split_sha256"], "local dev split")
    _require(lock.get("version") == "dualsql_lite_ctu_gpt5_v1", "series version")
    _require(lock.get("dev_version") == dev_lock.get("version"), "dev version")
    _require(lock.get("e0_run_id") == report.get("run_id") == "36520685612", "run ID")
    _require(report.get("run_status") == "complete" and report.get("pilot_eligible") is True,
             "run status")
    _require(all(report.get(key) == 8 for key in
                 ("attempted_calls", "responses_received", "calls_with_valid_usage")),
             "response and usage counts")

    case_ids = report.get("case_ids")
    _require(case_ids == list(EXPECTED_CASE_IDS)
             and case_ids == lock.get("case_ids") == dev_lock.get("case_ids"), "case IDs")
    cases = report.get("case_results")
    requests = report.get("serialized_requests")
    _require(isinstance(cases, list) and len(cases) == 8
             and isinstance(requests, list) and len(requests) == 8, "case/request count")
    _require([item.get("case_id") for item in cases] == case_ids
             and len({item.get("case_id") for item in cases}) == 8, "case result IDs")

    provenance = report.get("provenance", {})
    for key in ("split_sha256", "logical_snapshot_sha256", "source_file_sha256",
                "builder_scorer_sha256"):
        expected = dev_lock.get(key)
        _require(provenance.get(key) == expected == lock.get(key), key)
    _require(report.get("version") == dev_lock.get("version"), "report dev version")
    for key in ("system_prompt_sha256", "schema_context_sha256", "model_config_sha256"):
        value = report.get(key) if key == "model_config_sha256" else provenance.get(key)
        _require(value == lock.get(key), key)
    _require(provenance.get("model_config_sha256") == report.get("model_config_sha256"),
             "model config provenance")

    config = report.get("config", {})
    for key in ("model", "reasoning_effort", "max_completion_tokens", "max_retries"):
        _require(config.get(key) == lock.get(key), f"config {key}")
    _require(config.get("provider") == "openai", "provider")
    _require(config.get("temperature") is None, "descriptive temperature")
    _require(lock.get("model") == MODEL and lock.get("reasoning_effort") == "low"
             and lock.get("max_completion_tokens") == 1000
             and lock.get("max_retries") == 0, "GPT-5 request contract")

    pricing = lock.get("pricing", {})
    report_pricing = report.get("pricing", {})
    _require(pricing.get("source") == report_pricing.get("source")
             == "https://developers.openai.com/api/docs/models/gpt-5-mini",
             "pricing source")
    _require(pricing.get("input_usd_per_million") == report_pricing.get("input_usd_per_million") == 0.25
             and pricing.get("output_usd_per_million") == report_pricing.get("output_usd_per_million") == 2.0,
             "pricing rates")
    _require(isinstance(pricing.get("verified_utc"), str) and pricing["verified_utc"]
             and pricing.get("stop_if_current_official_price_differs") is True,
             "pricing verification policy")

    first_system: str | None = None
    derived_cost = 0.0
    for index, (case_id, case, request) in enumerate(zip(case_ids, cases, requests), start=1):
        _require(isinstance(request, dict) and "temperature" not in request
                 and "tools" not in request, f"request {index} forbidden keys")
        for key in ("model", "reasoning_effort", "max_completion_tokens"):
            _require(request.get(key) == lock[key], f"request {index} {key}")
        messages = request.get("messages")
        _require(isinstance(messages, list) and len(messages) == 2
                 and messages[0].get("role") == "system"
                 and messages[1].get("role") == "user", f"request {index} messages")
        system = messages[0].get("content")
        question = messages[1].get("content")
        _require(isinstance(system, str) and _sha256_text(system) == lock["system_prompt_sha256"],
                 f"request {index} system prompt")
        _require(question == raw_cases[f"{case_id}.json"]["question"],
                 f"request {index} question")
        if first_system is None:
            first_system = system
        _require(system == first_system, f"request {index} system consistency")
        schema_start = system.find("network_flows(")
        _require(schema_start >= 0
                 and _sha256_text(system[schema_start:]) == lock["schema_context_sha256"],
                 f"request {index} schema context")
        _require(case.get("case_id") == case_id and case.get("request_index") == index,
                 f"case {index} request order")
        _require(case.get("actual_model") == MODEL and isinstance(case.get("response_id"), str)
                 and case["response_id"], f"case {index} response identity")
        input_tokens, output_tokens = case.get("input_tokens"), case.get("output_tokens")
        _require(type(input_tokens) is int and input_tokens > 0
                 and type(output_tokens) is int and 0 <= output_tokens <= 1000,
                 f"case {index} usage")
        _require(isinstance(case.get("latency_ms"), (int, float)) and case["latency_ms"] >= 0,
                 f"case {index} latency")
        case_cost = (input_tokens * 0.25 + output_tokens * 2.0) / 1_000_000
        _require(abs(case.get("cost_usd", -1) - case_cost) < 1e-10,
                 f"case {index} cost")
        derived_cost += case_cost
    _require(abs(derived_cost - report_pricing.get("known_cost_usd", -1)) < 1e-10
             and report_pricing.get("cost_unknown") is False, "total usage cost")
    _require(report.get("metrics", {}).get("execution_accuracy") == 0.0
             and report["metrics"].get("syntax_validity_rate") == 1.0
             and report["metrics"].get("execution_success_rate") == 1.0
             and report["metrics"].get("safety_rejection_rate") == 0.0,
             "E0 score")

    report_sha = hashlib.sha256(report_path.read_bytes()).hexdigest()
    _require(report_sha == lock.get("e0_report_sha256") == E0_REPORT_SHA256,
             "fixed report SHA-256")
    return BaselineEvidence(
        run_id=report["run_id"], case_ids=tuple(case_ids),
        execution_accurate=0, known_cost_usd=derived_cost,
        report_sha256=report_sha,
        logical_snapshot_sha256=provenance["logical_snapshot_sha256"],
        split_sha256=provenance["split_sha256"],
        model_config_sha256=report["model_config_sha256"],
        system_prompt_sha256=provenance["system_prompt_sha256"],
        schema_context_sha256=provenance["schema_context_sha256"],
        model_calls=report["attempted_calls"],
        latency_ms=sum(item["latency_ms"] for item in cases),
        source_file_sha256=provenance["source_file_sha256"],
        builder_scorer_sha256=provenance["builder_scorer_sha256"],
    )
