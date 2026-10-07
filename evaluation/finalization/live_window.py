"""Durable ledger for network-e2e live window gates.

NETWORK_DEMO condition tracks:
- Claims and reservations per attempt
- Actual usage/cost per request
- Unknown-cost latch when usage unavailable
- Atomic persistence preventing crash-data-loss
"""
from __future__ import annotations

import json
import hashlib
import math
import os
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


def canonical_window_root() -> Path:
    """One durable task window across checkout, output and CLI modes."""
    return Path.home() / ".vinsoc" / "live-windows" / WINDOW_ID

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


def _fresh_utc(value: Any, *, max_age_seconds: int = 21600) -> bool:
    if not isinstance(value, str):
        return False
    try:
        timestamp = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return False
    if timestamp.tzinfo is None:
        return False
    age = (datetime.now(timezone.utc) - timestamp.astimezone(timezone.utc)).total_seconds()
    return -300 <= age <= max_age_seconds


def _finite_nonnegative(value: Any) -> bool:
    return type(value) in (int, float) and math.isfinite(value) and value >= 0


def _validate_gates(gates: Any, window_id: str) -> dict[str, Any]:
    """Validate the private CI/account/pricing/reconciliation evidence."""
    if not isinstance(gates, dict) or gates.get("schema_version") != 1:
        raise LiveWindowError("GATE_SCHEMA_INVALID")
    if gates.get("window_id") != window_id or window_id != WINDOW_ID:
        raise LiveWindowError("GATE_WINDOW_ID_MISMATCH")
    budget = gates.get("task_budget_usd")
    if not _finite_nonnegative(budget) or not 0 < budget <= 0.25:
        raise LiveWindowError("GATE_BUDGET_INVALID")
    sha = gates.get("implementation_sha")
    ci = gates.get("ci")
    if not isinstance(sha, str) or len(sha) != 40 or not isinstance(ci, dict):
        raise LiveWindowError("GATE_IMPLEMENTATION_SHA_MISMATCH")
    if ci.get("head_sha") != sha:
        raise LiveWindowError("GATE_IMPLEMENTATION_SHA_MISMATCH")
    jobs = ci.get("jobs")
    names = [item.get("name", "") for item in jobs] if isinstance(jobs, list) else []
    if (
        ci.get("conclusion") != "success"
        or not isinstance(ci.get("run_url"), str)
        or not ci["run_url"].startswith("https://github.com/")
        or not isinstance(jobs, list)
        or not all(isinstance(item, dict) and item.get("conclusion") == "success" for item in jobs)
        or not any("3.11" in name for name in names)
        or not any("3.12" in name for name in names)
    ):
        raise LiveWindowError("GATE_CI_INVALID")
    account = gates.get("account")
    if (
        not isinstance(account, dict)
        or account.get("source") not in {"owner_confirmation", "platform_check"}
        or account.get("project_verified") is not True
        or not _fresh_utc(account.get("confirmed_utc"))
        or not _finite_nonnegative(account.get("remaining_allocation_usd"))
        or account["remaining_allocation_usd"] < budget
    ):
        raise LiveWindowError("GATE_ACCOUNT_INVALID")
    pricing = gates.get("pricing")
    rates = (
        pricing.get("input_usd_per_million") if isinstance(pricing, dict) else None,
        pricing.get("cached_input_usd_per_million") if isinstance(pricing, dict) else None,
        pricing.get("output_usd_per_million") if isinstance(pricing, dict) else None,
    )
    if (
        not isinstance(pricing, dict)
        or not _fresh_utc(pricing.get("checked_utc"))
        or not isinstance(pricing.get("source_url"), str)
        or not pricing["source_url"].startswith("https://developers.openai.com/")
        or any(not _finite_nonnegative(rate) or rate <= 0 for rate in rates)
        or rates != (DEMO_INPUT_USD_M, DEMO_CACHED_INPUT_USD_M, DEMO_OUTPUT_USD_M)
    ):
        raise LiveWindowError("GATE_PRICING_INVALID")
    reconciliation = gates.get("reconciliation")
    if not isinstance(reconciliation, dict):
        raise LiveWindowError("GATE_RECONCILIATION_INVALID")
    if reconciliation.get("unresolved_cost_unknown") is not False:
        raise LiveWindowError("GATE_RECONCILIATION_UNKNOWN")
    hashes = reconciliation.get("receipt_hashes")
    prior = reconciliation.get("known_prior_cost_usd")
    if (
        not isinstance(hashes, list)
        or any(not isinstance(item, str) or len(item) != 64 for item in hashes)
        or not _finite_nonnegative(prior)
        or prior > budget
    ):
        raise LiveWindowError("GATE_RECONCILIATION_INVALID")
    return json.loads(json.dumps(gates))


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
        self._gates: dict[str, Any] | None = None
        self._owns_claim = False
        self._load()

    @classmethod
    def open(cls, root: Path, window_id: str, gates: dict[str, Any]) -> "LiveWindow":
        """Open a window only after validating the private paid-run gates."""
        validated = _validate_gates(gates, window_id)
        if Path(root).resolve() != canonical_window_root().resolve():
            raise LiveWindowError("NONCANONICAL_LEDGER_ROOT")
        window = cls(root=Path(root), window_id=window_id)
        canonical = json.dumps(validated, sort_keys=True, separators=(",", ":"))
        gate_sha = hashlib.sha256(canonical.encode()).hexdigest()
        existing = window._data.get("gates_sha256")
        if existing and existing != gate_sha:
            raise LiveWindowError("GATE_IDENTITY_MISMATCH")
        window._gates = validated
        window._data["gates_sha256"] = gate_sha
        if not window._data.get("attempts"):
            reconciliation = validated["reconciliation"]
            window._data["known_cost_usd"] = float(reconciliation["known_prior_cost_usd"])
            window._data["reconciled_receipt_hashes"] = list(reconciliation["receipt_hashes"])
        # Preflight/open is read-only. A second process must not overwrite the
        # first owner's request journal from an earlier cached ledger state.
        if (window.root / "claim.json").exists() and not window._data.get("consumed"):
            window._data["active_claim"] = True
        return window

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
                "attempted_requests": 0,
                "responses_received": 0,
                "valid_usage_records": 0,
            }

    def _persist(self) -> None:
        """Atomically persist ledger to disk."""
        self.root.mkdir(parents=True, exist_ok=True)
        # Write to temp file then rename for atomicity
        tmp = self.ledger_path.with_suffix(".tmp")
        with tmp.open("w", encoding="utf-8") as handle:
            json.dump(self._data, handle, indent=2, default=str)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp, self.ledger_path)

    def claim(self, implementation_sha: str, output: Path,
              budget_usd: float) -> dict[str, Any]:
        """
        Claim exclusive attempt before first request.

        Returns gates dict if claim succeeds.
        Raises LiveWindowError if already claimed or budget insufficient.
        """
        with self._lock:
            if self.ledger_path.exists():
                self._load()
            if self._gates is not None:
                if implementation_sha != self._gates["implementation_sha"]:
                    raise LiveWindowError("GATE_IMPLEMENTATION_SHA_MISMATCH")
                if budget_usd != self._gates["task_budget_usd"]:
                    raise LiveWindowError("GATE_BUDGET_MISMATCH")
            if self._data.get("consumed"):
                raise LiveWindowError("ATTEMPT_ALREADY_CONSUMED")

            # Check if output path matches registered output
            registered = self._data.get("registered_output")
            if registered and Path(registered) != Path(output):
                raise LiveWindowError("OUTPUT_PATH_MISMATCH")
            if self._data.get("active_claim"):
                raise LiveWindowError("ATTEMPT_ALREADY_CLAIMED")

            if type(budget_usd) not in (int, float) or not math.isfinite(budget_usd) or not 0 < budget_usd <= 0.25:
                raise LiveWindowError("INVALID_BUDGET")
            if self._gates is not None:
                gate_sha = hashlib.sha256(json.dumps(self._gates, sort_keys=True,
                    separators=(",", ":")).encode()).hexdigest()
                if self._data.get("gates_sha256") not in (None, gate_sha):
                    raise LiveWindowError("GATE_IDENTITY_MISMATCH")
                self._data["gates_sha256"] = gate_sha
                if not self._data.get("attempts"):
                    reconciliation = self._gates["reconciliation"]
                    self._data["known_cost_usd"] = float(reconciliation["known_prior_cost_usd"])
                    self._data["reconciled_receipt_hashes"] = list(reconciliation["receipt_hashes"])

            # Compute ceiling
            prior = self._data.get("known_cost_usd", 0.0)
            unknown = self._data.get("cost_unknown", False)
            reservations = sum(r.get("amount_usd", 0.0) for r in self._data.get("reservations", []))
            ceiling = prior + (0.0 if unknown else reservations)
            per_call = compute_request_reserve()

            if ceiling + per_call > budget_usd:
                raise LiveWindowError("BUDGET_INSUFFICIENT")

            self.root.mkdir(parents=True, exist_ok=True)
            try:
                # Durable and exclusive across processes. Never remove this
                # claim, including after crash or a terminal/failed run.
                with (self.root / "claim.json").open("x", encoding="utf-8") as handle:
                    json.dump({"implementation_sha": implementation_sha,
                               "condition": self.condition}, handle)
                    handle.flush()
                    os.fsync(handle.fileno())
            except FileExistsError:
                raise LiveWindowError("ATTEMPT_ALREADY_CLAIMED") from None

            # Register attempt
            self._data["attempts"].append({
                "implementation_sha": implementation_sha,
                "output": str(output),
                "budget_usd": budget_usd,
                "claimed_utc": datetime.now(timezone.utc).isoformat(),
                "calls": [],
            })
            self._data["registered_output"] = str(output)
            self._data["budget_usd"] = float(budget_usd)
            self._data["implementation_sha"] = implementation_sha
            self._data["active_claim"] = True
            self._persist()
            self._owns_claim = True

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
            if type(amount_usd) not in (int, float) or not math.isfinite(amount_usd) or amount_usd <= 0:
                raise LiveWindowError("INVALID_RESERVATION")
            self._data["reservations"].append({
                "amount_usd": amount_usd,
                "reserved_utc": datetime.now(timezone.utc).isoformat(),
            })
            self._persist()

    def record_response(self, stage: str, actual_model: str | None,
                       response_id: str | None, usage: dict | None,
                       cost_usd: float | None, latency_ms: float,
                       error: dict | None = None,
                       finish_reason: str | None = None) -> None:
        """Record a response after it arrives."""
        with self._lock:
            # Remove corresponding reservation
            if self._data["reservations"]:
                self._data["reservations"].pop(0)

            # Update cost
            if usage and cost_usd is not None:
                self._data["known_cost_usd"] = self._data.get("known_cost_usd", 0.0) + cost_usd
                self._data["valid_usage_records"] = self._data.get("valid_usage_records", 0) + 1
            elif usage is None or cost_usd is None:
                self._data["cost_unknown"] = True

            if error is None:
                self._data["responses_received"] = self._data.get("responses_received", 0) + 1

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
                "finish_reason": finish_reason,
            }
            if self._data["attempts"]:
                self._data["attempts"][-1]["calls"].append(call)

            self._persist()

    def record_terminal(self, status: str, final_cost_usd: float | None = None) -> None:
        """Mark window as terminal (complete or blocked)."""
        with self._lock:
            self._data["terminal_status"] = status
            self._data["terminal_utc"] = datetime.now(timezone.utc).isoformat()
            self._data["consumed"] = True
            self._data["active_claim"] = False
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
            "active_claim": self._data.get("active_claim", False),
            "terminal_status": self._data.get("terminal_status"),
            "known_cost_usd": self._data.get("known_cost_usd", 0.0),
            "cost_unknown": self._data.get("cost_unknown", False),
            "attempts": len(self._data.get("attempts", [])),
            "reservations": len(self._data.get("reservations", [])),
            "attempted_requests": self._data.get("attempted_requests", 0),
            "responses_received": self._data.get("responses_received", 0),
            "valid_usage_records": self._data.get("valid_usage_records", 0),
            "budget_usd": self._data.get("budget_usd"),
            "reserved_exposure_usd": sum(
                float(item.get("amount_usd", 0.0))
                for item in self._data.get("reservations", [])
            ),
        }

    def get_request_records(self) -> list[dict[str, Any]]:
        """Return the sanitized request journal for the active attempt."""
        if not self._data.get("attempts"):
            return []
        return [dict(item) for item in self._data["attempts"][-1].get("calls", [])]

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

        if not isinstance(contract, dict):
            raise LiveWindowError("MISSING_REQUEST_CONTRACT")
        return _GuardedClient(self, client, contract)

    def begin_request(self, reserve: float, request_summary: dict[str, Any]) -> None:
        """Persist a charged-attempt boundary before transport transmission."""
        with self._lock:
            if self._data.get("consumed") or self._data.get("terminal_status"):
                raise LiveWindowError("WINDOW_TERMINAL")
            if not self._data.get("active_claim"):
                raise LiveWindowError("WINDOW_NOT_CLAIMED")
            if not self._owns_claim:
                raise LiveWindowError("CLAIM_OWNERSHIP_REQUIRED")
            if self._data.get("cost_unknown"):
                raise LiveWindowError("COST_UNKNOWN_BLOCKS_RETRY")
            max_requests = int(request_summary["max_requests"])
            attempted = self._data.get("attempted_requests", 0)
            if attempted >= max_requests:
                raise LiveWindowError("REQUEST_LIMIT_REACHED")
            current_exposure = (
                float(self._data.get("known_cost_usd", 0.0))
                + sum(float(item["amount_usd"]) for item in self._data.get("reservations", []))
            )
            remaining_planned = max_requests - attempted
            if current_exposure + reserve * remaining_planned > float(self._data["budget_usd"]):
                raise LiveWindowError("BUDGET_INSUFFICIENT")
            self._data["attempted_requests"] = attempted + 1
            self._data["reservations"].append({
                "amount_usd": reserve,
                "reserved_utc": datetime.now(timezone.utc).isoformat(),
                "request": request_summary,
            })
            self._persist()


