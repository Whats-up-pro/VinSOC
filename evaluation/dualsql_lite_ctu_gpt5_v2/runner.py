"""v2 runner - controller validates grounded values on run_role path."""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from evaluation.dualsql_lite_ctu_gpt5_v2.prompts import (
    GENERATOR_INSTRUCTIONS, GENERATOR_PROMPT_VERSION,
    LINKER_INSTRUCTIONS, LINKER_PROMPT_VERSION,
)
from evaluation.dualsql_lite_ctu_gpt5_v2.tools import V2DatabaseTools, TOOL_SCHEMAS


MODEL = "gpt-5-mini-2025-08-07"
CAP = 1000
REASONING_EFFORT = "low"
MAX_TURNS = 5


@dataclass
class RoleResult:
    content: str | None
    turns: int
    tool_count: int
    error: str | None = None
    linked_schema: dict | None = None
    usage: list[dict] = field(default_factory=list)


def cost_usd(input_tokens: int, output_tokens: int) -> float:
    """GPT-5 Mini: $0.25/1M input, $2.00/1M output."""
    return (input_tokens * 0.25 + output_tokens * 2.00) / 1_000_000


def validate_linked_schema(raw: str, tools: V2DatabaseTools,
                           trajectory: list[dict]) -> tuple[dict, list[str]]:
    """
    Validate linked schema on v2 path.
    Returns (validated_schema, errors).
    Errors include provenance failures.
    """
    errors = []
    try:
        value = json.loads(raw)
    except json.JSONDecodeError as e:
        return {}, [f"Invalid JSON: {e}"]

    if not isinstance(value, dict):
        return {}, ["Schema must be JSON object"]
    if "tables" not in value:
        errors.append("Missing 'tables' field")
    if "grounded_values" not in value:
        errors.append("Missing 'grounded_values' field")
    if errors:
        return {}, errors

    tables = value.get("tables", [])
    grounded = value.get("grounded_values", [])

    if not isinstance(tables, list):
        return {}, ["'tables' must be list"]
    if not isinstance(grounded, list):
        return {}, ["'grounded_values' must be list"]

    # Track observed values from tool output
    observed: dict[tuple[str, str, str], str] = {}
    for call in trajectory:
        result = call.get("result", {})
        if not result.get("ok"):
            continue
        # From value_search matches
        for match in result.get("matches", []):
            key = (match.get("table", ""), match.get("column", ""), str(match.get("value", "")))
            observed[key] = call.get("tool_call_id", "")
        # From profiler column examples
        for table in result.get("tables", []):
            for col in table.get("columns", []):
                for example in col.get("examples", []):
                    key = (table.get("name", ""), col.get("name", ""), str(example))
                    observed[key] = call.get("tool_call_id", "")

    # Validate table names
    selected_tables = {}
    for entry in tables:
        if not isinstance(entry, dict):
            errors.append(f"Invalid table entry: {entry}")
            continue
        table = entry.get("table")
        columns = entry.get("columns", [])
        if not isinstance(table, str) or table not in tools.schema:
            errors.append(f"Unknown table: {table}")
            continue
        if not isinstance(columns, list):
            errors.append(f"Columns must be list for {table}")
            continue
        selected_tables[table] = set(columns)

    # Validate grounded values - MUST have tool provenance
    validated_values = []
    for gv in grounded:
        if not isinstance(gv, dict):
            errors.append(f"Invalid grounded_value: {gv}")
            continue
        table = gv.get("table")
        column = gv.get("column")
        gv_value = str(gv.get("value", ""))
        if not all([table, column, gv_value]):
            errors.append(f"Incomplete grounded_value: {gv}")
            continue
        # Check provenance
        key = (table, column, gv_value)
        if key not in observed:
            errors.append(f"Value '{gv_value}' in {table}.{column} has no tool provenance")
            continue
        validated_values.append({**gv, "provenance_call_id": observed[key]})

    if errors:
        return {}, errors

    return {"tables": tables, "grounded_values": validated_values}, []


