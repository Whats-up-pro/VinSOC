# VinSOC R1/R2 Evaluation Hardening Design

**Date:** 2026-09-23
**Repository:** `Whats-up-pro/VinSOC`
**Base:** `master@1a44b516903f3f379870e3161175e55eb47663f2`

## Goal

Make VinSOC's two mentor-facing evaluation tracks trustworthy and runnable:

1. Tool Calling Accuracy (R1): real-model decision-only benchmark with correct tool/argument metrics.
2. Text-to-SQL Accuracy (R2): offline execution-based benchmark on frozen read-only DuckDB snapshots.

## Constraints

- Extend existing implementation; do not rewrite stable runtime architecture.
- Production agent remains read-only and continues to call domain tools, not raw SQL.
- Text-to-SQL remains an offline evaluation track in this stage.
- Evaluation mode must not silently fall back to another provider/model.
- Baseline and improvement runs must pin model/config, dataset split, evaluator, and snapshot.
- Keep backward-compatible imports where practical.
- `master` is the active implementation branch per project working agreement.

## R1 Architecture

```text
ToolCallCase
  -> production tool schemas + evaluation system prompt
  -> pinned LLMProvider.generate(...)
  -> native LLMResponse.tool_calls
  -> PredictedCall[]
  -> deterministic matcher
  -> aggregate metrics + error taxonomy
```

### R1 headline metrics

- Tool-set exact match / tool selection correctness
- Exact call precision/recall/F1 (tool + required argument values)
- Required argument value accuracy
- Critical argument accuracy
- No-tool accuracy
- Trajectory success

Tool-level precision/recall/F1, forbidden-tool rate, latency, and cost remain diagnostics.

## R1 correctness changes

- Store exact-call counts separately from tool-name counts.
- Required-argument correctness must compare values, not only presence.
- A1 uses native provider tool calls; no regex/NL parser on the official path.
- A1 must use `get_tool_schemas()` from production code.
- A1 records provider telemetry and fails closed on provider errors.

## R2 Architecture

```text
SQLBenchmarkCase
  -> schema context + question
  -> pinned LLM provider
  -> generated SQL
  -> DuckDB parser
  -> VinSOC read-only SQL safety gate
  -> frozen snapshot execution
  -> compare to accepted gold result(s)
  -> execution metrics + error taxonomy
```

### R2 headline metric

- Execution Accuracy

Diagnostics:
- Syntax Validity
- Execution Success
- Safety Rejection Rate
- Error categories

## R2 package shape

Keep the existing `evaluation.text_to_sql` public API working while moving implementation into a package only if needed. Prefer the minimum change that yields a runnable benchmark CLI and dataset split.

## Dataset policy

- `dev`: visible authoring/tuning cases.
- `frozen`: holdout cases not used for tuning.
- R1 cases are SOC-domain tool decisions.
- R2 cases target real normalized tables: `cti_indicators`, `network_flows`, `sysmon_process_events`.
- Gold SQL and model SQL execute on the same immutable snapshot.
- No synthetic rows may enter a frozen benchmark snapshot; unit-test fixtures remain allowed.

## Improvement loop

For each track:
1. Run pinned baseline.
2. Classify errors.
3. Change one variable.
4. Re-run the same dev benchmark.
5. Promote the best configuration.
6. Run once on frozen holdout.
7. Report baseline vs improved with absolute percentage-point delta.

## Non-goals

- No model fine-tuning.
- No new agent framework.
- No production raw-SQL tool.
- No large generic evaluation abstraction layer.
- No UI work.
