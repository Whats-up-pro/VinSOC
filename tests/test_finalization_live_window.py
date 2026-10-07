"""Tests for LiveWindow transport guard.

These tests verify:
- Budget enforcement
- Race/crash handling
- Error/privacy guarantees
- Transport guard interception
"""
from __future__ import annotations

import json
import traceback
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest


def test_live_window_claim_blocks_duplicate_before_client(tmp_path):
    """Test that duplicate claim is blocked before client creation."""
    from evaluation.finalization.live_window import LiveWindow, LiveWindowError

    root = tmp_path / "duplicate_test"
    root.mkdir(parents=True, exist_ok=True)
    with pytest.raises(LiveWindowError, match="ATTEMPT_ALREADY_CONSUMED"):
        window = LiveWindow(root, window_id="test-duplicate")
        window._data["consumed"] = True
        window.claim(
            implementation_sha="abc123",
            output=tmp_path / "output.json",
            budget_usd=0.25,
        )


def test_live_window_budget_gate_blocks_insufficient(tmp_path):
    """Test that insufficient budget is blocked."""
    from evaluation.finalization.live_window import LiveWindow, LiveWindowError, compute_request_reserve

    window = LiveWindow(tmp_path / "window", window_id="test-budget")
    # Set prior cost to consume most of budget
    window._data["known_cost_usd"] = 0.24
    window._data["cost_unknown"] = False

    # Try to claim with remaining budget insufficient for one call
    with pytest.raises(LiveWindowError, match="BUDGET_INSUFFICIENT"):
        window.claim(
            implementation_sha="abc123",
            output=Path("tests/output.json"),
            budget_usd=0.25,
        )


def test_live_window_output_path_mismatch(tmp_path):
    """Test that changing output path after claim is blocked."""
    from evaluation.finalization.live_window import LiveWindow, LiveWindowError

    window = LiveWindow(tmp_path / "window", window_id="test-output")
    # First claim
    window.claim(
        implementation_sha="abc123",
        output=Path("tests/output1.json"),
        budget_usd=0.25,
    )

    # Try to claim with different output
    with pytest.raises(LiveWindowError, match="OUTPUT_PATH_MISMATCH"):
        window.claim(
            implementation_sha="abc123",
            output=Path("tests/output2.json"),
            budget_usd=0.25,
        )


def test_live_window_record_response_updates_cost(tmp_path):
    """Test that recording a response updates known cost."""
    from evaluation.finalization.live_window import LiveWindow

    root = tmp_path / "record_test"
    root.mkdir(parents=True, exist_ok=True)
    window = LiveWindow(root, window_id="test-record")
    window.claim(
        implementation_sha="abc123",
        output=tmp_path / "output.json",
        budget_usd=0.25,
    )
    # Reserve first
    window.reserve(0.0216)

    # Record response
    window.record_response(
        stage="test_call",
        actual_model="gpt-4.1-mini-2025-04-14",
        response_id="resp_123",
        usage={"input_tokens": 100, "output_tokens": 50, "cached_tokens": 0},
        cost_usd=0.0005,
        latency_ms=500.0,
    )

    assert window._data["known_cost_usd"] == 0.0005
    assert len(window._data["reservations"]) == 0  # Reservation consumed
    assert len(window._data["attempts"][0]["calls"]) == 1


def test_live_window_missing_usage_unknown_cost(tmp_path):
    """Test that missing usage sets cost_unknown flag."""
    from evaluation.finalization.live_window import LiveWindow

    window = LiveWindow(tmp_path / "window", window_id="test-unknown")
    window.claim(
        implementation_sha="abc123",
        output=Path("tests/output.json"),
        budget_usd=0.25,
    )
    window.reserve(0.0216)

    # Record error response with no usage
    window.record_response(
        stage="error_call",
        actual_model=None,
        response_id=None,
        usage=None,
        cost_usd=None,
        latency_ms=100.0,
        error={"status": 429, "code": "rate_limit"},
    )

    assert window._data["cost_unknown"] is True
    assert window._data["known_cost_usd"] == 0.0


