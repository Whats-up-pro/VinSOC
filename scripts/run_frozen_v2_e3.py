"""Run frozen v2 E3 - GPT-5 Mini with Linker + Generator + Tools."""

from __future__ import annotations

import json
import os
import time
from pathlib import Path
from datetime import datetime, timezone

# Model config
MODEL = "gpt-5-mini-2025-08-07"
REASONING_EFFORT = "low"
CAP = 1000
INPUT_USD_M = 0.25
OUTPUT_USD_M = 2.00
FROZEN_SNAPSHOT = Path("data/ctu_network_frozen/snapshots/frozen_v1.duckdb")
OUTPUT_DIR = Path("results/evaluation_v1/ctu_network_frozen/v2_e3")
MAX_TURNS = 5


def cost_usd(input_tokens: int, output_tokens: int) -> float:
    return (input_tokens * INPUT_USD_M + output_tokens * OUTPUT_USD_M) / 1_000_000


def load_cases() -> list[dict]:
    cases = []
    frozen_dir = Path("evaluation/ctu_network_frozen/frozen")
    for path in sorted(frozen_dir.glob("frozen_*.json")):
        with open(path) as f:
            cases.append(json.load(f))
    return cases


def get_schema_context(tools) -> str:
    """Get schema context for the tools."""
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


def value_search(tools, query: str, column: str = None, table: str = None) -> dict:
    """Search for values in the database."""
    args = {"query": query}
    if column:
        args["column"] = column
    if table:
        args["table"] = table
    return tools.value_search(args)


def sql_probe(tools, sql: str) -> dict:
    """Run a bounded SQL probe."""
    return tools.sql_probe({"sql": sql})


def run_linker(question: str, schema: str, tools, client) -> dict:
    """Run the linker role to discover schema and grounded values."""
    system = (
        "You are the Schema Linker. Map the question to the database schema using tools. "
        "Use database_profiler to inspect table structure and column types. "
        "Use value_search to find actual stored values in the database. "
        "Search for VALUES THAT EXACTLY MATCH what you need - check the actual stored values. "
        "Return one JSON object with exactly a tables array and a grounded_values array. "
        "Each table entry: {table: string, columns: [string]}. "
        "Each grounded_value: {table: string, column: string, value: string}. "
        "Values MUST come from tool output (value_search or profiler examples). "
        "Do not return SQL or prose."
        f"\n\nDatabase schema:\n{schema}"
    )

    messages = [
        {"role": "system", "content": system},
        {"role": "user", "content": question},
    ]

    trajectory = []
    tool_count = 0

    for turn in range(1, MAX_TURNS + 1):
        response = client.chat.completions.create(
            model=MODEL,
            reasoning_effort=REASONING_EFFORT,
            max_completion_tokens=CAP,
            messages=messages,
            tools=[
                {"type": "function", "function": {"name": "database_profiler",
                    "description": "Inspect table structure and column types.",
                    "parameters": {"type": "object", "properties": {
                        "table": {"type": "string"}}, "additionalProperties": False}}},
                {"type": "function", "function": {"name": "value_search",
                    "description": "Search actual stored values.",
                    "parameters": {"type": "object", "properties": {
                        "query": {"type": "string"},
                        "table": {"type": "string"},
                        "column": {"type": "string"}}, "required": ["query"],
                        "additionalProperties": False}}},
                {"type": "function", "function": {"name": "sql_probe",
                    "description": "Run bounded SELECT to inspect data.",
                    "parameters": {"type": "object", "properties": {
                        "sql": {"type": "string"}}, "required": ["sql"],
                        "additionalProperties": False}}},
            ],
            response_format={"type": "json_object"},
        )

        message = response.choices[0].message
        calls = getattr(message, "tool_calls", None) or []

        if not calls:
            content = getattr(message, "content", None)
            return {
                "content": content,
                "turns": turn,
                "tool_count": tool_count,
                "trajectory": trajectory,
                "usage": {
                    "input_tokens": response.usage.prompt_tokens,
                    "output_tokens": response.usage.completion_tokens,
                    "cost_usd": cost_usd(response.usage.prompt_tokens, response.usage.completion_tokens),
                }
            }

        messages.append({
            "role": "assistant",
            "content": getattr(message, "content", None),
            "tool_calls": [{
                "id": c.id,
                "type": "function",
                "function": {"name": c.function.name, "arguments": c.function.arguments}
            } for c in calls]
        })

        for call in calls:
            tool_count += 1
            try:
                args = json.loads(call.function.arguments)
            except:
                args = {}

            if call.function.name == "database_profiler":
                result = tools.database_profiler(args)
            elif call.function.name == "value_search":
                result = value_search(tools, args.get("query", ""), args.get("column"), args.get("table"))
            elif call.function.name == "sql_probe":
                result = sql_probe(tools, args.get("sql", ""))
            else:
                result = {"ok": False, "error": "Unknown tool"}

            trajectory.append({
                "tool": call.function.name,
                "arguments": args,
                "result": result,
            })

            messages.append({
                "role": "tool",
                "tool_call_id": call.id,
                "content": json.dumps(result, default=str),
            })

    return {
        "content": None,
        "turns": MAX_TURNS,
        "tool_count": tool_count,
        "trajectory": trajectory,
        "error": "TURN_LIMIT",
        "usage": {}
    }


