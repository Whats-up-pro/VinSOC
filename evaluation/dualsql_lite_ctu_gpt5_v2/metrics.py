"""Diagnostic-only metrics; the locked text-to-SQL scorer is unchanged."""

from __future__ import annotations

import re
from typing import Any

from evaluation.dualsql_lite_ctu_gpt5.tools import CATALOG_DISTINCT_LIMIT
from evaluation.dualsql_lite_ctu_gpt5_v2.tools import V2DatabaseTools


_STRING_PREDICATE = re.compile(
    r"\b(?P<column>[a-z_][a-z_0-9]*)\s*(?P<operator>=|ILIKE|LIKE)\s*"
    r"'(?P<literal>(?:''|[^'])*)'", re.IGNORECASE)


def linker_column_precision(selected: list[str], gold: list[str]) -> float | None:
    """Compute diagnostic precision after scoring, never during inference."""
    if not selected:
        return None
    return len(set(selected) & set(gold)) / len(set(selected))


def inspect_sql_literals(sql: str, tools: V2DatabaseTools) -> list[dict[str, Any]]:
    """Label supported string predicates; do not reject or rescore SQL."""
    known_columns = {item["name"] for item in tools.schema["network_flows"]}
    results: list[dict[str, Any]] = []
    for match in _STRING_PREDICATE.finditer(sql):
        column = match.group("column")
        if column not in known_columns:
            continue
        literal = match.group("literal").replace("''", "'")
        operator = match.group("operator").upper()
        catalog = [item["value"] for item in tools.catalog if item["column"] == column]
        if not catalog:
            continue
        if operator == "=":
            found = literal in catalog
        else:
            # SQL LIKE '%' and '_' are wildcards. ILIKE is case insensitive.
            pattern = "^" + "".join(
                ".*" if char == "%" else "." if char == "_" else re.escape(char)
                for char in literal) + "$"
            flags = re.IGNORECASE if operator == "ILIKE" else 0
            found = any(re.match(pattern, value, flags) is not None for value in catalog)
        status = ("grounded" if found else
                  "unknown" if len(catalog) >= CATALOG_DISTINCT_LIMIT else
                  "ungrounded")
        results.append({"column": column, "operator": operator,
                        "literal": literal, "status": status})
    return results