def test_live_window_provider_error_safe_details(tmp_path):
    """Test that provider errors are sanitized."""
    from evaluation.finalization.live_window import LiveWindow

    window = LiveWindow(tmp_path / "window", window_id="test-error")
    window.claim(
        implementation_sha="abc123",
        output=Path("tests/output.json"),
        budget_usd=0.25,
    )
    window.reserve(0.0216)

    # Record error with sensitive data
    error = {
        "status": 429,
        "code": "rate_limit_exceeded",
        "type": "requests",
        "request_id": "req_safe_123",
        "retry_after": "2",
    }

    window.record_response(
        stage="error_call",
        actual_model=None,
        response_id=None,
        usage=None,
        cost_usd=None,
        latency_ms=100.0,
        error=error,
    )

    # Verify error is stored safely
    call = window._data["attempts"][0]["calls"][0]
    assert call["error"]["status"] == 429
    assert call["error"]["code"] == "rate_limit_exceeded"
    assert call["error"]["request_id"] == "req_safe_123"
    assert "sk-" not in json.dumps(call)


def test_live_window_guard_blocks_wrong_condition(tmp_path):
    """Test that guarded client rejects wrong condition."""
    from evaluation.finalization.live_window import LiveWindow, LiveWindowError

    window = LiveWindow(tmp_path / "window", window_id="test-guard")
    mock_client = MagicMock()

    with pytest.raises(LiveWindowError, match="CONDITION_MISMATCH"):
        window.guarded_client(mock_client, condition="WRONG_CONDITION")


def test_live_window_terminal_blocks_further_calls(tmp_path):
    """Test that terminal window blocks further requests."""
    from evaluation.finalization.live_window import LiveWindow, LiveWindowError

    window = LiveWindow(tmp_path / "window", window_id="test-terminal")
    window._data["terminal_status"] = "complete"
    window._data["cost_unknown"] = False

    mock_client = MagicMock()
    mock_client.chat.completions.create.return_value = _response()
    guarded = window.guarded_client(
        mock_client,
        condition="NETWORK_DEMO",
        contract=_valid_contract(),
    )

    # Access through the proxy: guarded.chat.completions.create
    # But the proxy uses 'completions' not 'chat.completions'
    with pytest.raises(LiveWindowError, match="WINDOW_TERMINAL"):
        guarded.chat.completions.create(
            model="gpt-4.1-mini-2025-04-14",
            messages=[],
            temperature=0,
            max_completion_tokens=1000,
            tool_choice="auto",
        )


def test_live_window_atomic_persistence(tmp_path):
    """Test that ledger is persisted atomically."""
    from evaluation.finalization.live_window import LiveWindow

    root = tmp_path / "atomic_test"
    root.mkdir(parents=True, exist_ok=True)

    window = LiveWindow(root, window_id="test-atomic")

    # Create initial ledger
    window.claim(
        implementation_sha="abc123",
        output=tmp_path / "output.json",
        budget_usd=0.25,
    )

    ledger_path = root / "ledger.json"
    assert ledger_path.exists()

    # Read and verify structure
    data = json.loads(ledger_path.read_text())
    assert "window_id" in data
    assert "attempts" in data
    assert len(data["attempts"]) == 1


def test_compute_request_reserve():
    """Test request reserve calculation."""
    from evaluation.finalization.live_window import compute_request_reserve

    # Standard request
    reserve = compute_request_reserve(50000, 1000, 0)
    assert reserve > 0
    assert reserve < 0.03  # Should be around $0.0216

    # With caching
    reserve_cached = compute_request_reserve(50000, 1000, 10000)
    assert reserve_cached < reserve  # Caching should reduce cost


def test_safe_error_field():
    """Test that safe error fields block sensitive data."""
    from evaluation.finalization.live_window import _safe_error_field

    # Valid field
    assert _safe_error_field("rate_limit_exceeded") == "rate_limit_exceeded"

    # Key-like field blocked
    assert _safe_error_field("sk-proj-KEY") is None
    assert _safe_error_field("sk-key-123") is None

    # Invalid characters blocked
    assert _safe_error_field("has space") is None
    assert _safe_error_field("has\ttab") is None


