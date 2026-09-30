"""Single-consumption E3 dev smoke/suite; historical and frozen runners stay closed.

Only this entrypoint creates a live client, after verified gates. Tests inject a
real SDK with an offline HTTP transport; their reports are never live evidence.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from typing import Callable, Literal

from openai import OpenAI

from evaluation.dualsql_lite_ctu_gpt5.tools import SnapshotOnlyDuckDBSnapshot
from evaluation.dualsql_lite_ctu_gpt5_v2.experiment import _identity, load_cases, score_record
from evaluation.dualsql_lite_ctu_gpt5_v2.runner import CAP, MODEL, REASONING_EFFORT, MAX_TURNS, run_case
from evaluation.dualsql_lite_ctu_gpt5_v2.tools import TOOL_SCHEMAS, V2DatabaseTools

VERSION = "r2_remediation_live_e3_v1"
PRICING_URL = "https://developers.openai.com/api/docs/models/gpt-5-mini.md"
SNAPSHOT = Path("data/ctu_network_public/snapshots/ctu_dev.duckdb")
ATTEMPTS_ROOT = Path("results/evaluation_v1/ctu_network_public/dualsql_v2_remediation_live") / VERSION
GATES_PATH = Path(".superpowers/sdd/2026-09-30-r2-evidence-controller-remediation/live-gates.json")
REQUEST_BYTES_LIMIT = 20000
FRAMING_TOKENS = 512
PRICES = {"input": .25, "cached_input": .025, "output": 2.0}
STOP_ERRORS = {"RATE_LIMIT", "MODEL_UNAVAILABLE", "API_CONTRACT_ERROR", "AUTHENTICATION_ERROR",
               "PROVIDER_ERROR", "MODEL_IDENTITY_MISMATCH", "USAGE_INCOMPLETE", "SERVICE_TIER_MISMATCH",
               "REQUEST_CONTEXT_LIMIT", "REQUEST_CONTRACT_ERROR", "BUDGET_EXCEEDED", "TELEMETRY_WRITE_ERROR",
               "RESPONSE_ID_MISSING", "SCORER_INFRASTRUCTURE_ERROR", "TOOL_INFRASTRUCTURE_ERROR",
               "TOOL_EXECUTION_UNCLASSIFIED"}


class GateError(RuntimeError):
    """Category only: never propagate credentials or provider exception text."""


def utc_now():
    return datetime.now(timezone.utc).isoformat()


def encoded(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=False, default=str).encode("utf-8")


def digest(value):
    return hashlib.sha256(value.read_bytes() if isinstance(value, Path) else encoded(value)).hexdigest()


def write_new(path, value):
    with path.open("x", encoding="utf-8") as stream:
        stream.write(encoded(value).decode("utf-8") + "\n")
        stream.flush()
        os.fsync(stream.fileno())


def git_state():
    def git(*args):
        return subprocess.check_output(["git", *args], text=True).strip()
    return {"sha": git("rev-parse", "HEAD"), "origin": git("rev-parse", "origin/master"),
            "branch": git("branch", "--show-current"),
            "dirty": bool(git("status", "--porcelain", "--untracked-files=no"))}


def load_gates():
    try:
        return json.loads(GATES_PATH.read_text(encoding="utf-8"))
    except Exception:
        raise GateError("GATE_RECEIPT_MISSING") from None


def key_configuration():
    from scripts.check_env import load_env, resolve_openai_key
    dotenv = load_env(Path(".env"))
    resolution = resolve_openai_key(os.environ, dotenv)
    if not resolution.key:
        raise GateError("KEY_SOURCE_CONFLICT" if resolution.source == "conflicting_key_sources" else "KEY_MISSING")
    if os.environ.get("OPENAI_BASE_URL") or dotenv.get("OPENAI_BASE_URL"):
        raise GateError("ENDPOINT_OVERRIDE")
    options = {"source": resolution.source}
    for name, output in (("OPENAI_ORG_ID", "organization"), ("OPENAI_PROJECT_ID", "project")):
        a, b = os.environ.get(name), dotenv.get(name)
        if a and b and a != b:
            raise GateError("ACCOUNT_SOURCE_CONFLICT")
        options[output] = a or b
    return resolution.key, options


def production_client():
    key, options = key_configuration()
    return OpenAI(api_key=key, organization=options["organization"], project=options["project"],
                  base_url="https://api.openai.com/v1", max_retries=0, timeout=120)


def verified_environment(snapshot_path):
    from evaluation.ctu_network_public.contract import CASES, MANIFEST, validate, portable_text_sha256
    if snapshot_path.resolve() != SNAPSHOT.resolve():
        raise GateError("DEV_SNAPSHOT_PATH_MISMATCH")
    verified = validate(snapshot_path, manifest_path=MANIFEST)
    cases = load_cases(CASES)
    tools = V2DatabaseTools(snapshot_path, MANIFEST)
    identity = _identity(snapshot_path, MANIFEST, CASES, verified)
    identity.update(schema_sha256=digest(tools.schema), catalog_sha256=tools.catalog_sha256,
                    live_entrypoint_sha256=portable_text_sha256(Path(__file__)), live_version=VERSION,
                    split="ctu_network_public_dev_v1", condition="E3")
    identity.pop("verification_time_utc", None)  # verification time belongs to receipt, not compatibility
    identity["request_contract"].update(service_tier="default", serialized_utf8_bytes_limit=REQUEST_BYTES_LIMIT,
                                         framing_tokens_reserve=FRAMING_TOKENS)
    identity["pricing_usd_per_million"] = PRICES
    import importlib.metadata
    identity["runtime_versions"] = {name: importlib.metadata.version(name) for name in ("openai", "httpx", "duckdb")}
    identity["provenance_scope"] = "current live dev execution; not historical provenance backfill"
    return cases, tools, identity


def preflight_bound():
    # Each UTF-8 byte upper-bounds a byte-level token; reserve framing separately.
    per_call = ((REQUEST_BYTES_LIMIT + FRAMING_TOKENS) * PRICES["input"] + CAP * PRICES["output"]) / 1e6
    return {"serialized_utf8_bytes_limit": REQUEST_BYTES_LIMIT, "framing_tokens_reserve": FRAMING_TOKENS,
            "per_call_ceiling_usd": per_call, "smoke_max_calls": 2 * MAX_TURNS,
            "suite_max_calls": 8 * 2 * MAX_TURNS, "combined_max_calls": 9 * 2 * MAX_TURNS,
            "smoke_ceiling_usd": 2 * MAX_TURNS * per_call,
            "suite_ceiling_usd": 8 * 2 * MAX_TURNS * per_call,
            "combined_ceiling_usd": 9 * 2 * MAX_TURNS * per_call}


def validate_request(request):
    if (request.get("model") != MODEL or request.get("reasoning_effort") != REASONING_EFFORT
            or request.get("max_completion_tokens") != CAP or "temperature" in request
            or request.get("service_tier", "default") != "default"
            or ("tools" in request and request["tools"] != TOOL_SCHEMAS)):
        raise GateError("REQUEST_CONTRACT_ERROR")
    if len(encoded(request)) > REQUEST_BYTES_LIMIT:
        raise GateError("REQUEST_CONTEXT_LIMIT")


def fresh(timestamp):
    try:
        age = (datetime.now(timezone.utc) - datetime.fromisoformat(timestamp)).total_seconds()
        return 0 <= age <= 21600
    except (ValueError, TypeError):
        return False


def validate_gates(gates, state):
    if state["branch"] != "master" or state["dirty"] or state["sha"] != state["origin"]:
        raise GateError("IMPLEMENTATION_STATE_MISMATCH")
    ci = gates.get("ci", {})
    if (gates.get("implementation_sha") != state["sha"] or ci.get("headSha") != state["sha"]
            or ci.get("conclusion") != "success" or any(not any(
                version in job.get("name", "") and job.get("conclusion") == "success"
                for job in ci.get("jobs", [])) for version in ("3.11", "3.12"))):
        raise GateError("EXACT_SHA_CI_REQUIRED")
    account = gates.get("account", {})
    if (account.get("source") != "owner_confirmation" or not account.get("project_verified")
            or not fresh(account.get("confirmed_utc")) or account.get("credit_at_least_usd", 0) < .75
            or account.get("hard_limit_at_least_usd", 0) < .75):
        raise GateError("ACCOUNT_GATE_FAILED")
    prices = gates.get("pricing", {})
    if (prices.get("url") != PRICING_URL or not fresh(prices.get("checked_utc"))
            or len(prices.get("source_sha256", "")) != 64
            or any(prices.get(key) != value for key, value in PRICES.items())):
        raise GateError("PRICING_GATE_FAILED")
    if (gates.get("new_live_budget_usd") != .75 or gates.get("total_authorized_usd") != 2
            or not isinstance(gates.get("historical_recorded_lower_bound_usd"), (int, float))
            or gates["historical_recorded_lower_bound_usd"] + .75 > 2
            or preflight_bound()["combined_ceiling_usd"] > .75):
        raise GateError("BUDGET_GATE_FAILED")


def preflight(mode, snapshot_path, output_path, smoke_report_path=None, require_live=False):
    if mode not in {"smoke", "suite"}:
        raise GateError("E3_DEV_ONLY")
    if output_path.exists():
        raise GateError("OUTPUT_EXISTS")
    if (ATTEMPTS_ROOT / f"{mode}.claim.json").exists():
        raise GateError("ATTEMPT_ALREADY_CONSUMED")
    gates, state = load_gates(), git_state()
    validate_gates(gates, state)
    _, key_metadata = key_configuration()
    try:
        cases, tools, identity = verified_environment(snapshot_path)
    except Exception:
        raise GateError("DEV_IDENTITY_VERIFICATION_FAILED") from None
    if [c.case_id for c in cases] != [f"ctu_sql_{i:03d}" for i in range(1, 9)]:
        raise GateError("DEV_SPLIT_MISMATCH")
    if identity["git_sha"] != state["sha"] or identity["dirty_state"]:
        raise GateError("DEV_IMPLEMENTATION_MISMATCH")
    identity_sha = digest(identity)
    previous_cost = 0.0
    if mode == "suite":
        try:
            receipt = json.loads((ATTEMPTS_ROOT / "smoke.receipt.json").read_text())
            smoke = json.loads(smoke_report_path.read_text(encoding="utf-8"))
            if (receipt["report_sha256"] != digest(smoke_report_path)
                    or receipt["report_path"] != str(smoke_report_path.resolve())
                    or not smoke["smoke_gate_passed"] or not smoke["cost_complete"]
                    or smoke["identity_sha256"] != identity_sha
                    or (require_live and (smoke.get("provider_kind") != "openai_live"
                                          or "synthetic_provider" in smoke["eligibility_reasons"]))):
                raise ValueError()
            previous_cost = smoke["observed_cost_usd"]
        except Exception:
            raise GateError("SMOKE_GATE_FAILED") from None
    from evaluation.dualsql_lite_ctu_gpt5_v2.prompts import LINKER_INSTRUCTIONS
    for case in cases:
        validate_request({"model": MODEL, "reasoning_effort": REASONING_EFFORT,
                          "max_completion_tokens": CAP, "tools": TOOL_SCHEMAS,
                          "messages": [{"role": "system", "content": LINKER_INSTRUCTIONS + "\nDatabase schema:\n" + tools.schema_context()},
                                       {"role": "user", "content": case.question}]})
    return cases, tools, identity, identity_sha, gates, key_metadata, previous_cost


class GuardedSDK:
    def __init__(self, client, append, previous_cost, max_calls, suite_reserve_calls=0):
        if (not isinstance(client, OpenAI) or client.max_retries != 0
                or str(client.base_url).rstrip("/") != "https://api.openai.com/v1"):
            raise GateError("PROVIDER_CONTRACT_ERROR")
        self.client, self.append = client, append
        self.previous_cost, self.max_calls = previous_cost, max_calls
        self.suite_reserve_calls = suite_reserve_calls
        self.attempts = self.responses = 0
        self.usage = []
        self.cost = 0.0
        self.last = None
        self.error = None
        self.case_id = None
        self.chat = SimpleNamespace(completions=self)

    def create(self, **request):
        request = dict(request, service_tier="default")
        try:
            if self.error:
                raise GateError(self.error)
            validate_request(request)
            remaining = self.max_calls - self.attempts
            if remaining <= 0 or self.previous_cost + self.cost + (remaining + self.suite_reserve_calls) * preflight_bound()["per_call_ceiling_usd"] > .75 + 1e-12:
                raise GateError("BUDGET_EXCEEDED")
        except GateError as error:
            self.error = str(error)
            self.append({"event": "blocked_request", "case_id": self.case_id, "error_category": self.error})
            raise
        self.append({"event": "attempt", "case_id": self.case_id, "time_utc": utc_now(),
                     "request": request, "request_sha256": digest(request),
                     "serialized_utf8_bytes": len(encoded(request)), "remaining_max_calls": remaining})
        self.attempts += 1
        start = time.monotonic()
        try:
            response = self.client.chat.completions.create(**request)
        except Exception as error:
            status = getattr(error, "status_code", None)
            self.error = {429: "RATE_LIMIT", 404: "MODEL_UNAVAILABLE", 400: "API_CONTRACT_ERROR",
                          401: "AUTHENTICATION_ERROR", 403: "AUTHENTICATION_ERROR"}.get(status, "PROVIDER_ERROR")
            self.append({"event": "provider_failure", "case_id": self.case_id, "error_category": self.error,
                         "http_status": status, "cost_unknown": True})
            raise GateError(self.error) from None
        self.responses += 1
        usage = response.usage
        inp, out, total = (getattr(usage, k, None) for k in ("prompt_tokens", "completion_tokens", "total_tokens"))
        cached = getattr(getattr(usage, "prompt_tokens_details", None), "cached_tokens", 0)
        complete = (type(inp) is int and inp >= 0 and type(out) is int and 0 <= out <= CAP
                    and type(total) is int and total == inp + out
                    and type(cached) is int and 0 <= cached <= inp)
        tier = getattr(response, "service_tier", None)
        cost = ((inp - cached) * PRICES["input"] + cached * PRICES["cached_input"] + out * PRICES["output"]) / 1e6 if complete and response.model == MODEL and tier == "default" else None
        self.last = {"response_id": response.id, "model": response.model, "input_tokens": inp,
                     "cached_input_tokens": cached, "output_tokens": out, "total_tokens": total,
                     "usage_complete": complete, "service_tier": tier, "cost_usd": cost,
                     "latency_ms": (time.monotonic() - start) * 1000}
        self.usage.append(dict(self.last, case_id=self.case_id))
        if cost is not None:
            self.cost += cost
        # Persist the complete observed SDK response before controller argument parsing.
        try:
            self.append({"event": "sdk_response", "case_id": self.case_id, "telemetry": self.last,
                         "response": response.model_dump(mode="json")})
        except Exception:
            self.error = "TELEMETRY_WRITE_ERROR"
            raise GateError(self.error) from None
        self.error = ("MODEL_IDENTITY_MISMATCH" if response.model != MODEL else
                      "USAGE_INCOMPLETE" if not complete else "SERVICE_TIER_MISMATCH" if tier != "default" else None)
        return response


class GuardedTools:
    """Keep the recovered tool implementation; latch failures at the live boundary."""
    def __init__(self, tools, sdk):
        self.tools, self.sdk = tools, sdk

    def __getattr__(self, name):
        return getattr(self.tools, name)

    def invoke(self, name, arguments):
        try:
            result = self.tools.invoke(name, arguments)
        except Exception:
            self.sdk.error = "TOOL_INFRASTRUCTURE_ERROR"
            result = {"ok": False, "error_type": self.sdk.error}
        # The legacy tool boundary collapses execution exceptions. Do not guess
        # whether these are malformed SQL or a failed database connection.
        if result.get("error_type") in {"EXECUTION_ERROR", "TOOL_EXECUTION_ERROR"}:
            self.sdk.error = "TOOL_EXECUTION_UNCLASSIFIED"
        try:
            self.sdk.append({"event": "tool", "case_id": self.sdk.case_id, "tool": name,
                             "arguments": arguments, "result": result})
        except Exception:
            self.sdk.error = "TELEMETRY_WRITE_ERROR"
            raise GateError(self.sdk.error) from None
        return result


def run_live_dev(mode: Literal["smoke", "suite"], snapshot_path: Path, output_path: Path,
                 client_factory: Callable, smoke_report_path: Path | None = None) -> dict:
    cases, tools, identity, identity_sha, gates, key_meta, previous_cost = preflight(
        mode, snapshot_path, output_path, smoke_report_path, require_live=client_factory is production_client)
    selected = cases[:1] if mode == "smoke" else cases
    ATTEMPTS_ROOT.mkdir(parents=True, exist_ok=True)
    write_new(ATTEMPTS_ROOT / f"{mode}.claim.json", {"mode": mode, "time_utc": utc_now(),
              "identity_sha256": identity_sha, "output_path": str(output_path.resolve())})
    output_path.mkdir(parents=True, exist_ok=False)
    results, sdk, infrastructure_error, raw_client = [], None, None, None
    synthetic = client_factory is not production_client
    with (output_path / "partial.jsonl").open("x", encoding="utf-8") as journal:
        def append(value):
            journal.write(encoded(value).decode("utf-8") + "\n")
            journal.flush()
            os.fsync(journal.fileno())
        append({"event": "identity", "time_utc": utc_now(), "mode": mode, "identity": identity,
                "identity_sha256": identity_sha, "gates": gates, "bound": preflight_bound(),
                "key_source": key_meta["source"], "synthetic_provider": synthetic})
        try:
            raw_client = client_factory()
            sdk = GuardedSDK(raw_client, append, previous_cost, 10 if mode == "smoke" else 80,
                             suite_reserve_calls=80 if mode == "smoke" else 0)
            guarded_tools = GuardedTools(tools, sdk)
            snapshot = SnapshotOnlyDuckDBSnapshot(tools.snapshot_path)
            for case in selected:
                sdk.case_id, sdk.error = case.case_id, None
                before_attempts, before_responses = sdk.attempts, sdk.responses
                def sink(request, telemetry):
                    telemetry.update({k: v for k, v in sdk.last.items() if k != "latency_ms"})
                    append({"event": "controller_response", "case_id": case.case_id, "telemetry": telemetry,
                            "request_sha256": digest(dict(request, service_tier="default"))})
                    if sdk.error:
                        raise GateError(sdk.error)
                record = run_case(case, "E3", guarded_tools, sdk, tools.schema_context(), telemetry_sink=sink)
                if sdk.error:
                    record["error_category"] = sdk.error
                record["sdk_attempted_calls"] = sdk.attempts - before_attempts
                record["sdk_response_count"] = sdk.responses - before_responses
                record["db_calls"] = len(record["trajectory"])
                try:
                    score_record(case, record, snapshot)
                except Exception:
                    record.update(error_category="SCORER_INFRASTRUCTURE_ERROR", syntax_valid=False,
                                  execution_success=False, execution_accurate=False, safety_rejected=False)
                results.append(record)
                append({"event": "case", "record": record})
                write_new(output_path / f"{case.case_id}.json", record)
                if record["error_category"] in STOP_ERRORS:
                    break
        except Exception as error:
            category = str(error) if isinstance(error, GateError) else "LOCAL_INFRASTRUCTURE_ERROR"
            infrastructure_error = category
            append({"event": "infrastructure_failure", "error_category": category, "cost_unknown": True})
        finally:
            if raw_client:
                raw_client.close()
    usage = sdk.usage if sdk else []
    attempted, responses = (sdk.attempts, sdk.responses) if sdk else (0, 0)
    complete_cost = bool(sdk) and attempted == responses == len(usage) and all(u["cost_usd"] is not None and u["usage_complete"] for u in usage)
    counts = {field: sum(r[field] for r in results) for field in ("syntax_valid", "execution_success", "execution_accurate", "safety_rejected")}
    complete = not infrastructure_error and len(results) == len(selected) and not any(r["error_category"] in STOP_ERRORS for r in results)
    smoke_pass = (mode == "smoke" and complete and complete_cost and bool(results[0]["roles"]["linker"])
                  and bool(results[0]["roles"]["generator"]) and bool(results[0]["final_sql"])
                  and any(t["result"].get("ok") for t in results[0]["trajectory"])
                  and counts["syntax_valid"] == counts["execution_success"] == 1 and not counts["safety_rejected"]
                  and sdk.cost <= preflight_bound()["smoke_ceiling_usd"])
    reasons = (["synthetic_provider"] if synthetic else []) + (["smoke_subset"] if mode == "smoke" else [])
    if not complete: reasons.append("partial_run")
    if not complete_cost: reasons.append("incomplete_cost")
    report = {"series_version": VERSION, "scope": "public_dev_diagnostic", "mode": mode, "condition": "E3",
              "identity": identity, "identity_sha256": identity_sha, "gates": gates, "bound": preflight_bound(),
              "provider_kind": "synthetic_transport" if synthetic else "openai_live",
              "case_count": len(selected), "completed_case_count": len(results), "case_ids": [c.case_id for c in selected],
              "missing_case_ids": [c.case_id for c in selected if c.case_id not in {r["case_id"] for r in results}],
              "status": "complete" if complete else "partial", "smoke_gate_passed": smoke_pass,
              "official_eligible": mode == "suite" and not reasons, "eligibility_reasons": reasons,
              "counts": counts, "rates": {k: n / len(selected) for k, n in counts.items()},
              "attempted_calls": attempted, "response_count": responses, "db_calls": sum(r["db_calls"] for r in results),
              "actual_models": sorted({u["model"] for u in usage if u["model"]}),
              "input_tokens": sum(u["input_tokens"] for u in usage if type(u["input_tokens"]) is int),
              "cached_input_tokens": sum(u["cached_input_tokens"] for u in usage if type(u["cached_input_tokens"]) is int),
              "output_tokens": sum(u["output_tokens"] for u in usage if type(u["output_tokens"]) is int),
              "latency_ms": sum(u["latency_ms"] for u in usage), "observed_cost_usd": sdk.cost if sdk else 0,
              "cost_complete": complete_cost, "cost_unknown": not complete_cost,
              "response_usage": usage, "infrastructure_error": infrastructure_error,
              "smoke_report_sha256": digest(smoke_report_path) if smoke_report_path else None,
              "smoke_case_repeated_in_suite_by_protocol": mode == "suite", "case_results": results}
    write_new(output_path / "report.json", report)
    if mode == "smoke":
        write_new(ATTEMPTS_ROOT / "smoke.receipt.json", {"report_path": str((output_path / "report.json").resolve()),
                  "report_sha256": digest(output_path / "report.json"), "smoke_gate_passed": smoke_pass})
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", choices=["smoke", "suite", "smoke-and-suite"], default="smoke-and-suite")
    parser.add_argument("--snapshot", type=Path, default=SNAPSHOT)
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--smoke-report", type=Path)
    parser.add_argument("--preflight-only", action="store_true")
    args = parser.parse_args()
    if args.preflight_only:
        preflight("suite" if args.mode == "suite" else "smoke", args.snapshot,
                  args.output_root / ("suite" if args.mode == "suite" else "smoke"), args.smoke_report, require_live=True)
        print(json.dumps({"preflight": "PASS", "bound": preflight_bound()}))
        return 0
    if args.mode in {"smoke", "smoke-and-suite"}:
        smoke = run_live_dev("smoke", args.snapshot, args.output_root / "smoke", production_client)
        print(json.dumps({"mode": "smoke", "gate_passed": smoke["smoke_gate_passed"], "cost_usd": smoke["observed_cost_usd"]}))
        if args.mode == "smoke" or not smoke["smoke_gate_passed"]:
            return 0 if smoke["smoke_gate_passed"] else 1
    suite = run_live_dev("suite", args.snapshot, args.output_root / "suite", production_client,
                         args.smoke_report or args.output_root / "smoke" / "report.json")
    print(json.dumps({k: suite[k] for k in ("status", "counts", "attempted_calls", "response_count", "observed_cost_usd")}))
    return 0 if suite["status"] == "complete" else 1


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except GateError as error:
        print(json.dumps({"gate": "FAIL", "error_category": str(error)}))
        raise SystemExit(1) from None
