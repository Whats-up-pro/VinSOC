"""Offline remediation controller: one fail-closed gate, complete response telemetry."""
from __future__ import annotations

import json
import time
from dataclasses import asdict, dataclass, field
from typing import Any, Callable

from evaluation.r2_phase2.grounding import validate_link, Phase2Tools as V2DatabaseTools
from evaluation.dualsql_lite_ctu_gpt5_v2.prompts import GENERATOR_INSTRUCTIONS, LINKER_INSTRUCTIONS
from evaluation.dualsql_lite_ctu_gpt5_v2.tools import TOOL_SCHEMAS

MODEL = "gpt-5-mini-2025-08-07"
CAP = 1000
REASONING_EFFORT = "low"
MAX_TURNS = 5
MAX_DB_CALLS = 5
CONTROLLER_VERSION = "r2_generalized_controller_v3"


@dataclass
class RoleResult:
    content: str | None
    turns: int
    tool_count: int
    error: str | None = None
    linked_schema: dict | None = None
    usage: list[dict] = field(default_factory=list)
    trajectory: list[dict] = field(default_factory=list)
    attempted_calls: int = 0
    response_count: int = 0
    cost_unknown: bool = False


def cost_usd(input_tokens: int, output_tokens: int) -> float:
    return (input_tokens * .25 + output_tokens * 2) / 1_000_000


def validate_linked_schema(raw: str, tools: V2DatabaseTools, trajectory: list[dict],
                           question: str = "") -> tuple[dict, list[str]]:
    """Compatibility wrapper; validate_link is the only semantic/provenance gate."""
    try:
        value = json.loads(raw)
    except (ValueError, TypeError):
        return {}, ["LINKER_FORMAT_ERROR"]
    if (not isinstance(value, dict) or set(value) != {"tables", "grounded_values"}
            or not isinstance(value["grounded_values"], list)):
        return {}, ["LINKER_FORMAT_ERROR"]
    linked = validate_link(question, value["tables"], trajectory, tools,
                           submitted_values=value["grounded_values"])
    return ({}, [linked["error"]]) if linked["error"] else (linked, [])


