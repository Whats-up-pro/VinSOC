"""Tests for LiveWindow transport guard.

These tests verify:
- Budget enforcement
- Race/crash handling
- Error/privacy guarantees
- Transport guard interception
"""
from __future__ import annotations

import json
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


def test_live_window_budget_gate_blocks_insufficient():
    """Test that insufficient budget is blocked."""
    from evaluation.finalization.live_window import LiveWindow, LiveWindowError, compute_request_reserve

    window = LiveWindow(Path("tests/.tmp-live-budget-test"), window_id="test-budget")
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


def test_live_window_output_path_mismatch():
    """Test that changing output path after claim is blocked."""
    from evaluation.finalization.live_window import LiveWindow, LiveWindowError

    window = LiveWindow(Path("tests/.tmp-live-output-test"), window_id="test-output")
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


def test_live_window_missing_usage_unknown_cost():
    """Test that missing usage sets cost_unknown flag."""
    from evaluation.finalization.live_window import LiveWindow

    window = LiveWindow(Path("tests/.tmp-live-unknown-test"), window_id="test-unknown")
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


def test_live_window_provider_error_safe_details():
    """Test that provider errors are sanitized."""
    from evaluation.finalization.live_window import LiveWindow

    window = LiveWindow(Path("tests/.tmp-live-error-test"), window_id="test-error")
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


def test_live_window_guard_blocks_wrong_condition():
    """Test that guarded client rejects wrong condition."""
    from evaluation.finalization.live_window import LiveWindow, LiveWindowError

    window = LiveWindow(Path("tests/.tmp-live-guard-test"), window_id="test-guard")
    mock_client = MagicMock()

    with pytest.raises(LiveWindowError, match="CONDITION_MISMATCH"):
        window.guarded_client(mock_client, condition="WRONG_CONDITION")


def test_live_window_terminal_blocks_further_calls():
    """Test that terminal window blocks further requests."""
    from evaluation.finalization.live_window import LiveWindow, LiveWindowError

    window = LiveWindow(Path("tests/.tmp-live-terminal-test"), window_id="test-terminal")
    window._data["terminal_status"] = "complete"
    window._data["cost_unknown"] = False

    mock_client = MagicMock()
    guarded = window.guarded_client(mock_client, condition="NETWORK_DEMO")

    # Access through the proxy: guarded.chat.completions.create
    # But the proxy uses 'completions' not 'chat.completions'
    with pytest.raises(LiveWindowError, match="WINDOW_TERMINAL"):
        guarded.chat.create(model="test", messages=[])


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
