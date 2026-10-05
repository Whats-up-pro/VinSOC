"""One guarded E0 or E3 CTU dev condition for the v4 finalization series."""
from __future__ import annotations

import argparse
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Literal

from evaluation.finalization.contract import (ContractError, build_preflight_bound, canonical_bytes,
                                              sha256, validate_request_token_bound, verify_release_inputs)
from evaluation.r2_phase2.grounding import Phase2Tools
from evaluation.r2_phase2.runner import CAP, MODEL, REASONING_EFFORT, run_case
from evaluation.r2_phase2.scoring import score_prediction
from evaluation.r2_phase2.tool_schemas_v4 import TOOL_SCHEMAS
from scripts.run_r2_v2_dev_live import (GateError, GuardedSDK, GuardedTools, digest, git_state,
                                        key_configuration, production_client, write_new)

SERIES_ID = "r2_finalization_v4"
SNAPSHOT = Path("data/ctu_network_public/snapshots/ctu_dev.duckdb")
LOCK = Path("evaluation/r2_phase2/CONTRACT_v4.lock.json")
OUTPUT_ROOT = Path("results/evaluation_v1/finalization_v4")
PRICING_URL = "https://developers.openai.com/api/docs/models/gpt-5-mini"
PRICES = {"input": 0.25, "cached_input": 0.025, "output": 2.0}
REQUEST_CONTRACT = {"model": MODEL, "reasoning_effort": REASONING_EFFORT,
                    "max_completion_tokens": CAP, "service_tier": "default",
                    "input_token_ceiling": 20_512}


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _fresh(value: Any) -> bool:
    try:
        age = (datetime.now(timezone.utc) - datetime.fromisoformat(value)).total_seconds()
        return 0 <= age <= 21_600
    except (TypeError, ValueError):
        return False


def _ledger_path(output: Path) -> Path:
    return output.parent / "cost-ledger.jsonl"


