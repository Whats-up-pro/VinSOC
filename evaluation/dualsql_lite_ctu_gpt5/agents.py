"""CTU-only DualSQL-Lite agents with framework fixes for GPT-5 Mini."""

from __future__ import annotations

import hashlib
import json
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from evaluation.text_to_sql import (
    SQLBenchmarkCase, SQLEvaluationResult, _extract_sql, _sql_error_category,
    evaluate_sql_case,
)
from evaluation.dualsql_lite_ctu_gpt5.tools import DatabaseTools, SnapshotOnlyDuckDBSnapshot, TOOL_SCHEMAS
from evaluation.dualsql_lite_ctu_gpt5.prompts import (
    LINKER_INSTRUCTIONS, GENERATOR_INSTRUCTIONS,
    LINKER_PROMPT_VERSION, GENERATOR_PROMPT_VERSION,
)


MODEL = "gpt-5-mini-2025-08-07"
CAP = 1000
REASONING_EFFORT = "low"
MAX_TURNS = 5
MAX_TOOL_CALLS = 5

class InvalidEvidenceRun(ValueError):
    """Provider or experiment identity cannot support an evidence claim."""


@dataclass
class _RoleResult:
    content: str | None
    turns: int
    tool_count: int
    malformed: int
    usage: list[dict[str, Any]]
    trajectory: list[dict[str, Any]]
    error: str | None = None


