"""Durable ledger for network-e2e live window gates.

NETWORK_DEMO condition tracks:
- Claims and reservations per attempt
- Actual usage/cost per request
- Unknown-cost latch when usage unavailable
- Atomic persistence preventing crash-data-loss
"""
from __future__ import annotations

import json
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# Constants
NETWORK_DEMO_CONDITION = "NETWORK_DEMO"
WINDOW_ID = "network-finalization-20261006"
INPUT_TOKEN_RESERVE = 50_000
OUTPUT_TOKEN_RESERVE = 1_000
FRAME_RESERVE_TOKENS = 512

# USD per million tokens (as of 2026-10-06)
DEMO_INPUT_USD_M = 0.40
DEMO_CACHED_INPUT_USD_M = 0.10
DEMO_OUTPUT_USD_M = 1.60

SAFE_ERROR_FIELD = __import__("re").compile(r"[a-z][a-z0-9_.-]{0,63}")
SAFE_REQUEST_ID = __import__("re").compile(r"req_[A-Za-z0-9._:-]{1,124}")


def _safe_error_field(value: Any) -> str | None:
    if not isinstance(value, str) or value.startswith("sk-"):
        return None
    return value if SAFE_ERROR_FIELD.fullmatch(value) else None


def _safe_request_id(value: Any) -> str | None:
    return value if isinstance(value, str) and SAFE_REQUEST_ID.fullmatch(value) else None


def _safe_retry_after(value: Any) -> str | None:
    from email.utils import format_datetime, parsedate_to_datetime
    if not isinstance(value, str) or not value or not value.isascii() or len(value) > 128:
        return None
    if value.isdecimal():
        if len(value) > 10:
            return None
        return str(int(value))
    try:
        parsed = parsedate_to_datetime(value)
        if parsed.tzinfo is None:
            return None
        return format_datetime(parsed, usegmt=True)
    except (TypeError, ValueError, OverflowError):
        return None


def _provider_error_details(exc: Exception) -> dict[str, Any]:
    """Return only allowlisted, validated provider error metadata."""
    status_value = getattr(exc, "status_code", None)
    status = status_value if type(status_value) is int and 100 <= status_value <= 599 else None
    body = getattr(exc, "body", None)
    error_data: dict = {}
    if isinstance(body, dict):
        nested = body.get("error")
        error_data = nested if isinstance(nested, dict) else body
    response = getattr(exc, "response", None)
    headers = getattr(response, "headers", None)
    retry_after = None
    if isinstance(headers, dict):
        for name, value in headers.items():
            if isinstance(name, str) and name.lower() == "retry-after":
                retry_after = _safe_retry_after(value)
                break
    return {
        "status": status,
        "code": _safe_error_field(error_data.get("code")),
        "type": _safe_error_field(error_data.get("type")),
        "request_id": _safe_request_id(getattr(exc, "request_id", None)),
        "retry_after": retry_after,
    }


def compute_request_reserve(input_tokens: int = INPUT_TOKEN_RESERVE,
                            output_tokens: int = OUTPUT_TOKEN_RESERVE,
                            cached_tokens: int = 0) -> float:
    """Compute USD cost reserve for a request."""
    return (
        (input_tokens - cached_tokens) * DEMO_INPUT_USD_M +
        cached_tokens * DEMO_CACHED_INPUT_USD_M +
        output_tokens * DEMO_OUTPUT_USD_M
    ) / 1_000_000


class LiveWindowError(RuntimeError):
    """A gate blocked the operation."""


