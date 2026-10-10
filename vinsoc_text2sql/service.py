"""One generation algorithm shared by evaluation and VinSOC tools."""
from __future__ import annotations

import json
from copy import deepcopy
from dataclasses import dataclass
from time import monotonic
from typing import Callable, Literal, Protocol

from evaluation.r2_cross_domain_v1.data import DatabaseContext
from evaluation.r2_cross_domain_v1.release import CONDITIONS
from evaluation.r2_cross_domain_v1.tools import DatabaseTools

from .executor import SqlExecutor


@dataclass(frozen=True)
class QueryRequest:
    request_id: str
    database_id: str
    question: str

class QueryTransport(Protocol):
    contract: dict
    def request(self, payload: dict) -> dict: ...
    def counters(self) -> dict: ...

class TextToSQLService:
    VERSION = "shared_text2sql_v1"
    def __init__(self, executor=None):
        self.executor = executor or SqlExecutor()

    def generate(self, request: QueryRequest, *, condition: Literal["E0", "E3"],
                 context: DatabaseContext, transport: QueryTransport,
                 telemetry_sink: Callable[[dict], None]) -> dict:
        if (type(request) is not QueryRequest or request.database_id != context.database_id
                or condition not in CONDITIONS or not isinstance(request.question, str)
                or not request.question.strip() or len(request.question.encode()) > 8192):
            raise ValueError("INVALID_RUNTIME_CONTRACT")
        tools = DatabaseTools(context, executor=self.executor)
        record = _generate(request, condition, tools, transport, telemetry_sink)
        record.update(question=request.question, runtime_version=self.VERSION,
                      snapshot_identity=context.identity["logical_sha256"])
        telemetry_sink(deepcopy(record))
        return record

    def execute(self, generation: dict, *, context: DatabaseContext) -> dict:
        if (generation.get("database_id") != context.database_id
            or generation.get("snapshot_identity") != context.identity["logical_sha256"]):
            raise ValueError("INVALID_RUNTIME_CONTRACT")
        if generation.get("error_category") != "OK" or not generation.get("final_sql"):
            raise ValueError("NO_VALID_FINAL_SQL")
        return self.executor.query(context, generation["final_sql"], row_cap=10000, timeout_seconds=10)

def _generate(request, condition, tools, transport, telemetry_sink):
    """Only RuntimeCase enters generation; evaluator reference remains outside."""
    from evaluation.r2_cross_domain_v1.controller import ROLE_TURN_CAP
    from evaluation.r2_cross_domain_v1.grounding import GroundingError, validate_link
    from evaluation.r2_cross_domain_v1.prompts import GENERATOR, LINKER
    from evaluation.r2_cross_domain_v1.safety import SafetyError, validate_sql
    from evaluation.r2_cross_domain_v1.tool_schemas import TOOLS
    from evaluation.r2_cross_domain_v1.tools import ToolError
    if type(request) is not QueryRequest or condition not in CONDITIONS or request.database_id != tools.context.database_id:
        raise ValueError("INVALID_RUNTIME_CONTRACT")
    if transport is None or not callable(getattr(transport, "request", None)) or not callable(getattr(transport, "counters", None)):
        raise ValueError("GUARDED_OPENAI_TRANSPORT_REQUIRED")
    record = {"case_id": request.request_id, "database_id": request.database_id, "condition": condition,
              "final_sql": None, "attempted_calls": 0, "response_count": 0, "responses": [], "trajectory": [],
              "error_category": "UNFINISHED", "linked_schema": None, "evidence_kind": "openai_live"}
    started = monotonic()
    attempted_before = transport.counters()["attempted"]
    received_before = transport.counters()["received"]
    linked = None
    try:
        for role in (["linker", "generator"] if condition == "E3" else ["generator"]):
            data = {"question": request.question, "database_id": request.database_id, "catalog": tools.context.schema_context()}
            if linked is not None:
                data["linked_schema"] = linked
            messages = [{"role": "system", "content": LINKER if role == "linker" else GENERATOR},
                        {"role": "user", "content": json.dumps(data, ensure_ascii=False)}]
            completed = False
            turn_cap = ROLE_TURN_CAP if condition == "E3" else 1
            for turn in range(turn_cap):
                payload = {key: transport.contract[key] for key in ("model", "reasoning_effort", "max_completion_tokens", "service_tier")}
                finalization_turn = condition == "E3" and turn == turn_cap-1
                payload["messages"] = deepcopy(messages)
                if finalization_turn:
                    payload["messages"].append({"role":"user", "content":
                        "Tool access is complete. Return the required final JSON object now using only the acquired evidence."})
                elif condition == "E3":
                    payload["tools"] = deepcopy(TOOLS)
                response = transport.request(payload)
                event = {"role": role, "response": deepcopy(response)}
                record["responses"].append(event)
                telemetry_sink(deepcopy(record))  # before parsing/scoring
                calls = response.get("tool_calls") or []
                if calls:
                    if finalization_turn:
                        record["error_category"] = "TOOL_LIMIT"
                        return record
                    if condition == "E0" or len(calls) > 4:
                        raise ValueError("UNEXPECTED_OR_EXCESS_TOOL_CALLS")
                    messages.append({"role": "assistant", "content": response["content"], "tool_calls": calls})
                    for call in calls:
                        function = call["function"]
                        arguments = json.loads(function["arguments"]) if isinstance(function["arguments"], str) else function["arguments"]
                        result = tools.call(function["name"], arguments)
                        messages.append({"role": "tool", "tool_call_id": call["id"], "content": json.dumps(result, ensure_ascii=False)})
                    continue
                answer = json.loads(response.get("content") or "")
                if role == "linker":
                    linked = validate_link(request.question, answer, tools.trajectory, tools.context)
                    record["linked_schema"] = deepcopy(linked)
                else:
                    if not isinstance(answer, dict) or not isinstance(answer.get("sql"), str):
                        raise ValueError("INVALID_FINAL_SQL")
                    record["final_sql"] = answer["sql"]
                    validate_sql(answer["sql"], tools.context)
                completed = True
                break
            if not completed:
                record["error_category"] = "TOOL_LIMIT"
                return record
        record["error_category"] = "OK"
        return record
    except GroundingError:
        record["error_category"] = "INVALID_LINKED_SCHEMA"
        return record
    except SafetyError:
        record["error_category"] = "SAFETY_REJECTION"
        return record
    except ToolError:
        record["error_category"] = "TOOL_FAILURE"
        return record
    except Exception:
        # Provider problems latch the journal; model parse errors retain cost
        # and become a failed case, not an extra model retry.
        record["error_category"] = "PROVIDER_ERROR" if transport.counters().get("terminal", False) else "MODEL_PARSE_ERROR"
        return record
    finally:
        record.update(attempted_calls=transport.counters()["attempted"]-attempted_before,
                      response_count=transport.counters()["received"]-received_before,
                      trajectory=deepcopy(tools.trajectory), db_calls=tools.db_calls, wall_seconds=monotonic()-started)