def test_safe_request_id():
    """Test that request IDs are validated."""
    from evaluation.finalization.live_window import _safe_request_id

    # Valid IDs
    assert _safe_request_id("req_abc123") == "req_abc123"
    assert _safe_request_id("req_123.456:789") == "req_123.456:789"

    # Invalid IDs
    assert _safe_request_id("has space") is None
    assert _safe_request_id("sk-key") is None
    assert _safe_request_id("") is None


def _valid_contract(**overrides):
    contract = {
        "model": "gpt-4.1-mini-2025-04-14",
        "temperature": 0,
        "max_completion_tokens": 1000,
        "max_retries": 0,
        "tool_choice": "auto",
        "max_requests": 4,
        "budget_usd": 0.25,
    }
    contract.update(overrides)
    return contract


def _valid_gates(**overrides):
    now = datetime.now(timezone.utc).isoformat()
    gates = {
        "schema_version": 1,
        "window_id": "network-finalization-20261006",
        "task_budget_usd": 0.25,
        "implementation_sha": "a" * 40,
        "ci": {
            "head_sha": "a" * 40,
            "run_url": "https://github.com/Whats-up-pro/VinSOC/actions/runs/123",
            "conclusion": "success",
            "jobs": [
                {"name": "test (3.11)", "conclusion": "success", "job_url": "https://github.com/job/311"},
                {"name": "test (3.12)", "conclusion": "success", "job_url": "https://github.com/job/312"},
            ],
        },
        "account": {
            "source": "owner_confirmation",
            "confirmed_utc": now,
            "project_verified": True,
            "remaining_allocation_usd": 1.0,
        },
        "pricing": {
            "checked_utc": now,
            "source_url": "https://developers.openai.com/api/docs/models/gpt-4.1-mini",
            "input_usd_per_million": 0.40,
            "cached_input_usd_per_million": 0.10,
            "output_usd_per_million": 1.60,
        },
        "reconciliation": {
            "receipt_hashes": [],
            "known_prior_cost_usd": 0.0,
            "unresolved_cost_unknown": False,
        },
    }
    gates.update(overrides)
    return gates


def test_open_validates_private_gates_before_claim(tmp_path):
    from evaluation.finalization.live_window import LiveWindow, LiveWindowError

    window = LiveWindow.open(tmp_path / "window", "network-finalization-20261006", _valid_gates())
    window.claim("a" * 40, tmp_path / "result.json", 0.25)

    with pytest.raises(LiveWindowError, match="GATE_IMPLEMENTATION_SHA_MISMATCH"):
        LiveWindow.open(
            tmp_path / "wrong-sha",
            "network-finalization-20261006",
            _valid_gates(implementation_sha="b" * 40),
        )


@pytest.mark.parametrize(
    ("mutation", "expected"),
    [
        (lambda gates: gates["ci"].update(conclusion="failure"), "GATE_CI_INVALID"),
        (lambda gates: gates["account"].update(project_verified=False), "GATE_ACCOUNT_INVALID"),
        (lambda gates: gates["reconciliation"].update(unresolved_cost_unknown=True), "GATE_RECONCILIATION_UNKNOWN"),
        (lambda gates: gates["pricing"].update(input_usd_per_million=0.0), "GATE_PRICING_INVALID"),
    ],
)
def test_open_rejects_invalid_private_gates(tmp_path, mutation, expected):
    from evaluation.finalization.live_window import LiveWindow, LiveWindowError

    gates = _valid_gates()
    mutation(gates)
    with pytest.raises(LiveWindowError, match=expected):
        LiveWindow.open(tmp_path / "window", "network-finalization-20261006", gates)


def _response(*, model="gpt-4.1-mini-2025-04-14"):
    return SimpleNamespace(
        id="chatcmpl_safe123",
        model=model,
        usage=SimpleNamespace(
            prompt_tokens=120,
            completion_tokens=40,
            total_tokens=160,
            prompt_tokens_details=SimpleNamespace(cached_tokens=0),
        ),
        choices=[SimpleNamespace(finish_reason="stop")],
    )


