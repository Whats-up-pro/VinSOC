"""One-pass GPT-5 Mini decision-only evaluation on the locked R1 dev v2 split."""

from __future__ import annotations

import hashlib
import json
import math
import os
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from time import perf_counter
from typing import Any, Callable

from agent.provider import LLMResponse, ProviderError
from agent.tools import get_tool_schemas
from evaluation.tool_calling.decision_runner import A1Config, DecisionRunner
from evaluation.tool_calling.metrics import aggregate_case_results, generate_error_summary
from evaluation.tool_calling.models import ToolCallCase
from evaluation.tool_calling.provenance import build_a1_provenance, canonical_sha256

MODEL = "gpt-5-mini-2025-08-07"
CAP = 1000
INPUT_USD_M = 0.25
OUTPUT_USD_M = 2.00
SUITE_BUDGET_USD = 0.25
FRAMING_TOKENS = 4096
BASELINE_PROMPT_SHA256 = "21f87b197c1bf1206d4a36e111853bddf6ea623bab58a5da311ccbcb61d7780b"
BASELINE_SCHEMA_SHA256 = "aa214e730b1e3eb3ba03fdb08488dcfda4bc33b3c6d4c84700951f87e9c11ff0"
DEV_DIR = Path("evaluation/tool_calling/benchmarks/dev")
BASELINE = Path("results/evaluation_v1/r1/r1_a1_dev_v2_852e543.json")
E0_RECEIPT = Path("results/evaluation_v1/ctu_network_public/gpt5_e0/36520685612/receipt.json")


def git_head() -> str:
    return subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip()


def git_clean() -> bool:
    return not subprocess.check_output(["git", "status", "--porcelain"]).strip()


def cost_usd(input_tokens: int, output_tokens: int) -> float:
    return (input_tokens * INPUT_USD_M + output_tokens * OUTPUT_USD_M) / 1_000_000


def _text_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes().replace(b"\r\n", b"\n").replace(b"\r", b"\n")).hexdigest()


def _save(path: Path, report: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(report, indent=2, sort_keys=True, ensure_ascii=False, default=str) + "\n", encoding="utf-8")
    os.replace(temporary, path)


def _prepare() -> tuple[list[ToolCallCase], list[dict[str, Any]], dict[str, Any]]:
    lock = json.loads((DEV_DIR / "VERSION.lock").read_text(encoding="utf-8"))
    split = {p.name: json.loads(p.read_text(encoding="utf-8")) for p in sorted(DEV_DIR.glob("*.json"))}
    if lock["version"] != "r1_a1_dev_v2" or len(split) != lock["case_count"] != 24:
        raise ValueError("R1 dev v2 case count or version mismatch")
    if canonical_sha256(split) != lock["benchmark_split_sha256"]:
        raise ValueError("R1 dev v2 split hash mismatch")
    scorer_hashes = {name: _text_sha256(Path(name)) for name in lock["scorer_files"]}
    if scorer_hashes != lock["scorer_file_sha256"] or canonical_sha256(scorer_hashes) != lock["scorer_sha256"]:
        raise ValueError("R1 scorer hash mismatch")
    baseline = json.loads(BASELINE.read_text(encoding="utf-8"))
    if (baseline["provenance"]["prompt_sha256"] != BASELINE_PROMPT_SHA256
            or baseline["provenance"]["production_schema_sha256"] != BASELINE_SCHEMA_SHA256):
        raise ValueError("Historical baseline prompt or schema identity mismatch")
    cases = [ToolCallCase.from_dict(value) for value in split.values()]
    if len({case.case_id for case in cases}) != 24:
        raise ValueError("Duplicate R1 dev case ID")
    schemas = get_tool_schemas()
    prompts = []
    requests = []
    for case in cases:
        system, user = DecisionRunner.build_prompt(None, case)
        prompts.append({"case_id": case.case_id, "system_prompt": system,
                        "messages": [{"role": "user", "content": user}]})
        requests.append({"model": MODEL,
                         "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
                         "tools": schemas, "reasoning_effort": "low", "max_completion_tokens": CAP})
    if canonical_sha256(prompts) != BASELINE_PROMPT_SHA256 or canonical_sha256(schemas) != BASELINE_SCHEMA_SHA256:
        raise ValueError("R1 prompt or production tool schema drifted from fixed baseline")
    bounds = []
    for case, request in zip(cases, requests):
        size = len(json.dumps(request, ensure_ascii=True, separators=(",", ":")).encode("utf-8"))
        input_bound = size + FRAMING_TOKENS
        bounds.append({"case_id": case.case_id, "request_utf8_bytes": size,
                       "input_token_bound": input_bound, "max_output_tokens": CAP,
                       "max_cost_usd": cost_usd(input_bound, CAP)})
    ceiling = sum(item["max_cost_usd"] for item in bounds)
    prior = json.loads(E0_RECEIPT.read_text(encoding="utf-8"))["usage_derived_cost_usd"]
    if ceiling >= SUITE_BUDGET_USD:
        raise ValueError("R1 model-only suite cost preflight failed")
    info = {"lock": lock, "scorer_hashes": scorer_hashes, "bounds": bounds,
            "suite_ceiling_usd": ceiling, "prior_spend_usd": prior,
            "prompt_sha256": BASELINE_PROMPT_SHA256, "production_schema_sha256": BASELINE_SCHEMA_SHA256}
    return cases, requests, info


