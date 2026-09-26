"""Build the VinSOC public DuckDB snapshot from verified local source files.

This command never downloads data. Each input must be recorded in a closed
dataset manifest and its SHA-256 is verified before a database is created.
"""

from __future__ import annotations

import argparse
import csv
import io
import ipaddress
import json
import os
import re
import tempfile
import zipfile
from collections.abc import Callable, Iterable, Iterator
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from evaluation.text_to_sql_snapshot import sha256_file
from vinsoc_data.duckdb_store import DuckDBSnapshot, SocSnapshotBuilder

BUILDER_VERSION = "vinsoc_public_snapshot_v2_official"

_SOURCE_FIELDS = {
    "dataset_id",
    "source_name",
    "source_url",
    "retrieved_at",
    "file_sha256",
    "license_note",
    "format",
    "path",
    "archive_member",
}
_SOURCE_FORMATS = {
    "threatfox_csv",
    "ctu13_binetflow",
    "sysmon_jsonl",
    "sysmon_zip_jsonl",
}
_SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")


def _text(value: Any) -> str | None:
    if value is None:
        return None
    rendered = str(value).strip()
    return rendered or None


def _integer(value: Any, *, minimum: int | None = None, maximum: int | None = None) -> int | None:
    rendered = _text(value)
    if rendered is None:
        return None
    try:
        parsed = int(rendered, 0)
    except (TypeError, ValueError):
        return None
    if minimum is not None and parsed < minimum:
        return None
    if maximum is not None and parsed > maximum:
        return None
    return parsed


def _timestamp(value: Any) -> str | None:
    rendered = _text(value)
    if rendered is None:
        return None
    candidates = [rendered.replace("Z", "+00:00")]
    for pattern in (
        "%Y/%m/%d %H:%M:%S.%f",
        "%Y/%m/%d %H:%M:%S",
        "%Y-%m-%d %H:%M:%S.%f",
        "%Y-%m-%d %H:%M:%S",
    ):
        try:
            parsed = datetime.strptime(rendered, pattern).replace(tzinfo=UTC)
            return parsed.astimezone(UTC).replace(tzinfo=None).isoformat()
        except ValueError:
            pass
    for candidate in candidates:
        try:
            parsed = datetime.fromisoformat(candidate)
        except ValueError:
            continue
        if parsed.tzinfo is not None:
            parsed = parsed.astimezone(UTC).replace(tzinfo=None)
        return parsed.isoformat()
    return None


def _ip(value: Any) -> str | None:
    rendered = _text(value)
    if rendered is None:
        return None
    try:
        return str(ipaddress.ip_address(rendered))
    except ValueError:
        return None


def _csv_rows(path: Path) -> Iterable[tuple[int, dict[str, str]]]:
    with Path(path).open("r", encoding="utf-8-sig", newline="") as handle:
        lines = (line for line in handle if line.strip() and not line.lstrip().startswith("#"))
        reader = csv.DictReader(lines)
        if reader.fieldnames is None:
            raise ValueError(f"CSV source has no header: {path}")
        yield from enumerate(reader, start=2)


def _threatfox_csv_rows(path: Path) -> Iterable[tuple[int, dict[str, str]]]:
    """Read a ThreatFox export whose real header may itself be commented."""
    with Path(path).open("r", encoding="utf-8-sig", newline="") as handle:
        header: str | None = None
        header_line = 0
        data_lines: list[str] = []
        for line_number, line in enumerate(handle, start=1):
            if header is None:
                candidate = line.lstrip()
                if candidate.startswith("#"):
                    candidate = candidate[1:].lstrip()
                if "first_seen_utc" in candidate and "ioc_value" in candidate:
                    header = candidate
                    header_line = line_number
                continue
            if line.strip() and not line.lstrip().startswith("#"):
                data_lines.append(line)
    if header is None:
        raise ValueError("ThreatFox CSV header not found")
    reader = csv.DictReader([header, *data_lines])
    required = {"ioc_id", "ioc_value", "ioc_type", "first_seen_utc"}
    missing = sorted(required.difference(reader.fieldnames or ()))
    if missing:
        raise ValueError(f"ThreatFox CSV missing required column(s): {', '.join(missing)}")
    yield from enumerate(reader, start=header_line + 1)


