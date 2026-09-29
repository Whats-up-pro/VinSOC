"""One-shot paid runner for the locked CTU-only R2 public_dev pilot."""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from time import perf_counter
from typing import Any

from evaluation.ctu_network_public.contract import CASES, LOCK, validate
from evaluation.text_to_sql import SQLBenchmarkCase, _extract_sql, _sql_error_category, aggregate_sql_metrics, evaluate_sql_case
from vinsoc_data.duckdb_store import DuckDBSnapshot

# ---------------------------------------------------------------------------
# Load authoritative lock; compute SHA-256 of the lock file at runtime.
# ---------------------------------------------------------------------------
_LOCK_PATH = Path(__file__).parent / "MODEL_CONFIG_GPT5MINI.lock"

with _LOCK_PATH.open(encoding="utf-8") as _fh:
    _LOCK_RAW = _fh.read()

_MODEL_CONFIG_SHA256 = hashlib.sha256(_LOCK_RAW.encode("utf-8")).hexdigest()
_MODEL_CONFIG = json.loads(_LOCK_RAW)

# Runtime constants — must match lock values.
MODEL = "gpt-5-mini-2025-08-07"
REASONING_EFFORT = "low"
CAP = 1000
MAX_RETRIES = 0
INPUT_USD_M = 0.25
OUTPUT_USD_M = 2.00
# Conservative ceiling of actual 8 serialized requests must be < $0.10 before any call.
E0_SUITE_BUDGET_USD = 0.10
FRAMING_TOKENS = 4096
PRICING_SOURCE = "https://developers.openai.com/api/docs/models/gpt-5-mini"

# Verify lock fields match runtime constants (fail fast at import time).
if _MODEL_CONFIG.get("model") != MODEL:
    raise ValueError(f"lock model={_MODEL_CONFIG['model']} != runtime MODEL={MODEL}")
if _MODEL_CONFIG.get("reasoning_effort") != REASONING_EFFORT:
    raise ValueError(f"lock reasoning_effort={_MODEL_CONFIG['reasoning_effort']} != runtime REASONING_EFFORT={REASONING_EFFORT}")
if _MODEL_CONFIG.get("max_completion_tokens") != CAP:
    raise ValueError(f"lock max_completion_tokens={_MODEL_CONFIG['max_completion_tokens']} != runtime CAP={CAP}")
if _MODEL_CONFIG.get("max_retries") != MAX_RETRIES:
    raise ValueError(f"lock max_retries={_MODEL_CONFIG['max_retries']} != runtime MAX_RETRIES={MAX_RETRIES}")
if _MODEL_CONFIG.get("input_price_usd_per_million") != INPUT_USD_M:
    raise ValueError(f"lock input_price={_MODEL_CONFIG['input_price_usd_per_million']} != runtime INPUT_USD_M={INPUT_USD_M}")
if _MODEL_CONFIG.get("output_price_usd_per_million") != OUTPUT_USD_M:
    raise ValueError(f"lock output_price={_MODEL_CONFIG['output_price_usd_per_million']} != runtime OUTPUT_USD_M={OUTPUT_USD_M}")
if _MODEL_CONFIG.get("ceiling_8_cases_usd") != E0_SUITE_BUDGET_USD:
    raise ValueError(f"lock ceiling_8_cases_usd={_MODEL_CONFIG['ceiling_8_cases_usd']} != runtime E0_SUITE_BUDGET_USD={E0_SUITE_BUDGET_USD}")


def cost_usd(input_tokens: int, output_tokens: int) -> float:
    return (input_tokens * INPUT_USD_M + output_tokens * OUTPUT_USD_M) / 1_000_000


def schema_context(snapshot: DuckDBSnapshot) -> str:
    result = snapshot.query(
        "SELECT table_name,column_name,data_type FROM information_schema.columns "
        "WHERE table_schema='main' AND table_name='network_flows' ORDER BY ordinal_position"
    )
    return "network_flows(" + ", ".join(
        f'{row["column_name"]} {row["data_type"]}' for row in result.rows
    ) + ")"


def build_request(case: SQLBenchmarkCase, schema: str) -> dict[str, Any]:
    request: dict[str, Any] = {
        "model": MODEL,
        "messages": [
            {"role": "system", "content": "Generate exactly one read-only DuckDB SELECT statement and no prose. Do not attach databases, install extensions, or modify data.\n\nSchema:\n" + schema},
            {"role": "user", "content": case.question},
        ],
        "reasoning_effort": REASONING_EFFORT,
        "max_completion_tokens": CAP,
    }
    # temperature is ABSENT for gpt-5-mini
    return request