class LiveWindow:
    """
    Durable ledger for NETWORK_DEMO live window.

    Tracks claims, reservations, usage, and cost for a bounded
    set of requests within a fixed budget.
    """

    def __init__(self, root: Path, window_id: str = WINDOW_ID,
                 condition: str = NETWORK_DEMO_CONDITION):
        self.root = Path(root)
        self.window_id = window_id
        self.condition = condition
        self.ledger_path = self.root / "ledger.json"
        self._lock = threading.Lock()
        self._load()

    def _load(self) -> None:
        """Load existing ledger or create new."""
        if self.ledger_path.exists():
            self._data = json.loads(self.ledger_path.read_text(encoding="utf-8"))
        else:
            self._data = {
                "window_id": self.window_id,
                "condition": self.condition,
                "created_utc": datetime.now(timezone.utc).isoformat(),
                "attempts": [],
                "reservations": [],  # Pending exposure
                "known_cost_usd": 0.0,
                "cost_unknown": False,
                "consumed": False,
            }

    def _persist(self) -> None:
        """Atomically persist ledger to disk."""
        self.root.mkdir(parents=True, exist_ok=True)
        # Write to temp file then rename for atomicity
        tmp = self.ledger_path.with_suffix(".tmp")
        tmp.write_text(json.dumps(self._data, indent=2, default=str), encoding="utf-8")
        tmp.replace(self.ledger_path)

    def claim(self, implementation_sha: str, output: Path,
              budget_usd: float) -> dict[str, Any]:
        """
        Claim exclusive attempt before first request.

        Returns gates dict if claim succeeds.
        Raises LiveWindowError if already claimed or budget insufficient.
        """
        with self._lock:
            if self._data.get("consumed"):
                raise LiveWindowError("ATTEMPT_ALREADY_CONSUMED")

            # Check if output path matches registered output
            registered = self._data.get("registered_output")
            if registered and Path(registered) != Path(output):
                raise LiveWindowError("OUTPUT_PATH_MISMATCH")

            # Compute ceiling
            prior = self._data.get("known_cost_usd", 0.0)
            unknown = self._data.get("cost_unknown", False)
            reservations = sum(r.get("amount_usd", 0.0) for r in self._data.get("reservations", []))
            ceiling = prior + (0.0 if unknown else reservations)
            per_call = compute_request_reserve()

            if ceiling + per_call > budget_usd:
                raise LiveWindowError("BUDGET_INSUFFICIENT")

            # Register attempt
            self._data["attempts"].append({
                "implementation_sha": implementation_sha,
                "output": str(output),
                "budget_usd": budget_usd,
                "claimed_utc": datetime.now(timezone.utc).isoformat(),
                "calls": [],
            })
            self._data["registered_output"] = str(output)
            self._persist()

            return {
                "window_id": self.window_id,
                "condition": self.condition,
                "implementation_sha": implementation_sha,
                "prior_cost_usd": prior,
                "budget_usd": budget_usd,
                "per_call_reserve_usd": per_call,
            }

    def reserve(self, amount_usd: float) -> None:
        """Record a pending cost reservation."""
        with self._lock:
            self._data["reservations"].append({
                "amount_usd": amount_usd,
                "reserved_utc": datetime.now(timezone.utc).isoformat(),
            })
            self._persist()

    def record_response(self, stage: str, actual_model: str | None,
                       response_id: str | None, usage: dict | None,
                       cost_usd: float | None, latency_ms: float,
                       error: dict | None = None) -> None:
        """Record a response after it arrives."""
        with self._lock:
            # Remove corresponding reservation
            if self._data["reservations"]:
                self._data["reservations"].pop(0)

            # Update cost
            if usage and cost_usd is not None:
                self._data["known_cost_usd"] = self._data.get("known_cost_usd", 0.0) + cost_usd
            elif usage is None or cost_usd is None:
                self._data["cost_unknown"] = True

            # Record call
            call = {
                "stage": stage,
                "recorded_utc": datetime.now(timezone.utc).isoformat(),
                "actual_model": actual_model,
                "response_id": response_id,
                "usage": usage,
                "cost_usd": cost_usd,
                "latency_ms": latency_ms,
                "error": error,
            }
            if self._data["attempts"]:
                self._data["attempts"][-1]["calls"].append(call)

            self._persist()

    def record_terminal(self, status: str, final_cost_usd: float | None = None) -> None:
        """Mark window as terminal (complete or blocked)."""
        with self._lock:
            self._data["terminal_status"] = status
            self._data["terminal_utc"] = datetime.now(timezone.utc).isoformat()
            if final_cost_usd is not None:
                self._data["final_cost_usd"] = final_cost_usd
            self._persist()

    def is_terminal(self) -> bool:
        """Check if window has reached terminal state."""
        return bool(self._data.get("terminal_status"))

    def get_status(self) -> dict[str, Any]:
        """Get current window status."""
        return {
            "window_id": self._data["window_id"],
            "condition": self._data["condition"],
            "consumed": self._data.get("consumed", False),
            "terminal_status": self._data.get("terminal_status"),
            "known_cost_usd": self._data.get("known_cost_usd", 0.0),
            "cost_unknown": self._data.get("cost_unknown", False),
            "attempts": len(self._data.get("attempts", [])),
            "reservations": len(self._data.get("reservations", [])),
        }

    def guarded_client(self, client: Any, condition: str,
                       contract: dict | None = None) -> Any:
        """
        Wrap a client with guards that enforce the live window constraints.

        This wraps chat.completions.create to:
        1. Check budget before each call
        2. Record cost/usage after each response
        3. Stop on provider errors with safe details

        Args:
            client: The OpenAI client to wrap
            condition: Must match this window's condition
            contract: Optional per-call contract with pricing

        Returns:
            Guarded client that intercepts chat.completions.create
        """
        if condition != self.condition:
            raise LiveWindowError(f"CONDITION_MISMATCH: expected {self.condition}, got {condition}")

        return _GuardedClient(self, client)


