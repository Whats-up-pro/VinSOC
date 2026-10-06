"""Bounded generic inference controller, currently exposed only to synthetic transport.

The live adapter/release authorization is intentionally a later gate. This module
does not import OpenAI, create a provider client or label fake output as official.
"""
from __future__ import annotations

import json
import hashlib
from copy import deepcopy
from time import monotonic

from .grounding import GroundingError, validate_link
from .models import RuntimeCase
from .prompts import GENERATOR, LINKER
from .safety import SafetyError, validate_sql
from .tool_schemas import TOOLS
from .tools import DatabaseTools, ToolError


MODEL = "gpt-5-mini-2025-08-07"
ROLE_TURN_CAP = 3
REQUEST_BYTES_CAP = 32768  # Payload safety cap; NOT a proved billable-token bound.


def run_case(runtime_case: RuntimeCase, condition, tools: DatabaseTools, client, telemetry_sink):
    if type(runtime_case) is not RuntimeCase or condition not in ("E0", "E3"):
        raise ValueError("INVALID_RUNTIME_CONTRACT")
    if runtime_case.database_id != tools.context.database_id:
        raise ValueError("WRONG_DATABASE_CONTEXT")
    if getattr(client, "transport_kind", None) != "synthetic":
        raise ValueError("LIVE_RELEASE_GATE_NOT_IMPLEMENTED")
    record = {
        "case_id": runtime_case.case_id, "database_id": runtime_case.database_id,
        "question": runtime_case.question, "condition": condition, "final_sql": None,
        "error_category": "UNFINISHED", "attempted_calls": 0, "response_count": 0,
        "responses": [], "trajectory": [], "official_eligible": False,
        "evidence_kind": "synthetic_transport", "external_model_calls": 0,
    }
    started = monotonic()
    linked = None
    roles = ["linker", "generator"] if condition == "E3" else ["generator"]
    try:
        for role in roles:
            payload = {"question": runtime_case.question, "database_id": runtime_case.database_id,
                       "catalog": tools.context.schema_context()}
            if linked is not None:
                payload["linked_schema"] = linked
            messages = [{"role": "system", "content": LINKER if role == "linker" else GENERATOR},
                        {"role": "user", "content": json.dumps(payload, ensure_ascii=False)}]
            complete = False
            for _ in range(ROLE_TURN_CAP if condition == "E3" else 1):
                request = {"model": MODEL, "reasoning_effort": "low", "max_completion_tokens": 1000,
                           "service_tier": "default", "messages": deepcopy(messages)}
                if condition == "E3":
                    request["tools"] = deepcopy(TOOLS)
                if len(json.dumps(request, ensure_ascii=False).encode("utf-8")) > REQUEST_BYTES_CAP:
                    record["error_category"] = "REQUEST_PAYLOAD_LIMIT"
                    return record
                record["attempted_calls"] += 1
                call_started = monotonic()
                response = client.request(request)
                # Preserve response/usage before parsing any model content or tool arguments.
                record["response_count"] += 1
                event = {"role": role, "response": deepcopy(response), "latency_seconds": monotonic()-call_started,
                         "request_sha256": hashlib.sha256(json.dumps(request, sort_keys=True, ensure_ascii=False).encode()).hexdigest()}
                record["responses"].append(event)
                telemetry_sink(deepcopy(event))
                calls = response.get("tool_calls") or []
                if calls:
                    if condition == "E0":
                        record["error_category"] = "UNEXPECTED_TOOL_CALL"
                        return record
                    messages.append({"role": "assistant", "content": response.get("content"), "tool_calls": deepcopy(calls)})
                    for call in calls:
                        function = call.get("function", {})
                        arguments = function.get("arguments", {})
                        if isinstance(arguments, str):
                            arguments = json.loads(arguments)
                        if not isinstance(arguments, dict):
                            raise ValueError("INVALID_TOOL_ARGUMENTS")
                        result = tools.call(function.get("name"), arguments)
                        messages.append({"role": "tool", "tool_call_id": call.get("id"), "content": json.dumps(result, ensure_ascii=False)})
                    continue
                answer = json.loads(response.get("content", ""))
                if role == "linker":
                    linked = validate_link(runtime_case.question, answer, tools.trajectory, tools.context)
                    record["linked_schema"] = deepcopy(linked)
                else:
                    if not isinstance(answer, dict) or not isinstance(answer.get("sql"), str):
                        raise ValueError("INVALID_FINAL_SQL")
                    record["final_sql"] = answer["sql"]
                    validate_sql(answer["sql"], tools.context)
                complete = True
                break
            if not complete:
                record["error_category"] = "TOOL_LIMIT"
                return record
        record["error_category"] = "OK"  # Generation only; never an EX score.
        record["linked_schema"] = linked
        return record
    except GroundingError as error:
        record["error_category"] = "INVALID_TOOL_PROVENANCE" if "PROVENANCE" in str(error) or "WITNESS" in str(error) else "INVALID_LINKED_SCHEMA"
        record["failure_code"] = str(error)
        return record
    except SafetyError as error:
        record["error_category"] = "SAFETY_REJECTION"
        record["failure_code"] = str(error)
        return record
    except ToolError as error:
        record["error_category"] = "TOOL_LIMIT" if "LIMIT" in str(error) else "TOOL_FAILURE"
        record["failure_code"] = str(error)
        return record
    except Exception as error:
        # A safe class name avoids leaking a provider error or raw result rows.
        record["error_category"] = "TRANSPORT_OR_PARSE_FAILURE"
        record["failure_code"] = type(error).__name__
        return record
    finally:
        record["trajectory"] = deepcopy(tools.trajectory)
        record["db_calls"] = tools.db_calls
        record["wall_seconds"] = monotonic()-started
