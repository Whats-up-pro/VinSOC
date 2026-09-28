"""Run a read-only CTU-13 network investigation rehearsal from the locked snapshot."""

from __future__ import annotations

import json
import os
from datetime import timedelta
from pathlib import Path
from time import perf_counter
from typing import Any

from agent.orchestrator import InvestigationOrchestrator
from evaluation.ctu_network_public.contract import LOCK, validate
from evaluation.ctu_network_public.run_model import CAP, MODEL, cost_usd
from agent.tools import get_tool_schemas
from vinsoc_data.duckdb_store import DuckDBSnapshot


def _as_iso(value: Any) -> str:
    return value.isoformat() if hasattr(value, "isoformat") else str(value)


def select_scenario(snapshot_path: Path, name: str) -> dict[str, Any]:
    snapshot = DuckDBSnapshot(snapshot_path)
    if name == "no_evidence":
        return {
            "name": name,
            "indicator": "203.0.113.99",
            "label": None,
            "time_range": {"start": "2011-08-15T00:00:00", "end": "2011-08-16T00:00:00"},
        }
    label_filter = "%botnet%" if name == "botnet" else "%normal%"
    result = snapshot.query(
        "SELECT source_dataset, source_row_id, event_time, src_ip, label FROM network_flows "
        "WHERE lower(label) LIKE ? AND src_ip IS NOT NULL "
        "ORDER BY event_time, source_dataset, source_row_id LIMIT 1",
        [label_filter],
    )
    if not result.rows:
        raise ValueError(f"No CTU flow available for demo scenario: {name}")
    row = result.rows[0]
    event_time = row["event_time"]
    return {
        "name": name,
        "indicator": row["src_ip"],
        "label": "Botnet" if name == "botnet" else "Normal",
        "seed_source_dataset": row["source_dataset"],
        "seed_source_row_id": row["source_row_id"],
        "time_range": {
            "start": _as_iso(event_time - timedelta(minutes=1)),
            "end": _as_iso(event_time + timedelta(minutes=1)),
        },
    }
def _verify_evidence_pairs(snapshot: DuckDBSnapshot, evidence: list[dict[str, Any]]) -> None:
    for item in evidence:
        for record in item.get("provenance", {}).get("source_records", []):
            verified = snapshot.query(
                "SELECT count(*) AS matched FROM network_flows WHERE source_dataset = ? AND source_row_id = ?",
                [record["source_dataset"], record["source_row_id"]],
            )
            if verified.rows[0]["matched"] != 1:
                raise ValueError("Evidence source pair cannot be re-verified in the locked snapshot")


def run_offline_demo(snapshot_path: Path, scenario: dict[str, Any]) -> dict[str, Any]:
    """Execute only production ``network_investigation`` through the orchestrator."""
    snapshot_path = Path(snapshot_path)
    lock = validate(snapshot_path, LOCK)
    started = perf_counter()
    orchestrator = InvestigationOrchestrator(max_steps=1, duckdb_snapshot_path=str(snapshot_path))
    orchestrator.case_id = f"ctu_{scenario['name']}_rehearsal"
    orchestrator.evidence_store.clear()
    orchestrator.messages = []
    orchestrator.investigation_active = True
    arguments = {
        "indicator": scenario["indicator"],
        "indicator_type": "ipv4",
        "time_range": scenario["time_range"],
    }


    orchestrator._execute_tool_call({"id": "ctu_network_1", "name": "network_investigation", "arguments": arguments})
    all_evidence = [item.to_dict() for item in orchestrator.evidence_store.get_all_evidence()]
    evidence = [item for item in all_evidence if item.get("provenance", {}).get("source_records")]
    snapshot = DuckDBSnapshot(snapshot_path)
    _verify_evidence_pairs(snapshot, evidence)
    limitations = [
        "CTU-only snapshot has no CTI table; no CTI verification was performed.",
        "CTU-only snapshot has no endpoint telemetry; no endpoint verification was performed.",
        "The investigation used a fixed production network_investigation call; no model-generated SQL was executed.",
    ]
    if not evidence:
        limitations.insert(0, "No matching network telemetry")
        assessment = "Evidence gap: the selected historical network query returned no observed flow evidence."
    else:
        assessment = (
            "Observed network-flow evidence was retrieved and re-verified by source dataset and row ID. "
            "The CTU scenario label is retained as evaluation ground truth only; network evidence alone does not "
            "establish CTI or endpoint verification."
        )
    return {
        "demo_mode": "offline_rehearsal",
        "version": lock["version"],
        "snapshot_logical_sha256": lock["logical_snapshot_sha256"],
        "scenario": scenario,
        "tool_allowlist": ["network_investigation"],
        "tool_trace": [item.to_dict() for item in orchestrator.evidence_store.get_all_tool_calls()],
        "evidence": evidence,
        "evidence_ids": [item["evidence_id"] for item in evidence],
        "assessment": assessment,
        "limitations": limitations,
        "latency_ms": round((perf_counter() - started) * 1000, 3),
        "usage": {"attempted_calls": 0, "input_tokens": 0, "output_tokens": 0},
        "cost_usd": 0.0,
    }


