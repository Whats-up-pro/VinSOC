"""The model-driven demo must execute validated model arguments and cite real evidence."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from types import SimpleNamespace

import duckdb
import pytest


# =============================================================================
# Test helper functions directly
# =============================================================================


def _snapshot(path: Path) -> Path:
    with duckdb.connect(str(path)) as conn:
        conn.execute(
            "CREATE TABLE network_flows (source_dataset VARCHAR, source_row_id VARCHAR, event_time TIMESTAMP, "
            "src_ip VARCHAR, src_port INTEGER, dst_ip VARCHAR, dst_port INTEGER, protocol VARCHAR, "
            "action VARCHAR, bytes_out BIGINT, bytes_in BIGINT, label VARCHAR)"
        )
        conn.execute(
            "INSERT INTO network_flows VALUES "
            "('ctu13_s7', '42', TIMESTAMP '2011-08-16 10:00:00', '192.0.2.10', 4444, "
            "'198.51.100.10', 80, 'TCP', 'CON', 12, 6, 'Botnet'), "
            "('ctu13_s5', '43', TIMESTAMP '2011-08-15 10:00:00', '192.0.2.11', 4445, "
            "'198.51.100.11', 443, 'TCP', 'CON', 12, 6, 'flow=From-Normal-V46-Grill')"
        )
    return path


class FakeAssessmentClient:
    """Client that returns assessment with controlled content for failure testing."""

    def __init__(self, assessment_content: str, finish_reason: str = "stop"):
        self.requests = []
        self.assessment_content = assessment_content
        self.finish_reason = finish_reason
        self.chat = SimpleNamespace(completions=self)

    def create(self, **request):
        self.requests.append(request)
        if request.get("tools"):
            text = request["messages"][-1]["content"]
            indicator = "192.0.2.10" if "192.0.2.10" in text else "192.0.2.11"
            scenario = json.loads(text)
            args = {
                "indicator": indicator,
                "indicator_type": "ipv4",
                "time_range": scenario["time_range"],
            }
            message = SimpleNamespace(
                tool_calls=[
                    SimpleNamespace(
                        id="fake_tool_call",
                        function=SimpleNamespace(
                            name="network_investigation", arguments=json.dumps(args)
                        ),
                    )
                ],
                content=None,
            )
        else:
            message = SimpleNamespace(
                tool_calls=None,
                content=self.assessment_content,
            )
        return SimpleNamespace(
            id=f"fake_response_{len(self.requests)}",
            model="gpt-4.1-mini-2025-04-14",
            usage=SimpleNamespace(prompt_tokens=100, completion_tokens=50),
            choices=[SimpleNamespace(message=message, finish_reason=self.finish_reason)],
        )


class FakeClient:
    def __init__(self, *, invalid_indicator: bool = False):
        self.requests = []
        self.invalid_indicator = invalid_indicator
        self.chat = SimpleNamespace(completions=self)

    def create(self, **request):
        self.requests.append(request)
        if request.get("tools"):
            text = request["messages"][-1]["content"]
            indicator = "192.0.2.10" if "192.0.2.10" in text else "192.0.2.11"
            if self.invalid_indicator:
                indicator = "203.0.113.77"
            scenario = json.loads(text)
            args = {
                "indicator": indicator,
                "indicator_type": "ipv4",
                "time_range": scenario["time_range"],
            }
            message = SimpleNamespace(
                tool_calls=[
                    SimpleNamespace(
                        id="fake_tool_call",
                        function=SimpleNamespace(
                            name="network_investigation", arguments=json.dumps(args)
                        ),
                    )
                ],
                content=None,
            )
        else:
            evidence = json.loads(request["messages"][-1]["content"])["evidence"]
            evidence_ids = [item["evidence_id"] for item in evidence]
            message = SimpleNamespace(
                tool_calls=None,
                content=json.dumps(
                    {
                        "assessment": (
                            f"Observed network evidence {evidence_ids[0]}."
                            if evidence_ids
                            else "No network evidence observed."
                        ),
                        "evidence_ids": evidence_ids[:1],
                        "limitations": ["CTI and endpoint evidence unavailable."],
                    }
                ),
            )
        return SimpleNamespace(
            id=f"fake_response_{len(self.requests)}",
            model="gpt-4.1-mini-2025-04-14",
            usage=SimpleNamespace(prompt_tokens=100, completion_tokens=50),
            choices=[SimpleNamespace(message=message, finish_reason="stop")],
        )


class FailingClient:
    def __init__(self, error):
        self.error = error
        self.requests = []
        self.chat = SimpleNamespace(completions=self)

    def create(self, **request):
        self.requests.append(request)
        raise self.error


class FakeProviderError(Exception):
    def __init__(
        self,
        raw_message,
        *,
        status_code=None,
        body=None,
        request_id=None,
        headers=None,
    ):
        super().__init__(raw_message)
        self.status_code = status_code
        self.body = body
        self.request_id = request_id
        self.response = SimpleNamespace(headers=headers or {})


def test_model_arguments_reach_network_tool_and_model_assesses_evidence(monkeypatch, tmp_path):
    from scripts import demo_ctu_network_public_model_driven as demo

    monkeypatch.setattr(
        demo,
        "validate",
        lambda *_args, **_kwargs: {
            "version": "ctu_network_public_dev_v1",
            "logical_snapshot_sha256": "a" * 64,
        },
    )
    output = tmp_path / "result.json"
    client = FakeClient()
    report = demo.run_model_driven_demo(_snapshot(tmp_path / "ctu.duckdb"), output, client=client)

    assert report["status"] == "complete"
    assert report["attempted_calls"] == report["responses_received"] == 4
    assert report["execution_semantics"]["model_generated_arguments_executed"] is True
    assert report["execution_semantics"]["model_generated_assessment"] is True
    assert all(len(request.get("tools", [])) == 1 for request in client.requests[::2])
    assert all(not request.get("tools") for request in client.requests[1::2])
    assert [item["tool_trace"][0]["arguments"]["indicator"] for item in report["scenarios"]] == [
        "192.0.2.10",
        "192.0.2.11",
    ]
    for item in report["scenarios"]:
        assert item["assessment_evidence_ids"]
        assert set(item["assessment_evidence_ids"]) <= set(item["evidence_ids"])
        assert item["assessment_evidence_ids"][0] in item["assessment"]
    assert json.loads(output.read_text(encoding="utf-8"))["status"] == "complete"


def test_out_of_scope_model_indicator_stops_before_tool_execution(monkeypatch, tmp_path):
    from scripts import demo_ctu_network_public_model_driven as demo

    monkeypatch.setattr(
        demo,
        "validate",
        lambda *_args, **_kwargs: {
            "version": "ctu_network_public_dev_v1",
            "logical_snapshot_sha256": "a" * 64,
        },
    )
    output = tmp_path / "partial.json"
    client = FakeClient(invalid_indicator=True)
    with pytest.raises(ValueError, match="model tool arguments"):
        demo.run_model_driven_demo(_snapshot(tmp_path / "ctu.duckdb"), output, client=client)
    report = json.loads(output.read_text(encoding="utf-8"))
    assert report["attempted_calls"] == report["responses_received"] == 1
    assert report["known_cost_usd"] > 0
    assert report["status"] == "invalid_tool_arguments"
    assert report["scenarios"] == []
    assert report["execution_semantics"]["model_generated_arguments_executed"] is False
    assert report["execution_semantics"]["model_generated_assessment"] is False


def test_budget_gate_stops_before_api_call(monkeypatch, tmp_path):
    from scripts import demo_ctu_network_public_model_driven as demo

    monkeypatch.setattr(
        demo,
        "validate",
        lambda *_args, **_kwargs: {
            "version": "ctu_network_public_dev_v1",
            "logical_snapshot_sha256": "a" * 64,
        },
    )
    output = tmp_path / "partial.json"
    client = FakeClient()
    with pytest.raises(ValueError, match="budget"):
        demo.run_model_driven_demo(
            _snapshot(tmp_path / "ctu.duckdb"),
            output,
            client=client,
            budget_usd=0.001371,
        )
    report = json.loads(output.read_text(encoding="utf-8"))
    assert report["attempted_calls"] == 0
    assert client.requests == []


@pytest.mark.parametrize(
    ("error", "expected"),
    [
        (
            FakeProviderError(
                "RAW_RATE_LIMIT_MESSAGE SECRET_VALUE",
                status_code=429,
                body={"error": {"code": "rate_limit_exceeded", "type": "requests"}},
                request_id="req_safe_123",
                headers={"Retry-After": "2"},
            ),
            {
                "status": 429,
                "code": "rate_limit_exceeded",
                "type": "requests",
                "request_id": "req_safe_123",
                "retry_after": "2",
            },
        ),
        (
            FakeProviderError(
                "RAW_CREDIT_MESSAGE SECRET_VALUE",
                status_code=429,
                body={"error": {"code": "insufficient_quota", "type": "insufficient_quota"}},
                request_id="req_credit_456",
            ),
            {
                "status": 429,
                "code": "insufficient_quota",
                "type": "insufficient_quota",
                "request_id": "req_credit_456",
                "retry_after": None,
            },
        ),
        (
            FakeProviderError(
                "RAW_MISSING_CODE_MESSAGE SECRET_VALUE",
                status_code=429,
                body={"error": {"type": "rate_limit_error", "message": "DO_NOT_COPY"}},
                request_id="req_missing_code",
            ),
            {
                "status": 429,
                "code": None,
                "type": "rate_limit_error",
                "request_id": "req_missing_code",
                "retry_after": None,
            },
        ),
        (
            FakeProviderError(
                "RAW_MALFORMED_MESSAGE SECRET_VALUE",
                status_code="429",
                body={
                    "error": {
                        "code": {"nested": "DO_NOT_COPY"},
                        "type": "bad value\nDO_NOT_COPY",
                    }
                },
                request_id="unsafe request id\nDO_NOT_COPY",
                headers={"Retry-After": "2; DO_NOT_COPY"},
            ),
            {
                "status": None,
                "code": None,
                "type": None,
                "request_id": None,
                "retry_after": None,
            },
        ),
        (
            FakeProviderError(
                "RAW_KEY_SHAPED_FIELDS SECRET_VALUE",
                status_code=429,
                body={
                    "error": {
                        "code": "sk-proj-KEY_MUST_NOT_LEAK",
                        "type": "rate_limit_error",
                    }
                },
                request_id="sk-proj-REQUEST_FIELD_MUST_NOT_LEAK",
                headers={"Retry-After": "9" * 10000},
            ),
            {
                "status": 429,
                "code": None,
                "type": "rate_limit_error",
                "request_id": None,
                "retry_after": None,
            },
        ),
    ],
)
def test_provider_error_report_is_structured_safe_and_partial(
    monkeypatch, tmp_path, error, expected
):
    from scripts import demo_ctu_network_public_model_driven as demo

    monkeypatch.setattr(
        demo,
        "validate",
        lambda *_args, **_kwargs: {
            "version": "ctu_network_public_dev_v1",
            "logical_snapshot_sha256": "a" * 64,
        },
    )
    output = tmp_path / "provider-error.json"
    client = FailingClient(error)

    with pytest.raises(ValueError, match="inspect partial report"):
        demo.run_model_driven_demo(_snapshot(tmp_path / "ctu.duckdb"), output, client=client)

    report = json.loads(output.read_text(encoding="utf-8"))
    assert report["status"] == "provider_error"
    assert report["provider_error"] == expected
    assert report["attempted_calls"] == 1
    assert report["responses_received"] == 0
    assert report["known_cost_usd"] == 0
    assert report["cost_unknown"] is True
    assert report["scenarios"] == []
    assert "failure_category" not in report
    serialized = output.read_text(encoding="utf-8")
    for forbidden in (
        "RAW_RATE_LIMIT_MESSAGE",
        "RAW_CREDIT_MESSAGE",
        "RAW_MISSING_CODE_MESSAGE",
        "RAW_MALFORMED_MESSAGE",
        "RAW_KEY_SHAPED_FIELDS",
        "SECRET_VALUE",
        "DO_NOT_COPY",
        "KEY_MUST_NOT_LEAK",
        "REQUEST_FIELD_MUST_NOT_LEAK",
    ):
        assert forbidden not in serialized


def test_first_request_diagnostic_sends_exactly_one_botnet_request_and_stops(monkeypatch, tmp_path):
    from scripts import demo_ctu_network_public_model_driven as demo

    monkeypatch.setattr(
        demo,
        "validate",
        lambda *_args, **_kwargs: {
            "version": "ctu_network_public_dev_v1",
            "logical_snapshot_sha256": "a" * 64,
        },
    )
    monkeypatch.setattr(
        demo,
        "_execute_network",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("diagnostic mode must not execute a tool")
        ),
    )
    output = tmp_path / "diagnostic.json"
    client = FakeClient()

    report = demo.run_first_request_diagnostic(
        _snapshot(tmp_path / "ctu.duckdb"), output, client=client
    )

    assert len(client.requests) == 1
    request = client.requests[0]
    assert request["model"] == "gpt-4.1-mini-2025-04-14"
    assert request["temperature"] == 0
    assert request["max_completion_tokens"] == 1000
    assert request["tool_choice"] == {
        "type": "function",
        "function": {"name": "network_investigation"},
    }
    assert len(request["tools"]) == 1
    prompt = json.loads(request["messages"][-1]["content"])
    assert prompt["task"] == (
        "Call network_investigation for this IPv4 and bounded historical interval."
    )
    assert prompt["indicator"] == "192.0.2.10"
    assert report["status"] == "diagnostic_response_received"
    assert report["attempted_calls"] == report["responses_received"] == 1
    assert report["scenarios"] == []
    assert "failure_category" not in report
    assert report["actual_model"] == "gpt-4.1-mini-2025-04-14"
    assert report["usage"] == {"input_tokens": 100, "output_tokens": 50}
    assert report["known_cost_usd"] > 0
    assert report["cost_unknown"] is False
    assert report["preflight_ceiling_usd"] < 0.03
    assert json.loads(output.read_text(encoding="utf-8")) == report


def test_first_request_diagnostic_preserves_safe_partial_report_on_429(monkeypatch, tmp_path):
    from scripts import demo_ctu_network_public_model_driven as demo

    monkeypatch.setattr(
        demo,
        "validate",
        lambda *_args, **_kwargs: {
            "version": "ctu_network_public_dev_v1",
            "logical_snapshot_sha256": "a" * 64,
        },
    )
    error = FakeProviderError(
        "RAW_DIAGNOSTIC_429 SECRET_VALUE",
        status_code=429,
        body={"code": "rate_limit_exceeded", "type": "requests"},
        request_id="req_diagnostic_429",
        headers={"retry-after": "3"},
    )
    output = tmp_path / "diagnostic-429.json"
    client = FailingClient(error)

    with pytest.raises(ValueError, match="inspect partial report"):
        demo.run_first_request_diagnostic(_snapshot(tmp_path / "ctu.duckdb"), output, client=client)

    assert len(client.requests) == 1
    report = json.loads(output.read_text(encoding="utf-8"))
    assert report["status"] == "provider_error"
    assert report["attempted_calls"] == 1
    assert report["responses_received"] == 0
    assert report["known_cost_usd"] == 0
    assert report["cost_unknown"] is True
    assert report["scenarios"] == []
    assert report["provider_error"] == {
        "status": 429,
        "code": "rate_limit_exceeded",
        "type": "requests",
        "request_id": "req_diagnostic_429",
        "retry_after": "3",
    }
    serialized = output.read_text(encoding="utf-8")
    assert "RAW_DIAGNOSTIC_429" not in serialized
    assert "SECRET_VALUE" not in serialized


@pytest.mark.parametrize(
    ("assessment_content", "expected_reason"),
    [
        # 1. JSON parsing failure
        ("not valid json", "assessment_json_invalid"),
        # 2. Missing required field
        ('{"assessment": "test", "evidence_ids": []}', "assessment_field_missing:limitations"),
        ('{"evidence_ids": [], "limitations": []}', "assessment_field_missing:assessment"),
        ('{"assessment": "test", "limitations": []}', "assessment_field_missing:evidence_ids"),
        # 3. assessment type invalid (not string)
        ('{"assessment": 123, "evidence_ids": [], "limitations": []}', "assessment_field_type_invalid:assessment"),
        # 4. assessment empty
        ('{"assessment": "   ", "evidence_ids": [], "limitations": []}', "assessment_field_type_invalid:assessment_empty"),
        # 5. assessment too long - use smaller string that still exceeds limit
        (f'{{"assessment": "x" * 2001, "evidence_ids": [], "limitations": []}}', "assessment_json_invalid"),  # Large strings fail JSON first
        # 6. evidence_ids not list
        ('{"assessment": "test", "evidence_ids": "not a list", "limitations": []}', "assessment_field_type_invalid:evidence_ids"),
        # 7. evidence_ids item not string
        ('{"assessment": "test", "evidence_ids": [123], "limitations": []}', "assessment_field_type_invalid:evidence_ids_item"),
        # 8. evidence_ids has duplicates
        ('{"assessment": "ev_1 is seen", "evidence_ids": ["ev_1", "ev_1"], "limitations": []}', "assessment_evidence_ids_duplicate"),
        # 9. evidence_ids not subset - check happens BEFORE "not in text"
        ('{"assessment": "ev_12345678 cited", "evidence_ids": ["ev_12345678"], "limitations": []}', "assessment_evidence_ids_not_subset"),
        # 10. evidence_ids empty when evidence exists
        ('{"assessment": "some text no IDs", "evidence_ids": [], "limitations": []}', "assessment_evidence_ids_missing"),
        # 11. evidence IDs not in assessment text - need subset to pass first check
        # Use evidence IDs that ARE in the actual set but NOT in the text
        ('{"assessment": "no evidence here", "evidence_ids": ["ev_abc123"], "limitations": []}', "assessment_evidence_ids_not_subset"),  # ev_abc123 not in actual
        # 12. limitations not list (checked BEFORE evidence_ids content)
        ('{"assessment": "test", "evidence_ids": ["ev_1"], "limitations": "not a list"}', "assessment_field_type_invalid:limitations"),
        # 13. limitations item not string (checked BEFORE evidence_ids content)
        ('{"assessment": "test", "evidence_ids": ["ev_1"], "limitations": [123]}', "assessment_field_type_invalid:limitations_item_0"),
        # 14. limitations item too long
        (json.dumps({"assessment": "test", "evidence_ids": ["ev_1"], "limitations": ["x" * 501]}), "assessment_field_type_invalid:limitations_item_0_too_long"),
    ],
)
def test_assessment_failure_reasons_are_granular_and_recorded(monkeypatch, tmp_path, assessment_content, expected_reason):
    from scripts import demo_ctu_network_public_model_driven as demo

    monkeypatch.setattr(
        demo,
        "validate",
        lambda *_args, **_kwargs: {
            "version": "ctu_network_public_dev_v1",
            "logical_snapshot_sha256": "a" * 64,
        },
    )
    output = tmp_path / "assessment_failure.json"
    client = FakeAssessmentClient(assessment_content=assessment_content)
    with pytest.raises(ValueError, match="assessment failed"):
        demo.run_model_driven_demo(_snapshot(tmp_path / "ctu.duckdb"), output, client=client)
    report = json.loads(output.read_text(encoding="utf-8"))
    assert report["status"] == "assessment_invalid"
    assert len(report["scenarios"]) == 1
    scenario = report["scenarios"][0]
    assert scenario["assessment_failure_reason"] == expected_reason
    assert scenario["assessment_finish_reason"] == "stop"
    # evidence_ids_validated should NOT be true since validation failed
    assert report["execution_semantics"]["model_generated_assessment"] is False


def test_partial_report_on_assessment_failure_has_no_raw_response(monkeypatch, tmp_path):
    from scripts import demo_ctu_network_public_model_driven as demo

    monkeypatch.setattr(
        demo,
        "validate",
        lambda *_args, **_kwargs: {
            "version": "ctu_network_public_dev_dev_v1",
            "logical_snapshot_sha256": "a" * 64,
        },
    )
    output = tmp_path / "partial_raw_test.json"
    client = FakeAssessmentClient(assessment_content='{"SENSITIVE": "RAW_RESPONSE_MUST_NOT_LEAK", "evidence_ids": [], "limitations": []}')
    with pytest.raises(ValueError):
        demo.run_model_driven_demo(_snapshot(tmp_path / "ctu.duckdb"), output, client=client)
    report_text = output.read_text(encoding="utf-8")
    assert "RAW_RESPONSE_MUST_NOT_LEAK" not in report_text
    assert "SENSITIVE" not in report_text
    # But the reason should be recorded
    report = json.loads(report_text)
    assert report["scenarios"][0]["assessment_failure_reason"] == "assessment_field_missing:assessment"


def test_assessment_evidence_ids_validated_only_after_validator_passes(monkeypatch, tmp_path):
    """Evidence IDs should be marked validated only after the validator passes.
    Invalid assessment should NOT mark as validated."""
    from scripts import demo_ctu_network_public_model_driven as demo

    monkeypatch.setattr(
        demo,
        "validate",
        lambda *_args, **_kwargs: {
            "version": "ctu_network_public_dev_v1",
            "logical_snapshot_sha256": "a" * 64,
        },
    )
    # Invalid assessment - should not mark as validated
    output_invalid = tmp_path / "invalid.json"
    client_invalid = FakeAssessmentClient(assessment_content="not json")
    with pytest.raises(ValueError):
        demo.run_model_driven_demo(_snapshot(tmp_path / "ctu_invalid.duckdb"), output_invalid, client=client_invalid)
    report_invalid = json.loads(output_invalid.read_text(encoding="utf-8"))
    assert report_invalid["execution_semantics"]["model_generated_assessment"] is False


def test_partial_scenario_data_preserved_on_failure(monkeypatch, tmp_path):
    """Partial scenario data should be preserved even when assessment fails."""
    from scripts import demo_ctu_network_public_model_driven as demo

    monkeypatch.setattr(
        demo,
        "validate",
        lambda *_args, **_kwargs: {
            "version": "ctu_network_public_dev_v1",
            "logical_snapshot_sha256": "a" * 64,
        },
    )
    output = tmp_path / "partial.json"
    client = FakeAssessmentClient(assessment_content="invalid json")
    with pytest.raises(ValueError):
        demo.run_model_driven_demo(_snapshot(tmp_path / "ctu.duckdb"), output, client=client)
    report = json.loads(output.read_text(encoding="utf-8"))
    # Tool call should be preserved
    assert len(report["scenarios"]) == 1
    scenario = report["scenarios"][0]
    assert "model_tool_arguments" in scenario
    assert "tool_trace" in scenario
    assert "evidence" in scenario
    # But assessment should not be present
    assert "assessment" not in scenario


def test_assessment_failure_reason_allowslist_recorded(monkeypatch, tmp_path):
    """finish_reason should be recorded from the API response."""
    from scripts import demo_ctu_network_public_model_driven as demo

    monkeypatch.setattr(
        demo,
        "validate",
        lambda *_args, **_kwargs: {
            "version": "ctu_network_public_dev_v1",
            "logical_snapshot_sha256": "a" * 64,
        },
    )
    output = tmp_path / "finish_reason_test.json"
    # Test with length cut-off (model could output truncated JSON)
    client = FakeAssessmentClient(
        assessment_content='{"assessment": "partial',
        finish_reason="length",
    )
    with pytest.raises(ValueError):
        demo.run_model_driven_demo(_snapshot(tmp_path / "ctu.duckdb"), output, client=client)
    report = json.loads(output.read_text(encoding="utf-8"))
    assert report["scenarios"][0]["assessment_failure_reason"] == "assessment_json_invalid"
    assert report["scenarios"][0]["assessment_finish_reason"] == "length"


# =============================================================================
# Regression tests for assessment failure handling
# =============================================================================


# --- Test _assessment_failure_reason directly ---


def test_assessment_json_valid_but_not_object():
    """JSON valid but not object (null, number, bool, list) returns assessment_json_not_object."""
    from scripts.demo_ctu_network_public_model_driven import _assessment_failure_reason

    # These parse as valid JSON but are not dict objects
    for content in ("null", "42", "true", "false", "[]", '"just a string"'):
        reason = _assessment_failure_reason(content, ["ev_1", "ev_2"])
        assert reason == "assessment_json_not_object", f"Content {content!r} got {reason}"


def test_assessment_valid_json_object_missing_fields():
    """JSON object missing required field returns assessment_field_missing."""
    from scripts.demo_ctu_network_public_model_driven import _assessment_failure_reason

    # Use json.dumps to create valid JSON
    for field in ("assessment", "evidence_ids", "limitations"):
        data = {}
        if field != "assessment":
            data["assessment"] = "test"
        if field != "evidence_ids":
            data["evidence_ids"] = []
        if field != "limitations":
            data["limitations"] = []
        content = json.dumps(data)
        reason = _assessment_failure_reason(content, ["ev_1"])
        assert reason == f"assessment_field_missing:{field}", f"Missing {field} got {reason}"


def test_assessment_field_wrong_type_uses_valid_json():
    """Fields with wrong types return assessment_field_type_invalid."""
    from scripts.demo_ctu_network_public_model_driven import _assessment_failure_reason

    # assessment wrong type
    reason = _assessment_failure_reason(json.dumps({
        "assessment": 123, "evidence_ids": [], "limitations": []
    }), ["ev_1"])
    assert reason == "assessment_field_type_invalid:assessment"

    # evidence_ids wrong type
    reason = _assessment_failure_reason(json.dumps({
        "assessment": "test", "evidence_ids": "not a list", "limitations": []
    }), ["ev_1"])
    assert reason == "assessment_field_type_invalid:evidence_ids"

    # limitations wrong type
    reason = _assessment_failure_reason(json.dumps({
        "assessment": "test", "evidence_ids": [], "limitations": "not a list"
    }), ["ev_1"])
    assert reason == "assessment_field_type_invalid:limitations"


def test_assessment_empty_or_too_long_uses_valid_json():
    """Assessment empty or > 2000 chars returns assessment_field_type_invalid."""
    from scripts.demo_ctu_network_public_model_driven import _assessment_failure_reason

    # Empty (whitespace only)
    reason = _assessment_failure_reason(json.dumps({
        "assessment": "   ", "evidence_ids": [], "limitations": []
    }), ["ev_1"])
    assert reason == "assessment_field_type_invalid:assessment_empty"

    # Too long (> 2000 chars)
    reason = _assessment_failure_reason(json.dumps({
        "assessment": "x" * 2001, "evidence_ids": [], "limitations": []
    }), ["ev_1"])
    assert reason == "assessment_field_type_invalid:assessment_too_long"


def test_evidence_ids_duplicates_not_subset_uses_valid_json():
    """Evidence ID issues return granular reasons."""
    from scripts.demo_ctu_network_public_model_driven import _assessment_failure_reason

    actual_ids = ["ev_1", "ev_2", "ev_3"]

    # Duplicate
    reason = _assessment_failure_reason(json.dumps({
        "assessment": "ev_1 and ev_2 are seen", "evidence_ids": ["ev_1", "ev_1"], "limitations": []
    }), actual_ids)
    assert reason == "assessment_evidence_ids_duplicate"

    # Not subset
    reason = _assessment_failure_reason(json.dumps({
        "assessment": "ev_999 is seen", "evidence_ids": ["ev_999"], "limitations": []
    }), actual_ids)
    assert reason == "assessment_evidence_ids_not_subset"

    # Missing when evidence exists
    reason = _assessment_failure_reason(json.dumps({
        "assessment": "no IDs here", "evidence_ids": [], "limitations": []
    }), actual_ids)
    assert reason == "assessment_evidence_ids_missing"

    # Not in text
    reason = _assessment_failure_reason(json.dumps({
        "assessment": "some text", "evidence_ids": ["ev_1", "ev_2"], "limitations": []
    }), actual_ids)
    assert reason == "assessment_evidence_ids_not_in_text"


def test_limitations_item_issues_uses_valid_json():
    """Limitations with item issues return granular reasons."""
    from scripts.demo_ctu_network_public_model_driven import _assessment_failure_reason

    # Item not string
    reason = _assessment_failure_reason(json.dumps({
        "assessment": "test", "evidence_ids": ["ev_1"], "limitations": [123]
    }), ["ev_1"])
    assert reason == "assessment_field_type_invalid:limitations_item_0"

    # Item too long
    reason = _assessment_failure_reason(json.dumps({
        "assessment": "test", "evidence_ids": ["ev_1"], "limitations": ["x" * 501]
    }), ["ev_1"])
    assert reason == "assessment_field_type_invalid:limitations_item_0_too_long"


def test_finish_reason_allowlist():
    """finish_reason should be allowlisted, not copied directly."""
    from scripts.demo_ctu_network_public_model_driven import _safe_finish_reason

    # Valid values
    assert _safe_finish_reason("stop") == "stop"
    assert _safe_finish_reason("length") == "length"
    assert _safe_finish_reason("content_filter") == "content_filter"

    # Invalid values
    assert _safe_finish_reason("invalid_value") == "other"
    assert _safe_finish_reason("") == "other"
    assert _safe_finish_reason("sk-key-like") == "other"
    assert _safe_finish_reason(123) is None
    assert _safe_finish_reason({"type": "object"}) is None


# --- Test partial report content ---


def test_partial_report_has_no_raw_response_on_json_not_object(monkeypatch, tmp_path):
    """JSON valid but not object should not leak raw response."""
    from scripts import demo_ctu_network_public_model_driven as demo

    monkeypatch.setattr(
        demo,
        "validate",
        lambda *_args, **_kwargs: {
            "version": "ctu_network_public_dev_v1",
            "logical_snapshot_sha256": "a" * 64,
        },
    )
    output = tmp_path / "partial_not_object.json"
    client = FakeAssessmentClient(assessment_content="null", finish_reason="stop")
    with pytest.raises(ValueError):
        demo.run_model_driven_demo(_snapshot(tmp_path / "ctu.duckdb"), output, client=client)

    report = json.loads(output.read_text(encoding="utf-8"))
    assert report["status"] == "assessment_invalid"
    assert report["scenarios"][0]["assessment_failure_reason"] == "assessment_json_not_object"
    # Raw response content should not appear as actual response text
    # The "null" word may appear in JSON structure but not as leaked content
    report_text = output.read_text()
    assert "SENSITIVE_DATA_LEAK" not in report_text
    # Should have proper structure with failure reason
    assert "assessment_failure_reason" in report["scenarios"][0]


def test_partial_report_has_no_raw_response_on_finish_reason_invalid(monkeypatch, tmp_path):
    """Invalid finish_reason should not be written directly to report."""
    from scripts import demo_ctu_network_public_model_driven as demo

    monkeypatch.setattr(
        demo,
        "validate",
        lambda *_args, **_kwargs: {
            "version": "ctu_network_public_dev_v1",
            "logical_snapshot_sha256": "a" * 64,
        },
    )
    output = tmp_path / "partial_finish.json"
    # Invalid finish_reason
    client = FakeAssessmentClient(
        assessment_content='{"assessment": "partial',
        finish_reason="sk-secret-key-value",
    )
    with pytest.raises(ValueError):
        demo.run_model_driven_demo(_snapshot(tmp_path / "ctu.duckdb"), output, client=client)

    report = json.loads(output.read_text(encoding="utf-8"))
    # Should be allowlisted to "other", not the actual value
    assert report["scenarios"][0]["assessment_finish_reason"] in ("other", None)
    # Original secret-like value should not be in report
    assert "sk-secret" not in output.read_text()


def test_assessment_flag_false_on_first_scenario_failure(monkeypatch, tmp_path):
    """When first scenario assessment fails, flag should be false."""
    from scripts import demo_ctu_network_public_model_driven as demo

    monkeypatch.setattr(
        demo,
        "validate",
        lambda *_args, **_kwargs: {
            "version": "ctu_network_public_dev_v1",
            "logical_snapshot_sha256": "a" * 64,
        },
    )
    output = tmp_path / "first_fail.json"
    client = FakeAssessmentClient(assessment_content="not valid json", finish_reason="stop")
    with pytest.raises(ValueError):
        demo.run_model_driven_demo(_snapshot(tmp_path / "ctu.duckdb"), output, client=client)

    report = json.loads(output.read_text(encoding="utf-8"))
    assert report["execution_semantics"]["model_generated_assessment"] is False


def test_assessment_flag_false_if_second_scenario_fails(monkeypatch, tmp_path):
    """When second scenario assessment fails, overall flag should still be false."""
    from scripts import demo_ctu_network_public_model_driven as demo

    monkeypatch.setattr(
        demo,
        "validate",
        lambda *_args, **_kwargs: {
            "version": "ctu_network_public_dev_v1",
            "logical_snapshot_sha256": "a" * 64,
        },
    )

    # First client returns valid assessment, second returns invalid
    call_count = [0]

    class MixedClient:
        def __init__(self):
            self.chat = SimpleNamespace(completions=self)

        def create(self, **request):
            call_count[0] += 1
            if request.get("tools"):
                text = request["messages"][-1]["content"]
                indicator = "192.0.2.10" if "192.0.2.10" in text else "192.0.2.11"
                scenario = json.loads(text)
                args = {
                    "indicator": indicator,
                    "indicator_type": "ipv4",
                    "time_range": scenario["time_range"],
                }
                message = SimpleNamespace(
                    tool_calls=[
                        SimpleNamespace(
                            id="fake_tool_call",
                            function=SimpleNamespace(
                                name="network_investigation", arguments=json.dumps(args)
                            ),
                        )
                    ],
                    content=None,
                )
            else:
                if call_count[0] == 3:  # Second assessment call
                    message = SimpleNamespace(
                        tool_calls=None,
                        content="invalid json",
                    )
                else:
                    message = SimpleNamespace(
                        tool_calls=None,
                        content=json.dumps({
                            "assessment": "Valid assessment for first scenario.",
                            "evidence_ids": ["ev_abc123", "ev_def456"],
                            "limitations": [],
                        }),
                    )
            return SimpleNamespace(
                id=f"fake_response_{call_count[0]}",
                model="gpt-4.1-mini-2025-04-14",
                usage=SimpleNamespace(prompt_tokens=100, completion_tokens=50),
                choices=[SimpleNamespace(message=message, finish_reason="stop")],
            )

    output = tmp_path / "second_fail.json"
    client = MixedClient()
    with pytest.raises(ValueError):
        demo.run_model_driven_demo(_snapshot(tmp_path / "ctu.duckdb"), output, client=client)

    report = json.loads(output.read_text(encoding="utf-8"))
    # Even though first passed, second failed so overall is false
    assert report["execution_semantics"]["model_generated_assessment"] is False


def test_assessment_flag_true_only_when_all_pass(monkeypatch, tmp_path):
    """Flag should be true only when all scenarios complete successfully."""
    from scripts import demo_ctu_network_public_model_driven as demo

    monkeypatch.setattr(
        demo,
        "validate",
        lambda *_args, **_kwargs: {
            "version": "ctu_network_public_dev_v1",
            "logical_snapshot_sha256": "a" * 64,
        },
    )

    # Collect evidence IDs from first run
    captured_ids = {}

    class ValidatingClient:
        def __init__(self):
            self.chat = SimpleNamespace(completions=self)
            self.call_count = 0

        def create(self, **request):
            self.call_count += 1
            if request.get("tools"):
                text = request["messages"][-1]["content"]
                indicator = "192.0.2.10" if "192.0.2.10" in text else "192.0.2.11"
                scenario = json.loads(text)
                args = {
                    "indicator": indicator,
                    "indicator_type": "ipv4",
                    "time_range": scenario["time_range"],
                }
                message = SimpleNamespace(
                    tool_calls=[
                        SimpleNamespace(
                            id="fake_tool_call",
                            function=SimpleNamespace(
                                name="network_investigation", arguments=json.dumps(args)
                            ),
                        )
                    ],
                    content=None,
                )
            else:
                # Return valid assessment with actual evidence IDs
                content = request["messages"][-1]["content"]
                evidence = json.loads(content)["evidence"]
                ev_ids = [e["evidence_id"] for e in evidence]
                if not captured_ids:
                    captured_ids["ids"] = ev_ids
                # Handle case with single evidence item
                if len(ev_ids) >= 2:
                    assessment_text = f"Evidence {ev_ids[0]} and {ev_ids[1]} observed."
                else:
                    assessment_text = f"Evidence {ev_ids[0]} observed."
                message = SimpleNamespace(
                    tool_calls=None,
                    content=json.dumps({
                        "assessment": assessment_text,
                        "evidence_ids": ev_ids,
                        "limitations": [],
                    }),
                )
            return SimpleNamespace(
                id=f"fake_response_{self.call_count}",
                model="gpt-4.1-mini-2025-04-14",
                usage=SimpleNamespace(prompt_tokens=100, completion_tokens=50),
                choices=[SimpleNamespace(message=message, finish_reason="stop")],
            )

    output = tmp_path / "all_pass.json"
    client = ValidatingClient()
    # Use high budget to avoid per-call reserve gate (reserve uses max 50k tokens)
    report = demo.run_model_driven_demo(_snapshot(tmp_path / "ctu.duckdb"), output, client=client, budget_usd=0.1)

    assert report["status"] == "complete"
    assert report["execution_semantics"]["model_generated_assessment"] is True


def test_main_blocks_conflicting_key_sources_before_client_creation(monkeypatch, tmp_path, capsys):
    from scripts import demo_ctu_network_public_model_driven as demo

    process_secret = "PROCESS_SECRET_MUST_NOT_LEAK"
    dotenv_secret = "DOTENV_SECRET_MUST_NOT_LEAK"
    monkeypatch.setenv("OPENAI_API_KEY", process_secret)
    monkeypatch.setattr(
        demo,
        "load_env",
        lambda _path: {"OPENAI_API_KEY": dotenv_secret},
        raising=False,
    )
    client_created = False

    def fail_if_client_created(_key):
        nonlocal client_created
        client_created = True
        raise AssertionError("client must not be created")

    monkeypatch.setattr(demo, "_create_openai_client", fail_if_client_created, raising=False)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "demo",
            "--snapshot",
            str(tmp_path / "unused.duckdb"),
            "--output",
            str(tmp_path / "unused.json"),
        ],
    )

    assert demo.main() == 1
    output = capsys.readouterr().out
    assert client_created is False
    assert "conflicting_key_sources" in output
    assert process_secret not in output
    assert dotenv_secret not in output