def _make_client() -> Any:
    if os.environ.get("OPENAI_BASE_URL"):
        raise ValueError("OPENAI_BASE_URL is prohibited")
    key = os.environ.get("OPENAI_API_KEY")
    if not key:
        raise ValueError("OPENAI_API_KEY is unavailable")
    from openai import OpenAI
    return OpenAI(api_key=key, timeout=60, max_retries=0)


class PinnedProvider:
    def __init__(self, client: Any, on_record: Callable[[], None]):
        self.client = client
        self.on_record = on_record
        self.calls: list[dict[str, Any]] = []

    def generate(self, messages, tools=None, system_prompt=None, temperature=None) -> LLMResponse:
        if temperature is not None:
            raise ValueError("GPT-5 Mini temperature must be absent")
        request = {"model": MODEL, "messages": [{"role": "system", "content": system_prompt}, *messages],
                   "tools": tools, "reasoning_effort": "low", "max_completion_tokens": CAP}
        started = perf_counter()
        try:
            response = self.client.chat.completions.create(**request)
        except Exception as exc:
            self.calls.append({"status": "provider_error", "requested_model": MODEL,
                               "actual_model": None, "latency_ms": (perf_counter() - started) * 1000,
                               "error_type": type(exc).__name__, "cost_unknown": True})
            self.on_record()
            raise ProviderError("Pinned OpenAI request failed") from exc
        message = response.choices[0].message
        usage = getattr(response, "usage", None)
        inputs, outputs = getattr(usage, "prompt_tokens", None), getattr(usage, "completion_tokens", None)
        raw_calls = [{"id": call.id, "name": call.function.name,
                      "arguments": call.function.arguments} for call in (getattr(message, "tool_calls", None) or [])]
        chargeable_usage = type(inputs) is int and inputs > 0 and type(outputs) is int and outputs >= 0
        valid_usage = chargeable_usage and outputs <= CAP
        record = {"status": "received", "requested_provider": "openai", "actual_provider": "openai",
                  "requested_model": MODEL, "actual_model": getattr(response, "model", None),
                  "response_id": getattr(response, "id", None), "input_tokens": inputs,
                  "output_tokens": outputs, "cost_usd": cost_usd(inputs, outputs) if chargeable_usage else None,
                  "latency_ms": (perf_counter() - started) * 1000, "raw_tool_calls": raw_calls,
                  "finish_reason": getattr(response.choices[0], "finish_reason", None),
                  "cost_unknown": not chargeable_usage}
        self.calls.append(record)
        self.on_record()
        if record["actual_model"] != MODEL:
            record["status"] = "identity_error"
            self.on_record()
            raise ProviderError("OpenAI actual model mismatch")
        if not valid_usage:
            record["status"] = "usage_error"
            self.on_record()
            raise ProviderError("OpenAI usage missing or exceeds cap")
        parsed = []
        malformed = 0
        for call in raw_calls:
            try:
                arguments = json.loads(call["arguments"])
                if not isinstance(arguments, dict):
                    raise ValueError("tool arguments must be an object")
            except (TypeError, ValueError):
                arguments = None
                malformed += 1
            parsed.append({"id": call["id"], "name": call["name"], "arguments": arguments})
        if record["finish_reason"] == "length":
            parsed.append({"id": "truncated_response", "name": None, "arguments": None})
            malformed += 1
        record["malformed_native_calls"] = malformed
        record["status"] = "succeeded"
        self.on_record()
        return LLMResponse(content=message.content or "", tool_calls=parsed, raw={}, metadata=record)

    def get_name(self) -> str:
        return f"openai {MODEL}"

    def get_run_metadata(self) -> dict[str, Any]:
        return {"calls": self.calls, "total_calls": len(self.calls),
                "known_cost_usd": sum(call.get("cost_usd") or 0.0 for call in self.calls),
                "cost_complete": all(not call["cost_unknown"] for call in self.calls)}


