"""Deterministic, transport-only projections of full query evidence."""
from __future__ import annotations

import json
from copy import deepcopy


PROJECTION_VERSION = "query_result_projection_v1"


class ProjectionError(ValueError):
    """Safe public failure raised when the mandatory envelope cannot fit."""

    def __init__(self, code: str):
        self.code = code
        super().__init__(code)


def project_query_evidence(evidence: list[dict], *, max_rows: int = 20) -> list[dict]:
    """Copy evidence and retain only the first ``max_rows`` query rows."""
    if type(max_rows) is not int or max_rows < 0:
        raise ValueError("INVALID_QUERY_PROJECTION_ROW_LIMIT")
    projected = deepcopy(evidence)
    for item in projected:
        if not isinstance(item, dict) or item.get("type") != "query_result":
            continue
        data = item.get("data")
        if not isinstance(data, dict) or not isinstance(data.get("rows"), list):
            raise ProjectionError("ASSESSMENT_PROJECTION_SCHEMA_LIMIT")
        row_count = data.get("row_count")
        if type(row_count) is not int or row_count < 0 or row_count != len(data["rows"]):
            raise ProjectionError("ASSESSMENT_PROJECTION_SCHEMA_LIMIT")
        included = min(max_rows, row_count)
        data["rows"] = data["rows"][:included]
        item["assessment_projection"] = {
            "version": PROJECTION_VERSION,
            "complete": included == row_count,
            "included_rows": included,
            "omitted_rows": row_count - included,
        }
    return projected


def serialize_assessment_payload(
    question: str,
    evidence: list[dict],
    *,
    max_bytes: int = 32768,
) -> str:
    """Serialize the largest deterministic prefix projection within ``max_bytes``."""
    if type(max_bytes) is not int or max_bytes <= 0:
        raise ValueError("INVALID_QUERY_PROJECTION_BYTE_LIMIT")
    result_counts = [
        item.get("data", {}).get("row_count")
        for item in evidence
        if isinstance(item, dict) and item.get("type") == "query_result"
    ]
    largest = min(20, max(result_counts, default=0))
    for row_limit in range(largest, -1, -1):
        payload = {
            "tool": "network_query",
            "question": question,
            "status": "succeeded",
            "evidence": project_query_evidence(evidence, max_rows=row_limit),
        }
        encoded = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
        if len(encoded.encode("utf-8")) <= max_bytes:
            return encoded
    raise ProjectionError("ASSESSMENT_PROJECTION_SCHEMA_LIMIT")
