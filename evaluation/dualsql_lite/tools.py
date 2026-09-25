"""Snapshot-only, deterministic database tools for DualSQL-Lite."""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any

from vinsoc_data.duckdb_store import DuckDBSnapshot, QuerySafetyError, _read_only_statement


TOOL_VERSION = "dualsql_lite_tools_v1"
MAX_RESPONSE_BYTES = 1650  # Stricter than the 8192-byte specification ceiling.
MAX_PROBE_ROWS = 20
MAX_VALUES_PER_COLUMN = 5
MAX_VALUES_PER_CALL = 50
CATALOG_DISTINCT_LIMIT = 5000
ALLOWED_TABLES = frozenset({"network_flows", "sysmon_process_events", "cti_indicators"})
_BLOCKED_SQL = re.compile(
    r"\b(?:dataset_provenance|information_schema|pg_catalog|sqlite_master|"
    r"duckdb_[a-z_0-9]*|read_[a-z_0-9]*|sqlite_scan|postgres_scan|"
    r"mysql_scan|httpfs|glob|query_table|query|pragma_[a-z_0-9]*|"
    r"current_database|database_list|current_setting|"
    r"getenv|secret|parquet_scan|csv_scan)\b",
    re.IGNORECASE,
)
_EXTERNAL_LITERAL = re.compile(r"(?:[a-z]+://|[/\\]|[a-z]:\\)", re.IGNORECASE)


def _digest(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, default=str,
                                     separators=(",", ":")).encode()).hexdigest()


def _quote(identifier: str) -> str:
    return '"' + identifier.replace('"', '""') + '"'


def _bounded(value: dict[str, Any], *, limit: int = MAX_RESPONSE_BYTES) -> dict[str, Any]:
    if len(json.dumps(value, default=str, ensure_ascii=True).encode()) > limit:
        return {"ok": False, "error_type": "OUTPUT_LIMIT", "message": "Tool result exceeds byte limit"}
    return value


def validate_snapshot_only_sql(sql: str) -> str:
    """Constrain final and probe SQL to the verified local data boundary."""
    statement = _read_only_statement(sql)
    if ('"' in statement or '`' in statement or _BLOCKED_SQL.search(statement)
            or _EXTERNAL_LITERAL.search(statement)):
        raise QuerySafetyError("Query cannot access internal or external resources")
    return statement


class SnapshotOnlyDuckDBSnapshot(DuckDBSnapshot):
    """Preserve the existing R2 comparator with an explicit snapshot-only gate."""

    def _connect(self):
        import duckdb

        return duckdb.connect(str(self.database_path), read_only=True,
                              config={"enable_external_access": "false",
                                      "autoload_known_extensions": "false",
                                      "autoinstall_known_extensions": "false"})

    def query(self, sql: str, parameters=None):
        validate_snapshot_only_sql(sql)
        return super().query(sql, parameters)


TOOL_SCHEMAS = [
    {"type": "function", "function": {"name": "database_profiler",
        "description": "Inspect trusted snapshot table/column metadata and bounded low-cardinality examples.",
        "parameters": {"type": "object", "properties": {
            "table": {"type": "string", "description": "Optional exact table name"}},
            "additionalProperties": False}}},
    {"type": "function", "function": {"name": "value_search",
        "description": "Search real snapshot literals; returns their exact table and column.",
        "parameters": {"type": "object", "properties": {
            "query": {"type": "string"}, "table": {"type": "string"},
            "column": {"type": "string"}}, "required": ["query"],
            "additionalProperties": False}}},
    {"type": "function", "function": {"name": "sql_probe",
        "description": "Run one bounded, read-only SELECT against the evaluation snapshot.",
        "parameters": {"type": "object", "properties": {"sql": {"type": "string"}},
            "required": ["sql"], "additionalProperties": False}}},
]


