"""Build the CTU-13 scenario-5/7 network-only public pilot snapshot."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import tempfile
from pathlib import Path

from scripts.build_r2_public_pilot import iter_ctu_rows
from scripts.build_vinsoc_public_snapshot import _load_dataset_manifest, _validate_sources
from evaluation.text_to_sql_snapshot import sha256_file
from vinsoc_data.duckdb_store import DuckDBSnapshot, SocSnapshotBuilder

TABLES = {"dataset_provenance", "network_flows"}
SOURCE_IDS = ("ctu13_s5", "ctu13_s7")


def logical_content_hash(snapshot: Path) -> tuple[dict[str, int], str]:
    import duckdb

    digest = hashlib.sha256()
    counts: dict[str, int] = {}
    with duckdb.connect(str(snapshot), read_only=True) as conn:
        for table, ordering in (("dataset_provenance", "dataset_id"), ("network_flows", "source_dataset, source_row_id")):
            cursor = conn.execute(f"SELECT * FROM {table} ORDER BY {ordering}")
            columns = [(item[0], str(item[1])) for item in cursor.description]
            digest.update((table + "\n" + json.dumps(columns, separators=(",", ":")) + "\n").encode())
            count = 0
            while batch := cursor.fetchmany(4096):
                for row in batch:
                    digest.update((json.dumps(row, default=str, separators=(",", ":")) + "\n").encode())
                    count += 1
            counts[table] = count
    return {"network_flows": counts["network_flows"]}, digest.hexdigest()


def _copy_rows(snapshot: Path, rows: list[dict], temporary: Path) -> None:
    if not rows:
        raise ValueError("CTU source produced no valid network rows")
    csv_path = temporary / "network_flows.csv"
    with csv_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]), lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)
    import duckdb
    escaped = str(csv_path).replace("'", "''")
    try:
        with duckdb.connect(str(snapshot)) as conn:
            conn.execute(f"COPY network_flows FROM '{escaped}' (FORMAT CSV, HEADER TRUE, DELIMITER ',', QUOTE '\"', ESCAPE '\"', NULL '')")
    except duckdb.Error:
        raise RuntimeError("DuckDB COPY failed for network_flows") from None


def build_ctu_network_snapshot(manifest_path: Path, snapshot_path: Path) -> dict:
    sources = _load_dataset_manifest(Path(manifest_path))
    if tuple(sorted(source["dataset_id"] for source in sources)) != SOURCE_IDS:
        raise ValueError("CTU-only manifest must contain exactly ctu13_s5 and ctu13_s7")
    if any(source["format"] != "ctu13_binetflow" for source in sources):
        raise ValueError("CTU-only manifest may contain only CTU binetflow sources")
    try:
        _validate_sources(sources)
    except ValueError as exc:
        raise ValueError(f"source checksum validation failed: {exc}") from exc
    snapshot_path = Path(snapshot_path)
    if snapshot_path.exists():
        raise ValueError("Refusing to overwrite snapshot")
    snapshot_path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=snapshot_path.parent, prefix="ctu-network-") as root:
        temporary = Path(root)
        built = temporary / snapshot_path.name
        builder = SocSnapshotBuilder(built)
        builder.create_empty_snapshot()
        import duckdb
        with duckdb.connect(str(built)) as conn:
            conn.execute("DROP TABLE cti_indicators")
            conn.execute("DROP TABLE sysmon_process_events")
        rows: list[dict] = []
        for source in sources:
            builder.register_provenance(**{key: source[key] for key in ("dataset_id", "source_name", "source_url", "retrieved_at", "file_sha256", "license_note")})
            rows.extend(iter_ctu_rows(Path(source["path"]), source["dataset_id"]))
        _copy_rows(built, rows, temporary)
        counts, content_hash = logical_content_hash(built)
        with duckdb.connect(str(built), read_only=True) as conn:
            names = {row[0] for row in conn.execute("SHOW TABLES").fetchall()}
            provenance = conn.execute("SELECT count(*) FROM dataset_provenance").fetchone()[0]
            distinct = conn.execute("SELECT count(DISTINCT source_dataset || ':' || source_row_id) FROM network_flows").fetchone()[0]
        if names != TABLES or provenance != 2 or counts["network_flows"] <= 0 or distinct != counts["network_flows"]:
            raise ValueError("CTU-only snapshot contract failed")
        os.replace(built, snapshot_path)
    return {"version": "ctu_network_public_dev_v1", "sha256": sha256_file(snapshot_path), "content_sha256": content_hash, "row_counts": counts, "distinct_source_row_id": distinct, "source_hashes": {s["dataset_id"]: s["file_sha256"] for s in sources}}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--snapshot", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()
    report = build_ctu_network_snapshot(args.manifest, args.snapshot)
    args.report.write_text(json.dumps(report, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
