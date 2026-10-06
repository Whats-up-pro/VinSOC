"""Evaluator-only DB tool schema; production tool schemas are unchanged."""
def _tool(name, properties, required):
    return {"type": "function", "function": {"name": name, "parameters": {
        "type": "object", "properties": properties, "required": required, "additionalProperties": False,
    }}}


STRING = {"type": "string"}
TOOLS = [
    _tool("database_profiler", {"table": STRING, "columns": {"type": "array", "items": STRING}}, ["table"]),
    _tool("value_search", {"table": STRING, "column": STRING, "query": STRING,
        "match_kind": {"type": "string", "enum": ["exact", "prefix", "contains"]}}, ["table", "column", "query"]),
    _tool("sql_probe", {"sql": STRING}, ["sql"]),
]