def _write_report(path: Path, report: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(report, sort_keys=True, indent=2, default=str) + "\n", encoding="utf-8")
    os.replace(temporary, path)


def run_live_demo(snapshot_path: Path, output: Path, *, client: Any) -> dict[str, Any]:
    """Measure model tool selection, then run a fixed network lookup for each scenario."""
    scenarios = [select_scenario(snapshot_path, name) for name in ("botnet", "normal")]
    tools = [item for item in get_tool_schemas() if item["function"]["name"] == "network_investigation"]
    requests = [{"model": MODEL, "temperature": 0, "max_completion_tokens": CAP, "tools": tools,
                 "messages": [{"role": "system", "content": "Use only the supplied network tool. Never generate SQL."},
                              {"role": "user", "content": f"Investigate {item['indicator']} from {item['time_range']['start']} to {item['time_range']['end']}."}]} for item in scenarios]
    bounds = [cost_usd(len(json.dumps(item, separators=(",", ":")).encode()) + 4096, CAP) for item in requests]
    report: dict[str, Any] = {"demo_mode": "live", "model": MODEL, "temperature": 0, "max_completion_tokens": CAP,
        "max_retries": 0, "tool_allowlist": ["network_investigation"], "r2_known_cost_usd": 0.0008788,
        "combined_ceiling_usd": 0.0008788 + sum(bounds), "attempted_calls": 0, "responses_received": 0,
        "known_cost_usd": 0.0, "cost_unknown": False, "scenarios": [],
        "execution_semantics": {
            "model_role": "network_tool_selection_only",
            "tool_arguments_source": "preselected_scenario",
            "model_generated_arguments_executed": False,
            "assessment_source": "deterministic_template",
            "model_generated_assessment": False,
        }}
    if report["combined_ceiling_usd"] >= 1.0:
        raise ValueError("Combined R2 and live-demo budget ceiling exceeds $1.00")
    _write_report(output, report)
    for index, (scenario, request) in enumerate(zip(scenarios, requests)):
        if 0.0008788 + report["known_cost_usd"] + sum(bounds[index:]) >= 1.0:
            report["status"] = "budget_stopped"; _write_report(output, report); raise ValueError("Live demo budget stopped")
        report["attempted_calls"] += 1; _write_report(output, report)
        try:
            response = client.chat.completions.create(**request)
            report["responses_received"] += 1
            usage = response.usage
            if response.model != MODEL or type(usage.prompt_tokens) is not int or type(usage.completion_tokens) is not int:
                raise ValueError("Live response model or usage is invalid")
            charged = cost_usd(usage.prompt_tokens, usage.completion_tokens)
            report["known_cost_usd"] += charged
            calls = getattr(response.choices[0].message, "tool_calls", None) or []
            requested = any(call.function.name == "network_investigation" for call in calls)
            if requested:
                replay = run_offline_demo(snapshot_path, scenario)
                result = {key: replay[key] for key in ("tool_trace", "evidence", "evidence_ids", "assessment", "limitations")}
            else:
                result = {"tool_trace": [], "evidence": [], "evidence_ids": [],
                          "assessment": "Evidence gap: model did not request the allowed network tool.",
                          "limitations": ["No network evidence was collected.", "CTI and endpoint tools were unavailable by policy."]}
            report["scenarios"].append({"scenario": scenario["name"], "network_tool_requested": requested,
                "actual_model": response.model, "input_tokens": usage.prompt_tokens, "output_tokens": usage.completion_tokens,
                "cost_usd": charged, **result})
            _write_report(output, report)
        except Exception as exc:
            report.update({"status": "provider_or_validation_error", "cost_unknown": True,
                           "failure_category": type(exc).__name__})
            _write_report(output, report)
            raise
    report["status"] = "complete"; _write_report(output, report)
    return report


def main() -> int:
    import argparse

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--snapshot", type=Path, required=True)
    parser.add_argument("--scenario", choices=("botnet", "normal", "no_evidence"), required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--live", action="store_true")
    args = parser.parse_args()
    if args.live:
        if not os.environ.get("OPENAI_API_KEY") or os.environ.get("OPENAI_BASE_URL"):
            raise ValueError("Live demo requires OPENAI_API_KEY and prohibits OPENAI_BASE_URL")
        from openai import OpenAI
        result = run_live_demo(args.snapshot, args.output, client=OpenAI(api_key=os.environ["OPENAI_API_KEY"], timeout=60, max_retries=0))
        print(json.dumps({"status": result["status"], "attempted_calls": result["attempted_calls"], "known_cost_usd": result["known_cost_usd"]}, sort_keys=True))
    else:
        scenario = select_scenario(args.snapshot, args.scenario)
        result = run_offline_demo(args.snapshot, scenario)
        _write_report(args.output, result)
        print(json.dumps({"scenario": args.scenario, "evidence_ids": result["evidence_ids"], "latency_ms": result["latency_ms"]}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
