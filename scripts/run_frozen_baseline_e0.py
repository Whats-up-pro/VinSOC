"""Run frozen Baseline E0 - one-shot GPT-5 Mini without tools."""

from __future__ import annotations

import json
import os
import time
from pathlib import Path
from datetime import datetime, timezone

# Model config from locked contract
MODEL = "gpt-5-mini-2025-08-07"
REASONING_EFFORT = "low"
CAP = 1000
INPUT_USD_M = 0.25
OUTPUT_USD_M = 2.00
FROZEN_SNAPSHOT = Path("data/ctu_network_frozen/snapshots/frozen_v1.duckdb")
OUTPUT_DIR = Path("results/evaluation_v1/ctu_network_frozen/baseline_e0")
FRAMING_TOKENS = 4096


def cost_usd(input_tokens: int, output_tokens: int) -> float:
    return (input_tokens * INPUT_USD_M + output_tokens * OUTPUT_USD_M) / 1_000_000


def load_cases() -> list[dict]:
    cases = []
    frozen_dir = Path("evaluation/ctu_network_frozen/frozen")
    for path in sorted(frozen_dir.glob("frozen_*.json")):
        with open(path) as f:
            cases.append(json.load(f))
    return cases


def get_schema_context() -> str:
    """Get schema context for the snapshot."""
    import duckdb
    with duckdb.connect(str(FROZEN_SNAPSHOT), read_only=True) as conn:
        rows = conn.execute("""
            SELECT table_name, column_name, data_type
            FROM information_schema.columns
            WHERE table_schema='main' AND table_name='network_flows'
            ORDER BY ordinal_position
        """).fetchall()

    cols = [f"{col} {dtype}" for _, col, dtype in rows]
    return f"network_flows({', '.join(cols)})"


PROMPT_TEMPLATE = """Write one read-only DuckDB SELECT for the question.

{schema}

Return only SQL, without Markdown or commentary.

Question: {question}"""


def run_one_shot(question: str, schema: str, client) -> dict:
    """Run one-shot generation without tools."""
    prompt = PROMPT_TEMPLATE.format(schema=schema, question=question)

    messages = [{"role": "user", "content": prompt}]

    start = time.monotonic()
    response = client.chat.completions.create(
        model=MODEL,
        reasoning_effort=REASONING_EFFORT,
        max_completion_tokens=CAP,
        messages=messages,
    )
    latency_ms = (time.monotonic() - start) * 1000

    content = response.choices[0].message.content or ""

    return {
        "content": content,
        "input_tokens": response.usage.prompt_tokens,
        "output_tokens": response.usage.completion_tokens,
        "cost_usd": cost_usd(response.usage.prompt_tokens, response.usage.completion_tokens),
        "latency_ms": latency_ms,
        "model": response.model,
    }


def evaluate_sql(sql: str, gold_sql: list[str], snapshot: Path) -> dict:
    """Evaluate generated SQL against gold SQL."""
    import duckdb

    sql = sql.strip().strip('```sql').strip('```').strip()

    if not sql:
        return {"execution_accurate": False, "error_category": "EMPTY_SQL"}

    try:
        with duckdb.connect(str(snapshot), read_only=True) as conn:
            gold_result = conn.execute(gold_sql[0]).fetchall()

            try:
                gen_result = conn.execute(sql).fetchall()
            except Exception as e:
                return {"execution_accurate": False, "syntax_valid": False, "error_category": f"EXEC_ERROR: {e}"}

            if gold_result == gen_result:
                return {"execution_accurate": True, "syntax_valid": True}
            else:
                return {"execution_accurate": False, "syntax_valid": True, "error_category": "RESULT_MISMATCH"}
    except Exception as e:
        return {"execution_accurate": False, "syntax_valid": False, "error_category": f"ERROR: {e}"}


def main():
    import argparse
    from openai import OpenAI

    parser = argparse.ArgumentParser()
    parser.add_argument("--api-key", default=None)
    parser.add_argument("--snapshot", type=Path, default=FROZEN_SNAPSHOT)
    parser.add_argument("--output-dir", type=Path, default=OUTPUT_DIR)
    args = parser.parse_args()

    from scripts.frozen_run_guard import require_unconsumed_frozen
    require_unconsumed_frozen()

    client = OpenAI(api_key=args.api_key or os.getenv("OPENAI_API_KEY"))

    cases = load_cases()
    print(f"Loaded {len(cases)} frozen cases")
    print(f"Snapshot: {args.snapshot}")

    schema = get_schema_context()
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    results = []
    for case in cases:
        print(f"Running {case['case_id']}...")

        gen = run_one_shot(case["question"], schema, client)

        sql = gen["content"].strip().strip('```sql').strip('```').strip()
        eval_result = evaluate_sql(sql, case["gold_sql"], args.snapshot)

        result = {
            "case_id": case["case_id"],
            "question": case["question"],
            "generated_sql": sql,
            "gold_sql": case["gold_sql"],
            **gen,
            **eval_result,
        }
        results.append(result)

        (OUTPUT_DIR / f"{case['case_id']}.json").write_text(
            json.dumps(result, indent=2, default=str) + "\n"
        )

    # Summary
    accurate = sum(1 for r in results if r["execution_accurate"])
    syntax_valid = sum(1 for r in results if r.get("syntax_valid", False))
    total_cost = sum(r["cost_usd"] for r in results)

    report = {
        "condition": "Baseline E0",
        "snapshot": str(args.snapshot),
        "case_count": len(cases),
        "metrics": {
            "execution_accuracy": f"{accurate}/{len(cases)}",
            "syntax_valid": f"{syntax_valid}/{len(cases)}",
        },
        "total_cost_usd": total_cost,
        "case_ids": [r["case_id"] for r in results],
        "run_timestamp": datetime.now(timezone.utc).isoformat(),
    }

    (OUTPUT_DIR / "report.json").write_text(json.dumps(report, indent=2) + "\n")

    print(f"\n=== Baseline E0 Results ===")
    print(f"Execution Accuracy: {accurate}/{len(cases)}")
    print(f"Total Cost: ${total_cost:.6f}")


if __name__ == "__main__":
    main()
