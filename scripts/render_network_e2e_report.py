"""Render a network E2E technical receipt to a standalone HTML report.

This renderer:
- Reads the technical receipt JSON
- Produces standalone HTML with no external dependencies
- Escapes HTML/script content
- Shows COMPLETE / PARTIAL / AWAITING_HUMAN status
- Displays usage/cost, evidence, and assessment
"""
from __future__ import annotations

import html
import json
from pathlib import Path
from typing import Any


def escape_html(text: str) -> str:
    """Escape HTML special characters."""
    if text is None:
        return ""
    return html.escape(str(text), quote=True)


def escape_json_for_js(text: str) -> str:
    """Escape text for embedding in JavaScript."""
    return json.dumps(str(text))[1:-1]  # Remove quotes from json.dumps


def _json_panel(title: str, value: Any) -> str:
    content = json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True)
    return f"<details><summary>{escape_html(title)}</summary><pre>{escape_html(content)}</pre></details>"


def _money(value: Any) -> str:
    import math
    if type(value) not in (int, float) or not math.isfinite(value) or value < 0:
        return "unknown / unavailable"
    return "$" + f"{value:.6f}"


def render_report(receipt_path: Path, output_path: Path, *, review_path: Path | None = None) -> dict[str, Any]:
    """Render complete saved evidence; no client, inference or database access."""
    import hashlib
    import copy
    from evaluation.finalization.network_contract import valid_technical_receipt

    receipt_path, output_path = Path(receipt_path), Path(output_path)
    if receipt_path.resolve() == output_path.resolve():
        raise ValueError("Renderer must not overwrite technical receipt")
    if review_path is not None and Path(review_path).resolve() == output_path.resolve():
        raise ValueError("Renderer must not overwrite linked review receipt")
    try:
        raw = receipt_path.read_bytes()
    except OSError:
        raise ValueError("Receipt unavailable") from None
    try:
        receipt = json.loads(raw)
    except (UnicodeDecodeError, json.JSONDecodeError):
        raise ValueError("Invalid technical receipt JSON") from None
    if (
        not isinstance(receipt, dict) or type(receipt.get("schema_version")) is not int
        or receipt.get("schema_version") != 1
        or not isinstance(receipt.get("scenarios", []), list)
        or not isinstance(receipt.get("requests", []), list)
        or not all(isinstance(x, dict) for x in receipt.get("scenarios", []))
        or not all(isinstance(x, dict) for x in receipt.get("requests", []))
    ):
        raise ValueError("Invalid technical receipt schema")
    source_receipt = copy.deepcopy(receipt)
    linked_review = None
    if review_path is not None:
        try:
            linked_review = json.loads(Path(review_path).read_bytes())
            decisions = linked_review["decisions"]
            if (not valid_technical_receipt(receipt)
                or receipt.get("status") != "technical_complete_awaiting_human"
                or receipt.get("review_status") != "awaiting_human"
                or linked_review.get("input_receipt_sha256") != hashlib.sha256(raw).hexdigest()
                or linked_review.get("input_implementation_sha") != receipt["implementation_sha"]
                or linked_review.get("run_id") != receipt["run_id"]
                or len(decisions) != 2 or {d["scenario"] for d in decisions} != {"botnet", "normal"}
                or any(d.get("decision") not in {"APPROVE", "REJECT", "ESCALATE"}
                       or not isinstance(d.get("analyst"), str) or not d["analyst"] for d in decisions)):
                raise ValueError()
            values = [d["decision"] for d in decisions]
            expected_status = "approved" if all(value == "APPROVE" for value in values) else (
                "rejected" if "REJECT" in values else "escalated")
            if linked_review.get("status") != expected_status:
                raise ValueError()
            for scenario in receipt["scenarios"]:
                decision = next(d for d in decisions if d["scenario"] == scenario["name"])
                scenario["human_review"] = {"status": {"APPROVE": "approved", "REJECT": "rejected",
                    "ESCALATE": "escalated"}[decision["decision"]], "decisions": [decision]}
            receipt.update(status=expected_status, review_status=expected_status)
        except (OSError, ValueError, KeyError, TypeError, AttributeError, StopIteration):
            raise ValueError("Invalid or mismatched linked review receipt") from None
    scenarios, requests = receipt.get("scenarios", []), receipt.get("requests", [])
    for scenario in scenarios:
        if (not isinstance(scenario.get("evidence", []), list)
            or not all(isinstance(ev, dict) and isinstance(ev.get("provenance", {}), dict)
                       for ev in scenario.get("evidence", []))
            or not isinstance(scenario.get("validation", {}), dict)
            or not isinstance(scenario.get("human_review", {}), dict)):
            raise ValueError("Invalid technical receipt schema")
    status = receipt.get("status")
    synthetic = receipt.get("synthetic") is True or receipt.get("transport") in {
        "synthetic", "offline_rehearsal", "OFFLINE_REHEARSAL",
    }
    if status in {"technical_complete_awaiting_human", "awaiting_human"}:
        display, css = "AWAITING_HUMAN", "status-pending"
    elif status == "approved" and valid_technical_receipt(receipt, require_approval=True):
        display, css = "COMPLETE", "status-complete"
    elif status == "complete":
        display, css = "PARTIAL — legacy completion claim not revalidated", "status-partial"
    else:
        display, css = "PARTIAL", "status-partial"
    costs = receipt.get("cost_summary")
    costs = costs if isinstance(costs, dict) else receipt
    evidence_count = sum(len(s.get("evidence", [])) for s in scenarios)
    missing_sources = sum(
        1 for s in scenarios for ev in s.get("evidence", [])
        if isinstance(ev, dict) and ev.get("evidence_class") == "OBSERVED"
        and not ev.get("provenance", {}).get("source_records")
    )
    parts = [
        "<!DOCTYPE html><html lang='en'><head><meta charset='UTF-8'>",
        "<meta name='viewport' content='width=device-width, initial-scale=1.0'>",
        "<meta http-equiv='Content-Security-Policy' content=\"default-src 'none'; style-src 'unsafe-inline'\">",
        "<title>Network E2E receipt</title><style>", _get_css(),
        "pre{white-space:pre-wrap;overflow-wrap:anywhere;padding:12px;background:#f4f5f7}"
        "details{margin:10px 0}summary{cursor:pointer;font-weight:600}.warning{color:#8a3000}",
        "</style></head><body><main class='container'><h1>Network E2E technical receipt</h1>",
        f"<div class='status {css}'>{escape_html(display)}</div>",
        f"<p class='warning'>{'SYNTHETIC / OFFLINE REHEARSAL — not live evidence' if synthetic else 'SAVED RECEIPT — offline viewer, not a new model run'}</p>",
        "<h2>Run and stage</h2><table>",
    ]
    for key in ("run_id", "status", "scope", "transport", "implementation_sha", "review_status",
                "failed_stage", "failure_category", "attempted_calls", "responses_received", "valid_usage_records"):
        parts.append(f"<tr><th>{escape_html(key)}</th><td>{escape_html(receipt.get(key))}</td></tr>")
    parts.extend([
        "</table><h2>Cost Summary</h2>",
        f"<p>Known Cost: {_money(costs.get('known_cost_usd'))}</p>",
        f"<p>Cost Unknown: {'Yes — Total cost is unknown; known cost is not total' if costs.get('cost_unknown') else 'No'}</p>",
        f"<p>Budget: {_money(receipt.get('budget_usd'))}; Reserved Exposure: {_money(costs.get('reserved_exposure_usd'))}</p>",
        "<h2>API Requests</h2>",
    ])
    for index, request in enumerate(requests):
        parts.append(f"<article data-request-index='{index}'>")
        parts.append(f"<h3>{escape_html(request.get('stage'))}</h3><p>Cost: {_money(request.get('cost_usd'))}</p>")
        parts.extend([_json_panel("Complete request telemetry", request), "</article>"])
    parts.append("<h2>Scenarios</h2>")
    for index, scenario in enumerate(scenarios):
        parts.append(f"<article class='scenario' data-scenario-index='{index}'><h3>{escape_html(scenario.get('name'))}</h3>")
        assessment = scenario.get("assessment")
        text = assessment.get("assessment") if isinstance(assessment, dict) else assessment
        parts.append(f"<h4>Full model assessment</h4><p>{escape_html(text) or 'No assessment available'}</p>")
        for field in ("request", "ground_truth_label", "native_tool_calls", "tool_trace", "hypotheses",
                      "risk_level", "confidence", "evidence_ids", "observations", "limitations",
                      "coverage", "validation", "lifecycle", "human_review", "termination"):
            parts.append(_json_panel(field, scenario.get(field)))
        for ev_index, ev in enumerate(scenario.get("evidence", [])):
            parts.extend([f"<div data-evidence-index='{index}-{ev_index}'>",
                          _json_panel("Complete evidence and provenance", ev), "</div>"])
        parts.append("</article>")
    parts.append("<h2>Provenance</h2>")
    for field in ("ci", "contract", "snapshot", "request_config"):
        parts.append(_json_panel(field, receipt.get(field)))
    if missing_sources:
        parts.append(f"<p class='warning'>Missing source references: {missing_sources} observed items</p>")
    digest = hashlib.sha256(raw).hexdigest()
    parts.extend([f"<p>Input receipt SHA-256: <code>{digest}</code></p>",
                  _json_panel("Complete source receipt (all fields, unchanged)", source_receipt),
                  _json_panel("Linked human review (hash-verified)", linked_review),
                  "<footer>Offline viewer: no model calls, no database query, no benchmark score.</footer></main></body></html>"])
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text("\n".join(parts), encoding="utf-8")
    return {"status": "success", "output_path": str(output_path), "display_status": display.split(" — ")[0],
            "scenarios": len(scenarios), "requests": len(requests), "evidence_items": evidence_count,
            "missing_source_items": missing_sources, "receipt_sha256": digest, "api_calls": 0}


