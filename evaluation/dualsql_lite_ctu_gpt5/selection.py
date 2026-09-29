"""Selection logic for CTU-only DualSQL-Lite GPT-5 Mini E0-E3 series."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from evaluation.dualsql_lite_ctu_gpt5.experiment import CONDITIONS, SERIES_VERSION


def load_report(path: Path) -> dict[str, Any]:
    """Load a single condition report."""
    for report_path in path.glob("*_report.json"):
        with open(report_path) as f:
            return json.load(f)
    raise FileNotFoundError(f"No report found in {path}")


def load_all_reports(base_dir: Path) -> dict[str, dict[str, Any]]:
    """Load all E0-E3 reports from a series directory."""
    reports = {}
    for cond in CONDITIONS:
        for report_dir in base_dir.glob(f"{cond.lower()}-*"):
            if report_dir.is_dir():
                try:
                    reports[cond] = load_report(report_dir)
                    break
                except FileNotFoundError:
                    continue
    return reports


def select_winner(reports: list[dict[str, Any]]) -> dict[str, Any]:
    """
    Apply the predeclared selection order:
    1. Higher Execution Accuracy
    2. Lower calculated API cost
    3. Fewer model calls
    4. Lower latency
    5. Simpler architecture (E0 > E1 > E2 > E3)
    """
    if not reports:
        raise ValueError("No reports provided")

    if {report["experiment_id"] for report in reports} != set(CONDITIONS):
        missing = set(CONDITIONS) - {report["experiment_id"] for report in reports}
        raise ValueError(f"Selection requires all four conditions; missing: {missing}")

    if any(not report.get("eligible", False) for report in reports):
        raise ValueError("Cannot select from ineligible experiment results")

    def parse_accuracy(r: dict[str, Any]) -> int:
        acc = r.get("metrics", {}).get("execution_accuracy", "0/0")
        if "/" in acc:
            return int(acc.split("/")[0])
        return 0

    def parse_cost(r: dict[str, Any]) -> float:
        return r.get("total_cost_usd", 0.0)

    def parse_calls(r: dict[str, Any]) -> int:
        return r.get("model_calls", 0)

    def parse_latency(r: dict[str, Any]) -> float:
        return r.get("latency_ms", 0.0)

    def simplicity_index(r: dict[str, Any]) -> int:
        return CONDITIONS.index(r["experiment_id"])

    return min(reports, key=lambda r: (
        -parse_accuracy(r),
        parse_cost(r),
        parse_calls(r),
        parse_latency(r),
        simplicity_index(r)
    ))


def generate_selection_report(reports: dict[str, dict[str, Any]], winner: dict[str, Any]) -> dict[str, Any]:
    """Generate a human-readable selection report."""
    rows = []
    for cond in CONDITIONS:
        if cond not in reports:
            rows.append({"condition": cond, "status": "NOT_RUN"})
            continue
        r = reports[cond]
        acc = r.get("metrics", {}).get("execution_accuracy", "0/0")
        rows.append({
            "condition": cond,
            "execution_accuracy": acc,
            "cost_usd": f"${r.get('total_cost_usd', 0):.6f}",
            "model_calls": r.get("model_calls", 0),
            "latency_ms": round(r.get("latency_ms", 0), 1),
            "eligible": r.get("eligible", False),
        })

    return {
        "series_version": SERIES_VERSION,
        "winner": {
            "condition": winner["experiment_id"],
            "execution_accuracy": winner.get("metrics", {}).get("execution_accuracy", "N/A"),
            "cost_usd": winner.get("total_cost_usd", 0),
            "model_calls": winner.get("model_calls", 0),
        },
        "all_conditions": rows,
    }


def main() -> int:
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("results_dir", type=Path, help="Directory containing E0-E3 result directories")
    parser.add_argument("--output", type=Path, help="Output path for selection report")
    args = parser.parse_args()

    reports = load_all_reports(args.results_dir)
    if len(reports) < 4:
        print(f"Warning: Only {len(reports)} conditions found: {list(reports.keys())}")

    winner = select_winner(list(reports.values()))
    selection = generate_selection_report(reports, winner)

    print(json.dumps(selection, indent=2))
    if args.output:
        with open(args.output, "w") as f:
            json.dump(selection, f, indent=2)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