def run_role(
    role: str,
    question: str,
    system_prompt: str,
    tools: V2DatabaseTools | None,
    client,
    max_turns: int = 1,
    telemetry_sink: Any = None,
) -> RoleResult:
    """
    Run one role (linker or generator) with tools.
    Controller validates linked_schema provenance.
    """
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": question},
    ]

    trajectory = []
    tool_count = 0
    usage = []

    for turn in range(1, max_turns + 1):
        request = {
            "model": MODEL,
            "reasoning_effort": REASONING_EFFORT,
            "max_completion_tokens": CAP,
            "messages": messages,
            "tools": TOOL_SCHEMAS if tools else None,
        }
        if role == "linker":
            request["response_format"] = {"type": "json_object"}

        start = time.monotonic()
        response = client.chat.completions.create(**request)
        latency_ms = (time.monotonic() - start) * 1000

        # Extract usage
        tel = {
            "role": role,
            "turn": turn,
            "model": response.model,
            "input_tokens": response.usage.prompt_tokens,
            "output_tokens": response.usage.completion_tokens,
            "cost_usd": cost_usd(response.usage.prompt_tokens, response.usage.completion_tokens),
            "latency_ms": latency_ms,
        }
        usage.append(tel)
        if telemetry_sink:
            telemetry_sink(request, tel)

        message = response.choices[0].message
        calls = getattr(message, "tool_calls", None) or []

        if calls:
            if not tools:
                return RoleResult(None, turn, tool_count, "TOOLS_DISABLED")

            messages.append({
                "role": "assistant",
                "content": getattr(message, "content", None),
                "tool_calls": [{
                    "id": c.id,
                    "type": "function",
                    "function": {"name": c.function.name, "arguments": c.function.arguments}
                } for c in calls]
            })

            for call in calls:
                tool_count += 1
                try:
                    args = json.loads(call.function.arguments)
                except:
                    args = {}
                result = tools.invoke(call.function.name, args)
                trajectory.append({
                    "role": role,
                    "turn": turn,
                    "tool_call_id": call.id,
                    "tool": call.function.name,
                    "arguments": args,
                    "result": result,
                })
                messages.append({
                    "role": "tool",
                    "tool_call_id": call.id,
                    "content": json.dumps(result, default=str),
                })
            continue

        content = getattr(message, "content", None)
        if not content:
            return RoleResult(None, turn, tool_count, "EMPTY_RESPONSE")

        # Final submission
        linked_schema = None
        if role == "linker" and tools:
            validated, errors = validate_linked_schema(content, tools, trajectory)
            if errors:
                return RoleResult(content, turn, tool_count, f"LINKER_VALIDATION: {errors[0]}")
            linked_schema = validated

        return RoleResult(content.strip(), turn, tool_count, None, linked_schema, usage)

    return RoleResult(None, max_turns, tool_count, "TURN_LIMIT")


def run_case(
    case,
    condition: str,
    tools: V2DatabaseTools,
    client,
    schema_context: str,
) -> dict:
    """Run one case for v2 evaluation."""
    linked = None

    # Linker path (E1, E3)
    if condition in {"E1", "E3"}:
        linker = run_role(
            "linker", case.question,
            LINKER_INSTRUCTIONS + "\nDatabase schema:\n" + schema_context,
            tools, client, max_turns=5
        )
        if linker.error:
            return _result(case, condition, linker, None, linked, None, linker.error)
        linked = linker.linked_schema

    # Generator path
    if condition == "E0":
        system = GENERATOR_INSTRUCTIONS + "\nDatabase schema:\n" + schema_context
        tools_enabled = None
        max_turns = 1
    elif condition == "E1":
        system = GENERATOR_INSTRUCTIONS + "\nLinked schema:\n" + json.dumps(linked or {})
        tools_enabled = None
        max_turns = 1
    elif condition == "E2":
        system = GENERATOR_INSTRUCTIONS + "\nDatabase schema:\n" + schema_context
        tools_enabled = tools
        max_turns = 5
    else:  # E3
        system = GENERATOR_INSTRUCTIONS + "\nLinked schema:\n" + json.dumps(linked or {})
        tools_enabled = tools
        max_turns = 5

    generator = run_role("generator", case.question, system, tools_enabled, client, max_turns)

    if generator.error:
        return _result(case, condition, None, generator, linked, None, generator.error)

    sql = generator.content
    return _result(case, condition, None, generator, linked, sql, "OK")


def _result(case, condition, linker, generator, linked, sql, error) -> dict:
    usage = []
    if linker:
        usage.extend(linker.usage)
    if generator:
        usage.extend(generator.usage)

    return {
        "case_id": case.case_id,
        "condition": condition,
        "linked_schema": linked,
        "error_category": error,
        "final_sql": sql,
        "syntax_valid": sql is not None,
        "usage": usage,
        "total_cost_usd": sum(u["cost_usd"] for u in usage),
    }
