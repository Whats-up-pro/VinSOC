"""Build an independent CTU-13 S1/S4 network snapshot from pinned official bytes."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
from pathlib import Path
from typing import Any

from evaluation.text_to_sql_snapshot import sha256_file
from scripts.build_r2_public_pilot import iter_ctu_rows
from scripts.build_vinsoc_public_snapshot import _load_dataset_manifest, _validate_sources
from vinsoc_data.duckdb_store import SocSnapshotBuilder

SOURCE_URLS = {
    "ctu13_s1": "https://mcfp.felk.cvut.cz/publicDatasets/CTU-Malware-Capture-Botnet-42/detailed-bidirectional-flow-labels/capture20110810.binetflow",
    "ctu13_s4": "https://mcfp.felk.cvut.cz/publicDatasets/CTU-Malware-Capture-Botnet-45/detailed-bidirectional-flow-labels/capture20110815.binetflow",
}
TABLES = {"dataset_provenance", "network_flows"}
SCHEMA_TABLES = ("dataset_provenance", "network_flows")


def _quoted_path(path: Path) -> str:
    return str(path.resolve()).replace("'", "''")


def _check_sources(manifest_path: Path, receipt_path: Path) -> list[dict[str, Any]]:
    sources = _load_dataset_manifest(manifest_path)
    if {source["dataset_id"]: source["source_url"] for source in sources} != SOURCE_URLS:
        raise ValueError("Frozen source URL or S1/S4 identity mismatch")
    if any(source["format"] != "ctu13_binetflow" for source in sources):
        raise ValueError("Frozen source format mismatch")
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    checks = receipt["source_checks"]
    if set(checks) != set(SOURCE_URLS):
        raise ValueError("Frozen source provenance receipt mismatch")
    for source in sources:
        item = checks[source["dataset_id"]]
        if (item["source_url"] != source["source_url"]
                or item["sha256_stream_and_disk"] != source["file_sha256"]
                or Path(source["path"]).stat().st_size != item["content_length_bytes"]):
            raise ValueError("Frozen source provenance or checksum receipt mismatch")
    try:
        _validate_sources(sources)
    except ValueError as exc:
        raise ValueError(f"Frozen source checksum validation failed: {exc}") from exc
    return sorted(sources, key=lambda source: source["dataset_id"])


def _write_normalized_csv(source: dict[str, Any], path: Path) -> int:
    count = 0
    with path.open("x", encoding="utf-8", newline="") as handle:
        writer = None
        for row in iter_ctu_rows(Path(source["path"]), source["dataset_id"]):
            if writer is None:
                writer = csv.DictWriter(
                    handle,
                    fieldnames=list(row),
                    delimiter=",",
                    quotechar='"',
                    doublequote=True,
                    quoting=csv.QUOTE_MINIMAL,
                    lineterminator="\n",
                )
                writer.writeheader()
            writer.writerow(row)
            count += 1
    if count == 0:
        raise ValueError(f"Frozen source {source['dataset_id']} has no valid flows")
    return count


def _logical_content_hash(snapshot: Path, temp_directory: Path) -> tuple[dict[str, list[list[str]]], str]:
    import duckdb

    digest = hashlib.sha256()
    schema: dict[str, list[list[str]]] = {}
    with duckdb.connect(str(snapshot), read_only=True) as conn:
        conn.execute("SET memory_limit='1GB'")
        conn.execute("SET threads=1")
        conn.execute("SET preserve_insertion_order=false")
        conn.execute(f"SET temp_directory='{_quoted_path(temp_directory)}'")
        for table, ordering in (("dataset_provenance", "dataset_id"),
                                ("network_flows", "source_dataset, source_row_id")):
            cursor = conn.execute(f"SELECT * FROM {table} ORDER BY {ordering}")
            columns = [[item[0], str(item[1])] for item in cursor.description]
            schema[table] = columns
            digest.update((table + "\n" + json.dumps(columns, separators=(",", ":")) + "\n").encode())
            while batch := cursor.fetchmany(4096):
                for row in batch:
                    digest.update((json.dumps(row, default=str, separators=(",", ":")) + "\n").encode())
    return schema, digest.hexdigest()


def build_ctu_network_frozen_snapshot(
    manifest_path: Path, receipt_path: Path, snapshot_path: Path, work_directory: Path
) -> dict[str, Any]:
    """Validate pinned S1/S4 bytes and build once; never overwrite an output."""
    manifest_path, receipt_path = Path(manifest_path), Path(receipt_path)
    snapshot_path, work_directory = Path(snapshot_path), Path(work_directory)
    if snapshot_path.exists() or work_directory.exists():
        raise FileExistsError("Frozen snapshot or work directory already exists")
    sources = _check_sources(manifest_path, receipt_path)
    snapshot_path.parent.mkdir(parents=True, exist_ok=True)
    work_directory.mkdir(parents=True, exist_ok=False)
    temp_dir = work_directory / "duckdb-temp"
    temp_dir.mkdir()
    built = work_directory / "snapshot.duckdb"
    builder = SocSnapshotBuilder(built)
    builder.create_empty_snapshot()
    import duckdb

    with duckdb.connect(str(built)) as conn:
        conn.execute("DROP TABLE cti_indicators")
        conn.execute("DROP TABLE sysmon_process_events")
    counts: dict[str, int] = {}
    for source in sources:
        builder.register_provenance(**{
            key: source[key] for key in
            ("dataset_id", "source_name", "source_url", "retrieved_at", "file_sha256", "license_note")
        })
        csv_path = work_directory / f"{source['dataset_id']}-network_flows.csv"
        counts[source["dataset_id"]] = _write_normalized_csv(source, csv_path)
        with duckdb.connect(str(built)) as conn:
            conn.execute("SET memory_limit='512MB'")
            conn.execute(f"SET temp_directory='{_quoted_path(temp_dir)}'")
            conn.execute(
                f"COPY network_flows FROM '{_quoted_path(csv_path)}' "
                "(FORMAT CSV, HEADER TRUE, AUTO_DETECT FALSE, "
                "DELIMITER ',', QUOTE '\"', ESCAPE '\"', NULL '')"
            )
    with duckdb.connect(str(built), read_only=True) as conn:
        names = {row[0] for row in conn.execute("SHOW TABLES").fetchall()}
        actual_counts = dict(conn.execute(
            "SELECT source_dataset, count(*) FROM network_flows GROUP BY source_dataset"
        ).fetchall())
        distinct_source_row_id = conn.execute(
            "SELECT count(DISTINCT source_dataset || ':' || source_row_id) "
            "FROM network_flows"
        ).fetchone()[0]
        provenance = conn.execute("SELECT count(*) FROM dataset_provenance").fetchone()[0]
    if (names != TABLES or actual_counts != counts or provenance != 2
            or distinct_source_row_id != sum(counts.values())):
        raise ValueError("Frozen snapshot table, source count, or provenance mismatch")
    schema, content_hash = _logical_content_hash(built, temp_dir)
    os.replace(built, snapshot_path)
    return {
        "version": "ctu_network_frozen_s1_s4_v1",
        "snapshot_file_sha256": sha256_file(snapshot_path),
        "logical_snapshot_sha256": content_hash,
        "source_file_sha256": {s["dataset_id"]: s["file_sha256"] for s in sources},
        "source_urls": {s["dataset_id"]: s["source_url"] for s in sources},
        "source_row_counts": counts,
        "row_counts": {"network_flows": sum(counts.values())},
        "distinct_source_row_id": distinct_source_row_id,
        "row_identity_proof": "PRIMARY KEY(source_dataset, source_row_id) enforced on COPY",
        "tables": sorted(names),
        "schema": schema,
        "dataset_provenance_rows": provenance,
        "model_calls": 0,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--receipt", type=Path, required=True)
    parser.add_argument("--snapshot", type=Path, required=True)
    parser.add_argument("--work-directory", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()
    if args.report.exists():
        raise FileExistsError("Frozen build report already exists")
    result = build_ctu_network_frozen_snapshot(
        args.manifest, args.receipt, args.snapshot, args.work_directory
    )
    args.report.parent.mkdir(parents=True, exist_ok=True)
    with args.report.open("x", encoding="utf-8") as handle:
        json.dump(result, handle, indent=2, sort_keys=True)
        handle.write("\n")
    print(json.dumps({"logical_snapshot_sha256": result["logical_snapshot_sha256"],
                      "source_row_counts": result["source_row_counts"],
                      "model_calls": 0}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
