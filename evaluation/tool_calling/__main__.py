#!/usr/bin/env python3
"""
R1 Tool Calling Benchmark CLI

Usage:
    python -m evaluation.tool_calling benchmarks dev
    python -m evaluation.tool_calling benchmarks frozen
    python -m evaluation.tool_calling run --mode integration
    python -m evaluation.tool_calling run --mode decision --split dev
"""
import argparse
import json
import sys
from datetime import datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from evaluation.tool_calling.integration_runner import IntegrationRunner
from evaluation.tool_calling.decision_runner import (
    A1Config, DecisionRunner, generalization_git_identity,
    validate_generalization_run_gate,
)
from evaluation.tool_calling.generalization import verify_generalization_lock
from evaluation.tool_calling.metrics import aggregate_case_results, generate_error_summary
from evaluation.tool_calling.provenance import build_a1_provenance


def run_benchmark(args):
    """Run benchmark evaluation."""
    mode = args.mode
    split = args.split
    cases = args.cases

    if split == "generalization_v1":
        if mode != "decision" or cases is not None:
            print(json.dumps({"passed": False, "errors": ["generalization requires decision mode and the full 120-case suite"], "provider_created": False}))
            return 1
        receipt = generalization_preflight(args)
        if receipt is None or not receipt.passed:
            return 1
    else:
        receipt = None

    print(f"R1 Tool Calling Benchmark")
    print(f"Mode: {mode}")
    print(f"Split: {split}")
    print(f"Started: {datetime.utcnow().isoformat()}")
    print("-" * 50)

    if mode == "integration":
        runner = IntegrationRunner()
        case_ids = cases or [f"case_{i:03d}" for i in range(1, 21)]

        print(f"Running {len(case_ids)} integration cases...")
        results = runner.run_suite(case_ids)

    elif mode == "decision":
        config = A1Config(
            provider=getattr(args, "provider", "openai"),
            model=getattr(args, "model", "gpt-4o"),
            temperature=float(getattr(args, "temperature", 0.0)),
        )
        if split == "generalization_v1":
            runner = DecisionRunner(config=config, split=split, generalization_gate=receipt)
        else:
            runner = DecisionRunner(config=config)
        print(
            f"Running decision benchmark (split: {split}, "
            f"provider: {config.provider}, model: {config.model}, "
            f"temperature: {config.temperature})..."
        )
        results = runner.run_suite(split=split, case_ids=cases)
        if not results:
            print(f"No cases found in split '{split}'")
            return 1 if split == "generalization_v1" else 0

    else:
        print(f"Unknown mode: {mode}")
        return 1

    # Aggregate results
    run_id = f"r1_{mode}_{split}_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}"
    aggregate = aggregate_case_results(run_id, results)
    error_summary = generate_error_summary(results)

    # Print results
    print(f"\nResults:")
    print(f"  Cases: {aggregate.case_count}")
    print(f"  Tool Precision: {aggregate.tool_precision:.2%}")
    print(f"  Tool Recall: {aggregate.tool_recall:.2%}")
    print(f"  Tool F1: {aggregate.tool_f1:.2%}")
    print(f"  Exact Call F1: {aggregate.exact_call_f1:.2%}")
    print(f"  Tool Set EM: {aggregate.tool_set_exact_match_rate:.2%}")
    print(f"  Single-Turn Case Success: {aggregate.trajectory_success_rate:.2%}")
    print(f"  Provider Error Rate: {aggregate.provider_error_rate:.2%}")
    print(f"  Execution Error Rate: {aggregate.execution_error_rate:.2%}")

    if error_summary:
        print(f"\nError Summary:")
        for error_type, count in list(error_summary.items())[:5]:
            print(f"  {error_type}: {count}")

    # Save results
    output_dir = Path(f"results/tool_calling/{run_id}")
    output_dir.mkdir(parents=True, exist_ok=True)

    result_dict = {
        "run_id": run_id,
        "mode": mode,
        "split": split,
        "aggregate": aggregate.to_dict(),
        "error_summary": error_summary,
        "case_results": [r.to_dict() for r in results],
    }
    if mode == "decision":
        result_dict.update(
            {
                "provider": runner.provider.get_name(),
                "provider_metadata": runner.provider.get_run_metadata(),
                "config": {
                    "provider": runner.config.provider,
                    "model": runner.config.model,
                    "temperature": runner.config.temperature,
                    **({"max_completion_tokens": runner.applied_max_completion_tokens}
                       if getattr(runner, "applied_max_completion_tokens", None) is not None
                       else {}),
                },
                "provenance": build_a1_provenance(runner, split, results),
            }
        )

    with open(output_dir / "metrics.json", "w") as f:
        json.dump(result_dict, f, indent=2)

    print(f"\nResults saved to: {output_dir}")
    print("-" * 50)
    return 0


def _generalization_paths():
    split_dir = Path(__file__).parent / "benchmarks" / "generalization_v1"
    return split_dir, split_dir / "GENERALIZATION.lock"


