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


def build_lock(snapshot: Path, output_path: Path | None = None) -> dict[str, Any]:
    """
    Build a contract lock for the network E2E demo.

    Args:
        snapshot: Path to DuckDB snapshot
        output_path: Optional path to write lock file

    Returns:
        Lock dict
    """
    # Get snapshot facts
    qualify = qualify_snapshot(snapshot)

    # Get scenario hashes
    scenarios = {}
    for name in ["botnet", "normal"]:
        try:
            scenario = select_scenario(snapshot, name)
            scenarios[name] = {
                "indicator": scenario["indicator"],
                "source_dataset": scenario["source_dataset"],
            }
        except ValueError:
            scenarios[name] = {"error": "not found"}

    # Build lock
    lock = {
        "version": VERSION,
        "contract_identity": "network_e2e_v1",
        "snapshot_binary_sha256": sha256_file(snapshot),
        "snapshot_logical_sha256": qualify["checks"]["logical_sha256"],
        "source_counts": qualify["checks"]["source_counts"],
        "distinct_pairs": qualify["checks"]["distinct_source_pairs"],
        "scenarios": scenarios,
        "policy_version": "network_e2e_policy_v1",
        "schema_hashes": {
            "network_skill": portable_text_sha256(Path("skills/network_skill.py")),
            "orchestrator": portable_text_sha256(Path("agent/orchestrator.py")),
        },
    }

    if output_path:
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(
            json.dumps(lock, indent=2, sort_keys=True),
            encoding="utf-8"
        )

    return lock


def validate_lock(snapshot: Path, lock: dict[str, Any]) -> dict[str, Any]:
    """
    Validate a lock against a snapshot.

    Args:
        snapshot: Path to DuckDB snapshot
        lock: Lock dict

    Returns:
        Validation result

    Raises:
        ValueError: If validation fails
    """
    result = {
        "valid": True,
        "issues": [],
    }

    # Check contract identity
    if lock.get("contract_identity") != "network_e2e_v1":
        result["valid"] = False
        result["issues"].append("Contract identity mismatch")

    # Check binary SHA
    actual_binary = sha256_file(snapshot)
    if lock.get("snapshot_binary_sha256") != actual_binary:
        result["valid"] = False
        result["issues"].append("Binary SHA mismatch")

    # Check logical SHA
    _, actual_logical = logical_content_hash(snapshot)
    if lock.get("snapshot_logical_sha256") != actual_logical:
        result["valid"] = False
        result["issues"].append("Logical SHA mismatch")

    return result
