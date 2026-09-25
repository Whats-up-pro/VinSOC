"""Controlled E0-E3 public-dev series with immutable evidence and a spend gate."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from evaluation.dualsql_lite.agents import (
    GENERATOR_INSTRUCTIONS, GENERATOR_PROMPT_VERSION, LINKER_INSTRUCTIONS,
    LINKER_PROMPT_VERSION, MAX_TURNS, DualSQLCaseRunner, InvalidEvidenceRun,
)
from evaluation.dualsql_lite.tools import DatabaseTools, MAX_RESPONSE_BYTES, TOOL_SCHEMAS, TOOL_VERSION
from evaluation.public_pilot import contract
from evaluation.public_pilot.run_model import (
    BUDGET_USD, CAP, FRAMING_TOKENS, INPUT_USD_M, MODEL, OUTPUT_USD_M,
    build_r2_request, cost_usd, make_client,
)
from evaluation.text_to_sql import SQLBenchmarkCase
from evaluation.text_to_sql_snapshot import sha256_file


CONDITIONS = ("E0", "E1", "E2", "E3")
SERIES_VERSION = "dualsql_lite_public_dev_v1"
PRICING_SOURCE = "https://developers.openai.com/api/docs/models/gpt-4.1-mini"


def _hash(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, default=str,
                                     separators=(",", ":")).encode()).hexdigest()


def _write_partial(path: Path, data: dict[str, Any]) -> None:
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(data, sort_keys=True, default=str, indent=2) + "\n")
    os.replace(temporary, path)


def select_winner(reports: list[dict[str, Any]]) -> dict[str, Any]:
    """Apply the predeclared accuracy, cost, calls, latency, simplicity order."""
    if {report["experiment_id"] for report in reports} != set(CONDITIONS):
        raise ValueError("Selection requires all four completed conditions")
    if any(not report.get("eligible", True) for report in reports):
        raise ValueError("Cannot select from an invalid experiment")
    return min(reports, key=lambda r: (-r["metrics"]["execution_accuracy"],
                                       r["total_cost_usd"], r["model_calls"],
                                       r["latency_ms"], CONDITIONS.index(r["experiment_id"])))


class BudgetGate:
    """Reserve every possible model turn before a paid series starts."""

    def __init__(self, cases: list[SQLBenchmarkCase], schema: str, budget_usd: float):
        if not 0 < budget_usd <= 100:
            raise ValueError("budget_usd must be positive and finite within the configured limit")
        self.budget_usd = budget_usd
        self.slots: dict[tuple[str, str], list[tuple[str, int]]] = {}
        for experiment in CONDITIONS:
            for case in cases:
                roles = []
                if experiment in {"E1", "E3"}:
                    roles.append(("linker", LINKER_INSTRUCTIONS + "\nDatabase schema:\n" + schema,
                                  MAX_TURNS, True))
                if experiment == "E0":
                    roles.append(("generator", build_r2_request(case.question, schema)["messages"][0]["content"],
                                  1, False))
                elif experiment == "E2":
                    roles.append(("generator", GENERATOR_INSTRUCTIONS + "\nDatabase schema:\n" + schema,
                                  MAX_TURNS, True))
                else:
                    roles.append(("generator", GENERATOR_INSTRUCTIONS + "\nValidated linked schema:\n"
                                  + "x" * 8000, 1 if experiment == "E1" else MAX_TURNS,
                                  experiment == "E3"))
                bounds = []
                for role, system, turns, tools_enabled in roles:
                    initial = {"model": MODEL, "temperature": 0,
                               "max_completion_tokens": CAP,
                               "messages": [{"role": "system", "content": system},
                                            {"role": "user", "content": case.question}],
                               "tools": TOOL_SCHEMAS if tools_enabled else None}
                    size = len(json.dumps(initial, ensure_ascii=True).encode())
                    for turn in range(turns):
                        # Reserve prior assistant output, tool output and framing.
                        bounds.append((role, size + FRAMING_TOKENS
                                       + turn * (6000 + MAX_RESPONSE_BYTES + 1024)))
                self.slots[(experiment, case.case_id)] = bounds
        self.ceiling_usd = sum(cost_usd(bound, CAP)
                               for bounds in self.slots.values() for _, bound in bounds)
        if self.ceiling_usd >= budget_usd:
            raise ValueError(f"preflight spend ceiling ${self.ceiling_usd:.4f} exceeds budget ${budget_usd:.2f}")
        self.remaining_usd = self.ceiling_usd
        self.known_usd = 0.0
        self.current: tuple[str, str] | None = None
        self.used: set[int] = set()
        self.pending: tuple[int, int] | None = None

    def begin_case(self, experiment: str, case_id: str) -> None:
        self.current = (experiment, case_id)
        self.used = set()

    def before_call(self, request: dict[str, Any]) -> None:
        if self.current is None:
            raise InvalidEvidenceRun("No active budgeted case")
        bounds = self.slots[self.current]
        system = request["messages"][0]["content"]
        role = "linker" if system.startswith(LINKER_INSTRUCTIONS) else "generator"
        available = [(i, bound) for i, (slot_role, bound) in enumerate(bounds)
                     if slot_role == role and i not in self.used]
        if not available:
            raise InvalidEvidenceRun("Model turn exceeded role reservation")
        index, bound = available[0]
        size = len(json.dumps(request, ensure_ascii=True, default=str).encode())
        if size + FRAMING_TOKENS > bound:
            raise InvalidEvidenceRun("Actual request exceeded preflight input bound")
        if self.known_usd + self.remaining_usd >= self.budget_usd:
            raise InvalidEvidenceRun("Budget gate blocked before API request")
        self.pending = (index, bound)

    def after_call(self, request: dict[str, Any], usage: dict[str, Any]) -> None:
        if self.pending is None:
            raise InvalidEvidenceRun("Provider call bypassed budget gate")
        index, bound = self.pending
        if usage["input_tokens"] > bound:
            raise InvalidEvidenceRun("Provider input usage exceeds conservative bound")
        self.known_usd += usage["cost_usd"]
        self.remaining_usd -= cost_usd(bound, CAP)
        self.used.add(index)
        self.pending = None

    def finish_case(self) -> None:
        if self.current is None or self.pending is not None:
            raise InvalidEvidenceRun("Cannot release an active provider reservation")
        for index, (_, bound) in enumerate(self.slots[self.current]):
            if index not in self.used:
                self.remaining_usd -= cost_usd(bound, CAP)
        self.current = None


class ExperimentSeries:
    """Execute four fixed architecture conditions over one immutable split."""

    def __init__(self, snapshot_path: Path, cases: list[SQLBenchmarkCase],
                 output_dir: Path, client: Any, *, identity: dict[str, Any],
                 budget_usd: float):
        self.snapshot_path = Path(snapshot_path)
        self.cases = cases
        self.output_dir = Path(output_dir)
        self.client = client
        self.identity = identity
        self.budget_usd = budget_usd

    def run(self) -> list[dict[str, Any]]:
        if not self.cases or len({case.case_id for case in self.cases}) != len(self.cases):
            raise ValueError("Benchmark cases missing or duplicated")
        if self.output_dir.exists() and list(self.output_dir.iterdir()):
            raise FileExistsError("Evidence output directory already contains artifacts")
        tools = DatabaseTools(self.snapshot_path)
        gate = BudgetGate(self.cases, tools.schema_context(), self.budget_usd)
        snapshot_sha = sha256_file(self.snapshot_path)
        reports: list[dict[str, Any]] = []
        self.output_dir.mkdir(parents=True, exist_ok=True)
        for experiment in CONDITIONS:
            path = self.output_dir / f"{experiment}.json"
            partial = self.output_dir / f"{experiment}.partial.json"
            if path.exists() or partial.exists():
                raise FileExistsError("Append-only evidence path already exists")
            report: dict[str, Any] = {
                "run_id": self.output_dir.name, "experiment_id": experiment,
                "series_version": SERIES_VERSION, "split": "public_dev",
                "official_eligible": False, "eligible": False,
                "run_status": "in_progress", "identity": self.identity,
                "provider": "openai", "requested_model": MODEL, "temperature": 0,
                "max_completion_tokens": CAP, "max_retries": 0,
                "linker_prompt_version": LINKER_PROMPT_VERSION,
                "linker_prompt_sha256": _hash(LINKER_INSTRUCTIONS),
                "generator_prompt_version": GENERATOR_PROMPT_VERSION,
                "generator_prompt_sha256": _hash(GENERATOR_INSTRUCTIONS),
                "tool_schema_sha256": _hash(TOOL_SCHEMAS),
                "tool_implementation_version": TOOL_VERSION,
                "tool_implementation_sha256": sha256_file(Path(__file__).with_name("tools.py")),
                "catalog_builder_version": TOOL_VERSION,
                "catalog_sha256": tools.catalog_sha256,
                "snapshot_binary_sha256": snapshot_sha,
                "preflight": {"series_ceiling_usd": gate.ceiling_usd,
                              "budget_usd": gate.budget_usd,
                              "max_turns_per_role": MAX_TURNS,
                              "tool_result_byte_limit": MAX_RESPONSE_BYTES,
                              "method": "serialized request bytes plus framing and bounded prior turn context"},
                "pricing": {"input_usd_per_million": INPUT_USD_M,
                            "output_usd_per_million": OUTPUT_USD_M,
                            "source": PRICING_SOURCE,
                            "checked_utc": datetime.now(timezone.utc).isoformat()},
                "expected_case_ids": [case.case_id for case in self.cases],
                "case_results": [], "known_spend_usd": gate.known_usd,
            }
            _write_partial(partial, report)
            try:
                for case in self.cases:
                    gate.begin_case(experiment, case.case_id)

                    def after_call(request: dict[str, Any], usage: dict[str, Any]) -> None:
                        gate.after_call(request, usage)
                        report["known_spend_usd"] = gate.known_usd
                        report["last_provider_call"] = {"case_id": case.case_id, **usage}
                        _write_partial(partial, report)

                    runner = DualSQLCaseRunner(self.snapshot_path, self.client,
                                               before_call=gate.before_call,
                                               after_call=after_call)
                    result = runner.run_case(case, experiment)
                    gate.finish_case()
                    report["case_results"].append(result)
                    report["known_spend_usd"] = gate.known_usd
                    _write_partial(partial, report)
                report.update(_summarize(report["case_results"]))
                report["run_status"] = "completed"
                report["eligible"] = True
                report.pop("last_provider_call", None)
                report["known_spend_usd"] = gate.known_usd
                # Hard link fails if an immutable final artifact already exists.
                _write_partial(partial, report)
                os.link(partial, path)
                partial.unlink()
                reports.append(report)
            except Exception as exc:
                report["run_status"] = "invalid"
                report["ineligible_reasons"] = [type(exc).__name__]
                report["known_spend_usd"] = gate.known_usd
                _write_partial(partial, report)
                raise
        return reports


def _summarize(results: list[dict[str, Any]]) -> dict[str, Any]:
    n = len(results)
    correct = sum(r["execution_accurate"] for r in results)
    by_axis: dict[str, dict[str, Any]] = {}
    for axis in ("category", "difficulty"):
        groups = defaultdict(list)
        for row in results:
            groups[row[axis]].append(row)
        by_axis[axis] = {name: {"correct": sum(r["execution_accurate"] for r in rows),
                                "total": len(rows)} for name, rows in sorted(groups.items())}
    tool_counts = Counter(t["tool"] for row in results for t in row["trajectory"])
    return {
        "case_count": n, "correct_cases": correct,
        "metrics": {"execution_accuracy": correct / n,
                    "syntax_validity_rate": sum(r["syntax_valid"] for r in results) / n,
                    "execution_success_rate": sum(r["execution_success"] for r in results) / n,
                    "safety_rejection_rate": sum(r["safety_rejected"] for r in results) / n},
        "breakdown": by_axis, "error_summary": dict(Counter(r["error_category"] for r in results)),
        "model_calls": sum(r["model_calls"] for r in results),
        "database_tool_calls": sum(r["linker_tool_calls"] + r["generator_tool_calls"] for r in results),
        "input_tokens": sum(r["input_tokens"] for r in results),
        "output_tokens": sum(r["output_tokens"] for r in results),
        "total_cost_usd": sum(r["cost_usd"] for r in results),
        "latency_ms": sum(r["latency_ms"] for r in results),
        "cost_per_case_usd": sum(r["cost_usd"] for r in results) / n,
        "average_turns": sum(r["linker_turns"] + r["generator_turns"] for r in results) / n,
        "linker_completion_rate": sum(r["linked_schema"] is not None for r in results) / n,
        "linker_turns": sum(r["linker_turns"] for r in results),
        "generator_turns": sum(r["generator_turns"] for r in results),
        "linker_tool_calls": sum(r["linker_tool_calls"] for r in results),
        "generator_tool_calls": sum(r["generator_tool_calls"] for r in results),
        "tool_usage_rate": {name: sum(any(t["tool"] == name for t in r["trajectory"])
                                       for r in results) / n
                            for name in ("database_profiler", "value_search", "sql_probe")},
        "tool_counts": dict(tool_counts),
        "linked_tables": sum(len(r["linked_schema"]["tables"]) if r["linked_schema"] else 0
                             for r in results),
        "linked_columns": sum(sum(len(t["columns"]) for t in r["linked_schema"]["tables"])
                              if r["linked_schema"] else 0 for r in results),
        "generator_recovery_events": sum(r["generator_recovery_events"] for r in results),
        "malformed_agent_outputs": sum(r["malformed_agent_outputs"] for r in results),
    }


def run_public_dev(snapshot_path: Path, snapshot_report_path: Path,
                   output_dir: Path, budget_usd: float, client: Any = None) -> list[dict[str, Any]]:
    """Verify locked public sources, benchmark, scorer and clean checkout before API use."""
    sha = subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip()
    if subprocess.check_output(["git", "status", "--porcelain"]).strip():
        raise ValueError("Paid evidence requires a clean checkout")
    if os.environ.get("GITHUB_SHA") and os.environ["GITHUB_SHA"] != sha:
        raise ValueError("Actions checkout SHA mismatch")
    if os.environ.get("VINSOC_EVAL_MODEL") != MODEL:
        raise ValueError("VINSOC_EVAL_MODEL does not match pinned model")
    snapshot_report = json.loads(snapshot_report_path.read_text())
    if snapshot_report.get("sha256") != sha256_file(snapshot_path):
        raise ValueError("Snapshot binary hash mismatch")
    lock_path = Path(__file__).with_name("BASE.lock")
    contract.validate(snapshot_path, lock_path=lock_path)
    lock = json.loads(lock_path.read_text())
    cases = [SQLBenchmarkCase.from_dict(json.loads(p.read_text()))
             for p in sorted(contract.R2.glob("*.json"))]
    if len(cases) != 8 or len(set(c.case_id for c in cases)) != 8:
        raise ValueError("Public-dev benchmark IDs missing or duplicated")
    if any(case.database_snapshot != str(snapshot_path) for case in cases):
        raise ValueError("Case snapshot path does not match verified snapshot")
    identity = {"git_commit": sha, "benchmark_version": lock["version"],
                "benchmark_hash": lock["r2_split_sha256"],
                "snapshot_content_hash": lock["snapshot_content_sha256"],
                "snapshot_binary_hash": snapshot_report["sha256"],
                "source_hashes": lock["source_file_sha256"],
                "scorer_hash": _hash(lock["scorer_file_sha256"]),
                "scorer_file_hashes": lock["scorer_file_sha256"]}
    return ExperimentSeries(snapshot_path, cases, output_dir,
                            client if client is not None else make_client(),
                            identity=identity, budget_usd=budget_usd).run()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--snapshot", type=Path, default=Path("data/public_pilot/snapshot.duckdb"))
    parser.add_argument("--snapshot-report", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--budget-usd", type=float, required=True)
    args = parser.parse_args()
    reports = run_public_dev(args.snapshot, args.snapshot_report, args.output_dir, args.budget_usd)
    winner = select_winner(reports)
    print(json.dumps({"run_id": args.output_dir.name,
                      "results": {r["experiment_id"]: r["correct_cases"] for r in reports},
                      "winner": winner["experiment_id"]}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