class DatabaseTools:
    """A frozen snapshot and its derived value catalog; no benchmark case is accepted."""

    def __init__(self, snapshot_path: str | Path):
        self.snapshot_path = Path(snapshot_path)
        if not self.snapshot_path.is_file():
            raise ValueError("Verified evaluation snapshot is unavailable")
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT table_name, column_name, data_type FROM information_schema.columns "
                "WHERE table_schema='main' ORDER BY table_name, ordinal_position"
            ).fetchall()
            self.schema: dict[str, list[dict[str, str]]] = {}
            for table, column, dtype in rows:
                if table in ALLOWED_TABLES:
                    self.schema.setdefault(table, []).append({"name": column, "type": dtype})
            if not self.schema:
                raise ValueError("Evaluation snapshot contains no allowed data tables")
            catalog: list[dict[str, str]] = []
            for table, columns in sorted(self.schema.items()):
                for col in columns:
                    if col["type"].upper() not in {"VARCHAR", "TEXT"}:
                        continue
                    name = col["name"]
                    values = connection.execute(
                        f"SELECT DISTINCT {_quote(name)} FROM {_quote(table)} "
                        f"WHERE {_quote(name)} IS NOT NULL ORDER BY {_quote(name)} "
                        f"LIMIT {CATALOG_DISTINCT_LIMIT}"
                    ).fetchall()
                    catalog.extend({"table": table, "column": name, "value": str(v[0])}
                                   for v in values if len(str(v[0]).encode()) <= 512)
        self.catalog = catalog
        self.catalog_sha256 = _digest({"version": TOOL_VERSION, "limit": CATALOG_DISTINCT_LIMIT,
                                       "values": catalog})

    def _connect(self):
        import duckdb

        return duckdb.connect(str(self.snapshot_path), read_only=True,
                              config={"enable_external_access": "false",
                                      "autoload_known_extensions": "false",
                                      "autoinstall_known_extensions": "false"})

    def schema_context(self, tables: list[str] | None = None) -> str:
        selected = tables if tables is not None else sorted(self.schema)
        return "\n".join(f"{table}({', '.join(c['name'] + ' ' + c['type'] for c in self.schema[table])})"
                         for table in selected if table in self.schema)

    def profiler(self, args: dict[str, Any]) -> dict[str, Any]:
        table = args.get("table")
        if table is not None and (not isinstance(table, str) or table not in self.schema):
            return {"ok": False, "error_type": "INVALID_ARGUMENTS"}
        tables = [table] if table else sorted(self.schema)
        payload: dict[str, Any] = {"ok": True, "tables": []}
        with self._connect() as connection:
            for name in tables:
                count = connection.execute(f"SELECT count(*) FROM {_quote(name)}").fetchone()[0]
                columns = []
                for col in self.schema[name]:
                    values = [v["value"] for v in self.catalog
                              if v["table"] == name and v["column"] == col["name"]]
                    columns.append({"name": col["name"], "type": col["type"],
                                    "examples": values[:MAX_VALUES_PER_COLUMN]
                                    if len(values) <= MAX_VALUES_PER_COLUMN else []})
                payload["tables"].append({"name": name, "row_count": count,
                                          "columns": columns})
        return _bounded(payload)

    def value_search(self, args: dict[str, Any]) -> dict[str, Any]:
        query, table, column = args.get("query"), args.get("table"), args.get("column")
        if (not isinstance(query, str) or not query.strip() or len(query) > 200
                or (table is not None and table not in self.schema)
                or (column is not None and not isinstance(column, str))):
            return {"ok": False, "error_type": "INVALID_ARGUMENTS"}
        terms = set(re.findall(r"[a-z]+|\d+", query.casefold()))
        candidates = [item for item in self.catalog
                      if (not table or item["table"] == table)
                      and (not column or item["column"] == column)]
        exact = [item for item in candidates if query.casefold() in item["value"].casefold()]
        if exact:
            candidates = exact
        else:
            candidates = [item for item in candidates if terms.intersection(
                re.findall(r"[a-z]+|\d+", item["value"].casefold()))]
        hits = []
        per_column: dict[tuple[str, str], int] = {}
        for item in candidates:
            key = (item["table"], item["column"])
            if per_column.get(key, 0) < MAX_VALUES_PER_COLUMN:
                hits.append(item)
                per_column[key] = per_column.get(key, 0) + 1
            if len(hits) == MAX_VALUES_PER_CALL:
                break
        result = {"ok": True, "matches": hits, "truncated": False}
        while hits and len(json.dumps(result, ensure_ascii=True).encode()) > MAX_RESPONSE_BYTES:
            hits.pop()
            result["truncated"] = True
        return _bounded(result)

    def sql_probe(self, args: dict[str, Any]) -> dict[str, Any]:
        sql = args.get("sql")
        if not isinstance(sql, str) or len(sql) > 4000:
            return {"ok": False, "error_type": "INVALID_ARGUMENTS"}
        try:
            statement = validate_snapshot_only_sql(sql)
            # External access is independently disabled on the DuckDB connection.
            with self._connect() as connection:
                cursor = connection.execute(
                    f"SELECT * FROM ({statement}) AS vinsoc_probe LIMIT {MAX_PROBE_ROWS + 1}"
                )
                columns = [col[0] for col in cursor.description]
                rows = [dict(zip(columns, row)) for row in cursor.fetchall()]
            result = {"ok": True, "columns": columns, "rows": rows[:MAX_PROBE_ROWS],
                      "truncated": len(rows) > MAX_PROBE_ROWS}
            while rows and len(json.dumps(result, default=str, ensure_ascii=True).encode()) > MAX_RESPONSE_BYTES:
                rows.pop()
                result["rows"] = rows[:MAX_PROBE_ROWS]
                result["truncated"] = True
            return _bounded(result)
        except QuerySafetyError:
            return {"ok": False, "error_type": "SAFETY_REJECTION"}
        except Exception as exc:
            return _bounded({"ok": False, "error_type": "EXECUTION_ERROR",
                             "message": str(exc)[:300]})

    def invoke(self, name: str, args: Any) -> dict[str, Any]:
        if not isinstance(args, dict):
            return {"ok": False, "error_type": "INVALID_ARGUMENTS"}
        expected = {"database_profiler": (self.profiler, {"table"}),
                    "value_search": (self.value_search, {"query", "table", "column"}),
                    "sql_probe": (self.sql_probe, {"sql"})}
        if name not in expected:
            return {"ok": False, "error_type": "UNKNOWN_TOOL"}
        handler, keys = expected[name]
        if set(args) - keys:
            return {"ok": False, "error_type": "INVALID_ARGUMENTS"}
        return handler(args)
