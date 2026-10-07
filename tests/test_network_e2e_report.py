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


def _canonical_receipt():
    """Synthetic receipt in the actual public-lifecycle output shape."""
    return {
        "schema_version": 1, "synthetic": True, "run_id": "synthetic-e2e",
        "status": "technical_complete_awaiting_human",
        "scope": "network_only_public_lifecycle_demo", "transport": "synthetic",
        "implementation_sha": "a" * 40, "review_status": "awaiting_human",
        "attempted_calls": 4, "responses_received": 4, "valid_usage_records": 4,
        "cost_summary": {"known_cost_usd": 0.0123, "cost_unknown": False,
                         "reserved_exposure_usd": 0.0},
        "contract": {"prompt_sha256": "prompt-identity", "scenario_sha256": "scenario-identity"},
        "snapshot": {"logical_sha256": "snapshot-identity"},
        "requests": [{"stage": "botnet_tool", "actual_model": "actual-model",
                      "response_id": "response-1", "request_id": None,
                      "request_id_unavailable_reason": "not_exposed",
                      "usage": {"input_tokens": 100, "output_tokens": 20, "cached_tokens": 5},
                      "cost_usd": 0.0000705, "latency_ms": 120.0}],
        "scenarios": [{
            "name": "botnet", "assessment": "FULL MODEL ASSESSMENT " + "x" * 5000,
            "request": {"indicator": "10.0.0.1"},
            "risk_level": "UNKNOWN", "confidence": "LOW", "limitations": ["CTI unavailable"],
            "hypotheses": [{"description": "candidate", "supporting_evidence": ["ev-0"]}],
            "native_tool_calls": [{"tool_call_id": "call-1", "arguments": {"indicator": "10.0.0.1"}}],
            "tool_trace": [{"tool": "network_investigation", "call_id": "call-1"}],
            "evidence": [{"evidence_id": f"ev-{i}", "evidence_class": "OBSERVED",
                          "type": "network_flow_aggregate", "data": {"connection_count": i},
                          "provenance": {"source_records": [
                              {"source_dataset": "ctu13_s5", "source_row_id": f"row-{i}"}
                          ], "source_event_count": i}}
                         for i in range(25)],
            "observations": [{"evidence_id": "ev-24", "field": "connection_count", "value": 24}],
            "coverage": [{"record_ids_truncated": True}],
            "validation": {"technical_valid": True, "prose_semantics_machine_verified": False},
            "lifecycle": [{"phase": "verify", "status": "completed"}],
            "human_review": {"status": "awaiting_human"}, "termination": "FINAL_ASSESSMENT",
        }],
    }


def test_canonical_receipt_preserves_all_fields_and_nested_cost(tmp_path):
    from scripts.render_network_e2e_report import render_report
    receipt = _canonical_receipt()
    source, output = tmp_path / "receipt.json", tmp_path / "report.html"
    source.write_text(json.dumps(receipt), encoding="utf-8")
    result = render_report(source, output)
    rendered = output.read_text(encoding="utf-8")
    assert result["display_status"] == "AWAITING_HUMAN"
    assert result["evidence_items"] == 25
    assert result["api_calls"] == 0
    assert rendered.count("data-evidence-index=") == 25
    for value in ("ev-24", "row-24", "prompt-identity", "scenario-identity", "snapshot-identity",
                  "call-1", "response-1", "not_exposed", "CTI unavailable", "candidate"):
        assert value in rendered
    assert receipt["scenarios"][0]["assessment"] in rendered
    assert "$0.012300" in rendered
    assert "SYNTHETIC" in rendered
    assert "src='http" not in rendered and 'src="http' not in rendered


def test_partial_unknown_cost_is_not_rendered_as_free_or_complete(tmp_path):
    from scripts.render_network_e2e_report import render_report
    receipt = _canonical_receipt()
    receipt.update(status="partial", failed_stage="transport_guard", failure_category="PROVIDER_REQUEST_FAILED")
    receipt["cost_summary"]["cost_unknown"] = True
    receipt["requests"][0].update(usage=None, cost_usd=None, latency_ms=None)
    source, output = tmp_path / "partial.json", tmp_path / "partial.html"
    source.write_text(json.dumps(receipt), encoding="utf-8")
    result = render_report(source, output)
    rendered = output.read_text(encoding="utf-8")
    assert result["display_status"] == "PARTIAL"
    assert "transport_guard" in rendered and "PROVIDER_REQUEST_FAILED" in rendered
    assert "Total cost is unknown" in rendered
    assert "unknown / unavailable" in rendered


