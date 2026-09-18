"""Read-only local data access for VinSOC."""

from vinsoc_data.duckdb_store import (
    DataSourceUnavailable,
    DuckDBSnapshot,
    QueryResult,
    QuerySafetyError,
    SocSnapshotBuilder,
)

__all__ = [
    "DataSourceUnavailable",
    "DuckDBSnapshot",
    "QueryResult",
    "QuerySafetyError",
    "SocSnapshotBuilder",
]
