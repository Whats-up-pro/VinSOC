# VinSOC Evaluation Protocol V1

**Version:** 1  
**Protocol date:** 2026-09-23  
**Evaluator code commit:** `4ecc6f3f2da601a22d9a9cf76b8fd8ec61ed902c`

## Scope and claims

Evaluation V1 has two separate tracks:

- **R1 / A1:** single-turn, decision-only native tool calling against the exact production schemas from `agent.tools.get_tool_schemas()`.
- **R1 / A2:** deterministic integration/regression checks through the orchestrator and skills. A2 is not an official model-accuracy baseline.
- **R2:** model-generated DuckDB SQL scored by execution against the same verified, read-only snapshot used by gold SQL.

R1 does not claim BFCL V4 multi-turn agentic equivalence. R2 does not use exact SQL string match or an LLM judge.

## Split policy

Development cases are visible and may be used for error analysis. Frozen cases are holdout data and may be executed once only after the winning configuration is recorded. Challenge/OOD cases are reported separately and never enter the primary score. The present R2 case contract names one snapshot; independent source-session splits and multiple snapshots remain an unmet methodology requirement.

No prompt, schema, evaluator, case, or snapshot may be changed after a frozen score is observed. Such a change invalidates the holdout result and requires a new versioned holdout set. Dataset rows are grouped by public source/session/scenario rather than randomly split.

## R1 contract

Official R1 uses the model's native `tool_calls`; tool names are never inferred from prose. Before a run, record the provider, exact model ID, temperature, git commit, system prompt, production schema hash, and benchmark-directory hash with the output artifact. Provider and execution failures are explicit error categories and cannot receive no-tool, tool-set, exact-call, or single-turn case-success credit.

Headline metrics:

- Tool Selection Accuracy: tool multiset exact match.
- Exact Call Precision / Recall / F1: tool plus required argument values.
- Required Argument Accuracy.
- Critical Argument Accuracy.
- No-Tool Accuracy.
- Single-Turn Case Success (legacy field `trajectory_success_rate`).

Diagnostics include forbidden-tool rate, provider-error rate, execution-error rate, latency, tokens, and available cost metadata.

## R2 contract

Before provider creation or generation, the runner verifies canonical snapshot path, snapshot ID, and lowercase SHA-256 from `snapshot_manifest.json`. A mismatch fails closed without a score.

The primary metric is **Execution Accuracy**. Diagnostics are Syntax Validity, Execution Success, Safety Rejection Rate, provider errors, latency/tokens/cost, and per-category Execution Accuracy. `ordered_rows` preserves row order; `unordered_rows` and `multiset_rows` ignore order while preserving duplicate multiplicity; `scalar` and `boolean` compare their ordered value result.

All generated and gold queries pass through the same single-statement, read-only DuckDB boundary. Writes, attachment, extension installation, and other non-SELECT operations are rejected.

## Data provenance

Every source must record `dataset_id`, source name, absolute HTTPS URL, UTC retrieval timestamp, exact downloaded-file SHA-256, licence/usage note, schema version, local path, format, and archive member when applicable. Every normalized row retains `source_dataset` and stable `source_row_id`.

The public source families are ThreatFox, CTU-13, and OTRF Security-Datasets Sysmon telemetry. No synthetic row may enter an official snapshot. The builder verifies source hashes before database creation, registers provenance before rows, validates table coverage and row identity, executes all development gold queries, reopens read-only, and only then writes the real snapshot hash. The OTRF archive member and format still need inspection on actual downloaded bytes before any official build.

## Required configuration and commands

```bash
export VINSOC_EVAL_PROVIDER=openai
test -n "$VINSOC_EVAL_MODEL"
test -n "$OPENAI_API_KEY"

python -m evaluation.tool_calling benchmarks dev \
  --mode decision \
  --provider "$VINSOC_EVAL_PROVIDER" \
  --model "$VINSOC_EVAL_MODEL" \
  --temperature 0

python -m evaluation.text_to_sql evaluate \
  --snapshot data/snapshots/vinsoc_public_v1.duckdb \
  --manifest evaluation/text_to_sql_benchmarks/snapshot_manifest.json \
  --split dev \
  --provider "$VINSOC_EVAL_PROVIDER" \
  --model "$VINSOC_EVAL_MODEL" \
  --temperature 0 \
  --output results/evaluation_v1/r2/dev_baseline.json
```

Run development three times without tuning between repetitions when cost permits. Do not use fallback routing in an official run.

## Error analysis and experiments

R1 failures use `WRONG_TOOL`, `MISSING_TOOL`, `EXTRA_TOOL`, `NO_TOOL_HALLUCINATION`, `REQUIRED_ARG_MISSING`, `REQUIRED_ARG_WRONG_VALUE`, `CRITICAL_ARG_WRONG`, `FORBIDDEN_TOOL`, `DUPLICATE_CALL`, or `PROVIDER_ERROR`. R2 failures use `PROVIDER_ERROR`, `SYNTAX_ERROR`, `SAFETY_REJECTION`, `EXECUTION_ERROR`, or `RESULT_MISMATCH`.

Every failed development case must have one inspectable primary reason before optimization. Experiments change exactly one variable and record configuration hashes, metric deltas in percentage points, error-class deltas, and latency/cost deltas. Frozen data is never used to choose an experiment.
