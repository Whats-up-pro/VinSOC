from agent import tools
from agent.orchestrator import InvestigationOrchestrator


def test_sanitizer_drops_only_top_level_null_values():
    sanitizer = getattr(tools, "sanitize_tool_arguments_for_execution", None)
    assert callable(sanitizer)

    original = {
        "indicator": "1.2.3.4",
        "indicator_type": None,
        "time_range": None,
        "future_non_null_key": "preserve-me",
    }

    assert sanitizer("network_investigation", original) == {
        "indicator": "1.2.3.4",
        "future_non_null_key": "preserve-me",
    }
    assert original["indicator_type"] is None
    assert original["time_range"] is None


def test_sanitizer_does_not_repair_partially_invalid_time_range():
    sanitizer = getattr(tools, "sanitize_tool_arguments_for_execution", None)
    assert callable(sanitizer)

    partial = {"indicator": "1.2.3.4", "time_range": {"start": "2026-09-23T00:00:00Z"}}

    assert sanitizer("network_investigation", partial) == partial


def test_network_dispatch_treats_nullable_strict_fields_as_omitted():
    orchestrator = InvestigationOrchestrator(
        network_mock_data={
            "1.2.3.4": {"connections": [], "observed_evidence": []},
        }
    )

    orchestrator._execute_tool_call(
        {
            "id": "network-nullable",
            "name": "network_investigation",
            "arguments": {
                "indicator": "1.2.3.4",
                "indicator_type": None,
                "time_range": None,
            },
        }
    )

    call = orchestrator.evidence_store.get_all_tool_calls()[0]
    assert call.error is None
    assert call.arguments == {"indicator": "1.2.3.4"}


def test_endpoint_dispatch_treats_null_time_range_as_omitted():
    orchestrator = InvestigationOrchestrator(
        endpoint_mock_data={
            "WS-01": {"process_tree": [], "observed_evidence": []},
        }
    )

    orchestrator._execute_tool_call(
        {
            "id": "endpoint-nullable",
            "name": "endpoint_investigation",
            "arguments": {"host": "WS-01", "time_range": None},
        }
    )

    call = orchestrator.evidence_store.get_all_tool_calls()[0]
    assert call.error is None
    assert call.arguments == {"host": "WS-01"}