def request_bound(request: dict[str, Any]) -> dict[str, Any]:
    if request.get("model") != MODEL or request.get("reasoning_effort") != REASONING_EFFORT or request.get("max_completion_tokens") != CAP:
        raise ValueError("Unpinned request blocked")
    if "temperature" in request:
        raise ValueError("temperature must be absent for gpt-5-mini")
    size = len(json.dumps(request, ensure_ascii=True, separators=(",", ":")).encode())
    input_bound = size + FRAMING_TOKENS
    return {"request_utf8_bytes": size, "input_token_bound": input_bound,
            "max_output_tokens": CAP, "max_cost_usd": cost_usd(input_bound, CAP)}


def preflight_bounds(requests: list[dict[str, Any]]) -> dict[str, Any]:
    if len(requests) != 8:
        raise ValueError("Exactly eight R2 requests are required")
    bounds = [request_bound(request) for request in requests]
    # Conservative ceiling = sum of all 8 actual request costs.
    # Live demo is independent GPT-4.1-mini workflow — NOT mixed into GPT-5 Mini E0 budget.
    ceiling = sum(item["max_cost_usd"] for item in bounds)
    if ceiling >= E0_SUITE_BUDGET_USD:
        raise ValueError(
            f"Combined 8-case suite ceiling {ceiling:.6f} >= E0 budget ${E0_SUITE_BUDGET_USD:.2f}"
        )
    return {"method": "serialized request UTF-8 bytes + 4096 framing tokens; reasoning_effort=low; temperature absent; zero retries",
            "r2_bounds": bounds,
            "suite_ceiling_usd": ceiling,
            "e0_budget_limit_usd": E0_SUITE_BUDGET_USD}


def _save(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, sort_keys=True, indent=2, default=str) + "\n", encoding="utf-8")
    os.replace(temporary, path)


def make_client():
    if os.environ.get("OPENAI_BASE_URL"):
        raise ValueError("OPENAI_BASE_URL is prohibited")
    key = os.environ.get("OPENAI_API_KEY")
    if not key:
        raise ValueError("OPENAI_API_KEY is unavailable")
    from openai import OpenAI
    return OpenAI(api_key=key, timeout=60, max_retries=0)


def checked_usage(response: Any) -> tuple[int, int]:
    if getattr(response, "model", None) != MODEL:
        raise ValueError("Actual model differs from pinned model")
    usage = getattr(response, "usage", None)
    input_tokens = getattr(usage, "prompt_tokens", None)
    output_tokens = getattr(usage, "completion_tokens", None)
    if type(input_tokens) is not int or input_tokens <= 0 or type(output_tokens) is not int or not 0 <= output_tokens <= CAP:
        raise ValueError("Provider usage missing or invalid")
    return input_tokens, output_tokens


