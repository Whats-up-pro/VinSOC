"""v2 tools - CTU-only, with ambiguity detection for grounding."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

TOOL_VERSION = "dualsql_lite_ctu_gpt5_v2_remediation_tools_v1"

# Preserve the source-metadata API introduced at 92e20d5. The CTUDatabaseTools
# implementation used by the recorded frozen attempts remains separate below.
from evaluation.dualsql_lite_ctu_gpt5_v2.source_tools import V2DatabaseTools
TOOL_SCHEMAS = [
    {"type": "function", "function": {"name": "database_profiler",
        "description": "Inspect table structure and column types.",
        "parameters": {"type": "object", "properties": {
            "table": {"type": "string"}}, "additionalProperties": False}}},
    {"type": "function", "function": {"name": "value_search",
        "description": "Search actual stored values. Returns exact table.column.value matches.",
        "parameters": {"type": "object", "properties": {
            "query": {"type": "string", "description": "Search term"},
            "table": {"type": "string"},
            "column": {"type": "string"}}, "required": ["query"],
            "additionalProperties": False}}},
    {"type": "function", "function": {"name": "sql_probe",
        "description": "Run bounded SELECT to inspect data.",
        "parameters": {"type": "object", "properties": {
            "sql": {"type": "string"}}, "required": ["sql"],
            "additionalProperties": False}}},
]


def _quote(ident: str) -> str:
    return '"' + ident.replace('"', '""') + '"'


class CTUDatabaseTools:
    """CTU-only tools with value catalog."""

    def __init__(self, snapshot_path: str | Path):
        import duckdb
        self.snapshot_path = Path(snapshot_path)
        if not self.snapshot_path.is_file():
            raise ValueError("Snapshot not found")

        with duckdb.connect(str(self.snapshot_path), read_only=True) as conn:
            rows = conn.execute(
                "SELECT table_name, column_name, data_type FROM information_schema.columns "
                "WHERE table_schema='main' ORDER BY table_name, ordinal_position"
            ).fetchall()

            self.schema: dict[str, list[dict[str, str]]] = {}
            for table, column, dtype in rows:
                if table in {"network_flows", "dataset_provenance"}:
                    self.schema.setdefault(table, []).append({"name": column, "type": dtype})

            # Build value catalog
            self.catalog: list[dict] = []
            for table, columns in sorted(self.schema.items()):
                for col in columns:
                    if col["type"].upper() in {"VARCHAR", "TEXT"}:
                        vals = conn.execute(
                            f"SELECT DISTINCT {_quote(col['name'])} FROM {_quote(table)} "
                            f"WHERE {_quote(col['name'])} IS NOT NULL ORDER BY {_quote(col['name'])} LIMIT 5000"
                        ).fetchall()
                        for v in vals:
                            if len(str(v[0]).encode()) <= 512:
                                self.catalog.append({
                                    "table": table,
                                    "column": col["name"],
                                    "value": str(v[0])
                                })

    def _connect(self):
        import duckdb
        return duckdb.connect(str(self.snapshot_path), read_only=True)

    def schema_context(self, tables: list[str] | None = None) -> str:
        selected = tables if tables else sorted(self.schema)
        return "\n".join(
            f"{t}({', '.join(c['name'] + ' ' + c['type'] for c in self.schema[t])})"
            for t in selected if t in self.schema
        )

    def database_profiler(self, args: dict) -> dict:
        table = args.get("table")
        if table and table not in self.schema:
            return {"ok": False, "error_type": "INVALID_ARGUMENTS"}

        tables = [table] if table else sorted(self.schema)
        result = {"ok": True, "tables": []}

        for name in tables:
            cols = []
            for col in self.schema[name]:
                examples = [v["value"] for v in self.catalog
                           if v["table"] == name and v["column"] == col["name"]]
                cols.append({
                    "name": col["name"],
                    "type": col["type"],
                    "examples": examples[:5]
                })
            result["tables"].append({"name": name, "columns": cols})

        return result

    def value_search(self, args: dict) -> dict:
        """
        Search for stored values.
        Returns matches with ambiguity flag if single-digit query matches too many values.
        """
        query = args.get("query", "")
        table = args.get("table")
        column = args.get("column")

        if not query or not isinstance(query, str):
            return {"ok": False, "error_type": "INVALID_ARGUMENTS"}

        # Build candidates
        candidates = [v for v in self.catalog
                    if (not table or v["table"] == table)
                    and (not column or v["column"] == column)]

        # Exact substring match first
        exact = [v for v in candidates if query.lower() in v["value"].lower()]
        if exact:
            candidates = exact

        # Word/token match
        terms = set(re.findall(r"[a-z]+|\d+", query.casefold()))
        if not exact:
            candidates = [v for v in candidates
                         if terms & set(re.findall(r"[a-z]+|\d+", v["value"].casefold()))]

        # Limit
        hits = []
        seen: dict[tuple[str, str], int] = {}
        ambiguous = False

        for v in candidates:
            key = (v["table"], v["column"])
            if seen.get(key, 0) < 5:
                hits.append(v)
                seen[key] = seen.get(key, 0) + 1
            if len(hits) >= 50:
                break

        # Ambiguity detection: single digit or very short query
        if len(query) <= 2 or query.isdigit():
            # Count total matches across all columns
            total_matches = sum(1 for v in candidates)
            if total_matches > 10:
                ambiguous = True

        return {
            "ok": True,
            "matches": hits,
            "truncated": len(candidates) > len(hits),
            "ambiguous": ambiguous,
            "query": query,
            "total_matches": len(candidates),
        }

    def sql_probe(self, args: dict) -> dict:
        import duckdb
        sql = args.get("sql", "")
        if len(sql) > 4000:
            return {"ok": False, "error_type": "INVALID_ARGUMENTS"}

        # Basic safety check
        normalized = sql.lower()
        blocked = any(x in normalized for x in [
            "information_schema", "pg_catalog", "sqlite_master",
            "duckdb_", "read_", "pragma_", "attach"
        ])
        if blocked or '"' in sql or '`' in sql:
            return {"ok": False, "error_type": "SAFETY_REJECTION"}

        try:
            with self._connect() as conn:
                cursor = conn.execute(f"SELECT * FROM ({sql}) AS t LIMIT 21")
                cols = [c[0] for c in cursor.description]
                rows = [dict(zip(cols, r)) for r in cursor.fetchall()]
            return {
                "ok": True,
                "columns": cols,
                "rows": rows[:20],
                "truncated": len(rows) > 20,
            }
        except Exception:
            return {"ok": False, "error_type": "EXECUTION_ERROR"}

    def invoke(self, name: str, args: dict) -> dict:
        handlers = {
            "database_profiler": self.database_profiler,
            "value_search": self.value_search,
            "sql_probe": self.sql_probe,
        }
        if name not in handlers:
            return {"ok": False, "error_type": "UNKNOWN_TOOL"}
        return handlers[name](args)