def _get_css() -> str:
    """Get the CSS styles for the HTML report."""
    return """
* {
    box-sizing: border-box;
    margin: 0;
    padding: 0;
}

body {
    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Oxygen, Ubuntu, sans-serif;
    line-height: 1.6;
    color: #333;
    background: #f5f5f5;
}

.container {
    max-width: 1200px;
    margin: 0 auto;
    padding: 20px;
    background: white;
    min-height: 100vh;
}

header {
    border-bottom: 2px solid #e0e0e0;
    padding-bottom: 20px;
    margin-bottom: 20px;
}

h1 {
    color: #1a73e8;
    margin-bottom: 10px;
}

h2 {
    color: #333;
    border-left: 4px solid #1a73e8;
    padding-left: 10px;
    margin: 20px 0 10px;
}

h3 {
    color: #555;
    margin: 15px 0 10px;
}

h4 {
    color: #666;
    margin: 10px 0 5px;
}

section {
    margin-bottom: 30px;
}

.status {
    display: inline-block;
    padding: 5px 15px;
    border-radius: 4px;
    font-weight: bold;
    text-transform: uppercase;
}

.status-complete {
    background: #d4edda;
    color: #155724;
}

.status-partial {
    background: #fff3cd;
    color: #856404;
}

.status-pending {
    background: #cce5ff;
    color: #004085;
}

table {
    width: 100%;
    border-collapse: collapse;
    margin: 10px 0;
}

th, td {
    padding: 8px 12px;
    text-align: left;
    border-bottom: 1px solid #e0e0e0;
}

th {
    background: #f8f9fa;
    font-weight: 600;
    width: 30%;
}

code {
    background: #f4f4f4;
    padding: 2px 6px;
    border-radius: 3px;
    font-size: 0.9em;
}

.scenario {
    background: #f9f9f9;
    border: 1px solid #e0e0e0;
    border-radius: 8px;
    padding: 15px;
    margin-bottom: 20px;
}

.assessment, .evidence, .validation, .lifecycle, .review {
    margin: 15px 0;
}

.assessment {
    background: white;
    padding: 10px;
    border-radius: 4px;
}

footer {
    border-top: 1px solid #e0e0e0;
    padding-top: 20px;
    margin-top: 40px;
    color: #666;
    font-size: 0.9em;
}

@media (max-width: 768px) {
    .container {
        padding: 10px;
    }

    table {
        font-size: 0.9em;
    }

    th {
        width: 40%;
    }
}
"""


def main() -> int:
    import argparse

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--receipt", type=Path, required=True, help="Path to technical receipt JSON")
    parser.add_argument("--output", type=Path, required=True, help="Path to write HTML report")
    parser.add_argument("--review-receipt", type=Path, help="Optional linked offline human review JSON")
    args = parser.parse_args()

    try:
        result = render_report(args.receipt, args.output, review_path=args.review_receipt)
        print(f"Rendered {result['scenarios']} scenarios, {result['requests']} requests")
        print(f"Output: {result['output_path']}")
        return 0
    except Exception:
        print("Renderer stopped: INVALID_OR_UNAVAILABLE_RECEIPT")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
