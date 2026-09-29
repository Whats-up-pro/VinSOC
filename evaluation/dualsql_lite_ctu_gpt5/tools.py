"""Bounded, snapshot-derived CTU database tools for the GPT-5 comparison."""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any

from vinsoc_data.duckdb_store import DuckDBSnapshot, QuerySafetyError, _read_only_statement

TOOL_VERSION = "dualsql_lite_ctu_gpt5_tools_v2"
MAX_RESPONSE_BYTES = 1650
MAX_PROBE_ROWS = 20
MAX_VALUES_PER_COLUMN = 5
CATALOG_DISTINCT_LIMIT = 5000
ALLOWED_TABLES = frozenset({"network_flows"})

_BLOCKED_SQL = re.compile(
    r"\b(?:information_schema|pg_catalog|sqlite_master|dataset_provenance|"
    r"duckdb_[a-z_0-9]*|read_[a-z_0-9]*|sqlite_scan|postgres_scan|"
    r"mysql_scan|httpfs|glob|query_table|query|pragma_[a-z_0-9]*|"
    r"current_database|database_list|current_setting|getenv|secret|"
    r"parquet_scan|csv_scan|sysmon_process_events|cti_indicators)\b",
    re.IGNORECASE,
)
_EXTERNAL_LITERAL = re.compile(r"(?:[a-z]+://|[/\\]|[a-z]:\\)", re.IGNORECASE)
_TABLE_REFERENCE = re.compile(r"\b(?:from|join)\s+([a-z_][a-z_0-9]*)\b", re.IGNORECASE)


def _quote(identifier: str) -> str:
    return '"' + identifier.replace('"', '""') + '"'


def _size(value: dict[str, Any]) -> int:
    return len(json.dumps(value, default=str, ensure_ascii=True).encode("utf-8"))


def _error(category: str) -> dict[str, Any]:
    return {"ok": False, "error_type": category}


def validate_snapshot_only_sql(sql: str) -> str:
    """Allow one read-only query over network_flows, with no external access."""
    statement = _read_only_statement(sql)
    if (not statement.lstrip().lower().startswith("select ")
            or any(token in statement for token in ('"', '`', '--', '/*', '*/'))
            or _BLOCKED_SQL.search(statement) or _EXTERNAL_LITERAL.search(statement)):
        raise QuerySafetyError("Query is outside the CTU snapshot boundary")
    references = _TABLE_REFERENCE.findall(statement)
    if any(table.lower() not in ALLOWED_TABLES for table in references):
        raise QuerySafetyError("Query is outside the CTU snapshot boundary")
    return statement


class SnapshotOnlyDuckDBSnapshot(DuckDBSnapshot):
    """Read-only DuckDB comparator with external access disabled."""

    def _connect(self):
        import duckdb

        return duckdb.connect(
            str(self.database_path), read_only=True,
            config={"enable_external_access": "false",
                    "autoload_known_extensions": "false",
                    "autoinstall_known_extensions": "false"},
        )

    def query(self, sql: str, parameters=None):
        validate_snapshot_only_sql(sql)
        return super().query(sql, parameters)


TOOL_SCHEMAS = [
    {"type": "function", "function": {"name": "database_profiler",
        "description": "Inspect typed columns in the verified network_flows table.",
        "parameters": {"type": "object", "properties": {
            "table": {"type": "string", "description": "Optional exact table name"}},
            "additionalProperties": False}}},
    {"type": "function", "function": {"name": "value_search",
        "description": "Find stored text values in the verified network_flows snapshot.",
        "parameters": {"type": "object", "properties": {
            "query": {"type": "string"}, "table": {"type": "string"},
            "column": {"type": "string"}}, "required": ["query"],
            "additionalProperties": False}}},
    {"type": "function", "function": {"name": "sql_probe",
        "description": "Run one bounded read-only SELECT over network_flows.",
        "parameters": {"type": "object", "properties": {"sql": {"type": "string"}},
            "required": ["sql"], "additionalProperties": False}}},
]


