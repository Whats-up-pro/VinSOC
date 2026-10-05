"""One-consumption phase-2 E3 dev suite; no smoke, rerun or frozen entrypoint."""
from __future__ import annotations
import argparse
import json
import os
from pathlib import Path
from typing import Callable

from scripts.run_r2_v2_dev_live import (GateError, GuardedSDK, GuardedTools, production_client,
    key_configuration, git_state, validate_gates, validate_request, preflight_bound, digest,
    encoded, write_new, utc_now, SNAPSHOT, STOP_ERRORS, PRICING_URL, MODEL, PRICES)
from evaluation.r2_phase2.grounding import Phase2Tools, CONTRACT_IDENTITY
from evaluation.r2_phase2.runner import run_case, CONTROLLER_VERSION
from evaluation.r2_phase2.safety import Phase2Snapshot as SnapshotOnlyDuckDBSnapshot, POLICY_IDENTITY
from evaluation.dualsql_lite_ctu_gpt5_v2.experiment import score_record

VERSION = 'r2_phase2_live_e3_v1'
HISTORICAL_ENTRYPOINT_STATUS = 'RETIRED_FAIL_CLOSED'
ATTEMPTS_ROOT = Path('results/evaluation_v1/ctu_network_public/r2_phase2_live') / VERSION
GATES_PATH = Path('.superpowers/sdd/2026-10-01-vinsoc-remediation-phase2/live-gates.json')
CONTRACT_PATH = Path('evaluation/r2_phase2/CONTRACT_v3.lock.json')
CONTRACT_SHA256 = 'a8d43578b892d93c41c723ff8841f24e0b02aa2861048b5c92661d01f46ff132'


def load_gates():
    try:
        return json.loads(GATES_PATH.read_text(encoding='utf-8'))
    except Exception:
        raise GateError('GATE_RECEIPT_MISSING') from None


def verify_contract(path=CONTRACT_PATH):
    from evaluation.ctu_network_public.contract import portable_text_sha256
    try:
        if digest(path) != CONTRACT_SHA256:
            raise ValueError()
        contract=json.loads(path.read_text(encoding='utf-8'))
        if contract['contract_identity'] != CONTRACT_IDENTITY:
            raise ValueError()
        for file, sha in contract['files_portable_sha256'].items():
            if portable_text_sha256(Path(file)) != sha:
                raise ValueError()
        return contract
    except Exception:
        raise GateError('CONTRACT_IDENTITY_MISMATCH') from None


def verified_environment(snapshot_path):
    from evaluation.ctu_network_public.contract import CASES,MANIFEST,validate,portable_text_sha256
    from evaluation.dualsql_lite_ctu_gpt5_v2.experiment import _identity,load_cases
    import importlib.metadata
    if snapshot_path.resolve()!=SNAPSHOT.resolve():
        raise GateError('DEV_SNAPSHOT_PATH_MISMATCH')
    contract=verify_contract()
    verified=validate(snapshot_path,manifest_path=MANIFEST)
    if digest(verified)!=digest(contract['snapshot']):
        raise GateError('DEV_CONTRACT_MISMATCH')
    cases=load_cases(CASES)
    tools=Phase2Tools(snapshot_path,MANIFEST)
    identity=_identity(snapshot_path,MANIFEST,CASES,verified)
    identity.pop('verification_time_utc',None)
    identity.update(schema_sha256=digest(tools.schema),catalog_sha256=tools.catalog_sha256,
                    live_entrypoint_sha256=portable_text_sha256(Path(__file__)),live_version=VERSION,
                    reused_sdk_guard_sha256=portable_text_sha256(Path('scripts/run_r2_v2_dev_live.py')),
                    split='ctu_network_public_dev_v1',condition='E3',policy_identity=POLICY_IDENTITY,
                    contract_identity=CONTRACT_IDENTITY,contract_sha256=digest(CONTRACT_PATH),
                    phase2_files_sha256=contract['files_portable_sha256'],controller_version=CONTROLLER_VERSION,
                    tool_version=CONTRACT_IDENTITY)
    from scripts.run_r2_v2_dev_live import REQUEST_BYTES_LIMIT,FRAMING_TOKENS
    identity['request_contract'].update(service_tier='default',serialized_utf8_bytes_limit=REQUEST_BYTES_LIMIT,
                                        framing_tokens_reserve=FRAMING_TOKENS)
    identity['pricing_usd_per_million']=PRICES
    identity['runtime_versions']={name:importlib.metadata.version(name) for name in ('openai','httpx','duckdb')}
    identity['provenance_scope']='current phase2 dev only; no historical backfill or holdout claim'
    return cases,tools,identity


