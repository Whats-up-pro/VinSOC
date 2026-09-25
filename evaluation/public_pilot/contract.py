"""Versioned, source-grounded public_dev contract for both pilot tracks."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

from evaluation.text_to_sql import SQLBenchmarkCase, evaluate_sql_case
from evaluation.text_to_sql_snapshot import sha256_file
from evaluation.tool_calling.models import ToolCallCase
from scripts.build_r2_public_pilot import logical_content_hash
from scripts.build_vinsoc_public_snapshot import _load_dataset_manifest, _validate_sources
from vinsoc_data.duckdb_store import DuckDBSnapshot


ROOT = Path("evaluation/public_pilot")
R1 = ROOT / "r1/public_dev"
R2 = ROOT / "r2/public_dev"
SCORER_FILES = (
    "agent/tools.py",
    "evaluation/public_pilot/contract.py",
    "evaluation/public_pilot/run_model.py",
    "evaluation/tool_calling/arguments.py",
    "evaluation/tool_calling/decision_runner.py",
    "evaluation/tool_calling/matching.py",
    "evaluation/tool_calling/metrics.py",
    "evaluation/tool_calling/models.py",
    "evaluation/text_to_sql.py",
    "vinsoc_data/duckdb_store.py",
    "scripts/build_r2_public_pilot.py",
    "scripts/fetch_r2_public_pilot_sources.py",
)


def canonical_sha256(value: Any) -> str:
    payload = json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":"), default=str)
    return hashlib.sha256(payload.encode()).hexdigest()


def split_data(directory: Path) -> dict[str, Any]:
    return {path.name: json.loads(path.read_text(encoding="utf-8"))
            for path in sorted(directory.glob("*.json"))}


def verify_locked_files(directory: Path, expected_sha256: str) -> dict[str, Any]:
    files = split_data(directory)
    if canonical_sha256(files) != expected_sha256:
        raise ValueError(f"split hash mismatch: {directory}")
    return files


def build_lock(snapshot: Path) -> dict[str, Any]:
    sources = _load_dataset_manifest(ROOT / "dataset_manifest.json")
    _validate_sources(sources)
    counts, content_hash = logical_content_hash(snapshot)
    return {
        "version": "r1_r2_network_endpoint_public_dev_v1",
        "source_file_sha256": {s["dataset_id"]: s["file_sha256"] for s in sources},
        "snapshot_content_sha256": content_hash,
        "row_counts": counts,
        "r1_case_count": 20,
        "r2_case_count": 8,
        "r1_split_sha256": canonical_sha256(split_data(R1)),
        "r2_split_sha256": canonical_sha256(split_data(R2)),
        "scorer_file_sha256": {p: sha256_file(Path(p)) for p in SCORER_FILES},
    }


def validate(snapshot: Path, lock_path: Path = ROOT / "VERSION.lock") -> dict[str, Any]:
    lock = json.loads(lock_path.read_text(encoding="utf-8"))
    if lock != build_lock(snapshot):
        raise ValueError("Pilot source, snapshot, split or scorer lock mismatch")
    r1 = verify_locked_files(R1, lock["r1_split_sha256"])
    r2 = verify_locked_files(R2, lock["r2_split_sha256"])
    if len(r1) != len({c["case_id"] for c in r1.values()}):
        raise ValueError("R1 requires 20 distinct case IDs")
    if len(r1) != 20 or sorted(c["case_id"] for c in r1.values()) != [f"public_r1_{i:03d}" for i in range(1, 21)]:
        raise ValueError("R1 public_dev case IDs mismatch")
    if len(r2) != 8 or sorted(c["case_id"] for c in r2.values()) != [f"public_sql_{i:03d}" for i in range(1, 9)]:
        raise ValueError("R2 public_dev case IDs mismatch")
    if [sum(c["category"] == cat for c in r1.values()) for cat in ("network_only", "endpoint_only", "no_tool")] != [8, 8, 4]:
        raise ValueError("R1 case categories mismatch")
    snapshot_reader = DuckDBSnapshot(snapshot)
    import duckdb

    with duckdb.connect(str(snapshot), read_only=True) as conn:
        names = {row[0] for row in conn.execute("SHOW TABLES").fetchall()}
        if names != {"dataset_provenance", "network_flows", "sysmon_process_events"}:
            raise ValueError("Pilot snapshot must have network and Sysmon only")
        for raw in r1.values():
            case = ToolCallCase.from_dict(raw)
            if any(c.tool == "cti_enrichment" for c in case.expected_calls):
                raise ValueError(f"CTI is not verified: {case.case_id}")
            evidence = raw.get("evidence")
            if not case.expected_calls:
                if evidence is not None:
                    raise ValueError("No-tool case may not have fabricated evidence")
                continue
            if not evidence or evidence.get("table") not in {"network_flows", "sysmon_process_events"}:
                raise ValueError(f"Evidence missing: {case.case_id}")
            table = evidence["table"]
            cursor = conn.execute(
                f"SELECT * FROM {table} WHERE source_dataset=? AND source_row_id=?",
                [evidence["source_dataset"], evidence["source_row_id"]],
            )
            values = cursor.fetchone()
            if values is None:
                raise ValueError(f"Evidence row missing: {case.case_id}")
            row = {key: value.isoformat() if hasattr(value, "isoformat") else value
                   for (key, *_), value in zip(cursor.description, values)}
            if canonical_sha256(row) != evidence["normalized_row_sha256"]:
                raise ValueError(f"Evidence row changed: {case.case_id}")
            arguments = case.expected_calls[0].required_arguments
            if (table == "network_flows" and arguments["indicator"] != row["dst_ip"]) or (
                table == "sysmon_process_events" and arguments["host"].lower() != row["host"].lower()
            ):
                raise ValueError(f"Gold argument does not address evidence: {case.case_id}")
    gold_results: dict[str, Any] = {}
    for raw in r2.values():
        case = SQLBenchmarkCase.from_dict(raw)
        if case.database_snapshot != str(snapshot):
            raise ValueError(f"Snapshot path mismatch in gold: {case.case_id}")
        summaries = []
        for sql in case.gold_sql:
            evaluation = evaluate_sql_case(case, sql, snapshot_reader)
            if not evaluation.execution_accurate:
                raise ValueError(f"Gold SQL failed: {case.case_id}: {evaluation.error}")
            query = snapshot_reader.query(sql)
            if query.truncated:
                raise ValueError(f"Gold SQL was truncated: {case.case_id}")
            summaries.append({"row_count": len(query.rows), "result_sha256": canonical_sha256(query.rows)})
        gold_results[case.case_id] = summaries
    return {"version": lock["version"], "r1_ids": [c["case_id"] for c in r1.values()],
            "r2_ids": [c["case_id"] for c in r2.values()], "gold_results": gold_results,
            "snapshot_content_sha256": lock["snapshot_content_sha256"]}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--snapshot", type=Path, required=True)
    parser.add_argument("--write-lock", action="store_true")
    args = parser.parse_args()
    if args.write_lock:
        lock = build_lock(args.snapshot)
        path = ROOT / "VERSION.lock"
        path.write_text(json.dumps(lock, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(validate(args.snapshot), sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
