"""Validate v2 linker meaning against source metadata and observed tool output."""

from __future__ import annotations

from typing import Any

from evaluation.dualsql_lite_ctu_gpt5_v2.tools import V2DatabaseTools


def extract_question_references(question: str, tools: V2DatabaseTools) -> list[dict[str, str]]:
    return tools.source_references(question)


def validate_link(question: str, selected: list[dict[str, Any]],
                  trajectory: list[dict[str, Any]], tools: V2DatabaseTools) -> dict[str, Any]:
    """Reject missing or mismatched source references before a generator call."""
    schema = tools.schema["network_flows"]
    allowed = {item["name"] for item in schema}
    if (not isinstance(selected, list) or len(selected) != 1
            or selected[0].get("table") != "network_flows"):
        return {"error": "INVALID_LINKED_SCHEMA", "grounded_values": [],
                "unresolved_literals": []}
    columns = selected[0].get("columns")
    if (not isinstance(columns, list) or not columns
            or len(columns) != len(set(columns)) or any(column not in allowed for column in columns)):
        return {"error": "INVALID_LINKED_SCHEMA", "grounded_values": [],
                "unresolved_literals": []}
    references = extract_question_references(question, tools)
    reference_error = tools.source_reference_error(question)
    if reference_error:
        return {"error": reference_error, "grounded_values": [], "unresolved_literals": []}
    if any(reference["column"] not in columns for reference in references):
        return {"error": "WRONG_COLUMN_FOR_INTENT", "grounded_values": [],
                "unresolved_literals": [reference["surface"] for reference in references]}
    if len(columns) > max(2, len(schema) // 2):
        return {"error": "OVERBROAD_LINKED_SCHEMA", "grounded_values": [],
                "unresolved_literals": [reference["surface"] for reference in references]}
    values: list[dict[str, str]] = []
    for event in trajectory:
        result = event.get("result", {})
        if not result.get("ok"):
            continue
        if tools.observed_evidence.get(result.get("evidence_id")) != result:
            return {"error": "INVALID_TOOL_PROVENANCE", "grounded_values": [], "unresolved_literals": []}
        observed = list(result.get("matches", []))
        for column, domain in result.get("domains", {}).items():
            observed.extend({"table": "network_flows", "column": column,
                             "value": item["value"], "evidence_id": item["evidence_id"]}
                            for item in domain)
        for item in observed:
            column = item.get("column")
            value = item.get("value")
            if column not in columns or not isinstance(value, str):
                continue
            if column == "source_dataset" and not any(
                    reference["value"] == value for reference in references):
                continue
            if column != "source_dataset" and value.casefold() not in question.casefold():
                continue
            entry = {"table": "network_flows", "column": column,
                     "value": value, "evidence_id": item["evidence_id"]}
            if entry not in values:
                values.append(entry)
    unresolved = [reference["surface"] for reference in references
                  if not any(item["column"] == reference["column"] and
                             item["value"] == reference["value"] for item in values)]
    return {"error": "UNRESOLVED_LITERAL" if unresolved else None,
            "grounded_values": values[:20], "unresolved_literals": unresolved,
            "question_references": references,
            "tables": selected}