def preflight(snapshot_path,output_path,require_live=False):
    if output_path.exists():
        raise GateError('OUTPUT_EXISTS')
    if (ATTEMPTS_ROOT/'suite.claim.json').exists():
        raise GateError('ATTEMPT_ALREADY_CONSUMED')
    if require_live and not output_path.resolve().is_relative_to(ATTEMPTS_ROOT.parent.resolve()):
        raise GateError('OUTPUT_NAMESPACE_MISMATCH')
    gates,state=load_gates(),git_state()
    validate_gates(gates,state)
    _,key_meta=key_configuration()
    try:
        cases,tools,identity=verified_environment(snapshot_path)
    except Exception:
        raise GateError('DEV_IDENTITY_VERIFICATION_FAILED') from None
    if [c.case_id for c in cases]!=[f'ctu_sql_{i:03d}' for i in range(1,9)]:
        raise GateError('DEV_SPLIT_MISMATCH')
    if identity['git_sha']!=state['sha'] or identity['dirty_state']:
        raise GateError('DEV_IMPLEMENTATION_MISMATCH')
    from evaluation.dualsql_lite_ctu_gpt5_v2.prompts import LINKER_INSTRUCTIONS
    for case in cases:
        validate_request({'model':MODEL,'reasoning_effort':'low','max_completion_tokens':1000,
                          'messages':[{'role':'system','content':LINKER_INSTRUCTIONS+'\nDatabase schema:\n'+tools.schema_context()},
                                      {'role':'user','content':case.question}]})
    return cases,tools,identity,digest(identity),gates,key_meta,0.0


def run_suite(snapshot_path: Path, output_path: Path, client_factory: Callable) -> dict:
    mode = "suite"
    smoke_report_path = None
    cases, tools, identity, identity_sha, gates, key_meta, previous_cost = preflight(
        snapshot_path, output_path, require_live=client_factory is production_client)
    selected = cases
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
                try:
                    raw_client.close()
                except Exception:
                    infrastructure_error = infrastructure_error or 'CLIENT_CLEANUP_ERROR'
    usage = sdk.usage if sdk else []
    attempted, responses = (sdk.attempts, sdk.responses) if sdk else (0, 0)
    complete_cost = bool(sdk) and attempted == responses == len(usage) and all(u["cost_usd"] is not None and u["usage_complete"] for u in usage)
    counts = {field: sum(r[field] for r in results) for field in ("syntax_valid", "execution_success", "execution_accurate", "safety_rejected")}
    complete = not infrastructure_error and len(results) == len(selected) and not any(r["error_category"] in STOP_ERRORS for r in results)
    smoke_pass = False
    reasons = (["synthetic_provider"] if synthetic else []) + (["smoke_subset"] if mode == "smoke" else [])
    if not complete: reasons.append("partial_run")
    if not complete_cost: reasons.append("incomplete_cost")
    report = {"series_version": VERSION, "scope": "phase2_public_dev_diagnostic", "mode": mode, "condition": "E3",
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
              "smoke_case_repeated_in_suite_by_protocol": False, "case_results": results}
    write_new(output_path / "report.json", report)
    return report



def main():
    # This historical entrypoint has a v3 lock that does not cover the v4
    # controller. It must never be used to create a new paid attempt.
    raise GateError('HISTORICAL_ENTRYPOINT_RETIRED_USE_FINALIZATION_V4')
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--preflight-only',action='store_true')
    args=parser.parse_args()
    if args.preflight_only:
        preflight(SNAPSHOT,args.output,require_live=True)
        print(json.dumps({'preflight':'PASS','suite_ceiling_usd':preflight_bound()['suite_ceiling_usd']}))
        return 0
    report=run_suite(SNAPSHOT,args.output,production_client)
    print(json.dumps({k:report[k] for k in ('status','counts','attempted_calls','response_count','db_calls','observed_cost_usd','cost_complete')}))
    return 0 if report['status']=='complete' else 1


if __name__=='__main__':
    try:
        raise SystemExit(main())
    except GateError as error:
        print(json.dumps({'gate':'FAIL','error_category':str(error)}))
        raise SystemExit(1) from None
