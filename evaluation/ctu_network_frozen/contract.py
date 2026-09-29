"""Offline, source-separated CTU S1/S4 frozen benchmark contract."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

from evaluation.text_to_sql import SQLBenchmarkCase, evaluate_sql_case
from scripts.build_ctu_network_frozen_snapshot import (
    SOURCE_URLS,
    TABLES,
    _check_sources,
    _logical_content_hash,
)
from vinsoc_data.duckdb_store import DuckDBSnapshot


ROOT = Path("evaluation/ctu_network_frozen")
MANIFEST = ROOT / "dataset_manifest.json"
RECEIPT = ROOT / "source_receipt.json"
CASES = ROOT / "frozen"
LOCK = ROOT / "VERSION.lock"
VERSION = "ctu_network_frozen_s1_s4_v1"
SCORER_FILES = (
    "evaluation/text_to_sql.py",
    "evaluation/ctu_network_frozen/contract.py",
    "scripts/build_ctu_network_frozen_snapshot.py",
    "vinsoc_data/duckdb_store.py",
)
COMPARATORS = {"scalar", "boolean", "ordered_rows", "unordered_rows", "multiset_rows"}
REQUIRED_SEMANTICS = {
    "scalar_filter", "distinct", "boolean_precedence", "bounded_time_interval",
    "aggregation_group_by", "order_by_limit", "stored_value_grounding",
    "multi_row_comparison",
}


def canonical_sha256(value: Any) -> str:
    payload = json.dumps(value, sort_keys=True, ensure_ascii=False,
                         separators=(",", ":"), default=str).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def portable_text_sha256(path: Path) -> str:
    content = path.read_bytes().replace(b"\r\n", b"\n").replace(b"\r", b"\n")
    return hashlib.sha256(content).hexdigest()


def _cases(directory: Path) -> tuple[dict[str, dict[str, Any]], list[SQLBenchmarkCase]]:
    paths = sorted(directory.glob("*.json"))
    expected_names = [f"frozen_{number:03d}.json" for number in range(1, 9)]
    if [path.name for path in paths] != expected_names:
        raise ValueError("Frozen case directory requires eight numbered case files")
    raw = {path.name: json.loads(path.read_text(encoding="utf-8")) for path in paths}
    cases = [SQLBenchmarkCase.from_dict(payload) for payload in raw.values()]
    ids = [case.case_id for case in cases]
    expected_ids = [f"frozen_sql_{number:03d}" for number in range(1, 9)]
    if ids != expected_ids or len(set(ids)) != 8:
        raise ValueError("Frozen case ID set is missing or duplicated")
    if any(len(case.gold_sql) != 1 or case.result_comparator not in COMPARATORS
           or not case.database_snapshot for case in cases):
        raise ValueError("Frozen case gold, comparator, or snapshot declaration is invalid")
    if len({case.database_snapshot for case in cases}) != 1:
        raise ValueError("Frozen cases declare different database snapshots")
    covered = set().union(*(set(item.get("semantic_tags", [])) for item in raw.values()))
    if not REQUIRED_SEMANTICS.issubset(covered):
        raise ValueError("Frozen case semantic coverage is incomplete")
    return raw, cases


def _snapshot_facts(snapshot: Path, sources: list[dict[str, Any]]) -> dict[str, Any]:
    import duckdb

    expected_provenance = {
        item["dataset_id"]: (item["source_url"], item["file_sha256"])
        for item in sources
    }
    with duckdb.connect(str(snapshot), read_only=True) as conn:
        tables = {row[0] for row in conn.execute("SHOW TABLES").fetchall()}
        if tables != TABLES:
            raise ValueError("Frozen snapshot contains unexpected tables")
        counts = dict(conn.execute(
            "SELECT source_dataset, count(*) FROM network_flows GROUP BY source_dataset"
        ).fetchall())
        distinct = conn.execute(
            "SELECT count(DISTINCT source_dataset || ':' || source_row_id) FROM network_flows"
        ).fetchone()[0]
        provenance = {
            row[0]: (row[1], row[2]) for row in conn.execute(
                "SELECT dataset_id, source_url, file_sha256 FROM dataset_provenance"
            ).fetchall()
        }
    if (set(counts) != set(SOURCE_URLS) or distinct != sum(counts.values())
            or provenance != expected_provenance):
        raise ValueError("Frozen snapshot source, provenance, or row identity mismatch")
    temp_directory = snapshot.parent / "contract-hash-work"
    temp_directory.mkdir(exist_ok=True)
    schema, logical_hash = _logical_content_hash(snapshot, temp_directory)
    return {
        "tables": sorted(tables), "schema": schema,
        "source_row_counts": counts,
        "row_counts": {"network_flows": sum(counts.values())},
        "distinct_source_row_id": distinct,
        "logical_snapshot_sha256": logical_hash,
    }


def build_frozen_lock(
    snapshot: Path,
    cases_dir: Path = CASES,
    *,
    manifest_path: Path = MANIFEST,
    receipt_path: Path = RECEIPT,
) -> dict[str, Any]:
    """Recompute every frozen identity from pinned bytes and read-only SQL."""
    snapshot, cases_dir = Path(snapshot), Path(cases_dir)
    if not snapshot.is_file():
        raise ValueError("Frozen snapshot is unavailable")
    sources = _check_sources(Path(manifest_path), Path(receipt_path))
    raw, cases = _cases(cases_dir)
    facts = _snapshot_facts(snapshot, sources)
    reader = DuckDBSnapshot(snapshot)
    gold_results: dict[str, Any] = {}
    counterexamples: dict[str, Any] = {}
    for path_name, case in zip(raw, cases):
        gold = reader.query(case.gold_sql[0])
        if gold.truncated or not evaluate_sql_case(case, case.gold_sql[0], reader).execution_accurate:
            raise ValueError(f"Frozen gold SQL failed: {case.case_id}")
        gold_rows = gold.rows
        if case.result_comparator in {"unordered_rows", "multiset_rows"}:
            gold_rows = sorted(gold_rows, key=lambda row: json.dumps(row, sort_keys=True, default=str))
        gold_results[case.case_id] = {
            "row_count": len(gold_rows), "result_sha256": canonical_sha256(gold_rows),
            "gold_sql_sha256": canonical_sha256(case.gold_sql),
        }
        wrong_sql = raw[path_name].get("counterexample_sql")
        if not isinstance(wrong_sql, str) or not wrong_sql.strip():
            raise ValueError(f"Missing semantic counterexample: {case.case_id}")
        wrong = evaluate_sql_case(case, wrong_sql, reader)
        if not wrong.execution_success or wrong.execution_accurate:
            raise ValueError(f"Semantic counterexample does not differ from gold: {case.case_id}")
        counterexamples[case.case_id] = {
            "sql_sha256": hashlib.sha256(wrong_sql.encode("utf-8")).hexdigest(),
            "different_from_gold": True,
        }
    files = {
        path.name: portable_text_sha256(path) for path in sorted(cases_dir.glob("*.json"))
    }
    return {
        "version": VERSION,
        "source_urls": {item["dataset_id"]: item["source_url"] for item in sources},
        "source_file_sha256": {item["dataset_id"]: item["file_sha256"] for item in sources},
        "manifest_sha256": portable_text_sha256(Path(manifest_path)),
        "source_receipt_sha256": portable_text_sha256(Path(receipt_path)),
        **facts,
        "case_ids": [case.case_id for case in cases],
        "case_file_sha256": files,
        "case_directory_sha256": canonical_sha256(files),
        "split_sha256": canonical_sha256(raw),
        "gold_results": gold_results,
        "comparator_contract": {
            "cases": {case.case_id: case.result_comparator for case in cases},
            "scorer_sha256": portable_text_sha256(Path("evaluation/text_to_sql.py")),
        },
        "semantic_coverage": sorted(REQUIRED_SEMANTICS),
        "semantic_counterexamples": counterexamples,
        "builder_scorer_sha256": {
            name: portable_text_sha256(Path(name)) for name in SCORER_FILES
        },
        "model_calls": 0,
    }


def validate_frozen_contract(
    snapshot: Path,
    lock_path: Path = LOCK,
    cases_dir: Path = CASES,
    *,
    manifest_path: Path = MANIFEST,
    receipt_path: Path = RECEIPT,
) -> dict[str, Any]:
    expected = json.loads(Path(lock_path).read_text(encoding="utf-8"))
    actual = build_frozen_lock(
        snapshot, cases_dir, manifest_path=manifest_path, receipt_path=receipt_path
    )
    changed = [key for key in sorted(set(actual) | set(expected))
               if canonical_sha256(actual.get(key)) != canonical_sha256(expected.get(key))]
    if changed:
        raise ValueError("Frozen contract changed: " + ", ".join(changed))
    return actual


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--snapshot", type=Path, required=True)
    parser.add_argument("--write-lock", action="store_true")
    args = parser.parse_args()
    if args.write_lock:
        lock = build_frozen_lock(args.snapshot)
        with LOCK.open("x", encoding="utf-8") as handle:
            json.dump(lock, handle, sort_keys=True, indent=2)
            handle.write("\n")
    result = validate_frozen_contract(args.snapshot)
    print(json.dumps({
        "version": result["version"],
        "logical_snapshot_sha256": result["logical_snapshot_sha256"],
        "source_row_counts": result["source_row_counts"],
        "distinct_source_row_id": result["distinct_source_row_id"],
        "case_directory_sha256": result["case_directory_sha256"],
        "model_calls": 0,
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
