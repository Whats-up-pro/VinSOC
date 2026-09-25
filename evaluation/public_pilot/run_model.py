"""One-shot paid R1/R2 public_dev runs with fail-closed provenance and budget.

The workflow verifies source hashes, logical snapshot content, gold SQL and
all case IDs before constructing any OpenAI request. Partial JSON is always
written before a request and after its outcome.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from agent.tools import get_tool_schemas
from evaluation.public_pilot.contract import R1, R2, ROOT, canonical_sha256, validate
from evaluation.text_to_sql import (
    SQLBenchmarkCase, _extract_sql, _sql_error_category, aggregate_sql_metrics,
    evaluate_sql_case,
)
from evaluation.text_to_sql_snapshot import sha256_file
from evaluation.tool_calling.arguments import normalize_arguments
from evaluation.tool_calling.decision_runner import DecisionRunner
from evaluation.tool_calling.matching import compute_case_metrics
from evaluation.tool_calling.metrics import aggregate_case_results
from evaluation.tool_calling.models import CaseResult, PredictedCall, ToolCallCase
from vinsoc_data.duckdb_store import DuckDBSnapshot


MODEL = "gpt-4.1-mini-2025-04-14"
CAP = 1000
BUDGET_USD = 1.00  # Both tracks together, not one dollar per workflow.
INPUT_USD_M = 0.40
OUTPUT_USD_M = 1.60
FRAMING_TOKENS = 4096


def build_r1_request(case: ToolCallCase) -> dict:
    system_prompt, user_prompt = DecisionRunner.build_prompt(None, case)
    return {
        "model": MODEL, "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        "tools": get_tool_schemas(), "temperature": 0,
        "max_completion_tokens": CAP,
    }


def build_r2_request(question: str, schema: str) -> dict:
    system_prompt = (
        "You generate DuckDB SQL for the VinSOC SOC benchmark. "
        "Return exactly one read-only SELECT statement (WITH ... SELECT is allowed). "
        "Do not write data, attach databases, install extensions, or emit prose.\n\n"
        "Database schema:\n" + schema
    )
    return {
        "model": MODEL, "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": question},
        ],
        "tools": None, "temperature": 0,
        "max_completion_tokens": CAP,
    }


def send_request(client: Any, request: dict) -> Any:
    if request.get("model") != MODEL or request.get("temperature") != 0 or (
        type(request.get("max_completion_tokens")) is not int or request["max_completion_tokens"] != CAP
    ):
        raise ValueError("Model, temperature or completion cap mismatch; request blocked")
    return client.chat.completions.create(**request)


def make_client():
    from openai import OpenAI

    if os.environ.get("OPENAI_BASE_URL"):
        raise ValueError("OPENAI_BASE_URL override is prohibited for this pinned OpenAI pilot")
    key = os.environ.get("OPENAI_API_KEY")
    if not key:
        raise ValueError("OPENAI_API_KEY is unavailable to the job")
    return OpenAI(api_key=key, timeout=60, max_retries=0)


def checked_usage(response: Any) -> tuple[int, int]:
    if getattr(response, "model", None) != MODEL:
        raise ValueError("actual model differs from requested pinned model")
    usage = getattr(response, "usage", None)
    input_tokens = getattr(usage, "prompt_tokens", None)
    output_tokens = getattr(usage, "completion_tokens", None)
    if (type(input_tokens) is not int or input_tokens <= 0
            or type(output_tokens) is not int or not 0 <= output_tokens <= CAP):
        raise ValueError("provider usage is absent, invalid or exceeds completion cap")
    return input_tokens, output_tokens


def cost_usd(input_tokens: int, output_tokens: int) -> float:
    return (input_tokens * INPUT_USD_M + output_tokens * OUTPUT_USD_M) / 1_000_000


def preflight_bounds(requests: list[dict]) -> dict:
    bounds = []
    for request in requests:
        if request.get("model") != MODEL or request.get("max_completion_tokens") != CAP:
            raise ValueError("Unpinned preflight request")
        size = len(json.dumps(request, ensure_ascii=True, separators=(",", ":")).encode())
        bound = size + FRAMING_TOKENS
        if bound + CAP > 1_047_576:
            raise ValueError("Model context bound exceeded")
        bounds.append({"request_utf8_bytes": size, "input_token_bound": bound,
                       "max_cost_usd": cost_usd(bound, CAP)})
    return {"method": "serialized full request UTF-8 bytes + 4096 framing tokens; 1000 output tokens per call; zero retries",
            "bounds": bounds, "cost_ceiling_usd": sum(item["max_cost_usd"] for item in bounds),
            "budget_limit_usd": BUDGET_USD}


def _schema_context(snapshot: DuckDBSnapshot) -> str:
    result = snapshot.query(
        "SELECT table_name, column_name, data_type FROM information_schema.columns "
        "WHERE table_schema = 'main' AND table_name <> 'dataset_provenance' "
        "ORDER BY table_name, ordinal_position"
    )
    grouped: dict[str, list[str]] = {}
    for row in result.rows:
        grouped.setdefault(str(row["table_name"]), []).append(f'{row["column_name"]} {row["data_type"]}')
    return "\n".join(f"{table}({', '.join(columns)})" for table, columns in grouped.items())


def _score_r1(case: ToolCallCase, response: Any) -> CaseResult:
    calls = []
    for call in getattr(response.choices[0].message, "tool_calls", None) or []:
        name = call.function.name
        arguments = json.loads(call.function.arguments)
        if not name or not isinstance(arguments, dict):
            raise ValueError("Provider returned a malformed tool call")
        calls.append(PredictedCall(name, normalize_arguments(name, arguments)))
    result = CaseResult(case.case_id, case.expected_calls, calls)
    score = compute_case_metrics(case, calls)
    result.matches = score["matches"]
    result.true_positives = score["tp"]
    result.false_positives = score["fp"]
    result.false_negatives = score["fn"]
    result.forbidden_tool_violations = score["forbidden_violations"]
    result.trajectory_success = score["trajectory_success"]
    result.exact_call_match = score["exact_call_match"]
    result.tool_set_match = score["tool_set_match"]
    if result.forbidden_tool_violations:
        result.errors.append("FORBIDDEN_TOOL")
    return result


def _save(path: Path, report: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(report, ensure_ascii=False, sort_keys=True, indent=2, default=str) + "\n")
    os.replace(temporary, path)


def _breakdown_r1(results: list[CaseResult], cases: list[ToolCallCase]) -> dict:
    by_id = {c.case_id: c for c in cases}
    groups: dict[str, dict[str, list[CaseResult]]] = {
        "category": defaultdict(list), "difficulty": defaultdict(list), "no_tool": defaultdict(list),
    }
    for result in results:
        case = by_id[result.case_id]
        groups["category"][case.category.value].append(result)
        groups["difficulty"][case.difficulty.value].append(result)
        groups["no_tool"]["yes" if not case.expected_calls else "no"].append(result)
    return {axis: {name: {"case_ids": [r.case_id for r in subset],
                          "metrics": aggregate_case_results(axis + name, subset).to_dict()}
                   for name, subset in values.items()} for axis, values in groups.items()}


def run(track: str, snapshot_path: Path, snapshot_report_path: Path, out: Path, *, client=None) -> dict:
    if track not in {"r1", "r2"}:
        raise ValueError("Only r1 or r2 public_dev is permitted")
    sha = subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip()
    report: dict[str, Any] = {
        "track": track, "split": "public_dev", "run_status": "preflight_started",
        "pilot_eligible": False, "ineligible_reasons": ["preflight_not_complete"],
        "official_eligible": False, "official_ineligible_reasons": ["public_dev_pilot_is_distinct_from_official_benchmarks"],
        "evaluator_commit_sha": sha, "case_count": 0, "case_ids": [], "case_results": [],
        "provider_metadata": {"calls": [], "total_calls": 0},
        "pricing": {"input_usd_per_million": INPUT_USD_M, "output_usd_per_million": OUTPUT_USD_M,
                    "source": "https://developers.openai.com/api/docs/models/gpt-4.1-mini",
                    "checked_utc": datetime.now(timezone.utc).isoformat(),
                    "known_cost_usd": 0.0, "calculated_cost_usd": None, "usage_complete": False},
        "config": {"provider": "openai", "model": MODEL, "temperature": 0,
                   "max_completion_tokens": CAP, "max_retries": 0},
    }
    _save(out, report)
    try:
        if os.environ.get("GITHUB_REF") != "refs/heads/codex/r2-public-eval":
            raise ValueError("Wrong evaluation branch")
        if sha != os.environ.get("GITHUB_SHA"):
            raise ValueError("Evaluator commit SHA does not match Actions checkout")
        if subprocess.check_output(["git", "status", "--porcelain"]).strip():
            raise ValueError("Evaluator working tree is dirty")
        if os.environ.get("VINSOC_EVAL_MODEL") != MODEL:
            raise ValueError("VINSOC_EVAL_MODEL is not the pinned model")
        if not os.environ.get("OPENAI_API_KEY") and client is None:
            raise ValueError("OPENAI_API_KEY is unavailable to the job")
        snapshot_report = json.loads(snapshot_report_path.read_text(encoding="utf-8"))
        if snapshot_report.get("sha256") != sha256_file(snapshot_path):
            raise ValueError("Snapshot binary digest mismatch")
        verified = validate(snapshot_path)
        lock = json.loads((ROOT / "VERSION.lock").read_text(encoding="utf-8"))
        snapshot = DuckDBSnapshot(snapshot_path)
        r1_cases = [ToolCallCase.from_dict(json.loads(p.read_text())) for p in sorted(R1.glob("*.json"))]
        r2_cases = [SQLBenchmarkCase.from_dict(json.loads(p.read_text())) for p in sorted(R2.glob("*.json"))]
        schema = _schema_context(snapshot)
        all_requests = ([build_r1_request(case) for case in r1_cases]
                        + [build_r2_request(case.question, schema) for case in r2_cases])
        budget = preflight_bounds(all_requests)
        if budget["cost_ceiling_usd"] >= BUDGET_USD:
            raise ValueError("Combined 20+8 request ceiling exceeds $1; no API call")
        selected_cases = r1_cases if track == "r1" else r2_cases
        selected_requests = all_requests[:20] if track == "r1" else all_requests[20:]
        selected_bounds = budget["bounds"][:20] if track == "r1" else budget["bounds"][20:]
        report.update({
            "run_status": "preflight_complete", "ineligible_reasons": ["model_run_incomplete"],
            "benchmark_version": lock["version"],
            "benchmark_split_sha256": lock[f"{track}_split_sha256"],
            "scorer_file_sha256": lock["scorer_file_sha256"],
            "scorer_sha256": canonical_sha256(lock["scorer_file_sha256"]),
            "source_file_sha256": lock["source_file_sha256"],
            "snapshot_sha256": snapshot_report["sha256"],
            "snapshot_content_sha256": lock["snapshot_content_sha256"],
            "row_counts": lock["row_counts"], "gold_validation": verified["gold_results"],
            "expected_case_ids": [case.case_id for case in selected_cases],
            "prompt_sha256": canonical_sha256([r["messages"] for r in selected_requests]),
            "schema_sha256": canonical_sha256(get_tool_schemas() if track == "r1" else schema),
            "preflight": {**budget, "all_case_ids": [c.case_id for c in r1_cases + r2_cases]},
        })
        _save(out, report)
        actual_client = client if client is not None else make_client()
        known_cost = 0.0
        r1_results: list[CaseResult] = []
        r2_evaluations = []
        for position, (case, request, bound) in enumerate(zip(selected_cases, selected_requests, selected_bounds), 1):
            remainder = sum(b["max_cost_usd"] for b in selected_bounds[position - 1:])
            if known_cost + remainder >= BUDGET_USD:
                raise ValueError("Budget gate blocked before next API request")
            report["provider_metadata"]["total_calls"] += 1
            report["run_status"] = "in_progress"
            _save(out, report)
            response = None
            usage_accounted = False
            try:
                response = send_request(actual_client, request)
                input_tokens, output_tokens = checked_usage(response)
                spent = cost_usd(input_tokens, output_tokens)
                known_cost += spent
                usage_accounted = True
                if input_tokens > bound["input_token_bound"]:
                    raise ValueError("Input usage exceeded the conservative preflight bound")
                item = {"case_id": case.case_id, "category": case.category.value if track == "r1" else case.category,
                        "difficulty": case.difficulty.value if track == "r1" else case.difficulty,
                        "actual_provider": "openai", "actual_model": response.model,
                        "input_tokens": input_tokens, "output_tokens": output_tokens, "cost_usd": spent,
                        "status": "succeeded", "fallback_triggered": False}
                report["provider_metadata"]["calls"].append(item)
                if track == "r1":
                    scored = _score_r1(case, response)
                    scored.input_tokens, scored.output_tokens = input_tokens, output_tokens
                    r1_results.append(scored)
                    report["case_results"].append({**scored.to_dict(), "category": case.category.value,
                                                   "difficulty": case.difficulty.value})
                    report["aggregate"] = aggregate_case_results("r1_public_dev_v1", r1_results).to_dict()
                    report["breakdown"] = _breakdown_r1(r1_results, r1_cases)
                else:
                    generated = _extract_sql(getattr(response.choices[0].message, "content", "") or "")
                    evaluation = evaluate_sql_case(case, generated, snapshot)
                    r2_evaluations.append(evaluation)
                    report["case_results"].append({"case_id": case.case_id, "category": case.category,
                        "difficulty": case.difficulty, "generated_sql": generated,
                        "error_category": _sql_error_category(evaluation), "error": evaluation.error,
                        "syntax_valid": evaluation.syntax_valid, "execution_success": evaluation.execution_success,
                        "execution_accurate": evaluation.execution_accurate, "safety_rejected": evaluation.safety_rejected,
                        "input_tokens": input_tokens, "output_tokens": output_tokens, "cost_usd": spent})
                    report["metrics"] = aggregate_sql_metrics(r2_evaluations)
                    report["error_summary"] = dict(Counter(_sql_error_category(r) for r in r2_evaluations))
                    report["breakdown"] = {axis: {key: {"case_ids": [x["case_id"] for x in group],
                        "metrics": aggregate_sql_metrics([r2_evaluations[[c.case_id for c in selected_cases[:position]].index(x["case_id"])] for x in group])}
                        for key, group in groups.items()} for axis, groups in (
                        (axis, {name: [x for x in report["case_results"] if x[axis] == name]
                                for name in {x[axis] for x in report["case_results"]}})
                        for axis in ("category", "difficulty"))}
                report["case_count"] = len(report["case_results"])
                report["case_ids"].append(case.case_id)
                report["pricing"]["known_cost_usd"] = known_cost
                report["pricing"]["calculated_cost_usd"] = known_cost
                report["pricing"]["usage_complete"] = True
                _save(out, report)
                print(f"{track.upper()} case {position}/{len(selected_cases)} {case.case_id}: "
                      f"actual_model={response.model}; usage={input_tokens}/{output_tokens}; "
                      f"known_cost_usd={known_cost:.7f}")
            except Exception as exc:
                charged = None
                if response is not None:
                    usage = getattr(response, "usage", None)
                    prompt = getattr(usage, "prompt_tokens", None)
                    completion = getattr(usage, "completion_tokens", None)
                    if type(prompt) is int and prompt >= 0 and type(completion) is int and completion >= 0:
                        charged = cost_usd(prompt, completion)
                        if not usage_accounted:
                            known_cost += charged
                report["run_status"] = "stopped_provider_usage_or_scoring_error"
                report["ineligible_reasons"] = [type(exc).__name__, "model_run_incomplete"]
                if not any(call["case_id"] == case.case_id for call in report["provider_metadata"]["calls"]):
                    report["provider_metadata"]["calls"].append({"case_id": case.case_id,
                        "status": "failed_or_unverifiable", "error_type": type(exc).__name__,
                        "http_status": getattr(exc, "status_code", None),
                        "api_error_code": getattr(exc, "code", None),
                        "actual_model": getattr(response, "model", None)})
                error_case = {"case_id": case.case_id, "error_type": type(exc).__name__,
                              "errors": ["PROVIDER_OR_USAGE_ERROR"], "input_tokens": None,
                              "output_tokens": None, "cost_usd": charged}
                if report["case_results"] and report["case_results"][-1]["case_id"] == case.case_id:
                    report["case_results"][-1] = error_case
                else:
                    report["case_results"].append(error_case)
                report["case_count"] = len(report["case_results"])
                report["case_ids"].append(case.case_id)
                report["pricing"]["known_cost_usd"] = known_cost
                report["pricing"]["calculated_cost_usd"] = None
                report["pricing"]["usage_complete"] = False
                _save(out, report)
                raise RuntimeError(f"Pilot stopped at {case.case_id}: {type(exc).__name__}") from exc
        if len(report["case_ids"]) != len(set(report["case_ids"])):
            raise ValueError("Case IDs missing or duplicated")
        if len(report["case_ids"]) != len(selected_cases) or len(report["provider_metadata"]["calls"]) != len(selected_cases):
            raise ValueError("Incomplete model run")
        report["run_status"] = "completed"
        report["pilot_eligible"] = True
        report["ineligible_reasons"] = []
        _save(out, report)
        return report
    except Exception as exc:
        if report["run_status"] in {"preflight_started", "preflight_complete", "in_progress"}:
            report["run_status"] = "preflight_or_budget_failed"
            report["ineligible_reasons"] = [type(exc).__name__]
            _save(out, report)
        raise


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--track", choices=("r1", "r2"), required=True)
    parser.add_argument("--snapshot", type=Path, default=Path("data/public_pilot/snapshot.duckdb"))
    parser.add_argument("--snapshot-report", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()
    run(args.track, args.snapshot, args.snapshot_report, args.report)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
