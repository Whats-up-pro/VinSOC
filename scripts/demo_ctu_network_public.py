"""Run a read-only CTU-13 network investigation rehearsal from the locked snapshot."""

from __future__ import annotations

import json
from datetime import timedelta
from pathlib import Path
from time import perf_counter
from typing import Any

from agent.orchestrator import InvestigationOrchestrator
from evaluation.ctu_network_public.contract import LOCK, validate
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


def main() -> int:
    import argparse

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--snapshot", type=Path, required=True)
    parser.add_argument("--scenario", choices=("botnet", "normal", "no_evidence"), required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    scenario = select_scenario(args.snapshot, args.scenario)
    result = run_offline_demo(args.snapshot, scenario)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, sort_keys=True, indent=2, default=str) + "\n", encoding="utf-8")
    print(json.dumps({"scenario": args.scenario, "evidence_ids": result["evidence_ids"], "latency_ms": result["latency_ms"]}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
