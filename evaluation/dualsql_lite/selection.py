"""Lock the selected public-dev architecture without consulting frozen cases."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from evaluation.dualsql_lite.experiment import CONDITIONS, SERIES_VERSION, select_winner
from evaluation.text_to_sql_snapshot import sha256_file


def build_selection(directory: Path) -> dict:
    directory = Path(directory)
    reports = []
    hashes = {}
    for name in CONDITIONS:
        path = directory / f"{name}.json"
        raw = json.loads(path.read_text())
        if (raw["experiment_id"] != name or raw["run_status"] != "completed"
                or not raw["eligible"] or raw["case_count"] != 8
                or raw["correct_cases"] / 8 != raw["metrics"]["execution_accuracy"]):
            raise ValueError(f"Incomplete or inconsistent completed run: {name}")
        reports.append(raw)
        hashes[name] = sha256_file(path)
    if len({json.dumps(r["identity"], sort_keys=True) for r in reports}) != 1:
        raise ValueError("Experiment identity differs across runs")
    if len({r.get("series_version") for r in reports}) != 1:
        raise ValueError("Series version differs across runs")
    winner = select_winner(reports)
    return {"selection_rule": "accuracy_desc,cost_asc,model_calls_asc,latency_asc,E0_E1_E2_E3",
            "selected_experiment": winner["experiment_id"],
            "series_version": winner.get("series_version", SERIES_VERSION),
            "identity": winner["identity"], "artifact_sha256": hashes,
            "configuration": {key: winner.get(key) for key in (
                "provider", "requested_model", "temperature", "max_completion_tokens",
                "max_retries", "linker_prompt_version", "linker_prompt_sha256",
                "generator_prompt_version", "generator_prompt_sha256", "tool_schema_sha256",
                "tool_implementation_version", "tool_implementation_sha256",
                "catalog_builder_version", "catalog_sha256", "snapshot_binary_sha256")},
            "results": {r["experiment_id"]: {"correct": r["correct_cases"],
                        "total": r["case_count"], "execution_accuracy": r["metrics"]["execution_accuracy"],
                        "cost_usd": r["total_cost_usd"], "model_calls": r["model_calls"],
                        "latency_ms": r["latency_ms"]} for r in reports}}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory", type=Path)
    args = parser.parse_args()
    target = args.directory / "selection.json"
    if target.exists():
        raise FileExistsError(target)
    target.write_text(json.dumps(build_selection(args.directory), sort_keys=True, indent=2) + "\n")
    print(f"Selected configuration: {json.loads(target.read_text())['selected_experiment']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
