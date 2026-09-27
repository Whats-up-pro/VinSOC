"""One-shot paid runner for the locked CTU-only R2 public_dev pilot."""

from __future__ import annotations

import json
import os
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from evaluation.ctu_network_public.contract import CASES, LOCK, validate
from evaluation.text_to_sql import SQLBenchmarkCase, _extract_sql, _sql_error_category, aggregate_sql_metrics, evaluate_sql_case
from vinsoc_data.duckdb_store import DuckDBSnapshot

MODEL = "gpt-4.1-mini-2025-04-14"
CAP = 1000
INPUT_USD_M = 0.40
OUTPUT_USD_M = 1.60
BUDGET_USD = 1.00
DEMO_RESERVED_CALLS = 2
FRAMING_TOKENS = 4096
PRICING_SOURCE = "https://developers.openai.com/api/docs/models/gpt-4.1-mini"


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
    return {
        "model": MODEL,
        "messages": [
            {"role": "system", "content": "Generate exactly one read-only DuckDB SELECT statement and no prose. Do not attach databases, install extensions, or modify data.\n\nSchema:\n" + schema},
            {"role": "user", "content": case.question},
        ],
        "temperature": 0,
        "max_completion_tokens": CAP,
    }


def request_bound(request: dict[str, Any]) -> dict[str, Any]:
    if request.get("model") != MODEL or request.get("temperature") != 0 or request.get("max_completion_tokens") != CAP:
        raise ValueError("Unpinned request blocked")
    size = len(json.dumps(request, ensure_ascii=True, separators=(",", ":")).encode())
    input_bound = size + FRAMING_TOKENS
    return {"request_utf8_bytes": size, "input_token_bound": input_bound,
            "max_output_tokens": CAP, "max_cost_usd": cost_usd(input_bound, CAP)}


def preflight_bounds(requests: list[dict[str, Any]]) -> dict[str, Any]:
    if len(requests) != 8:
        raise ValueError("Exactly eight R2 requests are required")
    bounds = [request_bound(request) for request in requests]
    demo_bound = max(item["max_cost_usd"] for item in bounds) * DEMO_RESERVED_CALLS
    ceiling = sum(item["max_cost_usd"] for item in bounds) + demo_bound
    if ceiling >= BUDGET_USD:
        raise ValueError("Combined R2 plus reserved live-demo ceiling exceeds $1.00")
    return {"method": "serialized request UTF-8 bytes + 4096 framing tokens; 1000 output tokens; zero retries",
            "r2_bounds": bounds, "reserved_demo_calls": DEMO_RESERVED_CALLS,
            "reserved_demo_ceiling_usd": demo_bound, "combined_ceiling_usd": ceiling,
            "budget_limit_usd": BUDGET_USD}


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
    lock = validate(snapshot_path, LOCK)
    cases = [SQLBenchmarkCase.from_dict(json.loads(path.read_text(encoding="utf-8"))) for path in sorted(CASES.glob("*.json"))]
    snapshot = DuckDBSnapshot(snapshot_path)
    schema = schema_context(snapshot)
    requests = [build_request(case, schema) for case in cases]
    preflight = preflight_bounds(requests)
    sha = subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip()
    report: dict[str, Any] = {
        "version": lock["version"], "run_status": "preflight_complete", "pilot_eligible": False,
        "evaluator_commit_sha": sha, "case_ids": [case.case_id for case in cases],
        "config": {"provider": "openai", "model": MODEL, "temperature": 0, "max_completion_tokens": CAP, "max_retries": 0},
        "pricing": {"input_usd_per_million": INPUT_USD_M, "output_usd_per_million": OUTPUT_USD_M,
                    "source": PRICING_SOURCE, "checked_utc": datetime.now(timezone.utc).isoformat(),
                    "known_cost_usd": 0.0, "cost_unknown": False},
        "provenance": {"logical_snapshot_sha256": lock["logical_snapshot_sha256"],
                       "split_sha256": lock["split_sha256"], "source_file_sha256": lock["source_file_sha256"],
                       "builder_scorer_sha256": lock["builder_scorer_sha256"]},
        "preflight": preflight, "serialized_requests": requests, "case_results": [], "provider_calls": 0,
    }
    _save(output, report)
    if preflight_only:
        return report
    if os.environ.get("GITHUB_REF") != "refs/heads/master" or os.environ.get("GITHUB_SHA") != sha:
        raise ValueError("Paid runner requires exact master Actions checkout")
    client = client or make_client()
    known = 0.0
    evaluations = []
    for index, (case, request, bound) in enumerate(zip(cases, requests, preflight["r2_bounds"])):
        remaining = sum(item["max_cost_usd"] for item in preflight["r2_bounds"][index:]) + preflight["reserved_demo_ceiling_usd"]
        if known + remaining >= BUDGET_USD:
            report["run_status"] = "budget_stopped"
            _save(output, report)
            raise ValueError("Remaining conservative budget is insufficient")
        try:
            response = client.chat.completions.create(**request)
            report["provider_calls"] += 1
            input_tokens, output_tokens = checked_usage(response)
            if input_tokens > bound["input_token_bound"]:
                raise ValueError("Actual input usage exceeded preflight bound")
            charged = cost_usd(input_tokens, output_tokens)
            known += charged
            generated = _extract_sql(response.choices[0].message.content or "")
            evaluation = evaluate_sql_case(case, generated, snapshot)
            evaluations.append(evaluation)
            report["case_results"].append({"case_id": case.case_id, "generated_sql": generated,
                "syntax_valid": evaluation.syntax_valid, "execution_success": evaluation.execution_success,
                "execution_accurate": evaluation.execution_accurate, "safety_rejected": evaluation.safety_rejected,
                "error": evaluation.error, "error_category": _sql_error_category(evaluation),
                "actual_model": response.model, "input_tokens": input_tokens, "output_tokens": output_tokens,
                "cost_usd": charged})
            report["pricing"]["known_cost_usd"] = known
            report["run_status"] = "in_progress"
            _save(output, report)
        except Exception as exc:
            report["run_status"] = "provider_or_validation_error"
            report["pricing"]["cost_unknown"] = True
            report["failure"] = {"category": type(exc).__name__, "message": "Paid call or response validation failed"}
            _save(output, report)
            raise
    report["metrics"] = aggregate_sql_metrics(evaluations)
    report["run_status"] = "complete"
    report["pilot_eligible"] = len(evaluations) == 8 and report["provider_calls"] == 8 and not report["pricing"]["cost_unknown"]
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
    print(json.dumps({"run_status": result["run_status"], "provider_calls": result["provider_calls"], "known_cost_usd": result["pricing"]["known_cost_usd"], "combined_ceiling_usd": result["preflight"]["combined_ceiling_usd"]}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
