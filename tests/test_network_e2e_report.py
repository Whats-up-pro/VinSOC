"""Tests for network E2E report renderer.

These tests verify:
- JSON to HTML rendering
- Partial/awaiting-human statuses
- XSS escaping
- API/client calls = 0
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest


def test_render_complete_receipt(tmp_path):
    """Test rendering a complete receipt."""
    from scripts.render_network_e2e_report import render_report

    receipt = {
        "schema_version": 1,
        "run_id": "test_run_123",
        "status": "complete",
        "scope": "network_only_public_lifecycle_demo",
        "transport": "openai_sdk_live",
        "implementation_sha": "abc123def456",
        "budget_usd": 0.25,
        "known_cost_usd": 0.0123,
        "cost_unknown": False,
        "reserved_exposure_usd": 0.0086,
        "requests": [
            {
                "stage": "botnet_tool_request",
                "actual_model": "gpt-4.1-mini-2025-04-14",
                "usage": {"input_tokens": 500, "output_tokens": 50},
                "cost_usd": 0.003,
                "latency_ms": 500.0,
            },
            {
                "stage": "botnet_assessment",
                "actual_model": "gpt-4.1-mini-2025-04-14",
                "usage": {"input_tokens": 300, "output_tokens": 100},
                "cost_usd": 0.0018,
                "latency_ms": 300.0,
            },
        ],
        "scenarios": [
            {
                "name": "botnet",
                "ground_truth_label": "Botnet",
                "assessment": {
                    "assessment": "Suspicious network activity detected.",
                    "risk_level": "HIGH",
                    "confidence": "MEDIUM",
                },
                "evidence": [
                    {
                        "evidence_id": "ev_123",
                        "type": "network_flow",
                        "evidence_class": "OBSERVED",
                        "source_name": "ctu13_s5",
                    }
                ],
                "observations": [
                    {"evidence_id": "ev_123", "field": "connection_count", "value": 42},
                    {"evidence_id": "ev_123", "field": "protocol", "value": "TCP"},
                ],
                "validation": {"factual_check_passed": True, "issues": []},
                "lifecycle": {"investigate": "completed", "verify": "completed"},
                "human_review": {"status": "awaiting_human"},
            },
            {
                "name": "normal",
                "ground_truth_label": "Normal",
                "assessment": {
                    "assessment": "Normal traffic patterns observed.",
                    "risk_level": "LOW",
                    "confidence": "HIGH",
                },
                "evidence": [
                    {
                        "evidence_id": "ev_456",
                        "type": "network_flow",
                        "evidence_class": "OBSERVED",
                        "source_name": "ctu13_s7",
                    }
                ],
                "observations": [
                    {"evidence_id": "ev_456", "field": "connection_count", "value": 15},
                    {"evidence_id": "ev_456", "field": "protocol", "value": "TCP"},
                ],
                "validation": {"factual_check_passed": True, "issues": []},
                "lifecycle": {"investigate": "completed", "verify": "completed"},
                "human_review": {"status": "awaiting_human"},
            },
        ],
        "generated_at": "2026-10-06T12:00:00Z",
    }

    receipt_path = tmp_path / "receipt.json"
    receipt_path.write_text(json.dumps(receipt), encoding="utf-8")

    output_path = tmp_path / "report.html"
    result = render_report(receipt_path, output_path)

    assert result["status"] == "success"
    assert output_path.exists()

    html = output_path.read_text(encoding="utf-8")

    # Check status display
    assert "COMPLETE" in html
    assert "status-complete" in html

    # Check scenarios
    assert "botnet" in html
    assert "normal" in html
    assert "Suspicious network activity detected" in html

    # Check cost
    assert "$0.012300" in html or "0.0123" in html

    # Check no API calls (verify client_created is not in HTML)
    assert "client_created" not in html


def test_render_awaiting_human_receipt(tmp_path):
    """Test rendering a receipt awaiting human review."""
    from scripts.render_network_e2e_report import render_report

    receipt = {
        "schema_version": 1,
        "run_id": "test_run_456",
        "status": "awaiting_human",
        "scope": "network_only_public_lifecycle_demo",
        "transport": "openai_sdk_live",
        "implementation_sha": "abc123",
        "scenarios": [
            {
                "name": "botnet",
                "assessment": {
                    "assessment": "Analysis complete.",
                    "risk_level": "MEDIUM",
                    "confidence": "MEDIUM",
                },
                "evidence": [],
                "validation": {},
                "lifecycle": {},
                "human_review": {"status": "awaiting_human"},
            }
        ],
        "requests": [],
    }

    receipt_path = tmp_path / "receipt_awaiting.json"
    receipt_path.write_text(json.dumps(receipt), encoding="utf-8")

    output_path = tmp_path / "report_awaiting.html"
    result = render_report(receipt_path, output_path)

    assert result["status"] == "success"
    html = output_path.read_text(encoding="utf-8")

    # Check awaiting_human status display
    assert "AWAITING_HUMAN" in html
    assert "status-pending" in html


def test_render_partial_receipt(tmp_path):
    """Test rendering a partial receipt (some scenarios failed)."""
    from scripts.render_network_e2e_report import render_report

    receipt = {
        "schema_version": 1,
        "run_id": "test_run_789",
        "status": "partial",
        "scope": "network_only_public_lifecycle_demo",
        "transport": "openai_sdk_live",
        "implementation_sha": "abc123",
        "scenarios": [
            {
                "name": "botnet",
                "assessment": {
                    "assessment": "First scenario completed.",
                    "risk_level": "MEDIUM",
                    "confidence": "MEDIUM",
                },
                "evidence": [],
                "validation": {},
                "lifecycle": {},
                "human_review": {},
            },
            {
                "name": "normal",
                "assessment": None,
                "evidence": [],
                "validation": {},
                "lifecycle": {},
                "human_review": {},
                "termination": "error",
                "error": "Model returned invalid response",
            },
        ],
        "requests": [],
    }

    receipt_path = tmp_path / "receipt_partial.json"
    receipt_path.write_text(json.dumps(receipt), encoding="utf-8")

    output_path = tmp_path / "report_partial.html"
    result = render_report(receipt_path, output_path)

    assert result["status"] == "success"
    html = output_path.read_text(encoding="utf-8")

    # Check partial status
    assert "PARTIAL" in html
    assert "status-partial" in html


def test_xss_escaping(tmp_path):
    """Test that XSS payloads are escaped in HTML output."""
    from scripts.render_network_e2e_report import render_report

    receipt = {
        "schema_version": 1,
        "run_id": "test_xss",
        "status": "complete",
        "scope": "network_only_public_lifecycle_demo",
        "scenarios": [
            {
                "name": '<script>alert("XSS")</script>',
                "assessment": {
                    "assessment": 'Test with <img src=x onerror=alert("XSS")>',
                    "risk_level": "MEDIUM",
                    "confidence": "MEDIUM",
                },
                "evidence": [],
                "validation": {},
                "lifecycle": {},
                "human_review": {},
            }
        ],
        "requests": [],
    }

    receipt_path = tmp_path / "receipt_xss.json"
    receipt_path.write_text(json.dumps(receipt), encoding="utf-8")

    output_path = tmp_path / "report_xss.html"
    result = render_report(receipt_path, output_path)

    assert result["status"] == "success"
    html = output_path.read_text(encoding="utf-8")

    # Check that script tags are escaped
    assert "&lt;script&gt;" in html or "<script>" not in html
    assert "alert" in html  # The word "alert" should appear as text


def test_no_api_client_calls_in_renderer():
    """Test that renderer does not make API calls."""
    from scripts.render_network_e2e_report import render_report
    import inspect

    # Check that render_report doesn't call any API
    source = inspect.getsource(render_report)

    # Should not contain any API calls
    assert "openai" not in source.lower()
    assert "requests.get" not in source
    assert "urllib" not in source


def test_json_html_counts_parity(tmp_path):
    """Test that JSON and HTML have matching scenario/request counts."""
    from scripts.render_network_e2e_report import render_report

    receipt = {
        "schema_version": 1,
        "run_id": "test_parity",
        "status": "complete",
        "scope": "test",
        "scenarios": [
            {"name": "s1", "assessment": {}, "evidence": [], "validation": {}, "lifecycle": {}, "human_review": {}},
            {"name": "s2", "assessment": {}, "evidence": [], "validation": {}, "lifecycle": {}, "human_review": {}},
        ],
        "requests": [
            {"stage": "req1"},
            {"stage": "req2"},
        ],
    }

    receipt_path = tmp_path / "receipt_parity.json"
    receipt_path.write_text(json.dumps(receipt), encoding="utf-8")

    output_path = tmp_path / "report_parity.html"
    result = render_report(receipt_path, output_path)

    assert result["scenarios"] == 2
    assert result["requests"] == 2

    html = output_path.read_text(encoding="utf-8")

    # Check both scenarios appear
    assert "s1" in html
    assert "s2" in html

    # Check both requests appear
    assert "req1" in html
    assert "req2" in html


def test_missing_optional_fields_handled(tmp_path):
    """Test that missing optional fields are handled gracefully."""
    from scripts.render_network_e2e_report import render_report

    receipt = {
        "schema_version": 1,
        "run_id": "test_minimal",
        "status": "complete",
        "scope": "test",
        # Missing many optional fields
        "scenarios": [
            {"name": "s1"},  # Minimal scenario
        ],
        # Missing requests
    }

    receipt_path = tmp_path / "receipt_minimal.json"
    receipt_path.write_text(json.dumps(receipt), encoding="utf-8")

    output_path = tmp_path / "report_minimal.html"

    # Should not raise
    result = render_report(receipt_path, output_path)
    assert result["status"] == "success"
    assert output_path.exists()
