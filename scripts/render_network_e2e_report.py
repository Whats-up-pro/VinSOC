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


def render_report(receipt_path: Path, output_path: Path) -> dict[str, Any]:
    """
    Render a technical receipt to HTML.

    Args:
        receipt_path: Path to the technical receipt JSON
        output_path: Path to write the HTML file

    Returns:
        Dict with render stats
    """
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))

    # Extract key data
    status = receipt.get("status", "unknown")
    scope = receipt.get("scope", "unknown")
    transport = receipt.get("transport", "unknown")
    impl_sha = receipt.get("implementation_sha", "unknown")

    # Cost data
    known_cost = receipt.get("known_cost_usd", 0.0)
    unknown_cost = receipt.get("cost_unknown", False)
    budget = receipt.get("budget_usd", 0.0)
    reserved = receipt.get("reserved_exposure_usd", 0.0)

    # Requests
    requests = receipt.get("requests", [])
    scenarios = receipt.get("scenarios", [])

    # Status display
    if status == "complete":
        status_class = "status-complete"
        status_text = "COMPLETE"
    elif status == "awaiting_human":
        status_class = "status-pending"
        status_text = "AWAITING_HUMAN"
    else:
        status_class = "status-partial"
        status_text = "PARTIAL"

    # Build HTML
    html_parts = [
        "<!DOCTYPE html>",
        "<html lang='en'>",
        "<head>",
        "<meta charset='UTF-8'>",
        "<meta name='viewport' content='width=device-width, initial-scale=1.0'>",
        f"<title>VinSOC Network E2E Demo - {escape_html(status_text)}</title>",
        "<style>",
        _get_css(),
        "</style>",
        "</head>",
        "<body>",
        "<div class='container'>",

        # Header
        "<header>",
        "<h1>VinSOC Network E2E Demo Report</h1>",
        f"<div class='status {status_class}'>{status_text}</div>",
        "</header>",

        # Summary
        "<section class='summary'>",
        "<h2>Summary</h2>",
        "<table>",
        "<tr><th>Scope</th><td>" + escape_html(scope) + "</td></tr>",
        "<tr><th>Transport</th><td>" + escape_html(transport) + "</td></tr>",
        "<tr><th>Implementation SHA</th><td><code>" + escape_html(impl_sha) + "</code></td></tr>",
        "</table>",
        "</section>",

        # Cost
        "<section class='cost'>",
        "<h2>Cost Summary</h2>",
        "<table>",
        f"<tr><th>Known Cost</th><td>${known_cost:.6f}</td></tr>",
        f"<tr><th>Cost Unknown</th><td>{'Yes' if unknown_cost else 'No'}</td></tr>",
        f"<tr><th>Budget</th><td>${budget:.6f}</td></tr>",
        f"<tr><th>Reserved Exposure</th><td>${reserved:.6f}</td></tr>",
        "</table>",
        "</section>",
    ]

    # Requests
    if requests:
        html_parts.extend([
            "<section class='requests'>",
            "<h2>API Requests</h2>",
            "<table>",
            "<thead><tr><th>#</th><th>Stage</th><th>Model</th><th>Input</th><th>Output</th><th>Cost</th><th>Latency</th></tr></thead>",
            "<tbody>",
        ])

        for i, req in enumerate(requests, 1):
            stage = escape_html(req.get("stage", "unknown"))
            model = escape_html(req.get("actual_model", req.get("model", "unknown")))
            usage = req.get("usage", {})
            input_tok = usage.get("input_tokens", 0) if usage else 0
            output_tok = usage.get("output_tokens", 0) if usage else 0
            cost = req.get("cost_usd", 0.0)
            latency = req.get("latency_ms", 0)

            html_parts.extend([
                "<tr>",
                f"<td>{i}</td>",
                f"<td>{stage}</td>",
                f"<td>{model}</td>",
                f"<td>{input_tok}</td>",
                f"<td>{output_tok}</td>",
                f"<td>${cost:.6f}</td>",
                f"<td>{latency:.1f}ms</td>",
                "</tr>",
            ])

        html_parts.extend([
            "</tbody>",
            "</table>",
            "</section>",
        ])

    # Scenarios
    if scenarios:
        html_parts.extend([
            "<section class='scenarios'>",
            "<h2>Scenarios</h2>",
        ])

        for scenario in scenarios:
            name = escape_html(scenario.get("name", "unknown"))
            assessment = scenario.get("assessment", {})
            evidence = scenario.get("evidence", [])

            html_parts.extend([
                "<div class='scenario'>",
                f"<h3>Scenario: {name}</h3>",

                # Assessment
                "<div class='assessment'>",
                "<h4>Assessment</h4>",
            ])

            # Handle None assessment
            assessment = scenario.get("assessment")
            if assessment is None:
                html_parts.append("<p><em>No assessment available</em></p>")
            else:
                html_parts.append(f"<p>{escape_html(assessment.get('assessment', 'N/A'))}</p>")
                html_parts.extend([
                    "<table>",
                    f"<tr><th>Risk Level</th><td>{escape_html(assessment.get('risk_level', 'N/A'))}</td></tr>",
                    f"<tr><th>Confidence</th><td>{escape_html(assessment.get('confidence', 'N/A'))}</td></tr>",
                    "</table>",
                ])

            html_parts.extend([
                "</div>",

                # Evidence
                "<div class='evidence'>",
                "<h4>Evidence</h4>",
                f"<p>{len(evidence)} evidence items collected</p>",
            ])

            if evidence:
                html_parts.extend([
                    "<table>",
                    "<thead><tr><th>ID</th><th>Type</th><th>Class</th><th>Source</th></tr></thead>",
                    "<tbody>",
                ])

                for ev in evidence[:20]:  # Limit display
                    ev_id = escape_html(ev.get("evidence_id", "unknown"))
                    ev_type = escape_html(ev.get("type", "unknown"))
                    ev_class = escape_html(ev.get("evidence_class", "unknown"))
                    source = escape_html(ev.get("source_name", "unknown"))

                    html_parts.extend([
                        "<tr>",
                        f"<td><code>{ev_id}</code></td>",
                        f"<td>{ev_type}</td>",
                        f"<td>{ev_class}</td>",
                        f"<td>{source}</td>",
                        "</tr>",
                    ])

                html_parts.extend([
                    "</tbody>",
                    "</table>",
                ])

            html_parts.extend([
                "</div>",  # evidence

                # Validation
                "<div class='validation'>",
                "<h4>Validation</h4>",
                "<table>",
            ])

            validation = scenario.get("validation", {})
            if validation:
                html_parts.extend([
                    f"<tr><th>Factual Check</th><td>{'PASS' if validation.get('factual_check_passed') else 'FAIL'}</td></tr>",
                    f"<tr><th>Issues</th><td>{escape_html(', '.join(validation.get('issues', ['None'])))}</td></tr>",
                ])
            else:
                html_parts.append("<tr><td colspan='2'>No validation performed</td></tr>")

            html_parts.extend([
                "</table>",
                "</div>",  # validation

                # Lifecycle
                "<div class='lifecycle'>",
                "<h4>Lifecycle</h4>",
                "<table>",
            ])

            lifecycle = scenario.get("lifecycle", {})
            for phase, state in lifecycle.items():
                html_parts.append(f"<tr><th>{escape_html(phase)}</th><td>{escape_html(state)}</td></tr>")

            html_parts.extend([
                "</table>",
                "</div>",  # lifecycle

                # Human Review
                "<div class='review'>",
                "<h4>Human Review</h4>",
                "<table>",
            ])

            review = scenario.get("human_review", {})
            review_status = review.get("status", "not_started")
            html_parts.append(f"<tr><th>Status</th><td>{escape_html(review_status)}</td></tr>")

            if review.get("decision"):
                html_parts.append(f"<tr><th>Decision</th><td>{escape_html(review.get('decision'))}</td></tr>")
            if review.get("rationale"):
                html_parts.append(f"<tr><th>Rationale</th><td>{escape_html(review.get('rationale'))}</td></tr>")

            html_parts.extend([
                "</table>",
                "</div>",  # review

                "</div>",  # scenario
            ])

        html_parts.append("</section>")

    # Provenance
    html_parts.extend([
        "<section class='provenance'>",
        "<h2>Provenance</h2>",
        "<table>",
        f"<tr><th>Schema Version</th><td>{escape_html(receipt.get('schema_version', 'N/A'))}</td></tr>",
        f"<tr><th>Run ID</th><td><code>{escape_html(receipt.get('run_id', 'N/A'))}</code></td></tr>",
        "<tr><th>Generated</th><td>" + escape_html(receipt.get("generated_at", "N/A")) + "</td></tr>",
        "</table>",
        "</section>",

        # Footer
        "</div>",  # container
        "<footer>",
        "<p>Generated by VinSOC Network E2E Demo Renderer</p>",
        "<p>This report was generated from the technical receipt and does not require API access.</p>",
        "</footer>",
        "</body>",
        "</html>",
    ])

    # Write HTML
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text("\n".join(html_parts), encoding="utf-8")

    return {
        "status": "success",
        "output_path": str(output_path),
        "scenarios": len(scenarios),
        "requests": len(requests),
    }


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
    args = parser.parse_args()

    try:
        result = render_report(args.receipt, args.output)
        print(f"Rendered {result['scenarios']} scenarios, {result['requests']} requests")
        print(f"Output: {result['output_path']}")
        return 0
    except Exception as e:
        print(f"Error: {e}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