def run(snapshot_path: Path, output: Path, *, client: Any | None = None, preflight_only: bool = False) -> dict[str, Any]:
    snapshot_path, output = Path(snapshot_path), Path(output)
    if output.exists():
        raise FileExistsError(f"Evidence output already exists: {output}")
    lock = validate(snapshot_path, LOCK)
    cases = [SQLBenchmarkCase.from_dict(json.loads(path.read_text(encoding="utf-8"))) for path in sorted(CASES.glob("*.json"))]
    snapshot = DuckDBSnapshot(snapshot_path)
    schema = schema_context(snapshot)
    requests = [build_request(case, schema) for case in cases]
    sha = subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip()
    run_id = os.environ.get("GITHUB_RUN_ID") or output.parent.name

    def _make_report(preflight: dict[str, Any]) -> dict[str, Any]:
        return {
            "run_id": run_id, "version": lock["version"], "run_status": "preflight_complete", "pilot_eligible": False,
            "evaluator_commit_sha": sha, "case_ids": [case.case_id for case in cases],
            "model_config_sha256": _MODEL_CONFIG_SHA256,
            "config": {"provider": "openai", "model": MODEL, "reasoning_effort": REASONING_EFFORT,
                       "temperature": None, "max_completion_tokens": CAP, "max_retries": MAX_RETRIES},
            "pricing": {"input_usd_per_million": INPUT_USD_M, "output_usd_per_million": OUTPUT_USD_M,
                        "source": PRICING_SOURCE, "checked_utc": datetime.now(timezone.utc).isoformat(),
                        "known_cost_usd": 0.0, "cost_unknown": False},
            "provenance": {"logical_snapshot_sha256": lock["logical_snapshot_sha256"],
                           "split_sha256": lock["split_sha256"], "source_file_sha256": lock["source_file_sha256"],
                           "builder_scorer_sha256": lock["builder_scorer_sha256"],
                           "model_config_sha256": _MODEL_CONFIG_SHA256,
                           "system_prompt_sha256": hashlib.sha256(requests[0]["messages"][0]["content"].encode("utf-8")).hexdigest(),
                           "schema_context_sha256": hashlib.sha256(schema.encode("utf-8")).hexdigest()},
            "preflight": preflight, "serialized_requests": requests, "case_results": [],
            "attempted_calls": 0, "responses_received": 0, "calls_with_valid_usage": 0,
        }

    # Build skeleton report; will be replaced once preflight passes.
    report: dict[str, Any] = {"case_ids": [case.case_id for case in cases]}
    _save(output, report)

    try:
        preflight = preflight_bounds(requests)
    except ValueError as exc:
        report = _make_report({"preflight_error": str(exc)})
        report["run_status"] = "preflight_failed"
        _save(output, report)
        raise

    report = _make_report(preflight)
    _save(output, report)
    if preflight_only:
        return report
    if os.environ.get("GITHUB_RUN_ATTEMPT", "1") != "1":
        report["run_status"] = "identity_blocked"
        _save(output, report)
        raise ValueError("Actions rerun is blocked; use a new workflow dispatch for a diagnosed new attempt")
    if os.environ.get("GITHUB_REF") != "refs/heads/master" or os.environ.get("GITHUB_SHA") != sha:
        report["run_status"] = "identity_blocked"
        _save(output, report)
        raise ValueError("Paid runner requires exact master Actions checkout")
    client = client or make_client()
    known = 0.0
    evaluations = []
    for index, (case, request, bound) in enumerate(zip(cases, requests, preflight["r2_bounds"])):
        # Per-case budget gate: stop if remaining cases would exceed suite budget.
        remaining = sum(item["max_cost_usd"] for item in preflight["r2_bounds"][index:])
        if known + remaining >= E0_SUITE_BUDGET_USD:
            report["run_status"] = "budget_stopped"
            _save(output, report)
            raise ValueError("Remaining conservative budget is insufficient")
        attempt = {"case_id": case.case_id, "request_index": index + 1, "outcome": "attempted"}
        report["case_results"].append(attempt)
        report["attempted_calls"] += 1
        report["run_status"] = "in_progress"
        _save(output, report)
        started = perf_counter()
        try:
            response = client.chat.completions.create(**request)
            report["responses_received"] += 1
            attempt["latency_ms"] = (perf_counter() - started) * 1000
            attempt["response_id"] = getattr(response, "id", None)
            attempt["actual_model"] = getattr(response, "model", None)
            _save(output, report)
            input_tokens, output_tokens = checked_usage(response)
            charged = cost_usd(input_tokens, output_tokens)
            known += charged
            report["calls_with_valid_usage"] += 1
            report["pricing"]["known_cost_usd"] = known
            attempt.update({"actual_model": response.model, "input_tokens": input_tokens,
                            "output_tokens": output_tokens, "cost_usd": charged,
                            "outcome": "usage_recorded"})
            _save(output, report)
            if input_tokens > bound["input_token_bound"]:
                raise ValueError("Actual input usage exceeded preflight bound")
            generated = _extract_sql(response.choices[0].message.content or "")
            attempt["generated_sql"] = generated
            try:
                evaluation = evaluate_sql_case(case, generated, snapshot)
            except Exception as exc:
                attempt.update({"outcome": "scoring_error", "scoring_error": type(exc).__name__,
                                "syntax_valid": False, "execution_success": False,
                                "execution_accurate": False, "safety_rejected": False,
                                "error": "Scoring failed after a charged response.",
                                "error_category": "scoring_error"})
                _save(output, report)
                continue
            evaluations.append(evaluation)
            attempt.update({"outcome": "scored", "syntax_valid": evaluation.syntax_valid,
                            "execution_success": evaluation.execution_success,
                            "execution_accurate": evaluation.execution_accurate,
                            "safety_rejected": evaluation.safety_rejected, "error": evaluation.error,
                            "error_category": _sql_error_category(evaluation)})
            _save(output, report)
        except Exception as exc:
            attempt.setdefault("latency_ms", (perf_counter() - started) * 1000)
            if report["responses_received"] < report["attempted_calls"] or not attempt.get("cost_usd"):
                report["pricing"]["cost_unknown"] = True
            attempt.update({"outcome": "provider_or_validation_error", "failure_category": type(exc).__name__})
            report["run_status"] = "provider_or_validation_error"
            report["failure"] = {"category": type(exc).__name__, "message": "Paid call or response validation failed"}
            _save(output, report)
            raise
    report["metrics"] = aggregate_sql_metrics(evaluations)
    report["run_status"] = "complete"
    report["pilot_eligible"] = (
        len(report["case_results"]) == 8
        and report["attempted_calls"] == 8
        and report["responses_received"] == 8
        and report["calls_with_valid_usage"] == 8
        and len(evaluations) == 8
        and not report["pricing"]["cost_unknown"]
    )
    _save(output, report)
    return report


def main() -> int:
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--snapshot", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--preflight-only", action="store_true")
    args = parser.parse_args()
    result = run(args.snapshot, args.output, preflight_only=args.preflight_only)
    print(json.dumps({"run_status": result["run_status"], "attempted_calls": result["attempted_calls"],
                      "responses_received": result["responses_received"],
                      "calls_with_valid_usage": result["calls_with_valid_usage"],
                      "known_cost_usd": result["pricing"]["known_cost_usd"],
                      "suite_ceiling_usd": result["preflight"]["suite_ceiling_usd"]}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