def run(output: Path, *, client: Any | None = None, preflight_only: bool = False) -> dict[str, Any]:
    output = Path(output)
    if output.exists():
        raise FileExistsError(f"Evidence output already exists: {output}")
    cases, requests, info = _prepare()
    sha = git_head()
    config = {"provider": "openai", "model": MODEL, "reasoning_effort": "low",
              "temperature": None, "max_completion_tokens": CAP, "max_retries": 0}
    report: dict[str, Any] = {
        "run_id": os.environ.get("GITHUB_RUN_ID") or output.parent.name,
        "mode": "decision", "split": "dev", "run_status": "preflight_complete",
        "official_eligible": False, "expected_case_ids": [case.case_id for case in cases],
        "case_results": [], "attempted_calls": 0, "evaluator_commit_sha": sha,
        "benchmark_version": info["lock"]["version"],
        "benchmark_split_sha256": info["lock"]["benchmark_split_sha256"],
        "scorer_sha256": info["lock"]["scorer_sha256"],
        "scorer_file_sha256": info["scorer_hashes"],
        "config": config, "model_config_sha256": canonical_sha256(config),
        "provenance": {"prompt_sha256": info["prompt_sha256"],
                       "production_schema_sha256": info["production_schema_sha256"]},
        "preflight": {"method": "serialized UTF-8 request bytes + 4096 framing tokens; full output cap; zero retries",
                      "bounds": info["bounds"], "suite_ceiling_usd": info["suite_ceiling_usd"],
                      "suite_budget_usd": SUITE_BUDGET_USD, "prior_spend_usd": info["prior_spend_usd"]},
        "pricing": {"input_usd_per_million": INPUT_USD_M, "output_usd_per_million": OUTPUT_USD_M,
                    "source": "https://developers.openai.com/api/docs/models/gpt-5-mini",
                    "checked_utc": datetime.now(timezone.utc).isoformat(),
                    "known_cost_usd": 0.0, "cost_unknown": False},
    }
    _save(output, report)
    confirmed_raw = os.environ.get("VINSOC_CONFIRMED_TOTAL_BUDGET_USD")
    credit_raw = os.environ.get("VINSOC_VERIFIED_CREDIT_USD")
    if not preflight_only or confirmed_raw is not None or credit_raw is not None:
        try:
            if confirmed_raw is None or credit_raw is None:
                raise ValueError("verified credit and confirmed total budget are required")
            confirmed_total = float(confirmed_raw)
            verified_credit = float(credit_raw)
            if (not math.isfinite(confirmed_total) or not math.isfinite(verified_credit)
                    or confirmed_total <= 0 or verified_credit <= 0
                    or info["prior_spend_usd"] + info["suite_ceiling_usd"] >= confirmed_total
                    or info["suite_ceiling_usd"] >= verified_credit):
                raise ValueError("verified credit or confirmed total budget is insufficient")
        except ValueError:
            report["run_status"] = "funding_blocked"
            _save(output, report)
            raise
        report["preflight"]["funding_gate"] = {
            "source": "user-confirmed available credit and total limit",
            "confirmed_total_budget_usd": confirmed_total,
            "verified_credit_usd": verified_credit,
            "checked_utc": datetime.now(timezone.utc).isoformat(),
        }
        _save(output, report)
    if preflight_only:
        return report
    if (os.environ.get("GITHUB_REF") != "refs/heads/master" or os.environ.get("GITHUB_SHA") != sha
            or os.environ.get("GITHUB_RUN_ATTEMPT", "1") != "1" or not git_clean()):
        report["run_status"] = "identity_blocked"
        _save(output, report)
        raise ValueError("Paid R1 runner requires clean first-attempt master Actions checkout on exact SHA")
    provider: PinnedProvider

    def persist_provider() -> None:
        metadata = provider.get_run_metadata()
        report["provider_metadata"] = metadata
        report["pricing"]["known_cost_usd"] = metadata["known_cost_usd"]
        report["pricing"]["cost_unknown"] = not metadata["cost_complete"]
        _save(output, report)

    provider = PinnedProvider(client if client is not None else _make_client(), persist_provider)
    decision = DecisionRunner(config=A1Config(provider="openai", model=MODEL, temperature=None,
                                              max_tokens=CAP), provider=provider)
    decision._run_cases = cases
    results = []
    for index, case in enumerate(cases):
        remaining = sum(bound["max_cost_usd"] for bound in info["bounds"][index:])
        if (provider.get_run_metadata()["known_cost_usd"] + remaining >= SUITE_BUDGET_USD
                or info["prior_spend_usd"] + provider.get_run_metadata()["known_cost_usd"] + remaining
                >= confirmed_total
                or provider.get_run_metadata()["known_cost_usd"] + remaining >= verified_credit):
            report["run_status"] = "budget_stopped"
            _save(output, report)
            raise ValueError("R1 remaining conservative cost bound exceeds budget")
        report["attempted_calls"] += 1
        report["run_status"] = "in_progress"
        _save(output, report)
        result = decision.run_decision(case)
        results.append(result)
        record = provider.calls[-1]
        row = result.to_dict()
        row.update({"actual_model": record.get("actual_model"), "input_tokens": record.get("input_tokens"),
                    "output_tokens": record.get("output_tokens"), "cost_usd": record.get("cost_usd"),
                    "latency_ms": record.get("latency_ms"), "raw_tool_calls": record.get("raw_tool_calls", [])})
        report["case_results"].append(row)
        persist_provider()
        if record["status"] != "succeeded" or {"PROVIDER_ERROR", "EXECUTION_ERROR"}.intersection(result.errors):
            report["run_status"] = record["status"] if record["status"] != "succeeded" else "response_error"
            _save(output, report)
            raise ValueError("R1 provider, actual model, usage, or response error; inspect partial evidence")
        if record["input_tokens"] > info["bounds"][index]["input_token_bound"]:
            report["run_status"] = "usage_bound_exceeded"
            _save(output, report)
            raise ValueError("R1 actual input usage exceeded conservative bound")
    report["aggregate"] = aggregate_case_results(report["run_id"], results).to_dict()
    report["error_summary"] = generate_error_summary(results)
    report["provenance"] = build_a1_provenance(decision, "dev", results)
    report["official_eligible"] = bool(report["provenance"]["official_eligible"] and len(results) == 24)
    report["run_status"] = "complete"
    _save(output, report)
    return report


def main() -> int:
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--preflight-only", action="store_true")
    args = parser.parse_args()
    report = run(args.output, preflight_only=args.preflight_only)
    print(json.dumps({"run_status": report["run_status"], "attempted_calls": report["attempted_calls"],
                      "known_cost_usd": report["pricing"]["known_cost_usd"],
                      "suite_ceiling_usd": report["preflight"]["suite_ceiling_usd"]}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