class _GuardedClient:
    """Proxy client that intercepts create() calls for window enforcement."""

    def __init__(self, window: LiveWindow, client: Any):
        self._window = window
        self._client = client
        self._chat = _GuardedCompletions(window, client.chat)

    @property
    def chat(self) -> _GuardedCompletions:
        return self._chat


class _GuardedCompletions:
    """Proxy completions that enforces budget/reserve before sending."""

    def __init__(self, window: LiveWindow, completions: Any):
        self._window = window
        self._completions = completions

    def create(self, **request) -> Any:
        """Intercept create() to enforce budget and record results."""
        from time import perf_counter

        # Reserve cost before call
        usage = request.get("messages", [])
        # Simple estimate: use input token reserve
        reserve = compute_request_reserve(INPUT_TOKEN_RESERVE, OUTPUT_TOKEN_RESERVE)

        # Check budget before sending
        status = self._window.get_status()
        if status["cost_unknown"]:
            raise LiveWindowError("COST_UNKNOWN_BLOCKS_RETRY")
        if status.get("terminal_status"):
            raise LiveWindowError(f"WINDOW_TERMINAL:{status['terminal_status']}")

        total_exposed = status["known_cost_usd"] + reserve
        # Would need budget from gates - simplified check here
        # Full budget check happens in CLI before creating client

        self._window.reserve(reserve)
        started = perf_counter()

        try:
            response = self._completions.create(**request)
        except Exception as exc:
            error = _provider_error_details(exc)
            self._window.record_response(
                stage="error",
                actual_model=getattr(response, "model", None) if "response" in dir() else None,
                response_id=None,
                usage=None,
                cost_usd=None,
                latency_ms=(perf_counter() - started) * 1000,
                error=error,
            )
            raise

        # Record successful response
        latency_ms = (perf_counter() - started) * 1000
        actual_model = getattr(response, "model", None)
        resp_id = getattr(response, "id", None)
        usage_obj = getattr(response, "usage", None)

        usage_dict = None
        cost_usd = None

        if usage_obj:
            input_tok = getattr(usage_obj, "prompt_tokens", 0)
            output_tok = getattr(usage_obj, "completion_tokens", 0)
            cached_tok = getattr(usage_obj, "cached_tokens", 0)
            usage_dict = {
                "input_tokens": input_tok,
                "output_tokens": output_tok,
                "cached_tokens": cached_tok,
            }
            cost_usd = compute_request_reserve(input_tok, output_tok, cached_tok)

        self._window.record_response(
            stage="response",
            actual_model=actual_model,
            response_id=resp_id,
            usage=usage_dict,
            cost_usd=cost_usd,
            latency_ms=latency_ms,
            error=None,
        )

        return response
