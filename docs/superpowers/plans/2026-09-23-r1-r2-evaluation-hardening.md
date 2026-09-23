# VinSOC Tool Calling + Text-to-SQL Evaluation Hardening Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans in this harness. Steps use TDD (RED -> GREEN) and direct `master` commits.

**Goal:** Produce trustworthy, runnable R1 Tool Calling and R2 Text-to-SQL evaluation paths for mentor-facing baseline/improvement experiments.

**Architecture:** Harden the existing deterministic evaluators instead of replacing them. R1 connects the existing A1 runner to the existing provider abstraction and fixes metric semantics. R2 extends the existing execution evaluator into a runnable model-generation benchmark while preserving DuckDB's read-only boundary.

**Tech Stack:** Python 3.11+, pytest, OpenAI-compatible provider adapter, DuckDB, JSON benchmark cases.

**Spec:** `docs/superpowers/specs/2026-09-23-r1-r2-evaluation-hardening-design.md`

## Global Constraints

- Extend existing code; do not rewrite stable runtime paths.
- Production LLM never receives raw DuckDB access.
- R2 remains offline evaluation.
- Evaluation runs never silently switch provider/model.
- Use production tool schemas in R1 A1.
- Preserve current public imports where practical.
- Direct implementation target is `master`.

## Review Focus

1. Exact-call metrics accidentally reuse tool-level TP/FP/FN.
2. Required arguments counted as correct when merely present but wrong.
3. A1 benchmark accidentally parses prose instead of native tool calls.
4. Evaluation mode silently falls back or changes model.
5. Text-to-SQL runner bypasses the existing read-only SQL safety gate.

---

### Task 1: Correct R1 metric semantics

**Files:**
- Modify: `evaluation/tool_calling/models.py`
- Modify: `evaluation/tool_calling/matching.py`
- Modify: `evaluation/tool_calling/metrics.py`
- Modify: `tests/test_tool_calling_evaluator.py`

**Produces:** separate tool and exact-call counts; required-argument value accuracy.

**Acceptance:**
- A PARTIAL call is a tool TP but not exact-call TP.
- Wrong required value lowers argument accuracy.
- Exact-call PRF differs from tool PRF when arguments are wrong.
- Existing golden matcher behavior remains intact.

### Task 2: Connect R1 A1 to real provider abstraction

**Files:**
- Modify: `evaluation/tool_calling/decision_runner.py`
- Modify: `evaluation/tool_calling/__main__.py`
- Add/Modify tests under `tests/`

**Consumes:** `agent.provider.create_provider`, `agent.tools.get_tool_schemas`, corrected Task 1 metrics.

**Acceptance:**
- Injected provider can be tested without network.
- Official A1 consumes `LLMResponse.tool_calls` directly.
- Tool schemas are the production schemas.
- Provider errors become explicit evaluation failures.
- Model/provider metadata is included in run output.

### Task 3: Complete R1 benchmark split and reporting contract

**Files:**
- Modify benchmark loader/README as needed.
- Add `evaluation/tool_calling/benchmarks/frozen/` cases only from reviewed existing scenarios or authored cases.
- Tests for split loading and no-tool coverage.

**Acceptance:**
- Dev and frozen are separately runnable.
- Frozen cases are not loaded when running dev.
- Report exposes headline metrics plus error summary.

### Task 4: Make R2 a runnable generation benchmark

**Files:**
- Extend `evaluation/text_to_sql.py` or minimally package it.
- Modify `schemas/text_to_sql_case.json` only if new fields are actually consumed.
- Add tests under `tests/`.

**Produces:** case loader, provider-backed SQL generation runner, metrics/error summary, CLI entry path.

**Acceptance:**
- Provider is injectable for tests.
- Generated SQL is always evaluated through `evaluate_sql_case`.
- Read-only safety rejection remains enforced.
- Execution Accuracy is headline metric.
- Existing imports used by `tests/test_duckdb_data_layer.py` remain valid.

### Task 5: R2 benchmark split + semantic trap cases

**Files:**
- Add benchmark case directories/docs.
- Add unit-test fixtures for semantic traps; do not add synthetic rows to frozen benchmark data.

**Acceptance:**
- Covers filter, time range, aggregation/distinct, ordering/limit, CTI/network/endpoint table access.
- Test fixtures demonstrate at least one wrong-semantics/same-shape trap.
- Frozen snapshot requirement is documented and validated before official run.

### Task 6: Integration and final verification

**Verification:**
- Full GitHub Actions pytest matrix on Python 3.11 and 3.12.
- Self-review against spec because this harness has no subagent-dispatch tool.
- Search changed code for TODO/FIXME on critical paths.
- Verify README/docs commands match implemented CLI.

**Acceptance:**
- CI green on both Python versions.
- No Critical/Important review findings unresolved.
- Final report states which parts are code-complete and which require credentials/data snapshot for actual benchmark scores.