def run_role(role: str, question: str, system_prompt: str, tools: V2DatabaseTools | None,
             client: Any, max_turns: int = 1,
             telemetry_sink: Callable | None = None) -> RoleResult:
    messages = [{"role": "system", "content": system_prompt}, {"role": "user", "content": question}]
    usage, trajectory = [], []
    attempted = responses = tool_count = turn = 0
    unknown = False

    def done(error=None, content=None, linked=None):
        return RoleResult(content, turn, tool_count, error, linked, usage, trajectory,
                          attempted, responses, unknown)

    if role not in {"linker", "generator"} or max_turns < 1:
        return done("INVALID_ROLE_CONTRACT")
    for turn in range(1, min(max_turns, MAX_TURNS) + 1):
        request = {"model": MODEL, "reasoning_effort": REASONING_EFFORT,
                   "max_completion_tokens": CAP, "messages": list(messages)}
        if tools is not None:
            request["tools"] = TOOL_SCHEMAS
        if role == "linker":
            request["response_format"] = {"type": "json_object"}
        attempted += 1
        start = time.monotonic()
        try:
            response = client.chat.completions.create(**request)
        except Exception:
            unknown = True
            return done("PROVIDER_ERROR")
        responses += 1
        raw_usage = getattr(response, "usage", None)
        input_tokens = getattr(raw_usage, "prompt_tokens", None)
        output_tokens = getattr(raw_usage, "completion_tokens", None)
        total_tokens = getattr(raw_usage, "total_tokens", None)
        complete = (type(input_tokens) is int and input_tokens >= 0
                    and type(output_tokens) is int and output_tokens >= 0
                    and type(total_tokens) is int and total_tokens == input_tokens + output_tokens)
        actual_model = getattr(response, "model", None)
        response_id = getattr(response, "id", None)
        choices = getattr(response, "choices", None)
        choice = choices[0] if choices else None
        message = getattr(choice, "message", None)
        observed_response = {
            "content": getattr(message, "content", None),
            "finish_reason": getattr(choice, "finish_reason", None),
            "tool_calls": [{"id": getattr(call, "id", None), "function": {
                "name": getattr(getattr(call, "function", None), "name", None),
                "arguments": getattr(getattr(call, "function", None), "arguments", None)}}
                for call in (getattr(message, "tool_calls", None) or [])],
        }
        tel = {"role": role, "turn": turn, "response_id": response_id,
               "model": actual_model, "input_tokens": input_tokens, "output_tokens": output_tokens,
               "total_tokens": total_tokens, "usage_complete": complete,
               "cost_usd": cost_usd(input_tokens, output_tokens) if complete and actual_model == MODEL else None,
               "latency_ms": (time.monotonic() - start) * 1000, "response": observed_response}
        usage.append(tel)
        unknown |= not complete or actual_model != MODEL
        # The sink receives the observed response before any choices/tool parsing.
        if telemetry_sink:
            try:
                telemetry_sink(request, tel)
            except Exception:
                return done("TELEMETRY_WRITE_ERROR")
        if actual_model != MODEL:
            return done("MODEL_IDENTITY_MISMATCH")
        if not complete:
            return done("USAGE_INCOMPLETE")
        if not isinstance(response_id, str) or not response_id:
            return done("RESPONSE_ID_MISSING")
        choices = getattr(response, "choices", None)
        if not choices:
            return done("EMPTY_RESPONSE")
        choice = choices[0]
        message = getattr(choice, "message", None)
        content = getattr(message, "content", None)
        if getattr(choice, "finish_reason", None) == "length":
            return done("COMPLETION_LIMIT", content)
        calls = getattr(message, "tool_calls", None) or []
        if calls:
            if tools is None:
                return done("TOOLS_DISABLED")
            serialized_calls = []
            for call in calls:
                function = getattr(call, "function", None)
                arguments = getattr(function, "arguments", None)
                name = getattr(function, "name", None)
                call_id = getattr(call, "id", None)
                serialized_calls.append({"id": call_id, "type": "function",
                                         "function": {"name": name, "arguments": arguments}})
            messages.append({"role": "assistant", "content": content, "tool_calls": serialized_calls})
            for call in serialized_calls:
                if tool_count >= MAX_DB_CALLS:
                    return done("TOOL_LIMIT")
                try:
                    args = json.loads(call["function"]["arguments"])
                except (ValueError, TypeError):
                    return done("MALFORMED_TOOL_ARGUMENTS")
                if not isinstance(args, dict):
                    return done("MALFORMED_TOOL_ARGUMENTS")
                tool_count += 1
                try:
                    result = tools.invoke(call["function"]["name"], args)
                except Exception:
                    result = {"ok": False, "error_type": "TOOL_EXECUTION_ERROR"}
                trajectory.append({"role": role, "turn": turn, "tool_call_id": call["id"],
                                   "tool": call["function"]["name"], "arguments": args, "result": result})
                messages.append({"role": "tool", "tool_call_id": call["id"],
                                 "content": json.dumps(result, default=str)})
            continue
        if not isinstance(content, str) or not content.strip():
            return done("EMPTY_RESPONSE")
        if role == "linker":
            if tools is None:
                return done("TOOLS_DISABLED", content)
            linked, errors = validate_linked_schema(content, tools, trajectory, question)
            if errors:
                return done(errors[0], content)
            return done(content=content.strip(), linked=linked)
        return done(content=content.strip())
    return done("TURN_LIMIT")


def run_case(case, condition: str, tools: V2DatabaseTools, client: Any, schema_context: str,
             telemetry_sink: Callable | None = None) -> dict:
    linker = generator = linked = None
    if condition not in {"E0", "E1", "E2", "E3"}:
        raise ValueError("INVALID_CONDITION")
    if condition in {"E1", "E3"}:
        linker = run_role("linker", case.question, LINKER_INSTRUCTIONS + "\nDatabase schema:\n" + schema_context,
                          tools, client, MAX_TURNS, telemetry_sink)
        linked = linker.linked_schema
        if linker.error:
            return _result(case, condition, linker, None, linked, None, linker.error)
    system = GENERATOR_INSTRUCTIONS + ("\nLinked schema:\n" + json.dumps(linked) if linked is not None
                                       else "\nDatabase schema:\n" + schema_context)
    enabled = condition in {"E2", "E3"}
    generator = run_role("generator", case.question, system, tools if enabled else None,
                         client, MAX_TURNS if enabled else 1, telemetry_sink)
    return _result(case, condition, linker, generator, linked,
                   generator.content if not generator.error else None, generator.error or "OK")


def _result(case, condition, linker, generator, linked, sql, error) -> dict:
    roles = {"linker": asdict(linker) if linker else None,
             "generator": asdict(generator) if generator else None}
    usage = [u for role in (linker, generator) if role for u in role.usage]
    return {"case_id": case.case_id, "condition": condition, "roles": roles,
            "linked_schema": linked, "error_category": error, "final_sql": sql, "usage": usage,
            "trajectory": [t for role in (linker, generator) if role for t in role.trajectory],
            "attempted_calls": sum(role.attempted_calls for role in (linker, generator) if role),
            "response_count": len(usage), "cost_unknown": any(role.cost_unknown for role in (linker, generator) if role),
            "observed_cost_usd": sum(u["cost_usd"] for u in usage if u["cost_usd"] is not None)}