def _ledger_state(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {"observed_cost_usd": 0.0, "cost_unknown": False}
    total, unknown = 0.0, False
    for line in path.read_text(encoding="utf-8").splitlines():
        item = json.loads(line)
        total += float(item.get("observed_cost_usd", 0.0))
        unknown |= bool(item.get("cost_unknown"))
    return {"observed_cost_usd": total, "cost_unknown": unknown}


def _append_ledger(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as stream:
        stream.write(canonical_bytes(value).decode("utf-8") + "\n")
        stream.flush()
        os.fsync(stream.fileno())


def build_preflight_bound_for_series() -> dict[str, Any]:
    e0 = build_preflight_bound(REQUEST_CONTRACT, PRICES, 8)
    e3 = build_preflight_bound(REQUEST_CONTRACT, PRICES, 80)
    demo = build_preflight_bound({"input_token_ceiling": 50_000, "max_completion_tokens": 1000},
                                 {"input": 0.40, "output": 1.60}, 4)
    return {"E0": e0, "E3": e3, "demo_reserve": demo,
            "combined_ceiling_usd": e0["ceiling_usd"] + e3["ceiling_usd"] + demo["ceiling_usd"]}


def validate_gates(gates: dict[str, Any], state: dict[str, Any]) -> None:
    ci = gates.get("ci", {})
    if state["branch"] != "master" or state["dirty"] or state["sha"] != state["origin"]:
        raise GateError("IMPLEMENTATION_STATE_MISMATCH")
    if (gates.get("implementation_sha") != state["sha"] or ci.get("headSha") != state["sha"]
            or ci.get("conclusion") != "success" or any(not any(
                version in job.get("name", "") and job.get("conclusion") == "success"
                for job in ci.get("jobs", [])) for version in ("3.11", "3.12"))):
        raise GateError("EXACT_SHA_CI_REQUIRED")
    account = gates.get("account", {})
    if (account.get("source") != "owner_confirmation" or not account.get("project_verified")
            or not _fresh(account.get("confirmed_utc")) or account.get("credit_at_least_usd", 0) < .75
            or account.get("hard_limit_at_least_usd", 0) < .75):
        raise GateError("ACCOUNT_GATE_FAILED")
    pricing = gates.get("pricing", {})
    if (pricing.get("url") != PRICING_URL or not _fresh(pricing.get("checked_utc"))
            or len(pricing.get("source_sha256", "")) != 64
            or any(pricing.get(key) != value for key, value in PRICES.items())):
        raise GateError("PRICING_GATE_FAILED")
    if gates.get("new_live_budget_usd") != .75 or build_preflight_bound_for_series()["combined_ceiling_usd"] > .75:
        raise GateError("BUDGET_GATE_FAILED")


def _load_gates(path: Path) -> dict[str, Any]:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        raise GateError("GATE_RECEIPT_MISSING") from None


def _request_validator(condition: str):
    def validate(request: dict[str, Any]) -> None:
        if (request.get("model") != MODEL or request.get("reasoning_effort") != REASONING_EFFORT
                or request.get("max_completion_tokens") != CAP or "temperature" in request
                or request.get("service_tier", "default") != "default"):
            raise GateError("REQUEST_CONTRACT_ERROR")
        if condition == "E0" and "tools" in request:
            raise GateError("REQUEST_CONTRACT_ERROR")
        if condition == "E3" and request.get("tools") != TOOL_SCHEMAS:
            raise GateError("REQUEST_CONTRACT_ERROR")
        try:
            validate_request_token_bound(dict(request, service_tier="default"), REQUEST_CONTRACT["input_token_ceiling"])
        except ContractError as error:
            raise GateError(str(error)) from None
    return validate


def release_identity(snapshot: Path, lock: Path) -> tuple[list, Phase2Tools, dict[str, Any]]:
    try:
        release = verify_release_inputs(snapshot, lock)
        from evaluation.ctu_network_public.contract import CASES, MANIFEST, validate
        from evaluation.dualsql_lite_ctu_gpt5_v2.experiment import load_cases
        verified = validate(snapshot, manifest_path=MANIFEST)
        cases = load_cases(CASES)
        if [item.case_id for item in cases] != [f"ctu_sql_{i:03d}" for i in range(1, 9)]:
            raise ValueError("case split")
        tools = Phase2Tools(snapshot, MANIFEST)
        return cases, tools, {"release_lock_sha256": sha256(lock), "release": release,
                              "snapshot_validation": verified, "runtime_request_contract": REQUEST_CONTRACT}
    except Exception:
        raise GateError("DEV_IDENTITY_VERIFICATION_FAILED") from None


def claim_attempt(series_id: str, condition: Literal["E0", "E3"], output: Path,
                  claim_root: Path, client_factory: Callable | None = None) -> Path:
    claim = claim_root / f"{series_id}-{condition}.claim.json"
    if output.exists():
        raise GateError("OUTPUT_EXISTS")
    if claim.exists():
        raise GateError("ATTEMPT_ALREADY_CONSUMED")
    claim_root.mkdir(parents=True, exist_ok=True)
    write_new(claim, {"series_id": series_id, "condition": condition, "time_utc": utc_now(),
                      "output_path": str(output.resolve())})
    return claim


def preflight(condition: Literal["E0", "E3"], snapshot: Path, output: Path, gates_path: Path) -> tuple[list, Phase2Tools, dict, dict]:
    if condition not in {"E0", "E3"}:
        raise GateError("CONDITION_INVALID")
    gates, state = _load_gates(gates_path), git_state()
    validate_gates(gates, state)
    _key, _metadata = key_configuration()
    cases, tools, identity = release_identity(snapshot, LOCK)
    ledger = _ledger_state(_ledger_path(output))
    if ledger["cost_unknown"]:
        raise GateError("COST_RECONCILIATION_REQUIRED")
    planned = build_preflight_bound_for_series()
    if ledger["observed_cost_usd"] + planned[condition]["ceiling_usd"] + planned["demo_reserve"]["ceiling_usd"] > .75 + 1e-12:
        raise GateError("BUDGET_EXCEEDED")
    return cases, tools, identity, gates


def run_condition(condition: Literal["E0", "E3"], output: Path, client_factory: Callable,
                  snapshot: Path = SNAPSHOT, gates_path: Path = Path(".vinsoc/finalization-v4-gates.json")) -> dict:
    cases, tools, identity, gates = preflight(condition, snapshot, output, gates_path)
    claim = claim_attempt(SERIES_ID, condition, output, output.parent / "claims")
    output.mkdir(parents=True, exist_ok=False)
    journal_path = output / "partial.jsonl"
    raw_client = sdk = None
    records: list[dict] = []
    infrastructure_error = None
    bound = build_preflight_bound_for_series()[condition]
    ledger = _ledger_state(_ledger_path(output))
    with journal_path.open("x", encoding="utf-8") as journal:
        def append(value: dict) -> None:
            journal.write(canonical_bytes(value).decode("utf-8") + "\n")
            journal.flush()
            os.fsync(journal.fileno())
        append({"event": "identity", "identity": identity, "gates": gates, "condition": condition,
                "claim_sha256": sha256(claim), "bound": bound})
        try:
            raw_client = client_factory()
            sdk = GuardedSDK(raw_client, append, ledger["observed_cost_usd"], bound["max_calls"],
                             request_validator=_request_validator(condition), bound=bound, pricing=PRICES, model=MODEL)
            guarded_tools = GuardedTools(tools, sdk)
            for case in cases:
                sdk.case_id, sdk.error = case.case_id, None
                record = run_case(case, condition, guarded_tools if condition == "E3" else tools, sdk,
                                  tools.schema_context(), telemetry_sink=lambda request, telemetry: append({"event": "controller_response", "telemetry": telemetry, "request_sha256": digest(dict(request, service_tier="default"))}))
                record = score_prediction(case, record, snapshot)
                record["db_calls"] = len(record.get("trajectory", []))
                records.append(record)
                append({"event": "case", "record": record})
                write_new(output / f"{case.case_id}.json", record)
                if sdk.error:
                    infrastructure_error = sdk.error
                    break
        except Exception as error:
            infrastructure_error = str(error) if isinstance(error, GateError) else "LOCAL_INFRASTRUCTURE_ERROR"
            append({"event": "infrastructure_failure", "error_category": infrastructure_error, "cost_unknown": True})
        finally:
            if raw_client:
                raw_client.close()
    usage = sdk.usage if sdk else []
    attempted, received = (sdk.attempts, sdk.responses) if sdk else (0, 0)
    cost_complete = bool(sdk) and attempted == received == len(usage) and all(item["cost_usd"] is not None for item in usage)
    counts = {field: sum(bool(record.get(field)) for record in records) for field in ("syntax_valid", "execution_success", "execution_accurate", "safety_rejected")}
    report = {"series_id": SERIES_ID, "condition": condition, "scope": "ctu_public_dev_v4", "identity": identity,
              "status": "complete" if not infrastructure_error and len(records) == 8 else "partial", "case_count": 8,
              "completed_case_count": len(records), "case_results": records, "counts": counts,
              "attempted_calls": attempted, "response_count": received, "db_calls": sum(r["db_calls"] for r in records),
              "actual_models": sorted({u["model"] for u in usage if u.get("model")}), "response_usage": usage,
              "observed_cost_usd": sdk.cost if sdk else 0.0, "cost_complete": cost_complete,
              "cost_unknown": not cost_complete, "infrastructure_error": infrastructure_error,
              "official_eligible": client_factory is production_client and not infrastructure_error and cost_complete}
    write_new(output / "report.json", report)
    _append_ledger(_ledger_path(output), {"series_id": SERIES_ID, "condition": condition,
                                          "report_sha256": sha256(output / "report.json"),
                                          "observed_cost_usd": report["observed_cost_usd"], "cost_unknown": report["cost_unknown"]})
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--condition", choices=("E0", "E3"), required=True)
    parser.add_argument("--snapshot", type=Path, default=SNAPSHOT)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--gates", type=Path, default=Path(".vinsoc/finalization-v4-gates.json"))
    parser.add_argument("--preflight-only", action="store_true")
    args = parser.parse_args()
    if args.preflight_only:
        preflight(args.condition, args.snapshot, args.output, args.gates)
        print(json.dumps({"preflight": "PASS", "condition": args.condition, "bound": build_preflight_bound_for_series()}))
        return 0
    report = run_condition(args.condition, args.output, production_client, args.snapshot, args.gates)
    print(json.dumps({key: report[key] for key in ("status", "counts", "attempted_calls", "response_count", "observed_cost_usd", "cost_complete")}))
    return 0 if report["status"] == "complete" else 1


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except GateError as error:
        print(json.dumps({"gate": "FAIL", "error_category": str(error)}))
        raise SystemExit(1) from None
