"""Durable single-use scope and conservative exposure accounting before transmission."""

from contextlib import contextmanager
from datetime import datetime, timezone
import fcntl
import json
import math
import os
from pathlib import Path
from vinsoc_data.soc_corpus import canonical, digest
from evaluation.soc_traces_v1.release import (
    MODEL,
    private_directory,
    validate_release,
    validate_identities,
)


class SocTerminalError(RuntimeError):
    pass


def atomic_bytes(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    tmp = path.with_name(path.name + "." + str(os.getpid()) + ".tmp")
    fd = os.open(tmp, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(data)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, path)
        directory = os.open(path.parent, os.O_RDONLY)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
    finally:
        if tmp.exists():
            tmp.unlink()


def atomic_json(path, data):
    atomic_bytes(path, (canonical(data) + "\n").encode())


def _exclusive_claim(path, state):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    with os.fdopen(fd, "wb") as stream:
        stream.write(canonical(state).encode())
        stream.flush()
        os.fsync(stream.fileno())
    d = os.open(path.parent, os.O_RDONLY)
    try:
        os.fsync(d)
    finally:
        os.close(d)


def validate_request(payload, *, condition, turn):
    if (
        condition not in ("S0", "S1")
        or type(turn) != int
        or not 0 <= turn < (1 if condition == "S0" else 6)
    ):
        raise ValueError("SOC_REQUEST_CAP_EXCEEDED")
    if set(payload) - {
        "model",
        "temperature",
        "max_completion_tokens",
        "messages",
        "tools",
        "parallel_tool_calls",
        "tool_choice",
    }:
        raise ValueError("SOC_REQUEST_FIELD_UNSUPPORTED")
    if (
        payload.get("model") != MODEL
        or type(payload.get("temperature")) not in (int, float)
        or payload.get("temperature") != 0
        or type(payload.get("max_completion_tokens")) != int
        or payload.get("max_completion_tokens") != 2000
    ):
        raise ValueError("SOC_REQUEST_CONTRACT_INVALID")
    messages = payload.get("messages")
    if not isinstance(messages, list) or not 1 <= len(messages) <= 16:
        raise ValueError("SOC_MESSAGE_CAP_EXCEEDED")
    if any(m.get("role") not in ("system", "user", "assistant", "tool") for m in messages):
        raise ValueError("SOC_MESSAGE_ROLE_INVALID")
    tools = payload.get("tools")
    if (condition == "S0" or turn == 5) and tools:
        raise ValueError("SOC_FINAL_ONLY_REQUIRED")
    if tools:
        from agent.soc_investigation_policy import SocInvestigationPolicy

        if (
            tools != SocInvestigationPolicy(None).tool_schemas()
            or payload.get("parallel_tool_calls") is not False
            or payload.get("tool_choice") != "auto"
        ):
            raise ValueError("SOC_TOOL_CONTRACT_INVALID")
    size = len(canonical(payload).encode())
    if size > 128000:
        raise ValueError("SOC_REQUEST_BYTES_EXCEEDED")
    return size


def _response_usage(raw, pricing):
    usage = raw.get("usage")
    if not isinstance(usage, dict) or any(
        type(usage.get(k)) != int or usage[k] < 0
        for k in ("prompt_tokens", "completion_tokens", "total_tokens")
    ):
        raise ValueError("SOC_USAGE_MISSING_OR_INVALID")
    if usage["prompt_tokens"] + usage["completion_tokens"] != usage["total_tokens"]:
        raise ValueError("SOC_USAGE_TOTAL_INVALID")
    cost = (
        usage["prompt_tokens"] * pricing["input_usd_per_million"]
        + usage["completion_tokens"] * pricing["output_usd_per_million"]
    ) / 1000000
    if not math.isfinite(cost) or cost < 0:
        raise ValueError("SOC_COST_INVALID")
    return {"usage": usage, "estimated_cost_usd": cost}


def persist_and_validate_response(path, raw, *, pricing):
    atomic_json(path, raw)
    return _response_usage(raw, pricing)


class SocRunJournal:
    def __init__(self, path, release, checked):
        self.path = path
        self.release = release
        self.checked = checked
        self._claimed = True

    @classmethod
    def claim(cls, release, *, ledger_path, remote_store=None):
        expected = private_directory() / "ledger.json"
        path = Path(ledger_path)
        if path.is_symlink() or path.resolve() != expected.resolve():
            raise ValueError("SOC_CANONICAL_LEDGER_REQUIRED")
        checked = validate_release(release)
        if path.exists():
            raise SocTerminalError("SOC_SCOPE_ALREADY_CONSUMED")
        if remote_store is not None:
            from evaluation.soc_traces_v1.cloud import SocCloudStore

            if type(remote_store) is not SocCloudStore:
                raise ValueError("SOC_NATIVE_CLOUD_STORE_REQUIRED")
            remote_store.claim(release)
        state = {
            "window": release["window"],
            "release_sha256": release["release_sha256"],
            "status": "running",
            "claimed_at": datetime.now(timezone.utc).isoformat(),
            "owner_pid": os.getpid(),
            "reservations": [],
            "estimated_cost_usd": 0.0,
            "unknown_cost": False,
            "maximum_suite_usd": checked["maximum_suite_usd"],
        }
        try:
            _exclusive_claim(path, state)
        except FileExistsError:
            raise SocTerminalError("SOC_SCOPE_ALREADY_CONSUMED") from None
        return cls(path, release, checked)

    @contextmanager
    def _state(self):
        with self.path.with_suffix(".lock").open("a") as lock:
            fcntl.flock(lock.fileno(), fcntl.LOCK_EX)
            state = json.loads(self.path.read_text())
            if (
                state["release_sha256"] != self.release["release_sha256"]
                or state["owner_pid"] != os.getpid()
            ):
                raise SocTerminalError("SOC_JOURNAL_OWNER_MISMATCH")
            try:
                yield state
            finally:
                atomic_json(self.path, state)
                fcntl.flock(lock.fileno(), fcntl.LOCK_UN)

    def ensure_case_capacity(self, case_id, condition):
        with self._state() as state:
            if state["status"] != "running" or state["unknown_cost"]:
                raise SocTerminalError("SOC_RELEASE_TERMINAL")
            if case_id not in self.release["case_ids"] or condition not in ("S0", "S1"):
                raise ValueError("SOC_CASE_OUTSIDE_SCOPE")
            records = [
                r
                for r in state["reservations"]
                if r["case_id"] == case_id and r["condition"] == condition
            ]
            if any(r["status"] == "reserved" for r in state["reservations"]):
                raise SocTerminalError("SOC_UNRESOLVED_EXPOSURE")
            if len(records) >= self.release["caps"][condition] or len(state["reservations"]) >= 448:
                raise ValueError("SOC_REQUEST_CAP_EXCEEDED")

    def reserve(self, *, case_id, condition, turn, payload):
        self.ensure_case_capacity(case_id, condition)
        size = validate_request(payload, condition=condition, turn=turn)
        try:
            validate_identities(self.release)
        except (ValueError, OSError, KeyError):
            with self._state() as state:
                state["status"] = "terminal"
            raise SocTerminalError("SOC_RELEASE_IDENTITY_CHANGED") from None
        with self._state() as state:
            count = sum(
                r["case_id"] == case_id and r["condition"] == condition
                for r in state["reservations"]
            )
            if state["status"] != "running" or state["unknown_cost"]:
                raise SocTerminalError("SOC_UNRESOLVED_OR_TERMINAL_EXPOSURE")
            if count >= self.release["caps"][condition] or len(state["reservations"]) >= 448:
                raise ValueError("SOC_REQUEST_CAP_EXCEEDED")
            if turn != count:
                raise ValueError("SOC_TURN_SEQUENCE_INVALID")
            maximum = (
                (size + self.checked["evidence"]["request_bound"]["framing_token_reserve"])
                * self.checked["evidence"]["pricing"]["input_usd_per_million"]
                + 2000 * self.checked["evidence"]["pricing"]["output_usd_per_million"]
            ) / 1000000
            if (
                state["estimated_cost_usd"] + maximum
                > self.checked["evidence"]["budget"]["limit_usd"]
            ):
                state["status"] = "terminal"
                raise SocTerminalError("SOC_BUDGET_EXHAUSTED")
            reservation = len(state["reservations"])
            state["reservations"].append(
                {
                    "id": reservation,
                    "case_id": case_id,
                    "condition": condition,
                    "turn": turn,
                    "status": "reserved",
                    "request_sha256": digest(payload),
                    "request_bytes": size,
                    "reserved_usd": maximum,
                    "estimated_cost_usd": None,
                    "cost_unknown": True,
                    "reserved_at": datetime.now(timezone.utc).isoformat(),
                }
            )
            state["unknown_cost"] = True
            atomic_json(self.path.parent / "requests" / f"{reservation:04d}.json", payload)
        return reservation

    def record_response_bytes(self, reservation_id, body, *, transport=None):
        path = self.path.parent / "responses" / f"{reservation_id:04d}.json"
        atomic_bytes(path, body)
        if transport is not None:
            atomic_json(path.with_suffix(".transport.json"), transport)
        try:
            raw = json.loads(body)
            measured = _response_usage(raw, self.checked["evidence"]["pricing"])
        except (ValueError, TypeError):
            self.fail(reservation_id, "invalid_response_or_missing_usage")
            raise SocTerminalError("SOC_RESPONSE_UNKNOWN_COST") from None
        with self._state() as state:
            row = state["reservations"][reservation_id]
            if row["status"] != "reserved":
                raise SocTerminalError("SOC_RESPONSE_DUPLICATE")
            row.update(
                status="received",
                response_sha256=hashlib_sha(body),
                request_id=(transport or {}).get("request_id"),
                completion_id=raw.get("id"),
                actual_model=raw.get("model"),
                **measured,
                cost_unknown=False,
            )
            state["estimated_cost_usd"] += measured["estimated_cost_usd"]
            state["unknown_cost"] = False
            if (
                measured["estimated_cost_usd"] > row["reserved_usd"]
                or measured["usage"]["completion_tokens"] > 2000
                or measured["usage"]["prompt_tokens"]
                > row["request_bytes"]
                + self.checked["evidence"]["request_bound"]["framing_token_reserve"]
            ):
                state["status"] = "terminal"
                raise SocTerminalError("SOC_VERIFIED_BOUND_EXCEEDED")
        return raw, measured

    def record_response(self, reservation_id, raw_response):
        return self.record_response_bytes(reservation_id, canonical(raw_response).encode())[1]

    def fail(self, reservation_id, category):
        with self._state() as state:
            row = state["reservations"][reservation_id]
            row["failure"] = category
            row["status"] = "failed"
            state["status"] = "terminal"
            state["unknown_cost"] = row["cost_unknown"]

    def mark_client_created(self):
        with self._state() as state:
            state["client_created"] = True

    def finish(self):
        with self._state() as state:
            if state["status"] == "running" and not state["unknown_cost"]:
                state["status"] = "consumed"

    def snapshot(self):
        with self._state() as state:
            return json.loads(canonical(state))


def hashlib_sha(body):
    import hashlib

    return hashlib.sha256(body).hexdigest()
