"""DuckDB-backed NetworkDataSource for the VinSOC telemetry layer.

This bridges the DuckDB snapshot to the normalized telemetry interface.
It converts DuckDB rows into NormalizedNetworkEvent objects.
"""
from __future__ import annotations

from typing import Any, Iterable

from telemetry.network.base import NetworkDataSource
from telemetry.network.models import NormalizedNetworkEvent
from telemetry.network.query import NetworkQuery
from vinsoc_data.domain_queries import DuckDBNetworkRepository


class DuckDBNetworkDataSource(NetworkDataSource):
    """NetworkDataSource backed by DuckDB via DuckDBNetworkRepository."""

    name = "duckdb_network"

    def __init__(self, repository: DuckDBNetworkRepository):
        self.repository = repository
        self.query_coverage: dict[str, Any] = {}

    def query(self, query: NetworkQuery) -> Iterable[NormalizedNetworkEvent]:
        db_result = self.repository.find_connections(
            indicator=query.indicator,
            time_range={"start": query.start, "end": query.end} if query.start else None,
        )
        self.query_coverage = {
            "source": self.name,
            "repository_row_limit": self.repository.snapshot.row_limit,
            "repository_result_truncated": db_result.truncated,
            "retrieved_rows": len(db_result.rows),
            "query_population_complete": not db_result.truncated,
        }

        for row in db_result.rows:
            yield NormalizedNetworkEvent.create(
                event_id=f"duckdb:{row.get('source_dataset', 'unknown')}:{row.get('source_row_id', 0)}",
                source="duckdb",
                source_record_id=str(row.get("source_row_id", "")),
                observed_at=str(row.get("timestamp", "")),
                src_ip=str(row.get("src", "")),
                src_port=row.get("src_port"),
                dst_ip=str(row.get("dst", "")),
                dst_port=row.get("dst_port"),
                protocol=row.get("protocol"),
                app_protocol=row.get("app_protocol"),
                duration_seconds=row.get("duration"),
                bytes_src_to_dst=row.get("bytes_out"),
                bytes_dst_to_src=row.get("bytes_in"),
                packets_src_to_dst=row.get("packets_out"),
                packets_dst_to_src=row.get("packets_in"),
                state=row.get("state"),
                action=row.get("action"),
                source_event_type="flow",
                provenance={
                    "source": "duckdb",
                    "dataset": row.get("source_dataset", "unknown"),
                },
                raw=dict(row),
            )
