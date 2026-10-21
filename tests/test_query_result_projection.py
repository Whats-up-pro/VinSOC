import copy
import json

import pytest


def result_evidence(rows, *, columns=None, result_sha256="a" * 64):
    return [{
        "evidence_id": "ev_result",
        "source_tool": "network_query",
        "type": "query_result",
        "data": {
            "columns": columns or [{"name": "value", "type": "BIGINT"}],
            "rows": rows,
            "row_count": len(rows),
            "truncated": False,
            "result_sha256": result_sha256,
        },
    }]


@pytest.mark.parametrize("rows", [[[1], [2]], []])
def test_small_and_empty_results_preserve_full_projection_contract(rows):
    from agent.query_result_projection import serialize_assessment_payload

    evidence = result_evidence(rows)
    original = copy.deepcopy(evidence)

    first = serialize_assessment_payload("Count rows", evidence)
    second = serialize_assessment_payload("Count rows", evidence)
    delivered = json.loads(first)["evidence"][0]

    assert first == second
    assert evidence == original
    assert delivered["data"]["rows"] == rows
    assert delivered["data"]["row_count"] == len(rows)
    assert delivered["data"]["result_sha256"] == "a" * 64
    assert delivered["assessment_projection"] == {
        "version": "query_result_projection_v1",
        "complete": True,
        "included_rows": len(rows),
        "omitted_rows": 0,
    }


def test_large_result_is_bounded_without_mutating_full_result():
    from agent.query_result_projection import serialize_assessment_payload

    rows = [[index, "network observation"] for index in range(9780)]
    evidence = result_evidence(rows, columns=[
        {"name": "source_row_id", "type": "BIGINT"},
        {"name": "summary", "type": "VARCHAR"},
    ])
    original = copy.deepcopy(evidence)

    encoded = serialize_assessment_payload("List matching flows", evidence)
    delivered = json.loads(encoded)["evidence"][0]

    assert len(encoded.encode("utf-8")) <= 32768
    assert delivered["data"]["rows"] == rows[:20]
    assert delivered["data"]["row_count"] == 9780
    assert delivered["assessment_projection"]["included_rows"] == 20
    assert delivered["assessment_projection"]["omitted_rows"] == 9760
    assert delivered["assessment_projection"]["complete"] is False
    assert evidence == original


def test_unicode_uses_encoded_byte_limit_and_reduces_rows():
    from agent.query_result_projection import serialize_assessment_payload

    evidence = result_evidence([[index, "🔐" * 80] for index in range(20)], columns=[
        {"name": "position", "type": "BIGINT"},
        {"name": "message", "type": "VARCHAR"},
    ])

    encoded = serialize_assessment_payload("Unicode", evidence, max_bytes=1500)
    delivered = json.loads(encoded)["evidence"][0]

    assert len(encoded.encode("utf-8")) <= 1500
    assert 0 < delivered["assessment_projection"]["included_rows"] < 20
    assert delivered["data"]["rows"] == evidence[0]["data"]["rows"][
        :delivered["assessment_projection"]["included_rows"]
    ]


def test_schema_that_cannot_fit_raises_safe_projection_error():
    from agent.query_result_projection import ProjectionError, serialize_assessment_payload

    evidence = result_evidence([], columns=[{"name": "x" * 2048, "type": "VARCHAR"}])

    with pytest.raises(ProjectionError) as captured:
        serialize_assessment_payload("Too wide", evidence, max_bytes=256)

    assert captured.value.code == "ASSESSMENT_PROJECTION_SCHEMA_LIMIT"
    assert str(captured.value) == "ASSESSMENT_PROJECTION_SCHEMA_LIMIT"
