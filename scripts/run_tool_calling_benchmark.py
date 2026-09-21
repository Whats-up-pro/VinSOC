#!/usr/bin/env python3
"""
R1 Tool Calling Benchmark Runner

Usage:
    # A2 Integration evaluation (existing scenarios)
    python scripts/run_tool_calling_benchmark.py --mode integration

    # A1 Decision evaluation (benchmark cases)
    python scripts/run_tool_calling_benchmark.py --mode decision --split dev

    # A2 with specific cases
    python scripts/run_tool_calling_benchmark.py --mode integration --cases case_001 case_002
"""
import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

# Add parent to path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from evaluation.tool_calling.integration_runner import IntegrationRunner, run_legacy_integration_benchmark
from evaluation.tool_calling.decision_runner import run_a1_benchmark, DecisionRunner


def main():
    parser = argparse.ArgumentParser(description="R1 Tool Calling Benchmark Runner")
    parser.add_argument(
        "--mode",
        choices=["decision", "integration", "legacy"],
        default="integration",
        help="Evaluation mode: decision (A1) or integration (A2)",
    )
    parser.add_argument(
        "--split",
        choices=["dev", "frozen"],
        default="dev",
        help="Benchmark split for decision mode",
    )
    parser.add_argument(
        "--cases",
        nargs="+",
        help="Specific case IDs to run (default: all)",
    )
    parser.add_argument(
        "--output",
        type=Path,
        help="Output path for results",
    )
    parser.add_argument(
        "--legacy",
        action="store_true",
        help="Run legacy benchmark (20 scenarios, A2)",
    )

    args = parser.parse_args()

    print(f"R1 Tool Calling Benchmark")
    print(f"Mode: {args.mode}")
    print(f"Started: {datetime.utcnow().isoformat()}")
    print("-" * 50)

    if args.legacy or args.mode == "legacy":
        # Run legacy integration benchmark
        output_path = args.output or Path(f"results/tool_calling/legacy_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}/metrics.json")
        print(f"Running legacy integration benchmark...")
        result = run_legacy_integration_benchmark(output_path)

        print(f"\nResults:")
        print(f"  Cases: {result['aggregate']['case_count']}")
        print(f"  Tool Precision: {result['aggregate']['tool_precision']:.2%}")
        print(f"  Tool Recall: {result['aggregate']['tool_recall']:.2%}")
        print(f"  Tool F1: {result['aggregate']['tool_f1']:.2%}")
        print(f"  Tool Set EM: {result['aggregate']['tool_set_exact_match_rate']:.2%}")
        print(f"  Trajectory Success: {result['aggregate']['trajectory_success_rate']:.2%}")

    elif args.mode == "integration":
        # Run A2 integration evaluation
        runner = IntegrationRunner()

        case_ids = args.cases or [f"case_{i:03d}" for i in range(1, 21)]
        print(f"Running {len(case_ids)} integration cases...")

        results = runner.run_suite(case_ids)

        # Aggregate
        from evaluation.tool_calling.metrics import aggregate_case_results, generate_error_summary
        run_id = f"a2_integration_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}"
        aggregate = aggregate_case_results(run_id, results)
        error_summary = generate_error_summary(results)

        print(f"\nResults:")
        print(f"  Cases: {aggregate.case_count}")
        print(f"  Tool Precision: {aggregate.tool_precision:.2%}")
        print(f"  Tool Recall: {aggregate.tool_recall:.2%}")
        print(f"  Tool F1: {aggregate.tool_f1:.2%}")
        print(f"  Tool Set EM: {aggregate.tool_set_exact_match_rate:.2%}")
        print(f"  Trajectory Success: {aggregate.trajectory_success_rate:.2%}")

        if error_summary:
            print(f"\nError Summary:")
            for error_type, count in list(error_summary.items())[:5]:
                print(f"  {error_type}: {count}")

        # Save results
        output_path = args.output or Path(f"results/tool_calling/{run_id}/metrics.json")
        output_path.parent.mkdir(parents=True, exist_ok=True)

        result_dict = {
            "run_id": run_id,
            "mode": "integration",
            "aggregate": aggregate.to_dict(),
            "error_summary": error_summary,
            "case_results": [r.to_dict() for r in results],
        }

        with open(output_path, "w") as f:
            json.dump(result_dict, f, indent=2)

        print(f"\nResults saved to: {output_path}")

    elif args.mode == "decision":
        # Run A1 decision evaluation
        print(f"Running A1 decision benchmark (split: {args.split})...")
        result = run_a1_benchmark(split=args.split, output_path=args.output)

        if "error" in result:
            print(f"Error: {result['error']}")
            return

        print(f"\nResults:")
        print(f"  Cases: {result['case_count']}")
        print(f"  Tool Precision: {result['aggregate']['tool_precision']:.2%}")
        print(f"  Tool Recall: {result['aggregate']['tool_recall']:.2%}")
        print(f"  Tool F1: {result['aggregate']['tool_f1']:.2%}")

        print(f"\nResults saved to: {args.output}")

    print("-" * 50)
    print(f"Completed: {datetime.utcnow().isoformat()}")


if __name__ == "__main__":
    main()