class CTUDatabaseTools:
    """Three tools grounded in one verified S5/S7 snapshot."""

    def __init__(self, snapshot_path: str | Path):
        self.snapshot_path = Path(snapshot_path)
        if not self.snapshot_path.is_file():
            raise ValueError("Verified evaluation snapshot is unavailable")
        self._evidence_counter = 0
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT table_name, column_name, data_type FROM information_schema.columns "
                "WHERE table_schema='main' AND table_name='network_flows' "
                "ORDER BY ordinal_position"
            ).fetchall()
            if not rows:
                raise ValueError("Verified network_flows table is unavailable")
            self.schema = {"network_flows": [
                {"name": name, "type": dtype} for _, name, dtype in rows
            ]}
            catalog: list[dict[str, str]] = []
            for column in self.schema["network_flows"]:
                if column["type"].upper() not in {"VARCHAR", "TEXT"}:
                    continue
                name = column["name"]
                values = connection.execute(
                    f"SELECT DISTINCT {_quote(name)} FROM network_flows "
                    f"WHERE {_quote(name)} IS NOT NULL ORDER BY {_quote(name)} "
                    f"LIMIT {CATALOG_DISTINCT_LIMIT}"
                ).fetchall()
                catalog.extend({"table": "network_flows", "column": name,
                                "value": str(value)} for (value,) in values
                               if len(str(value).encode("utf-8")) <= 512)
        self.catalog = catalog
        encoded = json.dumps(catalog, ensure_ascii=False, sort_keys=True,
                             separators=(",", ":")).encode("utf-8")
        self.catalog_sha256 = hashlib.sha256(encoded).hexdigest()

    def _connect(self):
        import duckdb

        return duckdb.connect(
            str(self.snapshot_path), read_only=True,
            config={"enable_external_access": "false",
                    "autoload_known_extensions": "false",
                    "autoinstall_known_extensions": "false"},
        )

    def _evidence_id(self) -> str:
        self._evidence_counter += 1
        return f"ev-{self._evidence_counter:06d}"

    def schema_context(self, tables: list[str] | None = None) -> str:
        selected = tables if tables is not None else ["network_flows"]
        return "\n".join(
            f"{table}({', '.join(c['name'] + ' ' + c['type'] for c in self.schema[table])})"
            for table in selected if table in self.schema
        )

    def database_profiler(self, arguments: dict[str, Any]) -> dict[str, Any]:
        if (not isinstance(arguments, dict) or set(arguments) - {"table"}
                or arguments.get("table", "network_flows") != "network_flows"):
            return _error("INVALID_ARGUMENTS")
        result = {"ok": True, "evidence_id": self._evidence_id(), "tables": [
            {"name": "network_flows", "columns": self.schema["network_flows"]}
        ]}
        return result if _size(result) <= MAX_RESPONSE_BYTES else _error("OUTPUT_LIMIT")

    # Retain the previous method name for readers that have not migrated yet.
    profiler = database_profiler

    def value_search(self, arguments: dict[str, Any]) -> dict[str, Any]:
        if not isinstance(arguments, dict) or set(arguments) - {"query", "table", "column"}:
            return _error("INVALID_ARGUMENTS")
        query = arguments.get("query")
        table = arguments.get("table", "network_flows")
        column = arguments.get("column")
        if (not isinstance(query, str) or not query.strip() or len(query) > 200
                or table != "network_flows"
                or (column is not None and column not in {
                    item["name"] for item in self.schema["network_flows"]
                })):
            return _error("INVALID_ARGUMENTS")
        evidence_id = self._evidence_id()
        matches = [dict(item, evidence_id=evidence_id) for item in self.catalog
                   if (column is None or item["column"] == column)
                   and query.casefold() in item["value"].casefold()]
        result: dict[str, Any] = {"ok": True, "evidence_id": evidence_id,
                                  "matches": [], "truncated": False}
        for item in matches:
            if len(result["matches"]) >= 50:
                result["truncated"] = True
                break
            result["matches"].append(item)
            if _size(result) > MAX_RESPONSE_BYTES:
                result["matches"].pop()
                result["truncated"] = True
                break
        return result

    def sql_probe(self, arguments: dict[str, Any]) -> dict[str, Any]:
        if (not isinstance(arguments, dict) or set(arguments) != {"sql"}
                or not isinstance(arguments["sql"], str)
                or len(arguments["sql"]) > 4000):
            return _error("INVALID_ARGUMENTS")
        try:
            statement = validate_snapshot_only_sql(arguments["sql"])
            with self._connect() as connection:
                cursor = connection.execute(
                    f"SELECT * FROM ({statement}) AS vinsoc_probe LIMIT {MAX_PROBE_ROWS + 1}"
                )
                columns = [description[0] for description in cursor.description]
                rows = [dict(zip(columns, row)) for row in cursor.fetchall()]
            result = {"ok": True, "evidence_id": self._evidence_id(),
                      "columns": columns, "rows": rows[:MAX_PROBE_ROWS],
                      "truncated": len(rows) > MAX_PROBE_ROWS}
            return result if _size(result) <= MAX_RESPONSE_BYTES else _error("OUTPUT_LIMIT")
        except QuerySafetyError:
            return _error("SAFETY_REJECTION")
        except Exception:
            return _error("EXECUTION_ERROR")

    def invoke(self, name: str, arguments: Any) -> dict[str, Any]:
        handlers = {"database_profiler": self.database_profiler,
                    "value_search": self.value_search, "sql_probe": self.sql_probe}
        if name not in handlers:
            return _error("UNKNOWN_TOOL")
        if not isinstance(arguments, dict):
            return _error("INVALID_ARGUMENTS")
        return handlers[name](arguments)


# Compatibility for the historical CTU adapter while Task 5 migrates it.
DatabaseTools = CTUDatabaseTools
