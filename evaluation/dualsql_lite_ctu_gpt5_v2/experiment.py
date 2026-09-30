"""v2 experiment - separate from v1, uses v2 prompts and runner."""

from __future__ import annotations

import json
import hashlib
import subprocess
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from evaluation.dualsql_lite_ctu_gpt5_v2.prompts import (
    GENERATOR_PROMPT_VERSION, LINKER_PROMPT_VERSION,
)
from evaluation.dualsql_lite_ctu_gpt5_v2.runner import run_case, MODEL, CAP, REASONING_EFFORT, MAX_TURNS, MAX_DB_CALLS, CONTROLLER_VERSION
from evaluation.dualsql_lite_ctu_gpt5_v2.tools import V2DatabaseTools, TOOL_VERSION
from evaluation.text_to_sql import SQLBenchmarkCase

CONDITIONS = ["E0", "E1", "E2", "E3"]
SERIES_VERSION = "dualsql_lite_ctu_gpt5_v2_remediation_v1"


def create_client():
    """No live client until a separate paid plan implements every pre-run gate."""
    raise RuntimeError("PAID_EXECUTION_DISABLED")


def load_cases(cases_dir: Path) -> list[SQLBenchmarkCase]:
    """Load cases from directory."""
    from evaluation.ctu_network_public.contract import CASES
    if cases_dir.resolve() != CASES.resolve():
        raise ValueError("DEV_CASE_DIRECTORY_MISMATCH")
    cases = []
    for path in sorted(cases_dir.glob("*.json")):
        with open(path) as f:
            data = json.load(f)
        cases.append(SQLBenchmarkCase.from_dict(data))
    return cases


def verify_dev_inputs(cases: list[SQLBenchmarkCase], snapshot_path: Path, manifest_path: Path) -> dict[str, Any]:
    from dataclasses import asdict
    from evaluation.ctu_network_public.contract import CASES, split_data, validate
    raw = split_data(CASES)
    expected = [SQLBenchmarkCase.from_dict(v) for v in raw.values()]
    if (len(cases) != len(expected) or len({c.case_id for c in cases}) != len(cases)
            or sorted((asdict(c) for c in cases), key=lambda c: c["case_id"])
            != sorted((asdict(c) for c in expected), key=lambda c: c["case_id"])):
        raise ValueError("DEV_CASE_IDENTITY_MISMATCH")
    return validate(snapshot_path, manifest_path=manifest_path)


def score_record(case: SQLBenchmarkCase, record: dict[str, Any], snapshot) -> None:
    """Only the locked evaluator supplies score flags; diagnostics do not alter them."""
    from evaluation.text_to_sql import evaluate_sql_case
    result = evaluate_sql_case(case, record.get("final_sql") or "", snapshot)
    for field in ("syntax_valid", "execution_success", "execution_accurate", "safety_rejected"):
        record[field] = getattr(result, field)
    if record.get("error_category") == "OK":
        record["error_category"] = ("SYNTAX_ERROR" if not result.syntax_valid else
                                    "SAFETY_REJECTION" if result.safety_rejected else
                                    "EXECUTION_ERROR" if not result.execution_success else
                                    "RESULT_MISMATCH" if not result.execution_accurate else "OK")
    # Do not serialize DuckDB/provider exception strings from the evaluator.


def _sha(value: Any) -> str:
    if isinstance(value, Path):
        data = value.read_bytes()
    else:
        data = json.dumps(value, sort_keys=True, ensure_ascii=False, default=str).encode("utf-8")
    return hashlib.sha256(data).hexdigest()


def _identity(snapshot_path: Path, manifest_path: Path, cases_dir: Path, verified: dict) -> dict[str, Any]:
    from evaluation.ctu_network_public.contract import SCORER_FILES, portable_text_sha256
    from evaluation.dualsql_lite_ctu_gpt5_v2.tools import TOOL_SCHEMAS
    package = Path(__file__).parent
    return {
        "git_sha": subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip(),
        "dirty_state": bool(subprocess.check_output(["git", "status", "--porcelain", "--untracked-files=no"], text=True).strip()),
        "verification_time_utc": datetime.now(timezone.utc).isoformat(),
        "case_file_sha256": {p.name: _sha(p) for p in sorted(cases_dir.glob("*.json"))},
        "snapshot_sha256": _sha(snapshot_path),
        "logical_snapshot_sha256": verified["logical_snapshot_sha256"],
        "manifest_sha256": _sha(manifest_path),
        "sources": verified["source_file_sha256"],
        "scorer_builder_sha256": {p: portable_text_sha256(Path(p)) for p in SCORER_FILES},
        "prompt_sha256": {"file": portable_text_sha256(package / "prompts.py")},
        "tool_schema_sha256": _sha(TOOL_SCHEMAS),
        "tool_implementation_sha256": {name: portable_text_sha256(package / name) for name in ("source_tools.py", "tools.py", "agents.py", "runner.py", "experiment.py")},
        "controller_version": CONTROLLER_VERSION, "tool_version": TOOL_VERSION,
        "request_contract": {"model": MODEL, "reasoning_effort": REASONING_EFFORT,
                             "max_completion_tokens": CAP, "sdk_retries": 0,
                             "temperature_key_present": False, "no_tool_key_omitted": True,
                             "max_role_turns": MAX_TURNS, "max_role_database_calls": MAX_DB_CALLS},
        "pricing_usd_per_million": {"input": .25, "output": 2.0},
        "provenance_scope": "current offline execution only; not historical run backfill",
    }


