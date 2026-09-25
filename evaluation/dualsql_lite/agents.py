"""Two bounded inference roles sharing one pinned model; gold is scorer-only."""

from __future__ import annotations

import hashlib
import json
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from evaluation.public_pilot.run_model import CAP, MODEL, build_r2_request, cost_usd
from evaluation.text_to_sql import (
    SQLBenchmarkCase, SQLEvaluationResult, _extract_sql, _sql_error_category,
    evaluate_sql_case,
)
from evaluation.dualsql_lite.tools import DatabaseTools, SnapshotOnlyDuckDBSnapshot, TOOL_SCHEMAS


MAX_TURNS = 5
MAX_TOOL_CALLS = 5
LINKER_PROMPT_VERSION = "dualsql_linker_v3"
GENERATOR_PROMPT_VERSION = "dualsql_generator_v1"
LINKER_INSTRUCTIONS = (
    "You are the Schema Linker, not the SQL Generator. Link the question to the evaluation database. "
    "Use database_profiler and value_search to inspect uncertain schema or literals. "
    "SQL probe is available only for inspecting data; never return SQL in your final answer. "
    "Your final answer MUST be one JSON object with exactly tables and grounded_values. "
    "tables is a list of {table, columns} with real table/column names. "
    "grounded_values is a list of {table, column, value} copied exactly from a "
    "database_profiler example or value_search match. The validator attaches provenance. "
    "Do not include a tool ID or values copied only from the question, a SQL probe, "
    "or an empty/failed tool response. If none are verified, use an empty list. "
    "Example shape: {\"tables\":[{\"table\":\"network_flows\",\"columns\":[\"label\"]}],"
    "\"grounded_values\":[]}. Do not return SQL, Markdown or reasoning."
)
GENERATOR_INSTRUCTIONS = (
    "Generate exactly one read-only DuckDB SELECT statement for the question. "
    "Use database tools if enabled to check uncertain schema or values. "
    "Return only the final SQL, no prose or reasoning."
)


class InvalidEvidenceRun(RuntimeError):
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
                 *, model: str = MODEL, temperature: int = 0, cap: int = CAP,
                 before_call: Callable[[dict[str, Any]], None] | None = None,
                 after_call: Callable[[dict[str, Any], dict[str, Any]], None] | None = None):
        if model != MODEL or temperature != 0 or cap != CAP:
            raise ValueError("Evidence series requires one pinned provider configuration")
        self.tools = DatabaseTools(snapshot_path)
        self.snapshot = SnapshotOnlyDuckDBSnapshot(snapshot_path)
        self.client = client
        self.model = model
        self.temperature = temperature
        self.cap = cap
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
            request = {"model": self.model, "temperature": self.temperature,
                       "max_completion_tokens": self.cap, "messages": messages,
                       "tools": TOOL_SCHEMAS if enabled else None}
            if role == "linker":
                request["response_format"] = {"type": "json_object"}
            if self.before_call:
                self.before_call(request)
            start = time.monotonic()
            response = self.client.chat.completions.create(**request)
            latency_ms = round((time.monotonic() - start) * 1000, 3)
            if getattr(response, "model", None) != self.model:
                raise InvalidEvidenceRun("Wrong actual model in provider response")
            telemetry = getattr(response, "usage", None)
            input_tokens = getattr(telemetry, "prompt_tokens", None)
            output_tokens = getattr(telemetry, "completion_tokens", None)
            if (type(input_tokens) is not int or input_tokens <= 0
                    or type(output_tokens) is not int or not 0 <= output_tokens <= self.cap):
                raise InvalidEvidenceRun("Provider usage is missing or outside pinned cap")
            usage.append({"role": role, "turn": turn, "actual_model": response.model,
                          "input_tokens": input_tokens, "output_tokens": output_tokens,
                          "cost_usd": cost_usd(input_tokens, output_tokens),
                          "latency_ms": latency_ms})
            if self.after_call:
                self.after_call(request, usage[-1])
            message = response.choices[0].message
            calls = getattr(message, "tool_calls", None) or []
            if calls:
                if not enabled or len(calls) != 1 or tool_count + len(calls) > MAX_TOOL_CALLS:
                    return _RoleResult(None, turn, tool_count, malformed + 1,
                                       usage, trajectory, "TOOL_LIMIT_OR_UNAVAILABLE")
                messages.append({"role": "assistant", "content": getattr(message, "content", None),
                                 "tool_calls": [{"id": call.id, "type": "function",
                                                 "function": {"name": call.function.name,
                                                              "arguments": call.function.arguments}}
                                                for call in calls]})
                for call in calls:
                    try:
                        arguments = json.loads(call.function.arguments)
                    except (TypeError, ValueError):
                        arguments = None
                    result = self.tools.invoke(call.function.name, arguments)
                    tool_count += 1
                    malformed += int(result.get("error_type") in {"INVALID_ARGUMENTS", "UNKNOWN_TOOL"})
                    trajectory.append({"role": role, "turn": turn, "tool_call_id": call.id,
                                       "tool": call.function.name, "arguments": arguments,
                                       "result": result})
                    messages.append({"role": "tool", "tool_call_id": call.id,
                                     "content": json.dumps(result, default=str, ensure_ascii=True)})
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
        # Never serialize case or gold_sql into agent messages or tools.
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
            system = build_r2_request(question, schema)["messages"][0]["content"]
        elif experiment == "E2":
            system = GENERATOR_INSTRUCTIONS + "\nDatabase schema:\n" + schema
        else:
            system = GENERATOR_INSTRUCTIONS + "\nValidated linked schema:\n" + json.dumps(linked)
            if experiment == "E1":
                system += "\nThe generator has no database tools."
        generator = self._role("generator", question, system, experiment in {"E2", "E3"},
                               one_shot=experiment in {"E0", "E1"})
        recovered = 0
        if linked is not None:
            initial = {(x["table"], col) for x in linked["tables"] for col in x["columns"]}
            for call in generator.trajectory:
                result = call["result"]
                found = {(table["name"], col["name"])
                         for table in result.get("tables", []) for col in table["columns"]}
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
        return {"case_id": case.case_id, "question_sha256": _hash(case.question),
                "category": case.category, "difficulty": case.difficulty,
                "experiment": experiment, "linked_schema": linked,
                "linker_submission": linker.content, "linker_error": linker.error,
                "trajectory": linker.trajectory + generator.trajectory,
                "linker_turns": linker.turns, "linker_tool_calls": linker.tool_count,
                "generator_turns": generator.turns, "generator_tool_calls": generator.tool_count,
                "generator_recovery_events": recovered,
                "malformed_agent_outputs": linker.malformed + generator.malformed,
                "final_sql": sql, "error_category": category,
                "syntax_valid": evaluation.syntax_valid if evaluation else False,
                "execution_success": evaluation.execution_success if evaluation else False,
                "execution_accurate": evaluation.execution_accurate if evaluation else False,
                "safety_rejected": evaluation.safety_rejected if evaluation else False,
                "model_calls": len(telemetry),
                "input_tokens": sum(x["input_tokens"] for x in telemetry),
                "output_tokens": sum(x["output_tokens"] for x in telemetry),
                "cost_usd": sum(x["cost_usd"] for x in telemetry),
                "latency_ms": sum(x["latency_ms"] for x in telemetry),
                "provider_calls": telemetry}