def _hash(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


def cost_usd(input_tokens: int, output_tokens: int) -> float:
    """Calculate GPT-5 Mini cost using the pinned 0.25/2.00 USD rates."""
    return (input_tokens * 0.25 + output_tokens * 2.00) / 1_000_000


def validate_linked_schema(raw: str, tools: DatabaseTools,
                           trajectory: list[dict[str, Any]]) -> dict[str, Any]:
    """Accept only declared schema and literals backed by actual tool output."""
    value = json.loads(raw)
    if not isinstance(value, dict) or set(value) != {"tables", "grounded_values"}:
        raise ValueError("Linked schema must have tables and grounded_values only")
    if not isinstance(value["tables"], list) or not isinstance(value["grounded_values"], list):
        raise ValueError("Linked schema fields must be lists")
    if not value["tables"] or len(value["tables"]) > len(tools.schema):
        raise ValueError("Missing or excessive linked tables")
    selected: dict[str, set[str]] = {}
    for entry in value["tables"]:
        if not isinstance(entry, dict) or set(entry) != {"table", "columns"}:
            raise ValueError("Malformed linked table")
        table, columns = entry["table"], entry["columns"]
        if (not isinstance(table, str) or table not in tools.schema or table in selected
                or not isinstance(columns, list) or not columns
                or len(columns) != len(set(columns))
                or any(col not in {c["name"] for c in tools.schema[table]}
                       for col in columns)):
            raise ValueError("Invented table or column")
        selected[table] = set(columns)
    observed: dict[tuple[str, str, str], str] = {}
    for call in trajectory:
        result = call["result"]
        if not result.get("ok"):
            continue
        grounded = set()
        for match in result.get("matches", []):
            grounded.add((match["table"], match["column"], str(match["value"])))
        for table in result.get("tables", []):
            for col in table.get("columns", []):
                grounded.update((table["name"], col["name"], str(example))
                                for example in col.get("examples", []))
        for triple in grounded:
            observed.setdefault(triple, call["tool_call_id"])
    verified = []
    for item in value["grounded_values"]:
        if not isinstance(item, dict) or set(item) != {"table", "column", "value"}:
            raise ValueError("Malformed grounded value")
        table, col = item["table"], item["column"]
        key = (table, col, str(item["value"]))
        if (table not in selected or col not in selected[table]
                or key not in observed):
            raise ValueError("Invented or untraceable grounded value")
        verified.append({**item, "tool_call_id": observed[key]})
    return {**value, "grounded_values": verified}


class DualSQLCaseRunner:
    """Run E0-E3 for one question; expose gold only to the final evaluator."""

    def __init__(self, snapshot_path: str | Path, client: Any,
                 before_call: Callable[[dict[str, Any]], None] | None = None,
                 after_call: Callable[[dict[str, Any], dict[str, Any]], None] | None = None):
        self.tools = DatabaseTools(snapshot_path)
        self.snapshot = SnapshotOnlyDuckDBSnapshot(snapshot_path)
        self.client = client
        self.before_call = before_call
        self.after_call = after_call

    def _role(self, role: str, question: str, system: str, enabled: bool,
              *, one_shot: bool = False) -> _RoleResult:
        messages: list[dict[str, Any]] = [{"role": "system", "content": system},
                                          {"role": "user", "content": question}]
        trajectory: list[dict[str, Any]] = []
        usage: list[dict[str, Any]] = []
        tool_count = malformed = 0
        for turn in range(1, 2 if one_shot else MAX_TURNS + 1):
            request = {
                "model": MODEL,
                "reasoning_effort": REASONING_EFFORT,
                "max_completion_tokens": CAP,
                "messages": messages,
                "tools": TOOL_SCHEMAS if enabled else None
            }
            if role == "linker":
                request["response_format"] = {"type": "json_object"}
            if self.before_call:
                self.before_call(request)
            start = time.monotonic()
            response = self.client.chat.completions.create(**request)
            latency_ms = round((time.monotonic() - start) * 1000, 3)
            if getattr(response, "model", None) != MODEL:
                raise InvalidEvidenceRun("Wrong actual model in provider response")
            telemetry = getattr(response, "usage", None)
            input_tokens = getattr(telemetry, "prompt_tokens", None)
            output_tokens = getattr(telemetry, "completion_tokens", None)
            if (type(input_tokens) is not int or input_tokens <= 0
                    or type(output_tokens) is not int or not 0 <= output_tokens <= CAP):
                raise InvalidEvidenceRun("Provider usage is missing or outside pinned cap")
            usage.append({
                "role": role, "turn": turn, "actual_model": response.model,
                "input_tokens": input_tokens, "output_tokens": output_tokens,
                "cost_usd": cost_usd(input_tokens, output_tokens),
                "latency_ms": latency_ms
            })
            if self.after_call:
                self.after_call(request, usage[-1])
            message = response.choices[0].message
            calls = getattr(message, "tool_calls", None) or []
            if calls:
                if not enabled or tool_count + len(calls) > MAX_TOOL_CALLS:
                    return _RoleResult(None, turn, tool_count, malformed + 1,
                                       usage, trajectory, "TOOL_LIMIT_OR_UNAVAILABLE")
                messages.append({
                    "role": "assistant",
                    "content": getattr(message, "content", None),
                    "tool_calls": [{
                        "id": call.id,
                        "type": "function",
                        "function": {
                            "name": call.function.name,
                            "arguments": call.function.arguments
                        }
                    } for call in calls]
                })
                for call in calls:
                    try:
                        arguments = json.loads(call.function.arguments)
                    except (TypeError, ValueError):
                        arguments = None
                    result = self.tools.invoke(call.function.name, arguments)
                    tool_count += 1
                    malformed += int(result.get("error_type") in {"INVALID_ARGUMENTS", "UNKNOWN_TOOL"})
                    trajectory.append({
                        "role": role, "turn": turn, "tool_call_id": call.id,
                        "tool": call.function.name, "arguments": arguments,
                        "result": result
                    })
                    messages.append({
                        "role": "tool",
                        "tool_call_id": call.id,
                        "content": json.dumps(result, default=str, ensure_ascii=True)
                    })
                continue
            content = getattr(message, "content", None)
            if not isinstance(content, str) or not content.strip():
                return _RoleResult(None, turn, tool_count, malformed + 1, usage,
                                   trajectory, "EMPTY_FINAL_SUBMISSION")
            return _RoleResult(content.strip(), turn, tool_count, malformed,
                               usage, trajectory)
        return _RoleResult(None, MAX_TURNS, tool_count, malformed + 1, usage,
                           trajectory, "TURN_LIMIT")

    def run_case(self, case: SQLBenchmarkCase, experiment: str) -> dict[str, Any]:
        if experiment not in {"E0", "E1", "E2", "E3"}:
            raise ValueError("Unknown architecture condition")
        question = case.question
        schema = self.tools.schema_context()
        linked = None
        linker = _RoleResult(None, 0, 0, 0, [], [])
        if experiment in {"E1", "E3"}:
            linker = self._role("linker", question,
                                LINKER_INSTRUCTIONS + "\nDatabase schema:\n" + schema, True)
            if linker.content:
                try:
                    linked = validate_linked_schema(linker.content, self.tools, linker.trajectory)
                except (ValueError, KeyError, TypeError, json.JSONDecodeError) as exc:
                    linker.error = f"INVALID_LINKED_SCHEMA: {str(exc)[:200]}"
            if linked is None:
                return self._result(case, experiment, linker, _RoleResult(None, 0, 0, 0, [], []),
                                    None, None, "LINKER_FORMAT_OR_LIMIT_FAILURE", 0)

        if experiment == "E0":
            system = GENERATOR_INSTRUCTIONS + "\nDatabase schema:\n" + schema
            generator = self._role("generator", question, system, False, one_shot=True)
        elif experiment == "E2":
            system = GENERATOR_INSTRUCTIONS + "\nDatabase schema:\n" + schema
            generator = self._role("generator", question, system, True)
        else:
            system = GENERATOR_INSTRUCTIONS + "\nValidated linked schema:\n" + json.dumps(linked)
            if experiment == "E1":
                system += "\nThe generator has no database tools."
            generator = self._role("generator", question, system, experiment == "E3",
                                   one_shot=experiment == "E1")

        recovered = 0
        if linked is not None:
            initial = {(x["table"], col) for x in linked["tables"] for col in x["columns"]}
            for call in generator.trajectory:
                result = call["result"]
                found = {(table["name"], col["name"])
                         for table in result.get("tables", []) for col in table.get("columns", [])}
                found.update((m["table"], m["column"]) for m in result.get("matches", []))
                recovered += int(bool(found - initial))

        if generator.content is None:
            return self._result(case, experiment, linker, generator, linked, None,
                                "GENERATOR_FORMAT_OR_LIMIT_FAILURE", recovered)
        sql = _extract_sql(generator.content)
        evaluation = evaluate_sql_case(case, sql, self.snapshot)
        return self._result(case, experiment, linker, generator, linked, sql,
                            _sql_error_category(evaluation), recovered, evaluation)

    @staticmethod
    def _result(case: SQLBenchmarkCase, experiment: str, linker: _RoleResult,
                generator: _RoleResult, linked: dict[str, Any] | None,
                sql: str | None, category: str, recovered: int,
                evaluation: SQLEvaluationResult | None = None) -> dict[str, Any]:
        telemetry = linker.usage + generator.usage
        return {
            "case_id": case.case_id,
            "question_sha256": _hash(case.question),
            "category": case.category,
            "difficulty": case.difficulty,
            "experiment": experiment,
            "linked_schema": linked,
            "linker_submission": linker.content,
            "linker_error": linker.error,
            "trajectory": linker.trajectory + generator.trajectory,
            "linker_turns": linker.turns,
            "linker_tool_calls": linker.tool_count,
            "generator_turns": generator.turns,
            "generator_tool_calls": generator.tool_count,
            "generator_recovery_events": recovered,
            "malformed_agent_outputs": linker.malformed + generator.malformed,
            "final_sql": sql,
            "error_category": category,
            "syntax_valid": evaluation.syntax_valid if evaluation else False,
            "execution_success": evaluation.execution_success if evaluation else False,
            "execution_accurate": evaluation.execution_accurate if evaluation else False,
            "safety_rejected": evaluation.safety_rejected if evaluation else False,
            "model_calls": len(telemetry),
            "input_tokens": sum(x["input_tokens"] for x in telemetry),
            "output_tokens": sum(x["output_tokens"] for x in telemetry),
            "cost_usd": sum(x["cost_usd"] for x in telemetry),
            "latency_ms": sum(x["latency_ms"] for x in telemetry),
            "provider_calls": telemetry
        }


@dataclass(frozen=True)
class ProviderCall:
    """The charged response identity persisted before any content parsing."""

    response_id: str
    actual_model: str
    input_tokens: int
    output_tokens: int
    cost_usd: float
    latency_ms: float
    role: str
    turn: int


@dataclass
class RoleResult:
    content: str | None
    model_turns: int
    db_tool_calls: int
    trajectory: list[dict[str, Any]]
    provider_calls: list[ProviderCall]
    selected_schema: list[dict[str, Any]] | None = None
    grounded_values: list[dict[str, Any]] | None = None
    question_literals: list[dict[str, str]] | None = None
    error: str | None = None
    malformed: int = 0

    @property
    def turns(self) -> int:
        return self.model_turns

    @property
    def tool_count(self) -> int:
        return self.db_tool_calls

    @property
    def linked_schema(self) -> dict[str, Any] | None:
        if self.selected_schema is None:
            return None
        return {"tables": self.selected_schema,
                "grounded_values": self.grounded_values or [],
                "question_literals": self.question_literals or []}


def _selected_schema(content: str, tools: DatabaseTools) -> list[dict[str, Any]]:
    """Accept schema names only; tool values are attached by this controller."""
    try:
        payload = json.loads(content)
    except (TypeError, ValueError) as exc:
        raise ValueError("Invalid linked schema JSON") from exc
    if not isinstance(payload, dict) or set(payload) != {"tables"}:
        raise ValueError("Linked schema must contain only tables")
    tables = payload["tables"]
    if not isinstance(tables, list) or not 1 <= len(tables) <= len(tools.schema):
        raise ValueError("Invalid linked table count")
    selected = []
    seen = set()
    for item in tables:
        if not isinstance(item, dict) or set(item) != {"table", "columns"}:
            raise ValueError("Invalid linked table")
        table, columns = item["table"], item["columns"]
        if (not isinstance(table, str) or table not in tools.schema or table in seen
                or not isinstance(columns, list) or not columns
                or any(not isinstance(column, str) for column in columns)
                or len(columns) != len(set(columns))
                or any(column not in {c["name"] for c in tools.schema[table]}
                       for column in columns)):
            raise ValueError("Invented linked table or column")
        selected.append({"table": table, "columns": columns})
        seen.add(table)
    return selected


def _question_literals(question: str) -> list[dict[str, str]]:
    """Keep explicitly quoted question values separate from database evidence."""
    values = dict.fromkeys(match.group(2) for match in
                           __import__("re").finditer(r"(['\"])(.*?)\1", question)
                           if match.group(2))
    return [{"value": value, "evidence_class": "question"}
            for value in list(values)[:20]]


def run_role(
    *,
    role: str,
    question: str,
    system_prompt: str,
    tools: DatabaseTools | None,
    client: Any,
    telemetry_sink: Callable[[ProviderCall], None],
    max_turns: int = MAX_TURNS,
) -> RoleResult:
    """Run one bounded role with native tool calls and charged telemetry first."""
    if role not in {"linker", "generator"} or not 1 <= max_turns <= MAX_TURNS:
        raise ValueError("Invalid role or turn limit")
    messages: list[dict[str, Any]] = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": question},
    ]
    trajectory: list[dict[str, Any]] = []
    charged: list[ProviderCall] = []
    tool_count = 0
    malformed = 0

    def finish(turn: int, *, content: str | None = None,
               error: str | None = None) -> RoleResult:
        result = RoleResult(content, turn, tool_count, trajectory, charged,
                            question_literals=_question_literals(question), error=error,
                            malformed=malformed)
        if error is None and role == "linker":
            if tools is None:
                result.error = "INVALID_LINKED_SCHEMA"
                return result
            try:
                result.selected_schema = _selected_schema(content or "", tools)
            except ValueError:
                result.error = "INVALID_LINKED_SCHEMA"
                return result
            allowed = {(item["table"], column) for item in result.selected_schema
                       for column in item["columns"]}
            values: list[dict[str, Any]] = []
            for event in trajectory:
                for match in event["result"].get("matches", []):
                    if (match["table"], match["column"]) in allowed:
                        values.append({"table": match["table"], "column": match["column"],
                                       "value": match["value"],
                                       "evidence_id": match["evidence_id"]})
            result.grounded_values = values[:20]
        return result

    for turn in range(1, max_turns + 1):
        request: dict[str, Any] = {
            "model": MODEL,
            "reasoning_effort": REASONING_EFFORT,
            "max_completion_tokens": CAP,
            "messages": messages,
        }
        if tools is not None:
            request["tools"] = TOOL_SCHEMAS
        if role == "linker":
            request["response_format"] = {"type": "json_object"}
        started = time.monotonic()
        response = client.chat.completions.create(**request)
        latency_ms = round((time.monotonic() - started) * 1000, 3)
        response_id = getattr(response, "id", None)
        actual_model = getattr(response, "model", None)
        usage = getattr(response, "usage", None)
        input_tokens = getattr(usage, "prompt_tokens", None)
        output_tokens = getattr(usage, "completion_tokens", None)
        total_tokens = getattr(usage, "total_tokens", None)
        if not isinstance(response_id, str) or not response_id:
            raise InvalidEvidenceRun("Provider response ID is missing")
        if (type(input_tokens) is not int or input_tokens <= 0
                or type(output_tokens) is not int or not 0 <= output_tokens <= CAP
                or (total_tokens is not None and
                    (type(total_tokens) is not int or
                     total_tokens != input_tokens + output_tokens))):
            raise InvalidEvidenceRun("Provider charged usage is missing")
        call = ProviderCall(response_id, str(actual_model), input_tokens,
                            output_tokens, cost_usd(input_tokens, output_tokens),
                            latency_ms, role, turn)
        telemetry_sink(call)
        charged.append(call)
        if actual_model != MODEL:
            raise InvalidEvidenceRun("Wrong actual model in provider response")

        try:
            message = response.choices[0].message
            tool_calls = getattr(message, "tool_calls", None) or []
        except (AttributeError, IndexError, TypeError):
            return finish(turn, error="MALFORMED_RESPONSE")
        if tool_calls:
            if tools is None:
                return finish(turn, error="TOOL_UNAVAILABLE")
            if tool_count + len(tool_calls) > MAX_TOOL_CALLS:
                return finish(turn, error="TOOL_LIMIT")
            assistant_calls = []
            for native in tool_calls:
                try:
                    tool_id = native.id
                    tool_name = native.function.name
                    arguments = json.loads(native.function.arguments)
                except (AttributeError, TypeError, ValueError):
                    tool_id = getattr(native, "id", "malformed-tool")
                    tool_name = getattr(getattr(native, "function", None), "name", "")
                    arguments = None
                if not isinstance(arguments, dict):
                    malformed += 1
                    result = {"ok": False, "error_type": "INVALID_ARGUMENTS"}
                else:
                    result = tools.invoke(tool_name, arguments)
                tool_count += 1
                trajectory.append({"role": role, "turn": turn, "tool_call_id": tool_id,
                                   "tool": tool_name, "arguments": arguments,
                                   "result": result})
                assistant_calls.append({"id": tool_id, "type": "function",
                                        "function": {"name": tool_name,
                                                     "arguments": getattr(
                                                         getattr(native, "function", None),
                                                         "arguments", "")}})
            messages.append({"role": "assistant", "content": getattr(message, "content", None),
                             "tool_calls": assistant_calls})
            for event in trajectory[-len(tool_calls):]:
                messages.append({"role": "tool", "tool_call_id": event["tool_call_id"],
                                 "content": json.dumps(event["result"], default=str)})
            continue
        content = getattr(message, "content", None)
        if not isinstance(content, str) or not content.strip():
            return finish(turn, error="EMPTY_FINAL_SUBMISSION")
        return finish(turn, content=content.strip())
    return finish(max_turns, error="TURN_LIMIT")
