"""Controller-owned, bounded, read-only tools for a verified multi-table context."""
from __future__ import annotations

import hashlib
import json
from decimal import Decimal, InvalidOperation
from datetime import datetime, time
from threading import Timer

import duckdb

from .data import DatabaseContext, _quote
from .safety import SafetyError, validate_sql


class ToolError(ValueError):
    pass


def _json_value(value):
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, bytes):
        return {"bytes_hex": value.hex()}
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return value


def witness_id(witness):
    fields = {key: value for key, value in witness.items() if key != "evidence_id"}
    return "catalog_" + hashlib.sha256(json.dumps(fields, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


class DatabaseTools:
    def __init__(self, context: DatabaseContext, *, executor=None, max_db_calls=12, timeout_seconds=2, row_cap=20, payload_bytes=8192):
        self.context = context
        self.executor = executor
        self.max_db_calls = max_db_calls
        self.timeout_seconds = timeout_seconds
        self.row_cap = row_cap
        self.payload_bytes = payload_bytes
        self.db_calls = 0
        self.trajectory = []
        self.witnesses = {}

    def _table(self, table):
        matches = [item for item in self.context.identity["schema"] if item["name"] == table]
        if len(matches) != 1:
            raise ToolError("TABLE_NOT_REGISTERED")
        return matches[0]

    def column(self, table, column):
        matches = [item for item in self._table(table)["columns"] if item["name"] == column]
        if len(matches) != 1:
            raise ToolError("COLUMN_NOT_REGISTERED")
        return matches[0]

    def _execute(self, query, parameters=()):
        if self.db_calls >= self.max_db_calls:
            raise ToolError("DB_TOOL_LIMIT")
        self.db_calls += 1
        if self.executor is not None:
            from vinsoc_text2sql.executor import ExecutorError
            try:
                receipt = self.executor.query(self.context, query, parameters,
                    row_cap=self.row_cap, timeout_seconds=self.timeout_seconds)
            except ExecutorError as error:
                raise ToolError(str(error)) from None
            return [column['name'] for column in receipt['columns']], receipt['rows'], receipt['truncated']
        connection = duckdb.connect(str(self.context.snapshot_path), read_only=True, config={
            "enable_external_access": False, "autoload_known_extensions": False,
            "autoinstall_known_extensions": False, "threads": 1, "memory_limit": "64MB",
        })
        timer = Timer(self.timeout_seconds, connection.interrupt)
        timer.daemon = True
        timer.start()
        try:
            cursor = connection.execute(query, parameters)
            columns = [column[0] for column in cursor.description]
            rows = cursor.fetchmany(self.row_cap + 1)
            return columns, rows[:self.row_cap], len(rows) > self.row_cap
        except duckdb.Error as error:
            raise ToolError("SQL_EXECUTION_FAILED:" + type(error).__name__) from error
        finally:
            timer.cancel()
            connection.close()

    def _record(self, name, arguments, result):
        if len(json.dumps(result, ensure_ascii=False).encode()) > self.payload_bytes:
            raise ToolError("TOOL_PAYLOAD_LIMIT")
        self.trajectory.append({"tool": name, "arguments": arguments.copy(), "result": result})
        return result

    def database_profiler(self, arguments):
        table = arguments.get("table")
        schema = self._table(table)
        selected = arguments.get("columns") or [column["name"] for column in schema["columns"]]
        if len(selected) > 12:
            raise ToolError("PROFILE_COLUMN_LIMIT")
        columns = [self.column(table, name) for name in selected]
        expressions = ["COUNT(*)"] + [f"COUNT(DISTINCT {_quote(column['name'])})" for column in columns]
        _, rows, _ = self._execute(f"SELECT {','.join(expressions)} FROM {_quote(table)}")
        result = {"database_id": self.context.database_id, "snapshot_identity": self.context.identity["logical_sha256"],
                  "table": table, "row_count": rows[0][0], "columns": [
                      {"name": column["name"], "type": column["duckdb_type"], "distinct_count": rows[0][i+1]}
                      for i, column in enumerate(columns)
                  ], "relationships": self.context.identity["relationships"]}
        return self._record("database_profiler", arguments, result)

    def value_search(self, arguments):
        table, column, query = arguments.get("table"), arguments.get("column"), arguments.get("query")
        metadata = self.column(table, column)
        if not isinstance(query, str) or len(query.encode()) > 512:
            raise ToolError("INVALID_SEARCH_QUERY")
        type_name = metadata["duckdb_type"]
        declared_time = metadata.get("sqlite_type", "").upper() in ("DATE", "DATETIME", "TIMESTAMP", "TIME")
        base = {"database_id": self.context.database_id, "snapshot_identity": self.context.identity["logical_sha256"],
                "table": table, "column": column, "type": type_name}
        if declared_time or type_name.startswith(("BIGINT", "INTEGER", "DOUBLE", "DECIMAL", "TIMESTAMP", "DATE")):
            if type_name.startswith(("BIGINT", "INTEGER", "DOUBLE", "DECIMAL")):
                try:
                    if not Decimal(query).is_finite():
                        raise ToolError("NONFINITE_NUMERIC_CONSTRAINT")
                except InvalidOperation as error:
                    raise ToolError("WRONG_CONSTRAINT_TYPE") from error
            elif declared_time or type_name.startswith(("TIMESTAMP", "DATE")):
                try:
                    if metadata.get("sqlite_type", "").upper() == "TIME":
                        time.fromisoformat(query)
                    else:
                        datetime.fromisoformat(query)
                except ValueError as error:
                    raise ToolError("WRONG_CONSTRAINT_TYPE") from error
            return self._record("value_search", arguments, {**base, "resolution": "typed_constraint", "matches": [],
                "domain_complete": False, "constraint_hint": {"kind": "time_threshold" if declared_time else "typed_threshold", "literal": query, "type": type_name}})
        if type_name != "VARCHAR":
            raise ToolError("UNSUPPORTED_SEARCH_TYPE")
        mode = arguments.get("match_kind", "contains")
        if mode not in ("exact", "prefix", "contains"):
            raise ToolError("INVALID_MATCH_KIND")
        _, domain_rows, truncated = self._execute(
            f"SELECT DISTINCT {_quote(column)} FROM {_quote(table)} WHERE {_quote(column)} IS NOT NULL ORDER BY {_quote(column)} LIMIT ?",
            (self.row_cap + 1,),
        )
        if not truncated:
            matches = [row[0] for row in domain_rows if
                       (row[0] == query if mode == "exact" else row[0].startswith(query) if mode == "prefix" else query in row[0])]
        else:
            # A truncated domain is never interpreted as exhaustive or used to prove absence.
            predicate = f"{_quote(column)} = ?" if mode == "exact" else f"starts_with({_quote(column)}, ?)" if mode == "prefix" else f"contains({_quote(column)}, ?)"
            _, matched_rows, _ = self._execute(f"SELECT DISTINCT {_quote(column)} FROM {_quote(table)} WHERE {predicate} ORDER BY {_quote(column)} LIMIT ?", (query, 8))
            matches = [row[0] for row in matched_rows]
        def mint(value):
            witness = {**base, "value": value}
            witness["evidence_id"] = witness_id(witness)
            self.witnesses[witness["evidence_id"]] = witness
            return witness

        witnesses = [mint(value) for value in matches[:8]]
        # Small, complete domains can be cited without spending another search.
        # Larger or truncated domains are never treated as exhaustive witnesses.
        domain_witnesses = [mint(row[0]) for row in domain_rows] if not truncated and len(domain_rows) <= 8 else []
        return self._record("value_search", arguments, {**base, "resolution": "matched" if witnesses else "unresolved",
            "matches": witnesses, "domain_witnesses": domain_witnesses,
            "domain": [row[0] for row in domain_rows] if not truncated else [], "domain_complete": not truncated})

    def sql_probe(self, arguments):
        query = arguments.get("sql")
        validate_sql(query, self.context)
        columns, rows, truncated = self._execute(query)
        return self._record("sql_probe", arguments, {"database_id": self.context.database_id,
            "snapshot_identity": self.context.identity["logical_sha256"], "columns": columns,
            "rows": [[_json_value(value) for value in row] for row in rows], "truncated": truncated})

    def call(self, name, arguments):
        try:
            contracts = {
                "database_profiler": ({"table", "columns"}, {"table"}),
                "value_search": ({"table", "column", "query", "match_kind"}, {"table", "column", "query"}),
                "sql_probe": ({"sql"}, {"sql"}),
            }
            if name not in contracts:
                raise ToolError("TOOL_NOT_ALLOWLISTED")
            allowed, required = contracts[name]
            if not isinstance(arguments, dict) or not required <= arguments.keys() or not arguments.keys() <= allowed:
                raise ToolError("INVALID_TOOL_ARGUMENTS")
            if any(not isinstance(arguments[key], str) for key in required):
                raise ToolError("INVALID_TOOL_ARGUMENTS")
            if "columns" in arguments and (not isinstance(arguments["columns"], list) or any(not isinstance(column, str) for column in arguments["columns"])):
                raise ToolError("INVALID_TOOL_ARGUMENTS")
            return getattr(self, name)(arguments)
        except (ToolError, SafetyError) as error:
            self.trajectory.append({"tool": name, "arguments": arguments, "error_code": str(error)})
            raise