def run_generator(question: str, schema: str, linked_schema: dict, tools, client) -> dict:
    """Run the generator with linked schema."""
    system = (
        "Write one read-only DuckDB SELECT for the question. "
        "Use tools (value_search) to find actual stored values before using them in filters. "
        "Match the exact stored values in the database, not question text. "
        "Use exact filters, Boolean grouping, time boundaries, aggregation, ordering, and limits. "
        "Return only SQL, without Markdown or commentary."
        f"\n\nValidated linked schema:\n{json.dumps(linked_schema)}"
    )

    messages = [
        {"role": "system", "content": system},
        {"role": "user", "content": question},
    ]

    trajectory = []
    tool_count = 0

    for turn in range(1, MAX_TURNS + 1):
        response = client.chat.completions.create(
            model=MODEL,
            reasoning_effort=REASONING_EFFORT,
            max_completion_tokens=CAP,
            messages=messages,
            tools=[
                {"type": "function", "function": {"name": "value_search",
                    "description": "Search actual stored values.",
                    "parameters": {"type": "object", "properties": {
                        "query": {"type": "string"},
                        "table": {"type": "string"},
                        "column": {"type": "string"}}, "required": ["query"],
                        "additionalProperties": False}}},
            ],
        )

        message = response.choices[0].message
        calls = getattr(message, "tool_calls", None) or []

        if not calls:
            content = getattr(message, "content", None) or ""
            return {
                "content": content.strip().strip('```sql').strip('```').strip(),
                "turns": turn,
                "tool_count": tool_count,
                "trajectory": trajectory,
                "usage": {
                    "input_tokens": response.usage.prompt_tokens,
                    "output_tokens": response.usage.completion_tokens,
                    "cost_usd": cost_usd(response.usage.prompt_tokens, response.usage.completion_tokens),
                }
            }

        messages.append({
            "role": "assistant",
            "content": getattr(message, "content", None),
            "tool_calls": [{
                "id": c.id,
                "type": "function",
                "function": {"name": c.function.name, "arguments": c.function.arguments}
            } for c in calls]
        })

        for call in calls:
            tool_count += 1
            try:
                args = json.loads(call.function.arguments)
            except:
                args = {}

            result = value_search(tools, args.get("query", ""), args.get("column"), args.get("table"))
            trajectory.append({
                "tool": call.function.name,
                "arguments": args,
                "result": result,
            })

            messages.append({
                "role": "tool",
                "tool_call_id": call.id,
                "content": json.dumps(result, default=str),
            })

    return {
        "content": None,
        "turns": MAX_TURNS,
        "tool_count": tool_count,
        "trajectory": trajectory,
        "error": "TURN_LIMIT",
        "usage": {}
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
                return {"execution_accurate": False, "syntax_valid": False, "error_category": f"EXEC_ERROR"}

            if gold_result == gen_result:
                return {"execution_accurate": True, "syntax_valid": True}
            else:
                return {"execution_accurate": False, "syntax_valid": True, "error_category": "RESULT_MISMATCH"}
    except Exception as e:
        return {"execution_accurate": False, "syntax_valid": False, "error_category": f"ERROR"}


def main():
    import argparse
    from openai import OpenAI
    from evaluation.dualsql_lite_ctu_gpt5_v2.tools import CTUDatabaseTools

    parser = argparse.ArgumentParser()
    parser.add_argument("--api-key", default=None)
    parser.add_argument("--snapshot", type=Path, default=FROZEN_SNAPSHOT)
    parser.add_argument("--output-dir", type=Path, default=OUTPUT_DIR)
    args = parser.parse_args()

    from scripts.frozen_run_guard import require_unconsumed_frozen
    require_unconsumed_frozen()

    api_key = args.api_key or os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise ValueError("No API key provided")

    client = OpenAI(api_key=api_key)
    tools = CTUDatabaseTools(args.snapshot)

    cases = load_cases()
    print(f"Loaded {len(cases)} frozen cases")
    print(f"Snapshot: {args.snapshot}")

    schema = get_schema_context(tools)
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    results = []
    for case in cases:
        print(f"Running v2 E3: {case['case_id']}...")

        # Run linker
        linker = run_linker(case["question"], schema, tools, client)

        linked_schema = None
        if linker.get("content"):
            try:
                linked_schema = json.loads(linker["content"])
            except:
                linked_schema = {"tables": [], "grounded_values": []}

        # Run generator
        generator = run_generator(
            case["question"], schema, linked_schema or {"tables": [], "grounded_values": []},
            tools, client
        )

        sql = generator.get("content", "") or ""
        eval_result = evaluate_sql(sql, case["gold_sql"], args.snapshot)

        total_usage = linker.get("usage", {})
        gen_usage = generator.get("usage", {})
        total_usage["input_tokens"] = total_usage.get("input_tokens", 0) + gen_usage.get("input_tokens", 0)
        total_usage["output_tokens"] = total_usage.get("output_tokens", 0) + gen_usage.get("output_tokens", 0)
        total_usage["cost_usd"] = total_usage.get("cost_usd", 0) + gen_usage.get("cost_usd", 0)

        result = {
            "case_id": case["case_id"],
            "question": case["question"],
            "generated_sql": sql,
            "gold_sql": case["gold_sql"],
            "linker_turns": linker.get("turns", 0),
            "linker_tool_calls": linker.get("tool_count", 0),
            "generator_turns": generator.get("turns", 0),
            "generator_tool_calls": generator.get("tool_count", 0),
            "linked_schema": linked_schema,
            **eval_result,
            "usage": total_usage,
        }
        results.append(result)

        (OUTPUT_DIR / f"{case['case_id']}.json").write_text(
            json.dumps(result, indent=2, default=str) + "\n"
        )

    # Summary
    accurate = sum(1 for r in results if r["execution_accurate"])
    syntax_valid = sum(1 for r in results if r.get("syntax_valid", False))
    total_cost = sum(r["usage"].get("cost_usd", 0) for r in results)

    report = {
        "condition": "v2 E3",
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

    print(f"\n=== v2 E3 Results ===")
    print(f"Execution Accuracy: {accurate}/{len(cases)}")
    print(f"Total Cost: ${total_cost:.6f}")


if __name__ == "__main__":
    main()