class _GuardedClient:
    """Proxy client that intercepts create() calls for window enforcement."""

    def __init__(self, window: LiveWindow, client: Any, contract: dict[str, Any]):
        self._window = window
        self._client = client
        completions = getattr(getattr(client, "chat", None), "completions", None)
        if completions is None or not callable(getattr(completions, "create", None)):
            raise LiveWindowError("INVALID_CLIENT_SHAPE")
        self._chat = _GuardedChat(window, completions, contract)

    @property
    def chat(self) -> "_GuardedChat":
        return self._chat


class _GuardedChat:
    """OpenAI-compatible chat namespace; create alias keeps old tests compatible."""

    def __init__(self, window: LiveWindow, completions: Any, contract: dict[str, Any]):
        self.completions = _GuardedCompletions(window, completions, contract)

    def create(self, **request) -> Any:
        return self.completions.create(**request)


class _GuardedCompletions:
    """Proxy completions that enforces budget/reserve before sending."""

    def __init__(self, window: LiveWindow, completions: Any, contract: dict[str, Any]):
        self._window = window
        self._completions = completions
        self._contract = dict(contract)

    def _validate_request(self, request: dict[str, Any]) -> None:
        expected = {
            "model": self._contract.get("model"),
            "temperature": self._contract.get("temperature"),
            "max_completion_tokens": self._contract.get("max_completion_tokens"),
            "tool_choice": self._contract.get("tool_choice"),
        }
        for field in ("parallel_tool_calls", "service_tier", "response_format", "tools"):
            if field in self._contract:
                expected[field] = self._contract[field]
        for field, value in expected.items():
            same_type = type(request.get(field)) is type(value)
            if field == "temperature":
                same_type = type(request.get(field)) in (int, float) and type(value) in (int, float)
            if value is None or not same_type or request.get(field) != value:
                raise LiveWindowError(f"REQUEST_CONTRACT_MISMATCH:{field}")
        try:
            encoded = json.dumps(request, separators=(",", ":"), default=str).encode("utf-8")
        except (TypeError, ValueError):
            raise LiveWindowError("REQUEST_SERIALIZATION_FAILED") from None
        max_bytes = int(self._contract.get("max_request_bytes", 45_000))
        input_bound = int(self._contract.get("input_token_reserve", INPUT_TOKEN_RESERVE))
        frame_reserve = int(self._contract.get("frame_reserve_tokens", FRAME_RESERVE_TOKENS))
        # A BPE token consumes at least one serialized byte; bytes + framing is
        # therefore a conservative upper bound over the complete request payload.
        if len(encoded) > max_bytes or len(encoded) + frame_reserve > input_bound:
            raise LiveWindowError("PAYLOAD_BOUND_EXCEEDED")

    @staticmethod
    def _usage(response: Any) -> tuple[dict[str, int] | None, float | None]:
        usage = getattr(response, "usage", None)
        if usage is None:
            return None, None
        input_tokens = getattr(usage, "prompt_tokens", None)
        output_tokens = getattr(usage, "completion_tokens", None)
        total_tokens = getattr(usage, "total_tokens", None)
        details = getattr(usage, "prompt_tokens_details", None)
        cached_tokens = getattr(details, "cached_tokens", 0) if details is not None else 0
        values = (input_tokens, output_tokens, cached_tokens)
        if any(type(value) is not int or value < 0 for value in values):
            return None, None
        if total_tokens is not None and (type(total_tokens) is not int or total_tokens < input_tokens + output_tokens):
            return None, None
        if cached_tokens > input_tokens:
            return None, None
        usage_dict = {
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "cached_tokens": cached_tokens,
        }
        return usage_dict, compute_request_reserve(input_tokens, output_tokens, cached_tokens)

    def create(self, **request) -> Any:
        """Intercept create() to enforce budget and record results."""
        from time import perf_counter

        self._validate_request(request)
        reserve = compute_request_reserve(INPUT_TOKEN_RESERVE, OUTPUT_TOKEN_RESERVE)
        self._window.begin_request(
            reserve,
            {
                "model": request["model"],
                "max_completion_tokens": request["max_completion_tokens"],
                "max_requests": int(self._contract.get("max_requests", 4)),
            },
        )
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
            raise LiveWindowError("PROVIDER_REQUEST_FAILED") from None

        # Record successful response
        latency_ms = (perf_counter() - started) * 1000
        actual_model = getattr(response, "model", None)
        resp_id = getattr(response, "id", None)
        usage_dict, cost_usd = self._usage(response)

        choices = getattr(response, "choices", None)
        finish_reason = getattr(choices[0], "finish_reason", None) if choices else None
        self._window.record_response(
            stage="response",
            actual_model=actual_model,
            response_id=resp_id,
            usage=usage_dict,
            cost_usd=cost_usd,
            latency_ms=latency_ms,
            error=None,
            finish_reason=finish_reason,
        )

        if usage_dict is None:
            raise LiveWindowError("RESPONSE_USAGE_INVALID")
        if (
            usage_dict["input_tokens"] > int(self._contract.get("input_token_reserve", INPUT_TOKEN_RESERVE))
            or usage_dict["output_tokens"] > int(self._contract.get("output_token_reserve", OUTPUT_TOKEN_RESERVE))
        ):
            raise LiveWindowError("RESPONSE_USAGE_EXCEEDS_BOUND")
        if actual_model != self._contract.get("model"):
            raise LiveWindowError("ACTUAL_MODEL_MISMATCH")
        if not isinstance(resp_id, str) or not resp_id or len(resp_id) > 160:
            raise LiveWindowError("RESPONSE_ID_INVALID")
        message = getattr(choices[0], "message", None) if choices else None
        has_tool_calls = bool(getattr(message, "tool_calls", None))
        expected_finish = "tool_calls" if has_tool_calls else "stop"
        if finish_reason != expected_finish:
            raise LiveWindowError("RESPONSE_FINISH_REASON_INVALID")

        return response