def test_guarded_client_uses_openai_shape_and_journals_before_transport(tmp_path):
    """The real transport path is chat.completions.create and is journaled first."""
    from evaluation.finalization.live_window import LiveWindow

    window = LiveWindow(tmp_path / "window")
    window.claim("abc123", tmp_path / "result.json", 0.25)
    seen = {}

    class Completions:
        def create(self, **request):
            persisted = json.loads(window.ledger_path.read_text(encoding="utf-8"))
            seen["attempted_before_send"] = persisted["attempted_requests"]
            seen["request"] = request
            return _response()

    client = SimpleNamespace(chat=SimpleNamespace(completions=Completions()))
    guarded = window.guarded_client(client, "NETWORK_DEMO", _valid_contract())
    response = guarded.chat.completions.create(
        model="gpt-4.1-mini-2025-04-14",
        messages=[{"role": "user", "content": "bounded request"}],
        temperature=0,
        max_completion_tokens=1000,
        tool_choice="auto",
    )

    assert response.id == "chatcmpl_safe123"
    assert seen["attempted_before_send"] == 1
    status = window.get_status()
    assert status["attempted_requests"] == 1
    assert status["responses_received"] == 1
    assert status["valid_usage_records"] == 1
    assert status["cost_unknown"] is False


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("model", "wrong-model"),
        ("temperature", 1),
        ("max_completion_tokens", 999),
        ("tool_choice", {"type": "function", "function": {"name": "network_investigation"}}),
    ],
)
def test_guarded_client_rejects_request_contract_before_transport(tmp_path, field, value):
    from evaluation.finalization.live_window import LiveWindow, LiveWindowError

    window = LiveWindow(tmp_path / "window")
    window.claim("abc123", tmp_path / "result.json", 0.25)
    create = MagicMock(return_value=_response())
    client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)))
    guarded = window.guarded_client(client, "NETWORK_DEMO", _valid_contract())
    request = {
        "model": "gpt-4.1-mini-2025-04-14",
        "messages": [],
        "temperature": 0,
        "max_completion_tokens": 1000,
        "tool_choice": "auto",
    }
    request[field] = value

    with pytest.raises(LiveWindowError, match="REQUEST_CONTRACT_MISMATCH"):
        guarded.chat.completions.create(**request)

    create.assert_not_called()
    assert window.get_status()["attempted_requests"] == 0


def test_terminal_consumes_window_and_blocks_same_output_reclaim(tmp_path):
    from evaluation.finalization.live_window import LiveWindow, LiveWindowError

    root = tmp_path / "window"
    output = tmp_path / "result.json"
    window = LiveWindow(root)
    window.claim("abc123", output, 0.25)
    window.record_terminal("partial")

    reopened = LiveWindow(root)
    assert reopened.get_status()["consumed"] is True
    with pytest.raises(LiveWindowError, match="ATTEMPT_ALREADY_CONSUMED"):
        reopened.claim("abc123", output, 0.25)


def test_guarded_provider_error_is_safe_and_suppresses_raw_exception(tmp_path):
    from evaluation.finalization.live_window import LiveWindow, LiveWindowError

    secret = "SENSITIVE_RAW_ERROR sk-secret-never-print"
    window = LiveWindow(tmp_path / "window")
    window.claim("abc123", tmp_path / "result.json", 0.25)

    class ProviderFailure(Exception):
        status_code = 429
        body = {"error": {"code": "rate_limit_exceeded", "type": "requests"}}
        request_id = "req_safe123"
        response = SimpleNamespace(headers={"retry-after": "2"})

    create = MagicMock(side_effect=ProviderFailure(secret))
    client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)))
    guarded = window.guarded_client(client, "NETWORK_DEMO", _valid_contract())

    with pytest.raises(LiveWindowError, match="PROVIDER_REQUEST_FAILED") as caught:
        guarded.chat.completions.create(
            model="gpt-4.1-mini-2025-04-14",
            messages=[],
            temperature=0,
            max_completion_tokens=1000,
            tool_choice="auto",
        )

    rendered = "".join(traceback.format_exception(caught.value))
    ledger = window.ledger_path.read_text(encoding="utf-8")
    assert secret not in rendered
    assert secret not in ledger
    assert caught.value.__suppress_context__ is True
    assert window.get_status()["attempted_requests"] == 1
    assert window.get_status()["cost_unknown"] is True
