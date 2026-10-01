"""Test Case 006 with INTEGER column hint fix."""

import json
from pathlib import Path
from dataclasses import dataclass

from evaluation.r2_phase2.grounding import Phase2Tools
from evaluation.r2_phase2.runner import run_case
from evaluation.ctu_network_public.contract import CASES, MANIFEST

MODEL = "gpt-5-mini-2025-08-07"
CAP = 1000
REASONING_EFFORT = "low"


@dataclass
class Case:
    case_id: str
    question: str
    gold_sql: list[str]


def main():
    from openai import OpenAI
    import os

    client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

    # Load Case 006
    case_path = CASES / "ctu_sql_006.json"
    case_data = json.loads(case_path.read_text())
    case = Case(
        case_id=case_data['case_id'],
        question=case_data['question'],
        gold_sql=case_data['gold_sql']
    )

    # Create tools
    snapshot = Path("data/ctu_network_public/snapshots/ctu_dev.duckdb")
    tools = Phase2Tools(snapshot, MANIFEST)

    # Run Case 006
    print(f"Testing Case 006: {case.question}")
    print(f"Snapshot: {snapshot}")
    print()

    result = run_case(
        case=case,
        condition="E3",
        tools=tools,
        client=client,
        schema_context=tools.schema_context(),
    )

    print()
    print(f"Result:")
    print(f"  execution_accurate: {result.get('error_category') == 'OK'}")
    print(f"  error_category: {result.get('error_category')}")
    print(f"  final_sql: {result.get('final_sql', 'N/A')[:100]}...")

    # Check trajectory for INTEGER hint handling
    traj = result.get('trajectory', [])
    print(f"\nTrajectory ({len(traj)} steps):")
    for t in traj:
        res = t.get('result', {})
        if res.get('hint'):
            print(f"  - Hint received: {res['hint'][:80]}...")

    # Save result
    output_dir = Path("results/evaluation_v1/ctu_network_public/r2_phase2_test_case006")
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "ctu_sql_006.json").write_text(json.dumps(result, indent=2, default=str))

    print(f"\nSaved to: {output_dir / 'ctu_sql_006.json'}")


if __name__ == "__main__":
    main()