def _new_threatfox_diagnostics(dataset_id: str) -> dict[str, Any]:
    return {
        "dataset_id": dataset_id,
        "data_rows_seen": 0,
        "rows_accepted": 0,
        "rows_rejected": 0,
        "primary_rejection_reasons": {
            "missing_required_value": 0,
            "invalid_first_seen_timestamp": 0,
            "invalid_last_seen_timestamp": 0,
            "invalid_confidence_level": 0,
        },
        "timestamp_shape_counts": {
            "first_seen_ends_with_utc_literal": 0,
            "last_seen_ends_with_utc_literal": 0,
        },
    }


def _reject_threatfox_row(diagnostics: dict[str, Any], reason: str) -> None:
    diagnostics["rows_rejected"] += 1
    diagnostics["primary_rejection_reasons"][reason] += 1


def _iter_threatfox_csv(
    path: Path,
    dataset_id: str,
    *,
    diagnostics: dict[str, Any] | None = None,
) -> Iterator[dict[str, Any]]:
    diagnostics = diagnostics if diagnostics is not None else _new_threatfox_diagnostics(dataset_id)
    for line_number, row in _threatfox_csv_rows(path):
        diagnostics["data_rows_seen"] += 1
        first_seen_text = _text(row.get("first_seen_utc"))
        last_seen_text = _text(row.get("last_seen_utc"))
        if first_seen_text and first_seen_text.endswith(" UTC"):
            diagnostics["timestamp_shape_counts"][
                "first_seen_ends_with_utc_literal"
            ] += 1
        if last_seen_text and last_seen_text.endswith(" UTC"):
            diagnostics["timestamp_shape_counts"][
                "last_seen_ends_with_utc_literal"
            ] += 1
        source_row_id = _text(row.get("ioc_id"))
        indicator = _text(row.get("ioc_value"))
        indicator_type = _text(row.get("ioc_type"))
        if not source_row_id or not indicator or not indicator_type:
            _reject_threatfox_row(diagnostics, "missing_required_value")
            continue
        first_seen = _timestamp(first_seen_text)
        if first_seen_text and first_seen is None:
            _reject_threatfox_row(diagnostics, "invalid_first_seen_timestamp")
            continue
        last_seen = _timestamp(last_seen_text)
        if last_seen_text and last_seen is None:
            _reject_threatfox_row(diagnostics, "invalid_last_seen_timestamp")
            continue
        confidence = _integer(row.get("confidence_level"), minimum=0, maximum=100)
        if _text(row.get("confidence_level")) and confidence is None:
            _reject_threatfox_row(diagnostics, "invalid_confidence_level")
            continue
        diagnostics["rows_accepted"] += 1
        yield {
            "source_dataset": dataset_id,
            "source_row_id": source_row_id or f"line:{line_number}",
            "indicator": indicator,
            "indicator_type": indicator_type,
            "threat_type": _text(row.get("threat_type")),
            "malware_printable": _text(row.get("malware_printable")),
            "confidence_level": confidence,
            "first_seen": first_seen,
            "last_seen": last_seen,
            "reference_url": _text(row.get("reference")),
        }


def normalize_threatfox_csv(path: Path, dataset_id: str) -> list[dict[str, Any]]:
    """Normalize the documented ThreatFox CSV export columns."""
    return list(_iter_threatfox_csv(path, dataset_id))


