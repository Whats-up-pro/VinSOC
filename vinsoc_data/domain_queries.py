"""Domain-owned DuckDB queries used by VinSOC investigation skills.

The orchestrator passes validated business arguments, never raw SQL.  These
queries are the reference runtime implementation for Option A; Track B can
replace the query text with model output only through the same safety gate.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from vinsoc_data.duckdb_store import DuckDBSnapshot, QueryResult


def _time_parameters(time_range: dict[str, str] | None) -> tuple[str, list[Any]]:
    if not time_range:
        return "", []
    return " AND event_time >= ? AND event_time <= ?", [time_range["start"], time_range["end"]]


class DuckDBNetworkRepository:
    """Read-only network evidence retrieval over ``network_flows``."""

    def __init__(self, snapshot: DuckDBSnapshot):
        self.snapshot = snapshot

    def find_connections(
        self, indicator: str, time_range: dict[str, str] | None = None
    ) -> QueryResult:
        time_filter, parameters = _time_parameters(time_range)
        result = self.snapshot.query(
            """
            SELECT
                event_time AS timestamp,
                src_ip AS src,
                src_port,
                dst_ip AS dst,
                dst_port,
                protocol,
                action,
                COALESCE(bytes_out, 0) AS bytes_out,
                COALESCE(bytes_in, 0) AS bytes_in,
                source_dataset,
                source_row_id
            FROM network_flows
            WHERE (src_ip = ? OR dst_ip = ?)
            """ + time_filter + " ORDER BY event_time ASC, source_dataset, source_row_id",
            [indicator, indicator, *parameters],
        )
        return QueryResult(
            columns=result.columns,
            rows=[_normalize_timestamp(row) for row in result.rows],
            truncated=result.truncated,
        )

    def coverage_time_range(self) -> dict[str, str] | None:
        return _coverage_time_range(self.snapshot, "network_flows")


class DuckDBEndpointRepository:
    """Read-only Sysmon process retrieval over ``sysmon_process_events``."""

    def __init__(self, snapshot: DuckDBSnapshot):
        self.snapshot = snapshot

    def find_process_relationships(
        self, host: str, time_range: dict[str, str] | None = None
    ) -> QueryResult:
        time_filter, parameters = _time_parameters(time_range)
        result = self.snapshot.query(
            """
            SELECT
                event_time AS timestamp,
                host,
                parent_image AS parent,
                parent_pid,
                image AS child,
                process_id AS child_pid,
                command_line,
                source_dataset,
                source_row_id
            FROM sysmon_process_events
            WHERE lower(host) = lower(?)
              AND event_id = 1
            """ + time_filter + " ORDER BY event_time ASC, source_dataset, source_row_id",
            [host, *parameters],
        )
        return QueryResult(
            columns=result.columns,
            rows=[_normalize_timestamp(row) for row in result.rows],
            truncated=result.truncated,
        )

    def coverage_time_range(self) -> dict[str, str] | None:
        return _coverage_time_range(self.snapshot, "sysmon_process_events")


def _normalize_timestamp(row: dict[str, Any]) -> dict[str, Any]:
    """Make DuckDB timestamp values JSON-ready without losing the instant."""
    normalized = dict(row)
    value = normalized.get("timestamp")
    if isinstance(value, datetime):
        normalized["timestamp"] = value.isoformat()
    return normalized


def _coverage_time_range(snapshot: DuckDBSnapshot, table_name: str) -> dict[str, str] | None:
    result = snapshot.query(
        f"SELECT min(event_time) AS start, max(event_time) AS end FROM {table_name}"
    )
    if not result.rows or not result.rows[0]["start"] or not result.rows[0]["end"]:
        return None
    row = result.rows[0]
    return {
        "start": _as_iso_string(row["start"]),
        "end": _as_iso_string(row["end"]),
    }


def _as_iso_string(value: Any) -> str:
    return value.isoformat() if isinstance(value, datetime) else str(value)
