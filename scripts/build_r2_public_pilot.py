"""Build a network/Sysmon-only pilot snapshot from a closed source manifest.

No download or model request happens here. Content hashes describe ordered
normalized rows; DuckDB file bytes are also hashed but may vary between runs.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import tempfile
import zipfile
from collections.abc import Iterator
from pathlib import Path

from evaluation.text_to_sql_snapshot import sha256_file
from scripts.build_vinsoc_public_snapshot import (
    _integer, _ip, _load_dataset_manifest, _text, _timestamp, _validate_sources,
)
from vinsoc_data.duckdb_store import DuckDBSnapshot, SocSnapshotBuilder


def iter_ctu_rows(path: Path, dataset_id: str) -> Iterator[dict]:
    with Path(path).open("r", encoding="utf-8-sig", newline="") as handle:
        for line, row in enumerate(csv.DictReader(handle), start=2):
            when = _timestamp(row.get("StartTime"))
            source = _ip(row.get("SrcAddr"))
            destination = _ip(row.get("DstAddr"))
            sport = _integer(row.get("Sport"), minimum=0, maximum=65535)
            dport = _integer(row.get("Dport"), minimum=0, maximum=65535)
            total = _integer(row.get("TotBytes"), minimum=0)
            outgoing = _integer(row.get("SrcBytes"), minimum=0)
            if not all((when, source, destination)) or any(
                _text(row.get(key)) and value is None for key, value in (
                    ("Sport", sport), ("Dport", dport), ("TotBytes", total), ("SrcBytes", outgoing)
                )
            ) or (total is not None and outgoing is not None and outgoing > total):
                continue
            yield {
                "source_dataset": dataset_id, "source_row_id": f"line:{line}",
                "event_time": when, "src_ip": source, "src_port": sport,
                "dst_ip": destination, "dst_port": dport,
                "protocol": (_text(row.get("Proto")) or "").upper() or None,
                "action": _text(row.get("State")), "bytes_out": outgoing,
                "bytes_in": total - outgoing if total is not None and outgoing is not None else None,
                "label": _text(row.get("Label")),
            }


def iter_sysmon_rows(path: Path, dataset_id: str, member: str) -> Iterator[dict]:
    with zipfile.ZipFile(path) as archive:
        names = [info.filename for info in archive.infolist() if not info.is_dir()]
        if names != [member]:
            raise ValueError(f"Expected exactly the verified OTRF archive member {member}")
        with archive.open(member) as handle:
            for line, raw in enumerate(handle, start=1):
                payload = json.loads(raw)
                if payload.get("Channel") != "Microsoft-Windows-Sysmon/Operational":
                    continue
                when = _timestamp(payload.get("UtcTime") or payload.get("@timestamp"))
                hostname = _text(payload.get("Hostname"))  # `host` is the collector, not the endpoint.
                event_id = _integer(payload.get("EventID"), minimum=0)
                if not all((when, hostname)) or event_id is None:
                    continue
                yield {
                    "source_dataset": dataset_id,
                    "source_row_id": f"{member}:line:{line}",
                    "event_time": when, "host": hostname, "event_id": event_id,
                    "parent_image": _text(payload.get("ParentImage")),
                    "parent_pid": _integer(payload.get("ParentProcessId"), minimum=0),
                    "image": _text(payload.get("Image")),
                    "process_id": _integer(payload.get("ProcessId"), minimum=0),
                    "command_line": _text(payload.get("CommandLine")),
                    "user_name": _text(payload.get("User")),
                }


def _bulk_insert(snapshot: Path, table: str, rows: Iterator[dict], temp_dir: Path) -> int:
    """Stream normalized rows to CSV, then let DuckDB import them in one COPY."""
    import duckdb

    path = temp_dir / (table + "-" + str(len(list(temp_dir.glob(table + "-*.csv")))) + ".csv")
    count = 0
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = None
        for row in rows:
            if writer is None:
                writer = csv.DictWriter(handle, fieldnames=list(row), lineterminator="\n")
                writer.writeheader()
            writer.writerow(row)
            count += 1
    if count:
        escaped = str(path).replace("'", "''")
        with duckdb.connect(str(snapshot)) as conn:
            conn.execute(f"COPY {table} FROM '{escaped}' (FORMAT CSV, HEADER TRUE, NULL '')")
    path.unlink()
    return count


def logical_content_hash(snapshot_path: Path) -> tuple[dict[str, int], str]:
    import duckdb

    digest = hashlib.sha256()
    counts: dict[str, int] = {}
    with duckdb.connect(str(snapshot_path), read_only=True) as conn:
        for table in ("network_flows", "sysmon_process_events"):
            cursor = conn.execute(
                f"SELECT * FROM {table} ORDER BY source_dataset, source_row_id"
            )
            digest.update((table + "\n").encode())
            count = 0
            while batch := cursor.fetchmany(4096):
                for row in batch:
                    digest.update((json.dumps(row, ensure_ascii=False, default=str, separators=(",", ":")) + "\n").encode())
                    count += 1
            counts[table] = count
    return counts, digest.hexdigest()


def build_pilot_snapshot(manifest_path: Path, snapshot_path: Path) -> dict:
    manifest_path, snapshot_path = Path(manifest_path), Path(snapshot_path)
    sources = _load_dataset_manifest(manifest_path)
    if {source["format"] for source in sources} != {"ctu13_binetflow", "sysmon_zip_jsonl"}:
        raise ValueError("Public pilot requires only CTU-13 flows and OTRF Sysmon ZIP")
    _validate_sources(sources)
    if snapshot_path.exists():
        raise ValueError(f"Refusing to overwrite snapshot: {snapshot_path}")
    snapshot_path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=snapshot_path.parent, prefix="pilot-build-") as temp_dir:
        temporary = Path(temp_dir) / snapshot_path.name
        builder = SocSnapshotBuilder(temporary)
        builder.create_empty_snapshot()
        import duckdb

        with duckdb.connect(str(temporary)) as conn:
            conn.execute("DROP TABLE cti_indicators")
        for source in sources:
            builder.register_provenance(**{key: source[key] for key in (
                "dataset_id", "source_name", "source_url", "retrieved_at", "file_sha256", "license_note"
            )})
            if source["format"] == "ctu13_binetflow":
                table = "network_flows"
                rows = iter_ctu_rows(Path(source["path"]), source["dataset_id"])
            else:
                table = "sysmon_process_events"
                rows = iter_sysmon_rows(Path(source["path"]), source["dataset_id"], source["archive_member"])
            _bulk_insert(temporary, table, rows, Path(temp_dir))
        counts, content_sha256 = logical_content_hash(temporary)
        if min(counts.values()) <= 0:
            raise ValueError("Both network and Sysmon tables must have nonzero rows")
        with DuckDBSnapshot(temporary)._connect() as connection:
            provenance = connection.execute("SELECT count(*) FROM dataset_provenance").fetchone()[0]
            names = {name for (name,) in connection.execute("SHOW TABLES").fetchall()}
        if provenance != len(sources) or names != {"dataset_provenance", "network_flows", "sysmon_process_events"}:
            raise ValueError("Source provenance or pilot table set mismatch")
        os.replace(temporary, snapshot_path)
    return {
        "snapshot_id": snapshot_path.stem,
        "path": str(snapshot_path),
        "sha256": sha256_file(snapshot_path),
        "schema_version": "1",
        "content_sha256": content_sha256,
        "row_counts": counts,
        "source_hashes": {source["dataset_id"]: source["file_sha256"] for source in sources},
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, default=Path("evaluation/public_pilot/dataset_manifest.json"))
    parser.add_argument("--snapshot", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()
    report = build_pilot_snapshot(args.manifest, args.snapshot)
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, sort_keys=True, indent=2) + "\n")
    print(json.dumps({"content_sha256": report["content_sha256"], "row_counts": report["row_counts"]}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
