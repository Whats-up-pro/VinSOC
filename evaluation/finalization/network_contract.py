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
    """Compute logical content hash (row counts) and return (counts, sha256)."""
    import duckdb

    with duckdb.connect(str(snapshot), read_only=True) as conn:
        # Get row counts per source
        counts = dict(conn.execute(
            "SELECT source_dataset, count(*) FROM network_flows GROUP BY source_dataset"
        ).fetchall())
        # Canonical JSON
        content = json.dumps(counts, sort_keys=True, separators=(",", ":"))
        sha = hashlib.sha256(content.encode()).hexdigest()
        return counts, sha


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

    # Check 6: Logical content hash
    logical_counts, logical_sha = logical_content_hash(snapshot)
    result["checks"]["logical_counts"] = logical_counts
    result["checks"]["logical_sha256"] = logical_sha
    result["checks"]["logical_sha_matches_expected"] = logical_sha == EXPECTED_LOGICAL_SHA256

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

    with duckdb.connect(str(snapshot), read_only=True) as conn:
        if name == "botnet":
            # CTU S5: Botnet scenario from 2011-08-15
            row = conn.execute("""
                SELECT src_ip, min(event_time) as start_time, max(event_time) as end_time, label
                FROM network_flows
                WHERE source_dataset = 'ctu13_s5' AND label LIKE '%Botnet%'
                GROUP BY src_ip, label
                ORDER BY count(*) DESC
                LIMIT 1
            """).fetchone()

            if not row:
                raise ValueError("No botnet scenario found in snapshot")

            return {
                "name": "botnet",
                "indicator": row[0],
                "time_range": {
                    "start": row[1].isoformat(),
                    "end": row[2].isoformat(),
                },
                "label": row[3],
                "source_dataset": "ctu13_s5",
            }

        elif name == "normal":
            # CTU S7: Normal traffic scenario from 2011-08-16
            row = conn.execute("""
                SELECT src_ip, min(event_time) as start_time, max(event_time) as end_time, label
                FROM network_flows
                WHERE source_dataset = 'ctu13_s7' AND label LIKE '%Normal%'
                GROUP BY src_ip, label
                ORDER BY count(*) DESC
                LIMIT 1
            """).fetchone()

            if not row:
                raise ValueError("No normal scenario found in snapshot")

            return {
                "name": "normal",
                "indicator": row[0],
                "time_range": {
                    "start": row[1].isoformat(),
                    "end": row[2].isoformat(),
                },
                "label": row[3],
                "source_dataset": "ctu13_s7",
            }

        else:
            raise ValueError(f"Unknown scenario: {name}")


def verify_evidence_pairs(snapshot: Path, evidence: list[dict[str, Any]]) -> dict[str, Any]:
    """
    Independently verify evidence against the snapshot.

    Args:
        snapshot: Path to DuckDB snapshot
        evidence: List of evidence dicts with source_records

    Returns:
        Verification result dict
    """
    import duckdb

    result = {
        "verified": True,
        "issues": [],
        "checked": 0,
    }

    with duckdb.connect(str(snapshot), read_only=True) as conn:
        for ev in evidence:
            ev_id = ev.get("evidence_id", "unknown")
            source_records = ev.get("provenance", {}).get("source_records", [])

            for record in source_records:
                source_dataset = record.get("source_dataset")
                source_row_id = record.get("source_row_id")

                if not source_dataset or not source_row_id:
                    continue

                # Verify the record exists in snapshot
                exists = conn.execute("""
                    SELECT 1 FROM network_flows
                    WHERE source_dataset = ? AND source_row_id = ?
                """, [source_dataset, source_row_id]).fetchone()

                result["checked"] += 1

                if not exists:
                    result["verified"] = False
                    result["issues"].append(
                        f"Evidence {ev_id}: record {source_dataset}:{source_row_id} not found"
                    )

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
