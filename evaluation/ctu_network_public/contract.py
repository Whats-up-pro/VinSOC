"""Locked contract for the CTU-only R2 public_dev pilot."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from evaluation.text_to_sql import SQLBenchmarkCase, evaluate_sql_case
from evaluation.text_to_sql_snapshot import sha256_file
from scripts.build_ctu_network_public_snapshot import SOURCE_IDS, TABLES, logical_content_hash
from scripts.build_vinsoc_public_snapshot import _load_dataset_manifest, _validate_sources
from vinsoc_data.duckdb_store import DuckDBSnapshot

ROOT = Path("evaluation/ctu_network_public")
CASES = ROOT / "dev"
MANIFEST = ROOT / "dataset_manifest.json"
LOCK = ROOT / "VERSION.lock"
VERSION = "ctu_network_public_dev_v1"
EXPECTED_COUNTS = {"ctu13_s5": 129831, "ctu13_s7": 114075}
SCORER_FILES = (
    "evaluation/text_to_sql.py",
    "evaluation/ctu_network_public/contract.py",
    "scripts/build_ctu_network_public_snapshot.py",
    "vinsoc_data/duckdb_store.py",
)


def canonical_sha256(value: Any) -> str:
    encoded = json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":"), default=str).encode()
    return hashlib.sha256(encoded).hexdigest()


def portable_text_sha256(path: Path) -> str:
    """Hash tracked source text without checkout-specific line endings."""
    content = path.read_bytes().replace(b"\r\n", b"\n").replace(b"\r", b"\n")
    return hashlib.sha256(content).hexdigest()


def split_data(directory: Path = CASES) -> dict[str, Any]:
    return {path.name: json.loads(path.read_text(encoding="utf-8")) for path in sorted(directory.glob("*.json"))}


def _snapshot_facts(snapshot: Path) -> dict[str, Any]:
    import duckdb

    with duckdb.connect(str(snapshot), read_only=True) as conn:
        tables = {row[0] for row in conn.execute("SHOW TABLES").fetchall()}
        schema = {
            table: [[row[1], row[2]] for row in conn.execute(f"PRAGMA table_info('{table}')").fetchall()]
            for table in sorted(tables)
        }
        counts = dict(conn.execute("SELECT source_dataset, count(*) FROM network_flows GROUP BY source_dataset").fetchall())
        distinct = conn.execute("SELECT count(DISTINCT source_dataset || ':' || source_row_id) FROM network_flows").fetchone()[0]
        provenance = conn.execute("SELECT count(*) FROM dataset_provenance").fetchone()[0]
    if tables != TABLES or counts != EXPECTED_COUNTS or distinct != sum(EXPECTED_COUNTS.values()) or provenance != 2:
        raise ValueError("CTU-only snapshot schema, provenance, row count, or row identity mismatch")
    logical_counts, logical_sha = logical_content_hash(snapshot)
    return {"tables": sorted(tables), "schema": schema, "source_row_counts": counts,
            "row_counts": logical_counts, "distinct_source_row_id": distinct,
            "logical_snapshot_sha256": logical_sha}


def _load_cases(directory: Path = CASES) -> tuple[dict[str, Any], list[SQLBenchmarkCase]]:
    raw = split_data(directory)
    cases = [SQLBenchmarkCase.from_dict(item) for item in raw.values()]
    expected = [f"ctu_sql_{index:03d}" for index in range(1, 9)]
    ids = [case.case_id for case in cases]
    if sorted(ids) != expected or len(ids) != len(set(ids)):
        raise ValueError("CTU-only split requires eight distinct pinned case IDs")
    return raw, cases


def semantic_counterexamples(snapshot: Path, cases: list[SQLBenchmarkCase]) -> dict[str, Any]:
    reader = DuckDBSnapshot(snapshot)
    by_id = {case.case_id: case for case in cases}
    wrong = {
        "distinct": ("ctu_sql_003", "SELECT count(dst_ip) AS destination_count FROM network_flows WHERE source_dataset = 'ctu13_s5'"),
        "time_boundary": ("ctu_sql_004", "SELECT count(*) AS flow_count FROM network_flows WHERE source_dataset = 'ctu13_s5' AND event_time > TIMESTAMP '2011-08-15 16:43:20.931208' AND event_time < TIMESTAMP '2011-08-15 16:43:20.931209'"),
        "boolean": ("ctu_sql_005", "SELECT count(*) AS flow_count FROM network_flows WHERE source_dataset = 'ctu13_s7' AND protocol = 'UDP' OR bytes_out > 0"),
        "ordering": ("ctu_sql_006", "SELECT dst_port, count(*) AS flow_count FROM network_flows WHERE source_dataset = 'ctu13_s5' GROUP BY dst_port ORDER BY flow_count ASC, dst_port DESC LIMIT 5"),
    }
    result = {}
    for name, (case_id, sql) in wrong.items():
        evaluation = evaluate_sql_case(by_id[case_id], sql, reader)
        if evaluation.execution_accurate or not evaluation.execution_success:
            raise ValueError(f"Semantic counterexample did not distinguish gold: {name}")
        result[name] = {"case_id": case_id, "different_from_gold": True}
    return result


def build_lock(snapshot: Path, manifest_path: Path = MANIFEST, cases_dir: Path = CASES) -> dict[str, Any]:
    sources = _load_dataset_manifest(manifest_path)
    _validate_sources(sources)
    if tuple(sorted(source["dataset_id"] for source in sources)) != SOURCE_IDS:
        raise ValueError("CTU-only manifest source IDs mismatch")
    raw, cases = _load_cases(cases_dir)
    reader = DuckDBSnapshot(snapshot)
    gold = {}
    for case in cases:
        query = reader.query(case.gold_sql[0])
        if query.truncated or not evaluate_sql_case(case, case.gold_sql[0], reader).execution_accurate:
            raise ValueError(f"Invalid or truncated gold SQL: {case.case_id}")
        rows = query.rows
        if case.result_comparator in {"unordered_rows", "multiset_rows"}:
            rows = sorted(rows, key=lambda row: json.dumps(row, sort_keys=True, default=str))
        gold[case.case_id] = {"row_count": len(rows), "result_sha256": canonical_sha256(rows)}
    facts = _snapshot_facts(snapshot)
    return {
        "version": VERSION,
        "source_file_sha256": {source["dataset_id"]: source["file_sha256"] for source in sources},
        "manifest_sha256": sha256_file(manifest_path),
        "builder_scorer_sha256": {path: portable_text_sha256(Path(path)) for path in SCORER_FILES},
        "case_ids": sorted(case.case_id for case in cases),
        "split_sha256": canonical_sha256(raw),
        **facts,
        "gold_results": gold,
        "semantic_counterexamples": semantic_counterexamples(snapshot, cases),
    }


def validate(snapshot: Path, lock_path: Path = LOCK, manifest_path: Path = MANIFEST, cases_dir: Path = CASES) -> dict[str, Any]:
    expected = json.loads(lock_path.read_text(encoding="utf-8"))
    actual = build_lock(snapshot, manifest_path, cases_dir)
    validate_contract_payload(actual, expected)
    return actual


def validate_contract_payload(actual: dict[str, Any], expected: dict[str, Any]) -> None:
    if canonical_sha256(actual) != canonical_sha256(expected):
        changed = sorted(
            key for key in set(actual) | set(expected)
            if canonical_sha256(actual.get(key)) != canonical_sha256(expected.get(key))
        )
        raise ValueError("CTU-only contract changed: " + ", ".join(changed))


def main() -> int:
    import argparse

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--snapshot", type=Path, required=True)
    parser.add_argument("--write-lock", action="store_true")
    args = parser.parse_args()
    if args.write_lock:
        LOCK.write_text(json.dumps(build_lock(args.snapshot), sort_keys=True, indent=2) + "\n", encoding="utf-8")
    result = validate(args.snapshot)
    print(json.dumps({"version": result["version"], "logical_snapshot_sha256": result["logical_snapshot_sha256"], "source_row_counts": result["source_row_counts"], "gold_results": result["gold_results"], "semantic_counterexamples": result["semantic_counterexamples"]}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
