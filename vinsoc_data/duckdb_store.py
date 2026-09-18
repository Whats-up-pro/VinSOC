"""DuckDB storage boundary for the VinSOC public-data benchmark.

The runtime opens a frozen snapshot in read-only mode.  Snapshot creation is a
separate, explicit action so an investigation cannot alter benchmark data.
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any


class DataSourceUnavailable(RuntimeError):
    """Raised when the configured frozen snapshot cannot be opened."""


class QuerySafetyError(ValueError):
    """Raised before a query that is outside the read-only policy is executed."""


@dataclass(frozen=True)
class QueryResult:
    """Serializable result of a bounded read-only query."""

    columns: tuple[str, ...]
    rows: list[dict[str, Any]]
    truncated: bool = False


_FORBIDDEN_SQL_KEYWORDS = {
    "alter",
    "attach",
    "call",
    "copy",
    "create",
    "delete",
    "detach",
    "drop",
    "execute",
    "export",
    "import",
    "insert",
    "install",
    "load",
    "merge",
    "pragma",
    "replace",
    "set",
    "truncate",
    "update",
    "vacuum",
}


def _sql_tokens(sql: str) -> list[str]:
    """Return SQL keywords while ignoring comments and quoted literal contents."""
    clean: list[str] = []
    index = 0
    length = len(sql)
    quote: str | None = None
    while index < length:
        char = sql[index]
        next_char = sql[index + 1] if index + 1 < length else ""
        if quote:
            if char == quote:
                if next_char == quote:  # SQL escaped quote
                    index += 2
                    continue
                quote = None
            clean.append(" ")
            index += 1
            continue
        if char in {"'", '"', "`"}:
            quote = char
            clean.append(" ")
            index += 1
            continue
        if char == "-" and next_char == "-":
            index = sql.find("\n", index)
            if index < 0:
                break
            clean.append("\n")
            index += 1
            continue
        if char == "/" and next_char == "*":
            end = sql.find("*/", index + 2)
            if end < 0:
                raise QuerySafetyError("SQL contains an unclosed block comment")
            clean.append(" ")
            index = end + 2
            continue
        clean.append(char)
        index += 1
    if quote:
        raise QuerySafetyError("SQL contains an unclosed quoted literal")
    return re.findall(r"[a-z_][a-z0-9_]*|;", "".join(clean).lower())


def validate_read_only_sql(sql: str) -> None:
    """Apply VinSOC's conservative SQL execution policy.

    Only a single ``SELECT`` statement or ``WITH ... SELECT`` statement is
    accepted.  The DuckDB connection is also read-only, which provides a
    second enforcement layer.
    """
    if not isinstance(sql, str) or not sql.strip():
        raise QuerySafetyError("SQL must be a non-empty string")
    tokens = _sql_tokens(sql)
    if not tokens:
        raise QuerySafetyError("SQL contains no executable statement")
    if ";" in tokens:
        raise QuerySafetyError("Multi-statement SQL is not allowed")
    if tokens[0] not in {"select", "with"}:
        raise QuerySafetyError("Only SELECT or WITH ... SELECT statements are allowed")
    forbidden = sorted(set(tokens).intersection(_FORBIDDEN_SQL_KEYWORDS))
    if forbidden:
        raise QuerySafetyError(f"Read-only policy blocked SQL keyword(s): {', '.join(forbidden)}")
    if "select" not in tokens:
        raise QuerySafetyError("A read-only query must contain SELECT")


class DuckDBSnapshot:
    """Read-only query interface over one frozen DuckDB snapshot."""

    def __init__(self, database_path: str | Path, *, row_limit: int = 10_000):
        self.database_path = Path(database_path)
        if row_limit <= 0:
            raise ValueError("row_limit must be positive")
        self.row_limit = row_limit

    def _connect(self):
        try:
            import duckdb
        except ImportError as exc:  # pragma: no cover - dependency is declared
            raise RuntimeError(
                "DuckDB is required. Install dependencies with pip install -r requirements.txt"
            ) from exc
        if not self.database_path.is_file():
            raise DataSourceUnavailable(
                f"Frozen DuckDB snapshot is unavailable: {self.database_path}"
            )
        try:
            return duckdb.connect(str(self.database_path), read_only=True)
        except Exception as exc:
            raise DataSourceUnavailable(
                f"Cannot open frozen DuckDB snapshot {self.database_path}: {exc}"
            ) from exc

    def query(self, sql: str, parameters: Sequence[Any] | None = None) -> QueryResult:
        """Execute a validated query and return at most ``row_limit`` rows."""
        validate_read_only_sql(sql)
        # A wrapper gives every model-generated query the same bounded result
        # contract without modifying the source snapshot.
        bounded_sql = f"SELECT * FROM ({sql}) AS vinsoc_result LIMIT {self.row_limit + 1}"
        with self._connect() as connection:
            try:
                cursor = connection.execute(bounded_sql, parameters or [])
                columns = tuple(item[0] for item in cursor.description)
                rows = [dict(zip(columns, row)) for row in cursor.fetchall()]
            except Exception as exc:
                raise RuntimeError(f"DuckDB query execution failed: {exc}") from exc
        truncated = len(rows) > self.row_limit
        return QueryResult(columns=columns, rows=rows[: self.row_limit], truncated=truncated)


class SocSnapshotBuilder:
    """Explicit builder for a reproducible public-data snapshot.

    This class may be used only during data preparation.  It does not download
    data and it requires source provenance before rows are inserted.
    """

    SCHEMA_VERSION = "vinsoc_soc_schema_v1"

    def __init__(self, database_path: str | Path):
        self.database_path = Path(database_path)

    def create_empty_snapshot(self) -> None:
        """Create the normalized schema; no benchmark rows are fabricated."""
        try:
            import duckdb
        except ImportError as exc:  # pragma: no cover
            raise RuntimeError(
                "DuckDB is required. Install dependencies with pip install -r requirements.txt"
            ) from exc
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        with duckdb.connect(str(self.database_path)) as connection:
            connection.execute("""
                CREATE TABLE IF NOT EXISTS dataset_provenance (
                    dataset_id VARCHAR PRIMARY KEY,
                    source_name VARCHAR NOT NULL,
                    source_url VARCHAR NOT NULL,
                    retrieved_at TIMESTAMP NOT NULL,
                    file_sha256 VARCHAR NOT NULL,
                    license_note VARCHAR NOT NULL,
                    schema_version VARCHAR NOT NULL
                );
                CREATE TABLE IF NOT EXISTS cti_indicators (
                    source_dataset VARCHAR NOT NULL,
                    source_row_id VARCHAR NOT NULL,
                    indicator VARCHAR NOT NULL,
                    indicator_type VARCHAR NOT NULL,
                    threat_type VARCHAR,
                    malware_printable VARCHAR,
                    confidence_level INTEGER,
                    first_seen TIMESTAMP,
                    last_seen TIMESTAMP,
                    reference_url VARCHAR,
                    PRIMARY KEY (source_dataset, source_row_id)
                );
                CREATE TABLE IF NOT EXISTS network_flows (
                    source_dataset VARCHAR NOT NULL,
                    source_row_id VARCHAR NOT NULL,
                    event_time TIMESTAMP,
                    src_ip VARCHAR,
                    src_port INTEGER,
                    dst_ip VARCHAR,
                    dst_port INTEGER,
                    protocol VARCHAR,
                    action VARCHAR,
                    bytes_out BIGINT,
                    bytes_in BIGINT,
                    label VARCHAR,
                    PRIMARY KEY (source_dataset, source_row_id)
                );
                CREATE TABLE IF NOT EXISTS sysmon_process_events (
                    source_dataset VARCHAR NOT NULL,
                    source_row_id VARCHAR NOT NULL,
                    event_time TIMESTAMP,
                    host VARCHAR NOT NULL,
                    event_id INTEGER NOT NULL,
                    parent_image VARCHAR,
                    parent_pid BIGINT,
                    image VARCHAR,
                    process_id BIGINT,
                    command_line VARCHAR,
                    user_name VARCHAR,
                    PRIMARY KEY (source_dataset, source_row_id)
                );
                """)

    def register_provenance(
        self,
        *,
        dataset_id: str,
        source_name: str,
        source_url: str,
        retrieved_at: str,
        file_sha256: str,
        license_note: str,
    ) -> None:
        """Record immutable provenance for a downloaded public source."""
        if not all([dataset_id, source_name, source_url, retrieved_at, file_sha256, license_note]):
            raise ValueError("All provenance fields are required")
        try:
            import duckdb
        except ImportError as exc:  # pragma: no cover
            raise RuntimeError("DuckDB is required") from exc
        if not self.database_path.is_file():
            raise DataSourceUnavailable("Create the snapshot schema before registering provenance")
        with duckdb.connect(str(self.database_path)) as connection:
            connection.execute(
                """
                INSERT OR REPLACE INTO dataset_provenance
                VALUES (?, ?, ?, CAST(? AS TIMESTAMP), ?, ?, ?)
                """,
                [
                    dataset_id,
                    source_name,
                    source_url,
                    retrieved_at,
                    file_sha256,
                    license_note,
                    self.SCHEMA_VERSION,
                ],
            )

    def insert_rows(
        self,
        table_name: str,
        rows: Iterable[Mapping[str, Any]],
        *,
        source_dataset: str,
    ) -> int:
        """Insert normalized public rows after their source is registered.

        ``rows`` must already include the schema columns and a stable
        ``source_row_id``.  The method rejects unregistered sources so each
        evidence row remains traceable to public data.
        """
        allowed_tables = {"cti_indicators", "network_flows", "sysmon_process_events"}
        if table_name not in allowed_tables:
            raise ValueError(f"Unsupported VinSOC table: {table_name}")
        records = [dict(row) for row in rows]
        if not records:
            return 0
        if any(row.get("source_dataset") != source_dataset for row in records):
            raise ValueError("Every row must have the registered source_dataset value")
        try:
            import duckdb
        except ImportError as exc:  # pragma: no cover
            raise RuntimeError("DuckDB is required") from exc
        with duckdb.connect(str(self.database_path)) as connection:
            present = connection.execute(
                "SELECT 1 FROM dataset_provenance WHERE dataset_id = ?", [source_dataset]
            ).fetchone()
            if present is None:
                raise ValueError(f"Dataset provenance is not registered: {source_dataset}")
            columns = list(records[0])
            if any(set(row) != set(columns) for row in records):
                raise ValueError("All normalized rows must have the same columns")
            placeholders = ", ".join("?" for _ in columns)
            quoted_columns = ", ".join(columns)
            values = [[row[column] for column in columns] for row in records]
            connection.executemany(
                f"INSERT INTO {table_name} ({quoted_columns}) VALUES ({placeholders})",
                values,
            )
        return len(records)