def generalization_preflight(args):
    """Offline, fail-closed authorization check shared by preflight and run."""
    errors = []
    authorization = {}
    if not getattr(args, "authorization", None):
        errors.append("suite authorization is required")
    else:
        try:
            authorization = json.loads(Path(args.authorization).read_text(encoding="utf-8"))
            if not isinstance(authorization, dict):
                raise ValueError("authorization must be a JSON object")
        except (OSError, ValueError) as exc:
            errors.append(f"invalid authorization: {exc}")
    try:
        budget = Decimal(getattr(args, "budget_usd", None))
    except (TypeError, InvalidOperation):
        budget = Decimal("0")
        errors.append("budget-usd is required")
    if errors:
        print(json.dumps({"passed": False, "errors": errors, "provider_created": False, "model_calls": 0}))
        return None

    split_dir, lock_path = _generalization_paths()
    receipt = validate_generalization_run_gate(
        split_dir, lock_path, authorization, args.model, budget,
        generalization_git_identity(Path(__file__).resolve().parents[2]),
    )
    print(json.dumps(receipt.to_dict() if hasattr(receipt, "to_dict") else {
        "passed": receipt.passed, "errors": list(receipt.errors),
        "provider_created": False, "model_calls": 0,
    }))
    output = getattr(args, "output", None)
    if output:
        path = Path(output)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(receipt.to_dict(), indent=2) + "\n", encoding="utf-8")
    return receipt


def preflight(args):
    receipt = generalization_preflight(args)
    return 0 if receipt is not None and receipt.passed else 1


def lock_cases(args):
    split_dir, lock_path = _generalization_paths()
    result = verify_generalization_lock(split_dir, lock_path)
    print(json.dumps({
        "passed": result.passed, "errors": list(result.errors),
        "case_count": result.case_count, "distribution": result.distribution,
        "lock_sha256": result.lock_sha256, "provider_created": False, "model_calls": 0,
    }))
    return 0 if result.passed else 1


def list_cases(args):
    """List available benchmark cases."""
    benchmarks_dir = Path(__file__).parent / "benchmarks"
    split_dir = benchmarks_dir / args.split

    if not split_dir.exists():
        print(f"No cases found in split '{args.split}'")
        return 1
    if args.split == "generalization_v1":
        result = verify_generalization_lock(split_dir, split_dir / "GENERALIZATION.lock")
        if not result.passed:
            print(json.dumps({"passed": False, "errors": list(result.errors), "provider_created": False}))
            return 1

    cases = sorted(split_dir.glob("*.json"))
    print(f"Available cases in '{args.split}': {len(cases)}")
    for case_file in cases:
        with open(case_file) as f:
            case = json.load(f)
        print(f"  {case['case_id']}: {case['category']} ({case['difficulty']})")
    return 0


def main(argv=None):
    parser = argparse.ArgumentParser(description="R1 Tool Calling Benchmark")
    subparsers = parser.add_subparsers(dest="command", help="Commands")

    # benchmark command
    bench_parser = subparsers.add_parser("benchmarks", help="Run benchmark")
    bench_parser.add_argument("split", choices=["dev", "frozen"], default="dev")
    bench_parser.add_argument("--cases", nargs="+", help="Specific case IDs")
    bench_parser.add_argument("--mode", choices=["integration", "decision"], default="integration")
    bench_parser.add_argument("--provider", default="openai")
    bench_parser.add_argument("--model", default="gpt-4o")
    bench_parser.add_argument("--temperature", type=float, default=0.0)
    bench_parser.set_defaults(func=run_benchmark)

    # list command
    list_parser = subparsers.add_parser("list", help="List benchmark cases")
    list_parser.add_argument("split", choices=["dev", "frozen", "generalization_v1"], default="dev", nargs="?")
    list_parser.set_defaults(func=list_cases)

    lock_parser = subparsers.add_parser("lock", help="Verify locked generalization split offline")
    lock_parser.add_argument("split", choices=["generalization_v1"])
    lock_parser.set_defaults(func=lock_cases)

    preflight_parser = subparsers.add_parser("preflight", help="Check authorization offline")
    preflight_parser.add_argument("split", choices=["generalization_v1"])
    preflight_parser.add_argument("--authorization")
    preflight_parser.add_argument("--model", default="gpt-4.1-mini-2025-04-14")
    preflight_parser.add_argument("--budget-usd")
    preflight_parser.add_argument("--output")
    preflight_parser.set_defaults(func=preflight)

    # run command (alias for benchmarks)
    run_parser = subparsers.add_parser("run", help="Run evaluation")
    run_parser.add_argument("--mode", choices=["integration", "decision"], default="integration")
    run_parser.add_argument("--split", default="dev")
    run_parser.add_argument("--cases", nargs="+")
    run_parser.add_argument("--provider", default="openai")
    run_parser.add_argument("--model", default="gpt-4o")
    run_parser.add_argument("--temperature", type=float, default=0.0)
    run_parser.add_argument("--authorization")
    run_parser.add_argument("--budget-usd")
    run_parser.set_defaults(func=run_benchmark)

    args = parser.parse_args(argv)

    if hasattr(args, "func"):
        return args.func(args)
    else:
        parser.print_help()
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