def build_report_identity(snapshot_path: Path, manifest_path: Path, cases_dir: Path) -> dict[str, Any]:
    from evaluation.ctu_network_public.contract import CASES, validate
    if cases_dir.resolve() != CASES.resolve():
        raise ValueError("DEV_CASE_DIRECTORY_MISMATCH")
    verified = validate(snapshot_path, manifest_path=manifest_path, cases_dir=cases_dir)
    return _identity(snapshot_path, manifest_path, cases_dir, verified)


def run_condition(condition: str, cases: list[SQLBenchmarkCase], snapshot_path: Path,
                  client: Any, output_dir: Path, manifest_path: Path) -> dict[str, Any]:
    from evaluation.ctu_network_public.contract import CASES
    from evaluation.dualsql_lite_ctu_gpt5.tools import SnapshotOnlyDuckDBSnapshot
    from openai import OpenAI, AsyncOpenAI
    # This entrypoint accepts injected offline providers only. Live creation is closed.
    if isinstance(client, (OpenAI, AsyncOpenAI)):
        raise RuntimeError("PAID_EXECUTION_DISABLED")
    if condition not in CONDITIONS:
        raise ValueError("INVALID_CONDITION")
    if output_dir.exists():
        raise FileExistsError("OUTPUT_EXISTS")
    ids = [c.case_id for c in cases]
    if not ids or len(ids) != len(set(ids)):
        raise ValueError("DEV_CASE_IDENTITY_MISMATCH")
    verified = verify_dev_inputs(cases, snapshot_path, manifest_path)
    identity = _identity(snapshot_path, manifest_path, CASES, verified)
    identity["case_hashes"] = {c.case_id: _sha(asdict(c)) for c in cases}
    tools = V2DatabaseTools(snapshot_path, manifest_path)
    identity["schema_sha256"] = _sha(tools.schema)
    identity["catalog_sha256"] = tools.catalog_sha256
    snapshot = SnapshotOnlyDuckDBSnapshot(snapshot_path)
    output_dir.mkdir(parents=True, exist_ok=False)
    results = []
    reasons = ["synthetic_provider"]
    if identity["dirty_state"]:
        reasons.append("dirty_implementation")
    invalidating = {"PROVIDER_ERROR", "MODEL_IDENTITY_MISMATCH", "USAGE_INCOMPLETE", "RESPONSE_ID_MISSING", "TELEMETRY_WRITE_ERROR"}
    with (output_dir / "partial.jsonl").open("x", encoding="utf-8") as partial:
        def append(event):
            partial.write(json.dumps(event, default=str, sort_keys=True) + "\n")
            partial.flush()
        append({"event": "identity", "identity": identity, "condition": condition})
        for case in cases:
            def sink(request, telemetry):
                append({"event": "response", "case_id": case.case_id,
                        "request_sha256": _sha(request), "telemetry": telemetry})
            record = run_case(case, condition, tools, client, tools.schema_context(), telemetry_sink=sink)
            score_record(case, record, snapshot)
            results.append(record)
            append({"event": "case", "record": record})
            with (output_dir / f"{case.case_id}.json").open("x", encoding="utf-8") as stream:
                json.dump(record, stream, indent=2, default=str)
                stream.write("\n")
            if record["error_category"] in invalidating:
                reasons.append(record["error_category"])
                break
    usage = [u for r in results for u in r["usage"]]
    attempted = sum(r["attempted_calls"] for r in results)
    cost_complete = attempted == len(usage) and all(u["cost_usd"] is not None and u["usage_complete"] for u in usage)
    counts = {field: sum(r[field] for r in results) for field in
              ("syntax_valid", "execution_success", "execution_accurate", "safety_rejected")}
    report = {"series_version": SERIES_VERSION, "condition": condition, "identity": identity,
              "case_count": len(cases), "completed_case_count": len(results), "case_ids": ids,
              "missing_case_ids": [i for i in ids if i not in {r["case_id"] for r in results}],
              "status": "partial" if any(r in invalidating for r in reasons) else "complete",
              "official_eligible": False, "eligibility_reasons": reasons,
              "counts": counts, "rates": {k: n / len(cases) for k, n in counts.items()},
              "attempted_calls": attempted, "response_count": len(usage),
              "input_tokens": sum(u["input_tokens"] for u in usage if type(u["input_tokens"]) is int and u["input_tokens"] >= 0),
              "output_tokens": sum(u["output_tokens"] for u in usage if type(u["output_tokens"]) is int and u["output_tokens"] >= 0),
              "latency_ms": sum(u["latency_ms"] for u in usage),
              "observed_cost_usd": sum(r["observed_cost_usd"] for r in results),
              "cost_complete": cost_complete, "cost_unknown": not cost_complete, "case_results": results}
    with (output_dir / "report.json").open("x", encoding="utf-8") as stream:
        json.dump(report, stream, indent=2, default=str)
        stream.write("\n")
    return report


def main():
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--condition", required=True, choices=CONDITIONS)
    parser.add_argument("--snapshot", type=Path, required=True)
    parser.add_argument("--cases-dir", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--api-key", default=None)
    args = parser.parse_args()

    create_client()


if __name__ == "__main__":
    main()