def normalize_threatfox_csv_with_diagnostics(
    path: Path, dataset_id: str
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Normalize ThreatFox rows and return privacy-preserving rejection counts."""
    diagnostics = _new_threatfox_diagnostics(dataset_id)
    rows = list(_iter_threatfox_csv(path, dataset_id, diagnostics=diagnostics))
    return rows, diagnostics


def _iter_ctu13_binetflow(path: Path, dataset_id: str) -> Iterator[dict[str, Any]]:
    for line_number, row in _csv_rows(path):
        event_time = _timestamp(row.get("StartTime"))
        src_ip = _ip(row.get("SrcAddr"))
        dst_ip = _ip(row.get("DstAddr"))
        src_port = _integer(row.get("Sport"), minimum=0, maximum=65535)
        dst_port = _integer(row.get("Dport"), minimum=0, maximum=65535)
        total_bytes = _integer(row.get("TotBytes"), minimum=0)
        source_bytes = _integer(row.get("SrcBytes"), minimum=0)
        if event_time is None or src_ip is None or dst_ip is None:
            continue
        if _text(row.get("Sport")) and src_port is None:
            continue
        if _text(row.get("Dport")) and dst_port is None:
            continue
        if _text(row.get("TotBytes")) and total_bytes is None:
            continue
        if _text(row.get("SrcBytes")) and source_bytes is None:
            continue
        if total_bytes is not None and source_bytes is not None and source_bytes > total_bytes:
            continue
        yield {
            "source_dataset": dataset_id,
            "source_row_id": f"line:{line_number}",
            "event_time": event_time,
            "src_ip": src_ip,
            "src_port": src_port,
            "dst_ip": dst_ip,
            "dst_port": dst_port,
            "protocol": (_text(row.get("Proto")) or "").upper() or None,
            "action": _text(row.get("State")),
            "bytes_out": source_bytes,
            "bytes_in": (
                total_bytes - source_bytes
                if total_bytes is not None and source_bytes is not None
                else None
            ),
            "label": _text(row.get("Label")),
        }


def normalize_ctu13_binetflow(path: Path, dataset_id: str) -> list[dict[str, Any]]:
    """Normalize CTU-13 detailed bidirectional ``.binetflow`` records."""
    return list(_iter_ctu13_binetflow(path, dataset_id))


def _nested(payload: dict[str, Any], *path: str) -> Any:
    current: Any = payload
    for item in path:
        if not isinstance(current, dict):
            return None
        current = current.get(item)
    return current


def _normalize_sysmon_lines(
    lines: Iterable[str], dataset_id: str, *, source_prefix: str | None = None
) -> list[dict[str, Any]]:
    return list(_iter_sysmon_lines(lines, dataset_id, source_prefix=source_prefix))


def _iter_sysmon_lines(
    lines: Iterable[str], dataset_id: str, *, source_prefix: str | None = None
) -> Iterator[dict[str, Any]]:
    for line_number, line in enumerate(lines, start=1):
        if not line.strip():
            continue
        try:
            payload = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not isinstance(payload, dict):
            continue
        channel = _text(payload.get("Channel"))
        if channel is not None and channel != "Microsoft-Windows-Sysmon/Operational":
            continue
        winlog = payload.get("winlog") if isinstance(payload.get("winlog"), dict) else {}
        event_data = winlog.get("event_data")
        if not isinstance(event_data, dict):
            event_data = payload.get("EventData")
        if not isinstance(event_data, dict):
            event_data = {}
        event_time = _timestamp(payload.get("@timestamp") or payload.get("UtcTime"))
        host = _text(
            winlog.get("computer_name")
            or _nested(payload, "host", "name")
            or payload.get("Hostname")
            or payload.get("Computer")
        )
        event_id = _integer(
            winlog.get("event_id") or _nested(payload, "event", "code") or payload.get("EventID"),
            minimum=0,
        )
        if event_time is None or host is None or event_id is None:
            continue
        row_id = f"line:{line_number}"
        if source_prefix:
            row_id = f"{source_prefix}:{row_id}"
        yield {
            "source_dataset": dataset_id,
            "source_row_id": row_id,
            "event_time": event_time,
            "host": host,
            "event_id": event_id,
            "parent_image": _text(
                event_data.get("ParentImage")
                or payload.get("ParentImage")
                or _nested(payload, "process", "parent", "executable")
            ),
            "parent_pid": _integer(
                event_data.get("ParentProcessId")
                or payload.get("ParentProcessId")
                or _nested(payload, "process", "parent", "pid"),
                minimum=0,
            ),
            "image": _text(
                event_data.get("Image")
                or payload.get("Image")
                or _nested(payload, "process", "executable")
            ),
            "process_id": _integer(
                event_data.get("ProcessId")
                or payload.get("ProcessId")
                or _nested(payload, "process", "pid"), minimum=0
            ),
            "command_line": _text(
                event_data.get("CommandLine")
                or payload.get("CommandLine")
                or _nested(payload, "process", "command_line")
            ),
            "user_name": _text(
                event_data.get("User")
                or payload.get("User")
                or payload.get("SubjectUserName")
                or _nested(payload, "user", "name")
            ),
        }


def normalize_sysmon_jsonl(path: Path, dataset_id: str) -> list[dict[str, Any]]:
    """Normalize OTRF-style JSONL Windows/Sysmon event records."""
    with Path(path).open("r", encoding="utf-8-sig") as handle:
        return _normalize_sysmon_lines(handle, dataset_id)


def _iter_sysmon_jsonl(path: Path, dataset_id: str) -> Iterator[dict[str, Any]]:
    with Path(path).open("r", encoding="utf-8-sig") as handle:
        yield from _iter_sysmon_lines(handle, dataset_id)


def normalize_sysmon_zip_jsonl(
    path: Path, dataset_id: str, archive_member: str
) -> list[dict[str, Any]]:
    """Normalize one explicitly named JSONL member from a verified ZIP archive."""
    try:
        with zipfile.ZipFile(path) as archive:
            info = archive.getinfo(archive_member)
            if info.is_dir():
                raise ValueError(f"Sysmon ZIP member is a directory: {archive_member}")
            with (
                archive.open(info, "r") as raw_handle,
                io.TextIOWrapper(raw_handle, encoding="utf-8-sig") as text_handle,
            ):
                return _normalize_sysmon_lines(
                    text_handle, dataset_id, source_prefix=archive_member
                )
    except KeyError as exc:
        raise ValueError(f"Sysmon ZIP member does not exist: {archive_member}") from exc
    except zipfile.BadZipFile as exc:
        raise ValueError(f"Invalid Sysmon ZIP archive: {path}") from exc


def _iter_sysmon_zip_jsonl(
    path: Path, dataset_id: str, archive_member: str
) -> Iterator[dict[str, Any]]:
    try:
        with zipfile.ZipFile(path) as archive:
            info = archive.getinfo(archive_member)
            if info.is_dir():
                raise ValueError(f"Sysmon ZIP member is a directory: {archive_member}")
            with (
                archive.open(info, "r") as raw_handle,
                io.TextIOWrapper(raw_handle, encoding="utf-8-sig") as text_handle,
            ):
                yield from _iter_sysmon_lines(
                    text_handle, dataset_id, source_prefix=archive_member
                )
    except KeyError as exc:
        raise ValueError(f"Sysmon ZIP member does not exist: {archive_member}") from exc
    except zipfile.BadZipFile as exc:
        raise ValueError(f"Invalid Sysmon ZIP archive: {path}") from exc


def _load_dataset_manifest(path: Path) -> list[dict[str, Any]]:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(payload, dict) or set(payload) != {"schema_version", "sources"}:
        raise ValueError("Dataset manifest must contain exactly schema_version and sources")
    if payload["schema_version"] != "1" or not isinstance(payload["sources"], list):
        raise ValueError("Unsupported dataset manifest schema_version or sources type")
    if not payload["sources"]:
        raise ValueError("Dataset manifest must contain at least one source")
    sources: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    for source in payload["sources"]:
        if not isinstance(source, dict) or set(source) != _SOURCE_FIELDS:
            raise ValueError("Each dataset source must contain exactly the required fields")
        string_fields = _SOURCE_FIELDS - {"archive_member"}
        if not all(
            isinstance(source[field], str) and source[field].strip() for field in string_fields
        ):
            raise ValueError("Dataset source fields must be non-empty strings")
        if source["format"] not in _SOURCE_FORMATS:
            raise ValueError(f"Unsupported source format: {source['format']}")
        if not _SHA256_PATTERN.fullmatch(source["file_sha256"]):
            raise ValueError("Dataset source file_sha256 must be 64 lowercase hex characters")
        if source["dataset_id"] in seen_ids:
            raise ValueError(f"Duplicate dataset_id: {source['dataset_id']}")
        parsed_url = urlparse(source["source_url"])
        if parsed_url.scheme != "https" or not parsed_url.netloc:
            raise ValueError(f"Source must use an absolute HTTPS URL: {source['dataset_id']}")
        try:
            retrieved_at = datetime.fromisoformat(source["retrieved_at"])
        except ValueError as exc:
            raise ValueError(
                f"retrieved_at must be an ISO 8601 UTC date-time: {source['dataset_id']}"
            ) from exc
        if retrieved_at.tzinfo is None or retrieved_at.utcoffset() != timedelta(0):
            raise ValueError(
                f"retrieved_at must be an ISO 8601 UTC date-time: {source['dataset_id']}"
            )
        archive_member = source["archive_member"]
        if source["format"] == "sysmon_zip_jsonl":
            if not isinstance(archive_member, str) or not archive_member.strip():
                raise ValueError("sysmon_zip_jsonl requires a non-empty archive_member")
        elif archive_member is not None:
            raise ValueError("archive_member is allowed only for sysmon_zip_jsonl")
        seen_ids.add(source["dataset_id"])
        sources.append(source)
    return sources


def _validate_sources(sources: list[dict[str, Any]]) -> None:
    for source in sources:
        path = Path(source["path"])
        if not path.is_file():
            raise ValueError(f"Source file does not exist: {path}")
        actual_sha256 = sha256_file(path)
        if actual_sha256 != source["file_sha256"]:
            raise ValueError(
                f"Source SHA-256 mismatch for {source['dataset_id']}: "
                f"expected {source['file_sha256']}, received {actual_sha256}"
            )


def _validate_built_snapshot(path: Path, expected_sources: int) -> dict[str, int]:
    snapshot = DuckDBSnapshot(path)
    provenance_count = snapshot.query("SELECT count(*) AS n FROM dataset_provenance").rows[0]["n"]
    if provenance_count != expected_sources:
        raise ValueError("Snapshot provenance count does not match the dataset manifest")
    counts: dict[str, int] = {}
    for table in ("cti_indicators", "network_flows", "sysmon_process_events"):
        count = snapshot.query(f"SELECT count(*) AS n FROM {table}").rows[0]["n"]
        missing_identity = snapshot.query(
            f"SELECT count(*) AS n FROM {table} "
            "WHERE source_dataset IS NULL OR source_dataset = '' "
            "OR source_row_id IS NULL OR source_row_id = ''"
        ).rows[0]["n"]
        if count <= 0:
            raise ValueError(f"Snapshot table has no rows: {table}")
        if missing_identity:
            raise ValueError(f"Snapshot table has rows without source identity: {table}")
        counts[table] = count
    benchmarks_dir = (
        Path(__file__).resolve().parents[1] / "evaluation" / "text_to_sql_benchmarks" / "dev"
    )
    for case_path in sorted(benchmarks_dir.glob("*.json")):
        case = json.loads(case_path.read_text(encoding="utf-8"))
        for gold_sql in case["gold_sql"]:
            snapshot.query(gold_sql)
    return counts


def _bulk_insert_rows(
    snapshot_path: Path,
    table: str,
    rows: Iterable[dict[str, Any]],
    temporary_directory: Path,
) -> int:
    """Stream normalized rows through a temporary CSV into DuckDB."""
    import duckdb

    with tempfile.NamedTemporaryFile(
        "w",
        encoding="utf-8",
        newline="",
        suffix=f"-{table}.csv",
        dir=temporary_directory,
        delete=False,
    ) as handle:
        staged_path = Path(handle.name)
        writer: csv.DictWriter | None = None
        count = 0
        for row in rows:
            if writer is None:
                writer = csv.DictWriter(handle, fieldnames=list(row), lineterminator="\n")
                writer.writeheader()
            elif set(row) != set(writer.fieldnames or ()):
                raise ValueError(f"Normalized {table} rows have inconsistent columns")
            writer.writerow(row)
            count += 1
    try:
        if count:
            escaped_path = str(staged_path).replace("'", "''")
            with duckdb.connect(str(snapshot_path)) as connection:
                connection.execute(
                    f"COPY {table} FROM '{escaped_path}' "
                    "(FORMAT CSV, HEADER TRUE, NULL '')"
                )
        return count
    finally:
        staged_path.unlink(missing_ok=True)


def build_snapshot(
    dataset_manifest_path: Path,
    snapshot_path: Path,
    snapshot_manifest_path: Path,
) -> dict[str, int]:
    """Build, validate, and atomically publish one verified snapshot."""
    dataset_manifest_path = Path(dataset_manifest_path)
    snapshot_path = Path(snapshot_path)
    snapshot_manifest_path = Path(snapshot_manifest_path)
    if snapshot_path.exists():
        raise ValueError(f"Refusing to overwrite existing snapshot: {snapshot_path}")
    if snapshot_manifest_path.exists():
        raise ValueError(f"Refusing to overwrite existing manifest: {snapshot_manifest_path}")
    sources = _load_dataset_manifest(dataset_manifest_path)
    _validate_sources(sources)
    snapshot_path.parent.mkdir(parents=True, exist_ok=True)
    snapshot_manifest_path.parent.mkdir(parents=True, exist_ok=True)
    adapters: dict[str, tuple[str, Callable[[Path, str], Iterable[dict[str, Any]]]]] = {
        "threatfox_csv": ("cti_indicators", _iter_threatfox_csv),
        "ctu13_binetflow": ("network_flows", _iter_ctu13_binetflow),
        "sysmon_jsonl": ("sysmon_process_events", _iter_sysmon_jsonl),
    }
    with tempfile.TemporaryDirectory(
        prefix="vinsoc-snapshot-", dir=snapshot_path.parent
    ) as temp_dir:
        temporary_snapshot = Path(temp_dir) / snapshot_path.name
        builder = SocSnapshotBuilder(temporary_snapshot)
        builder.create_empty_snapshot()
        for source in sources:
            builder.register_provenance(
                dataset_id=source["dataset_id"],
                source_name=source["source_name"],
                source_url=source["source_url"],
                retrieved_at=source["retrieved_at"],
                file_sha256=source["file_sha256"],
                license_note=source["license_note"],
            )
            if source["format"] == "sysmon_zip_jsonl":
                table = "sysmon_process_events"
                rows = _iter_sysmon_zip_jsonl(
                    Path(source["path"]), source["dataset_id"], source["archive_member"]
                )
            else:
                table, adapter = adapters[source["format"]]
                rows = adapter(Path(source["path"]), source["dataset_id"])
            _bulk_insert_rows(temporary_snapshot, table, rows, Path(temp_dir))
        counts = _validate_built_snapshot(temporary_snapshot, len(sources))
        os.replace(temporary_snapshot, snapshot_path)

    manifest_payload = {
        "snapshot_id": snapshot_path.stem,
        "path": str(snapshot_path),
        "sha256": sha256_file(snapshot_path),
        "schema_version": "1",
    }
    with tempfile.NamedTemporaryFile(
        "w", encoding="utf-8", dir=snapshot_manifest_path.parent, delete=False
    ) as handle:
        temporary_manifest = Path(handle.name)
        json.dump(manifest_payload, handle, indent=2)
        handle.write("\n")
    os.replace(temporary_manifest, snapshot_manifest_path)
    return counts


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset-manifest", type=Path, required=True)
    parser.add_argument(
        "--snapshot", type=Path, default=Path("data/snapshots/vinsoc_public_v1.duckdb")
    )
    parser.add_argument(
        "--snapshot-manifest",
        type=Path,
        default=Path("evaluation/text_to_sql_benchmarks/snapshot_manifest.json"),
    )
    args = parser.parse_args()
    counts = build_snapshot(args.dataset_manifest, args.snapshot, args.snapshot_manifest)
    print(json.dumps(counts, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