@pytest.mark.parametrize("receipt", [{"schema_version": 2}, [], {"schema_version": 1, "scenarios": "wrong"}])
def test_renderer_rejects_invalid_schema_before_creating_output(tmp_path, receipt):
    from scripts.render_network_e2e_report import render_report
    source, output = tmp_path / "bad.json", tmp_path / "bad.html"
    source.write_text(json.dumps(receipt), encoding="utf-8")
    with pytest.raises(ValueError, match="Invalid technical receipt"):
        render_report(source, output)
    assert not output.exists()


def test_renderer_never_overwrites_input_receipt(tmp_path):
    from scripts.render_network_e2e_report import render_report
    source = tmp_path / "receipt.json"
    source.write_text(json.dumps(_canonical_receipt()), encoding="utf-8")
    before = source.read_bytes()
    with pytest.raises(ValueError, match="overwrite"):
        render_report(source, source)
    assert source.read_bytes() == before


def test_renderer_missing_source_has_safe_error_and_no_output(tmp_path):
    from scripts.render_network_e2e_report import render_report
    output = tmp_path / "report.html"
    with pytest.raises(ValueError, match="Receipt unavailable"):
        render_report(tmp_path / "missing.json", output)
    assert not output.exists()


def test_legacy_complete_claim_with_deferred_review_is_not_complete(tmp_path):
    from scripts.render_network_e2e_report import render_report
    receipt = _canonical_receipt()
    receipt["status"] = "complete"
    source, output = tmp_path / "legacy.json", tmp_path / "legacy.html"
    source.write_text(json.dumps(receipt), encoding="utf-8")
    assert render_report(source, output)["display_status"] != "COMPLETE"


def test_renderer_does_not_trust_two_empty_approved_scenarios(tmp_path):
    from scripts.render_network_e2e_report import render_report
    receipt = {"schema_version": 1, "status": "approved", "scenarios": [
        {"validation": {"technical_valid": True}, "human_review": {"status": "approved"}},
        {"validation": {"technical_valid": True}, "human_review": {"status": "approved"}}]}
    source, output = tmp_path / "false.json", tmp_path / "false.html"
    source.write_text(json.dumps(receipt), encoding="utf-8")
    assert render_report(source, output)["display_status"] != "COMPLETE"


def test_linked_review_renders_complete_packet_and_rejects_wrong_input(tmp_path):
    from tests.test_network_e2e_runner import _reviewable_receipt
    from scripts.demo_ctu_network_public_model_driven import finalize_offline_review
    from scripts.render_network_e2e_report import render_report
    from agent.hitl import HumanDecision
    receipt = _reviewable_receipt()
    technical, reviewed, output = tmp_path / "technical.json", tmp_path / "review.json", tmp_path / "view.html"
    technical.write_text(json.dumps(receipt), encoding="utf-8")
    before = technical.read_bytes()
    class Gate:
        def review_final(self, _case):
            return HumanDecision("APPROVE", "synthetic review", analyst="synthetic-reviewer")
    finalize_offline_review(technical, reviewed, gate=Gate())
    result = render_report(technical, output, review_path=reviewed)
    assert result["display_status"] == "COMPLETE" and result["scenarios"] == 2
    assert technical.read_bytes() == before
    rendered = output.read_text()
    assert "synthetic-reviewer" in rendered and "Grounded assessment" in rendered and "ev_1" in rendered
    review = json.loads(reviewed.read_text())
    review["input_receipt_sha256"] = "f" * 64
    reviewed.write_text(json.dumps(review))
    with pytest.raises(ValueError, match="linked review"):
        render_report(technical, tmp_path / "invalid.html", review_path=reviewed)


@pytest.mark.parametrize("field,value", [("evidence", "bad"), ("validation", "bad"), ("human_review", [])])
def test_renderer_rejects_malformed_nested_fields(tmp_path, field, value):
    from scripts.render_network_e2e_report import render_report
    receipt = _canonical_receipt()
    receipt["scenarios"][0][field] = value
    source, output = tmp_path / "bad.json", tmp_path / "bad.html"
    source.write_text(json.dumps(receipt), encoding="utf-8")
    with pytest.raises(ValueError, match="Invalid technical receipt schema"):
        render_report(source, output)
    assert not output.exists()


def test_render_unverified_legacy_receipt_without_false_completion(tmp_path):
    """A synthetic legacy claim cannot substitute for validated review."""
    from scripts.render_network_e2e_report import render_report

    receipt = {
        "schema_version": 1,
        "synthetic": True, "run_id": "test_run_123",
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
    assert result["display_status"] == "PARTIAL"
    assert "class='status status-complete'" not in html

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
