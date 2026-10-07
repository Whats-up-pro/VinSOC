"""Network E2E demo contract for snapshot/scenario qualification.

This module provides:
- Snapshot logical verification
- Binary SHA verification
- Scenario selection and verification
- Contract lock generation
"""
from __future__ import annotations

import hashlib
import json
from datetime import timedelta
from pathlib import Path
from typing import Any

# Expected values for CTU public snapshot
EXPECTED_LOGICAL_SHA256 = "42c8e0a62441295cc5d95329a65dc22409c37de5b26a1e37dd56fbf0164a758c"
EXPECTED_SOURCE_COUNTS = {"ctu13_s5": 129831, "ctu13_s7": 114075}
EXPECTED_TABLES = {"dataset_provenance", "network_flows"}
EXPECTED_ROWS = 243906  # S5 + S7
EXPECTED_DISTINCT_PAIRS = 243906  # Distinct source_dataset:source_row_id

VERSION = "network_e2e_v1"
LOCK_PATH = Path("evaluation/finalization/NETWORK_E2E_v1.lock.json")


def sha256_file(path: Path) -> str:
    """Compute SHA256 of a file's binary content."""
    with open(path, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()


def portable_text_sha256(path: Path) -> str:
    """Hash tracked source text without checkout-specific line endings."""
    content = path.read_bytes().replace(b"\r\n", b"\n").replace(b"\r", b"\n")
    return hashlib.sha256(content).hexdigest()


def logical_content_hash(snapshot: Path) -> tuple[dict[str, int], str]:
    """Hash the canonical schemas and every logical row, not only row counts."""
    from scripts.build_ctu_network_public_snapshot import logical_content_hash as canonical_hash

    return canonical_hash(Path(snapshot))


def qualify_snapshot(snapshot: Path) -> dict[str, Any]:
    """
    Verify that snapshot meets demo qualification requirements.

    Args:
        snapshot: Path to DuckDB snapshot

    Returns:
        Dict with qualification results

    Raises:
        ValueError: If qualification fails
    """
    import duckdb

    result = {
        "snapshot_path": str(snapshot),
        "qualified": False,
        "checks": {},
    }

    # Check 1: Binary SHA
    binary_sha = sha256_file(snapshot)
    result["checks"]["binary_sha256"] = binary_sha
    result["checks"]["binary_sha_matches_lock"] = False  # Lock may not exist yet

    # Check 2: Tables
    with duckdb.connect(str(snapshot), read_only=True) as conn:
        tables = {row[0] for row in conn.execute("SHOW TABLES").fetchall()}
        result["checks"]["tables"] = sorted(tables)
        result["checks"]["tables_match"] = tables == EXPECTED_TABLES

        if tables != EXPECTED_TABLES:
            raise ValueError(f"Tables mismatch: {tables} vs {EXPECTED_TABLES}")

    # Check 3: Row counts
    with duckdb.connect(str(snapshot), read_only=True) as conn:
        counts = dict(conn.execute(
            "SELECT source_dataset, count(*) FROM network_flows GROUP BY source_dataset"
        ).fetchall())
        result["checks"]["source_counts"] = counts
        result["checks"]["counts_match"] = counts == EXPECTED_SOURCE_COUNTS

        if counts != EXPECTED_SOURCE_COUNTS:
            raise ValueError(f"Row counts mismatch: {counts} vs {EXPECTED_SOURCE_COUNTS}")

    # Check 4: Distinct source pairs
    with duckdb.connect(str(snapshot), read_only=True) as conn:
        distinct = conn.execute(
            "SELECT count(DISTINCT source_dataset || ':' || source_row_id) FROM network_flows"
        ).fetchone()[0]
        result["checks"]["distinct_source_pairs"] = distinct
        result["checks"]["distinct_match"] = distinct == EXPECTED_DISTINCT_PAIRS

        if distinct != EXPECTED_DISTINCT_PAIRS:
            raise ValueError(f"Distinct pairs mismatch: {distinct} vs {EXPECTED_DISTINCT_PAIRS}")

    # Check 5: Dataset provenance
    with duckdb.connect(str(snapshot), read_only=True) as conn:
        provenance_count = conn.execute(
            "SELECT count(*) FROM dataset_provenance"
        ).fetchone()[0]
        result["checks"]["provenance_count"] = provenance_count
        result["checks"]["provenance_match"] = provenance_count == 2
        if provenance_count != 2:
            raise ValueError("Dataset provenance mismatch")

    # Check 6: Logical content hash
    logical_counts, logical_sha = logical_content_hash(snapshot)
    result["checks"]["logical_counts"] = logical_counts
    result["checks"]["logical_sha256"] = logical_sha
    result["checks"]["logical_sha_matches_expected"] = logical_sha == EXPECTED_LOGICAL_SHA256
    if logical_sha != EXPECTED_LOGICAL_SHA256:
        raise ValueError("Logical content hash mismatch")

    # Check 7: Open read-only
    try:
        with duckdb.connect(str(snapshot), read_only=True) as conn:
            conn.execute("SELECT 1").fetchone()
        result["checks"]["read_only_ok"] = True
    except Exception as e:
        result["checks"]["read_only_ok"] = False
        result["checks"]["read_only_error"] = str(e)
        raise ValueError(f"Snapshot not readable read-only: {e}")

    result["qualified"] = (
        result["checks"]["tables_match"]
        and result["checks"]["counts_match"]
        and result["checks"]["distinct_match"]
        and result["checks"]["provenance_match"]
        and result["checks"]["logical_sha_matches_expected"]
        and result["checks"]["read_only_ok"]
    )

    return result


def select_scenario(snapshot: Path, name: str) -> dict[str, Any]:
    """
    Select a scenario from the snapshot.

    Args:
        snapshot: Path to DuckDB snapshot
        name: Scenario name (botnet or normal)

    Returns:
        Scenario dict with indicator, time_range, and label
    """
    import duckdb

    config = {
        "botnet": ("ctu13_s5", "%botnet%", "Botnet"),
        "normal": ("ctu13_s7", "%normal%", "Normal"),
    }
    if name not in config:
        raise ValueError("Unknown scenario")
    source_dataset, label_filter, public_label = config[name]
    with duckdb.connect(str(snapshot), read_only=True) as conn:
        row = conn.execute(
            """
            SELECT source_row_id, event_time, src_ip
            FROM network_flows
            WHERE source_dataset = ? AND lower(label) LIKE ? AND src_ip IS NOT NULL
            ORDER BY event_time, source_dataset, source_row_id
            LIMIT 1
            """,
            [source_dataset, label_filter],
        ).fetchone()
    if not row:
        raise ValueError("Required scenario not found in snapshot")
    source_row_id, event_time, indicator = row
    return {
        "name": name,
        "indicator": indicator,
        "time_range": {
            "start": (event_time - timedelta(minutes=1)).isoformat(),
            "end": (event_time + timedelta(minutes=1)).isoformat(),
        },
        "label": public_label,
        "source_dataset": source_dataset,
        "seed_source_row_id": str(source_row_id),
        "seed_event_time": event_time.isoformat(),
    }


def _iso(value: Any) -> str | None:
    if value is None:
        return None
    return value.isoformat() if hasattr(value, "isoformat") else str(value)


def verify_network_evidence(
    snapshot: Path,
    arguments: dict[str, Any],
    evidence: list[dict[str, Any]],
) -> dict[str, Any]:
    """Recompute observed network facts from the scoped snapshot population."""
    import duckdb

    result = {
        "verified": True,
        "issues": [],
        "checked_source_pairs": 0,
        "checked_aggregates": 0,
    }
    indicator = arguments.get("indicator")
    time_range = arguments.get("time_range") or {}
    start = time_range.get("start")
    end = time_range.get("end")
    if arguments.get("indicator_type") != "ipv4" or not all(
        isinstance(value, str) and value for value in (indicator, start, end)
    ):
        return {**result, "verified": False, "issues": ["invalid_query_scope"]}

    with duckdb.connect(str(snapshot), read_only=True) as conn:
        for ev in evidence:
            if ev.get("evidence_class") != "OBSERVED" or ev.get("type") != "network_flow_aggregate":
                continue
            data = ev.get("data") if isinstance(ev.get("data"), dict) else {}
            source_records = ev.get("provenance", {}).get("source_records", [])
            if not isinstance(source_records, list) or not source_records:
                result["verified"] = False
                result["issues"].append("observed_evidence_missing_source_pairs")
                continue

            for record in source_records:
                if not isinstance(record, dict):
                    result["verified"] = False
                    result["issues"].append("invalid_source_pair")
                    continue
                source_dataset = record.get("source_dataset")
                source_row_id = record.get("source_row_id")
                if not isinstance(source_dataset, str) or not isinstance(source_row_id, str):
                    result["verified"] = False
                    result["issues"].append("invalid_source_pair")
                    continue
                row = conn.execute(
                    """
                    SELECT src_ip, dst_ip, dst_port, protocol
                    FROM network_flows
                    WHERE source_dataset = ? AND source_row_id = ?
                      AND event_time >= ? AND event_time <= ?
                      AND (src_ip = ? OR dst_ip = ?)
                    """,
                    [source_dataset, source_row_id, start, end, indicator, indicator],
                ).fetchone()
                result["checked_source_pairs"] += 1
                expected_group = (
                    data.get("src_ip"), data.get("dst_ip"), data.get("dst_port"), data.get("protocol")
                )
                if row is None or tuple(row) != expected_group:
                    result["verified"] = False
                    result["issues"].append("source_pair_outside_query_scope")

            aggregate = conn.execute(
                """
                SELECT count(*), min(event_time), max(event_time),
                       sum(COALESCE(bytes_out, 0)), sum(COALESCE(bytes_in, 0))
                FROM network_flows
                WHERE event_time >= ? AND event_time <= ?
                  AND (src_ip = ? OR dst_ip = ?)
                  AND src_ip = ? AND dst_ip = ?
                  AND dst_port IS NOT DISTINCT FROM ?
                  AND protocol IS NOT DISTINCT FROM ?
                """,
                [
                    start, end, indicator, indicator, data.get("src_ip"), data.get("dst_ip"),
                    data.get("dst_port"), data.get("protocol"),
                ],
            ).fetchone()
            result["checked_aggregates"] += 1
            actual = {
                "connection_count": aggregate[0],
                "first_seen": _iso(aggregate[1]),
                "last_seen": _iso(aggregate[2]),
                "bytes_src_to_dst": aggregate[3],
                "bytes_dst_to_src": aggregate[4],
            }
            expected = {key: data.get(key) for key in actual}
            source_event_count = ev.get("provenance", {}).get("source_event_count")
            if actual != expected or source_event_count != actual["connection_count"]:
                result["verified"] = False
                result["issues"].append("aggregate_fact_mismatch")

    if result["checked_source_pairs"] == 0 or result["checked_aggregates"] == 0:
        result["verified"] = False
        if not result["issues"]:
            result["issues"].append("no_observed_evidence_verified")

    result["issues"] = list(dict.fromkeys(result["issues"]))
    return result


def verify_evidence_pairs(snapshot: Path, evidence: list[dict[str, Any]]) -> dict[str, Any]:
    """Deprecated pair-only verifier retained for non-E2E compatibility."""
    import duckdb

    result = {"verified": True, "issues": [], "checked": 0}
    with duckdb.connect(str(snapshot), read_only=True) as conn:
        for item in evidence:
            for record in item.get("provenance", {}).get("source_records", []):
                row = conn.execute(
                    "SELECT 1 FROM network_flows WHERE source_dataset = ? AND source_row_id = ?",
                    [record.get("source_dataset"), record.get("source_row_id")],
                ).fetchone()
                result["checked"] += 1
                if row is None:
                    result["verified"] = False
                    result["issues"].append("source_pair_not_found")
    if result["checked"] == 0:
        result["verified"] = False
        result["issues"].append("no_source_pairs_verified")

    return result


def _canonical_sha256(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")).hexdigest()


def request_envelope() -> dict[str, Any]:
    """Application request limits, not a provider billing hard cap."""
    return {
        "model": "gpt-4.1-mini-2025-04-14", "temperature": 0,
        "max_completion_tokens": 1000, "max_retries": 0,
        "parallel_tool_calls": False, "tool_choice": "auto", "service_tier": "default",
        "response_format": {"type": "json_object"},
        "max_requests": 4, "max_steps_per_scenario": 2, "max_review_cycles": 0,
        "input_token_reserve": 50000, "output_token_reserve": 1000,
        "max_request_bytes": 45000, "frame_reserve_tokens": 512, "budget_usd": 0.25,
        "input_bound_method": "utf8_serialized_payload_bytes_plus_512_framing_tokens",
        "input_bound_assumption": "Each text BPE token consumes at least one UTF-8 byte; complete serialized payload includes tool/history metadata.",
    }


def valid_technical_receipt(receipt: Any, *, require_approval: bool = False) -> bool:
    """Structural/accounting/fact validation for saved review/viewer inputs.

    This checks the saved packet, not cryptographic authenticity or prose truth.
    It performs no database, SDK or model call.
    """
    import math
    import re
    def digest(value, length):
        return isinstance(value, str) and re.fullmatch(f"[0-9a-f]{{{length}}}", value) is not None
    def nonnegative(value):
        return type(value) in (int, float) and math.isfinite(value) and value >= 0
    try:
        if (type(receipt) is not dict or type(receipt.get("schema_version")) is not int
            or receipt["schema_version"] != 1 or not receipt.get("run_id")
            or not digest(receipt.get("implementation_sha"), 40)
            or receipt.get("scope") != "network_only_public_lifecycle_demo"
            or not digest(receipt["snapshot"].get("binary_sha256"), 64)
            or not digest(receipt["snapshot"].get("logical_sha256"), 64)
            or not digest(receipt["contract"].get("lock_sha256"), 64)):
            return False
        if any(type(receipt.get(key)) is not int or receipt[key] != 4 for key in (
            "attempted_calls", "responses_received", "valid_usage_records")):
            return False
        requests = receipt.get("requests")
        if not isinstance(requests, list) or len(requests) != 4:
            return False
        for call in requests:
            usage = call.get("usage")
            if (call.get("actual_model") != request_envelope()["model"] or not isinstance(usage, dict)
                or any(type(usage.get(field)) is not int or usage[field] < 0
                       for field in ("input_tokens", "output_tokens", "cached_tokens"))
                or usage["cached_tokens"] > usage["input_tokens"]
                or usage["output_tokens"] > 1000 or not nonnegative(call.get("cost_usd"))):
                return False
        costs = receipt["cost_summary"]
        if costs.get("cost_unknown") is not False or not nonnegative(costs.get("known_cost_usd")):
            return False
        if sum(call["cost_usd"] for call in requests) > costs["known_cost_usd"] + 1e-12:
            return False
        config = receipt["request_config"]
        if any(type(config.get(field)) is not type(value) or config[field] != value for field, value in (
            ("model", request_envelope()["model"]), ("max_completion_tokens", 1000), ("max_retries", 0))):
            return False
        scenarios = receipt.get("scenarios")
        if not isinstance(scenarios, list) or len(scenarios) != 2 or {s["name"] for s in scenarios} != {"botnet", "normal"}:
            return False
        for scenario in scenarios:
            validation = scenario["validation"]
            if (validation.get("technical_valid") is not True or validation.get("schema_valid") is not True
                or validation["policy"].get("valid") is not True
                or validation["independent_snapshot"].get("verified") is not True
                or scenario.get("termination") != "FINAL_ASSESSMENT"
                or not isinstance(scenario.get("assessment"), str) or not scenario["assessment"].strip()
                or len(scenario.get("tool_trace", [])) != 1
                or scenario["tool_trace"][0].get("tool") != "network_investigation"
                or scenario["tool_trace"][0].get("error")):
                return False
            evidence = {ev["evidence_id"]: ev for ev in scenario["evidence"]}
            ids = scenario["evidence_ids"]
            if not isinstance(ids, list) or not ids or any(eid not in evidence for eid in ids):
                return False
            fields = set()
            for obs in scenario["observations"]:
                value = evidence[obs["evidence_id"]]["data"][obs["field"]]
                if type(obs["value"]) is not type(value) or obs["value"] != value:
                    return False
                fields.add(obs["field"])
            if "connection_count" not in fields or not fields.intersection({"src_ip", "dst_ip", "dst_port", "protocol"}):
                return False
            for ev in evidence.values():
                if ev.get("evidence_class") == "OBSERVED" and not ev["provenance"].get("source_records"):
                    return False
                if ev.get("evidence_class") == "DERIVED" and (
                    not ev.get("related_evidence_ids") or any(parent not in evidence for parent in ev["related_evidence_ids"])):
                    return False
            if require_approval:
                review = scenario["human_review"]
                decisions = review.get("decisions")
                if (review.get("status") != "approved" or not isinstance(decisions, list) or not decisions
                    or decisions[-1].get("decision") != "APPROVE" or not decisions[-1].get("analyst")):
                    return False
        return True
    except (KeyError, TypeError, AttributeError, ValueError):
        return False


def qualify_demo(snapshot: Path) -> dict[str, Any]:
    """Public qualification interface for the pinned CTU S5/S7 demo."""
    return qualify_snapshot(snapshot)


def build_lock(snapshot: Path, output_path: Path | None = None) -> dict[str, Any]:
    """Create a release identity only from a qualified, read-only snapshot."""
    import duckdb
    from agent.network_investigation_policy import NetworkInvestigationPolicy

    if output_path is not None and Path(output_path).exists():
        raise FileExistsError("Refusing to overwrite an existing network contract lock")
    qualification = qualify_demo(snapshot)
    root = Path(__file__).resolve().parents[2]
    manifest_path = root / "evaluation/ctu_network_public/dataset_manifest.json"
    with duckdb.connect(str(snapshot), read_only=True) as conn:
        schema = {
            name: [[row[0], row[1]] for row in conn.execute(f'DESCRIBE "{name}"').fetchall()]
            for name in sorted(EXPECTED_TABLES)
        }
        sources = dict(conn.execute(
            "SELECT dataset_id, file_sha256 FROM dataset_provenance ORDER BY dataset_id"
        ).fetchall())
    paths = (
        "agent/investigation_policy.py", "agent/network_investigation_policy.py",
        "agent/orchestrator.py", "agent/provider.py", "agent/tools.py",
        "agent/evidence.py", "skills/network_skill.py",
        "agent/triage.py", "agent/hitl.py", "agent/runbooks.py",
        "skills/base.py", "skills/validators.py", "schemas/investigation_case.json",
        "schemas/network_result.json", "schemas/triage_result.json",
        "telemetry/network/base.py", "telemetry/network/models.py", "telemetry/network/query.py",
        "analytics/network/__init__.py", "scripts/build_ctu_network_public_snapshot.py",
        "vinsoc_data/network_source.py", "vinsoc_data/domain_queries.py",
        "vinsoc_data/duckdb_store.py", "analytics/network/scanning.py",
        "analytics/network/beaconing.py", "analytics/network/fanout.py", "analytics/network/transfer.py",
        "evaluation/finalization/live_window.py", "evaluation/finalization/network_contract.py",
        "scripts/demo_ctu_network_public_model_driven.py",
    )
    content_files = {path: portable_text_sha256(root / path) for path in paths}
    policy = NetworkInvestigationPolicy()
    scenarios = {name: select_scenario(snapshot, name) for name in ("botnet", "normal")}
    envelope = request_envelope()
    lock = {
        "schema_version": 1, "version": VERSION, "contract_identity": VERSION,
        "snapshot_binary_sha256": qualification["checks"]["binary_sha256"],
        "snapshot_logical_sha256": qualification["checks"]["logical_sha256"],
        "source_counts": qualification["checks"]["source_counts"],
        "distinct_pairs": qualification["checks"]["distinct_source_pairs"],
        "source_file_sha256": sources,
        "manifest_sha256": portable_text_sha256(manifest_path),
        "schema": schema, "schema_sha256": _canonical_sha256(schema),
        "scenarios": scenarios, "scenario_sha256": _canonical_sha256(scenarios),
        "policy_version": policy.VERSION,
        "policy_sha256": content_files["agent/network_investigation_policy.py"],
        "prompt_sha256": _canonical_sha256(policy.system_prompt()),
        "tool_schema_sha256": _canonical_sha256(policy.tool_schemas()),
        "request_envelope": envelope, "request_envelope_sha256": _canonical_sha256(envelope),
        "content_files": content_files,
    }
    lock["lock_sha256"] = _canonical_sha256(lock)
    if output_path is not None:
        target = Path(output_path)
        target.parent.mkdir(parents=True, exist_ok=True)
        with target.open("x", encoding="utf-8") as handle:
            handle.write(json.dumps(lock, indent=2, sort_keys=True) + "\n")
    return lock


def validate_lock(snapshot: Path, lock: dict[str, Any]) -> dict[str, Any]:
    """Every pinned field must still match data, scenario and executing code."""
    if not isinstance(lock, dict):
        return {"valid": False, "issues": ["invalid_lock"]}
    try:
        current = build_lock(snapshot)
    except Exception:
        return {"valid": False, "issues": ["snapshot_or_content_unavailable"]}
    issues = [field for field, value in current.items() if lock.get(field) != value]
    issues.extend(sorted(set(lock) - set(current)))
    return {"valid": not issues, "issues": issues}


def main() -> int:
    """Offline lock generation; never downloads data or constructs a client."""
    import argparse

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--snapshot", type=Path, required=True)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    try:
        if args.output:
            lock = build_lock(args.snapshot, args.output)
            print(json.dumps({"status": "locked", "lock_sha256": lock["lock_sha256"]}))
        else:
            result = qualify_demo(args.snapshot)
            print(json.dumps(result, default=str, sort_keys=True))
        return 0
    except Exception:
        print(json.dumps({"status": "blocked", "failure_category": "snapshot_or_contract_qualification_failed"}))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
