# VinSOC E2E/R2 Closeout Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:executing-plans` to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. Work directly on `master`; do not create a PR or use this plan to change the R1 generalization track.

**Goal:** Close the integrated Text-to-SQL E2E evidence honestly, then decide and execute any R2 calibration/evaluation work as a separately authorized scope without rewriting failed runs or shrinking official denominators.

**Architecture:** Treat the single-case query demo, the 48-record R2 calibration, the 192-record R2 evaluation, and the 32-case pipeline as four distinct evidence scopes with distinct authorization, budget, ledger, and completion receipts. Existing failed demo artifacts remain append-only; a future demo execution gets a new execution ID and can become technically complete only from its own native model/tool/DB/assessment trace, independent replay, and human review.

**Tech Stack:** Python 3.11/3.12, pytest, GitHub Actions, OpenAI guarded transport, DuckDB read-only worker, existing `vinsoc_text2sql` service, JSON/HTML offline renderer.

**Spec:** `docs/superpowers/plans/2026-10-08-vinsoc-text2sql-integration-and-final-demo.md`; `docs/evaluation/VinSOC_Offline_Release_Handoff_2026-10-10.md`; `docs/evaluation/VinSOC_Offline_Release_Addendum_2026-10-11.md`; `docs/evaluation/VinSOC_R6_Budget_Decision_2026-10-10.md`.

## Global Constraints

- Keep R1 generalization work under `docs/superpowers/plans/2026-10-09-vinsoc-r1-tool-calling-generalization.md`; no task in this plan changes its benchmark, lock, runner, authorization, result directory, or denominator.
- Preserve every historical request, response, outcome audit, tag, lock, prompt, scorer, benchmark, and result byte. Never edit a failed run into a success or reuse its execution ID.
- Do not call a model, create a provider, or transmit a request from an offline/test step. A paid step needs a new scope-specific authorization and budget receipt even if an older receipt reports unused balance.
- Do not retry automatically, splice responses, change caps after output, fabricate reviewer approval, or reduce a planned denominator to obtain a passing result.
- A query demo is not R2 calibration, evaluation, pipeline scoring, or proof of general Text-to-SQL accuracy. R2 replay/gold tests are not model predictions.
- Keep `gpt-5-mini-2025-08-07`, reasoning `low`, `max_completion_tokens=1000`, zero SDK retries, and the current production prompt/schema/scorer unless a new protocol version and budget decision explicitly replace them before output is opened.
- At or after the documented model retirement date, stop and create a new protocol decision; do not silently migrate models.
- Push each completed code/data milestone directly to `origin/master` only after local verification, then require GitHub Actions success for that exact full SHA.

## Verified Starting Point

The starting point for this plan is `master@1b002cdbeab5d319d8c419f64c745730f98df84a`. CI run [38196398929](https://github.com/Whats-up-pro/VinSOC/actions/runs/38196398929) succeeded for that exact SHA.

| Evidence | Immutable conclusion |
|---|---|
| `single_demo_full_e2e_5_20261012` | `technical_incomplete`; `MODEL_PARSE_ERROR`; 5/5 responses; no final SQL, assessment, replay, or human review; current-run cost `$0.0042944` |
| `single_demo_full_e2e_6_20261012` | `technical_incomplete`; `RESULT_MISMATCH`; 6/6 responses; final SQL executed but semantic result was wrong, assessment contract invalid, no human review; current-run cost `$0.0068423` |
| Cumulative query-demo ledger after run 6 | `$0.0270214`; this is not permission for another run and not an R2 budget |
| Current source fix | `1b002cd` rechecks grouped conjunctive counts; code/CI success is not a successful post-fix live result |
| R2 official scopes | Calibration `0/48`, evaluation `0/192`, pipeline `0/32`; all remain pending with no new model score |

## Review Focus

1. A run with final SQL and successful DB execution but a semantic result mismatch remains technically incomplete and cannot enter human approval as a success.
2. A valid model response after earlier failed executions does not replace or mutate the earlier artifacts; every execution ID and cost remains visible.
3. An unused dollar balance in a demo receipt does not authorize R2 calibration/evaluation or another demo execution.
4. Missing calibration pairs, evaluation records, pipeline records, usage, or provenance block release; they are not removed from the denominator.
5. Human review can approve/reject/escalate only a technically valid receipt and cannot repair SQL, assessment, provenance, or replay failures.

---

### Task 1: Seal the current E2E checkpoint without another model call

**Files:**
- Create: `docs/evaluation/VinSOC_E2E_R2_Closeout_Status_2026-10-12.md`
- Create: `results/evaluation_v1/text2sql_integration_v1/closeout_20261012/checkpoint_receipt.json`
- Test: `tests/test_query_release_receipts.py`

**Interfaces:**
- Consumes: the committed outcome audits for executions `full-e2e-5` and `full-e2e-6`, their manifests, commit/tag identities, and current release receipt.
- Produces: one machine-readable offline checkpoint that records each execution separately, cumulative cost `$0.0270214`, latest implementation SHA, exact-SHA CI, and all still-pending deliverables.

- [ ] **Step 1: Write a failing receipt test.** Add `test_closeout_checkpoint_preserves_failed_demo_status_and_costs` asserting that both execution IDs are present, both are `technical_incomplete`, cumulative cost equals the deduplicated committed ledger, official eligibility is false, and calibration/evaluation/pipeline counts remain `0/48`, `0/192`, and `0/32`.
- [ ] **Step 2: Run the focused test and verify RED.** Run `python -m pytest tests/test_query_release_receipts.py -k closeout_checkpoint -q`. Expected: failure because the checkpoint receipt does not exist.
- [ ] **Step 3: Build the checkpoint only from committed artifacts.** Do not invoke the query runner, OpenAI SDK, database worker, or renderer. Reject missing manifests, duplicate execution IDs, mismatched artifact hashes, non-monotonic cumulative cost, and a clean/success claim for either failed execution.
- [ ] **Step 4: Write the status document from the verified checkpoint.** State that CI at `1b002cd` is green, but there is no successful post-fix demo and no official R2 result.
- [ ] **Step 5: Verify GREEN and preservation.** Run the focused test, `python -m pytest tests/test_query_release_receipts.py -q`, historical artifact hash checks, and `git diff --check`. Expected: no SDK client, attempted requests, responses, or new model cost.
- [ ] **Step 6: Commit and push.** Commit `docs(query): seal E2E and R2 closeout checkpoint`, push `HEAD:master`, and require exact-SHA CI success.

### Task 2: Gate any future single-case demo as a new execution

**Files:**
- Modify: `scripts/run_query_demo_cloud.py`
- Modify: `.github/workflows/query-demo-once.yml`
- Modify: `tests/test_query_cloud.py`
- Modify: `tests/test_query_journal_persistence.py`

**Interfaces:**
- Consumes: exact clean `master`, exact-SHA green CI, current implementation/data/schema/prompt identities, authoritative query-demo ledger, explicit new execution ID, and a scope-specific authorization receipt.
- Produces: `validate_query_demo_run_gate(...) -> receipt` that fails before provider creation or a new append-only preflight receipt.

- [ ] **Step 1: Write failing tests for all blocked states.** Cover reused execution ID, authorization for another scope, stale/wrong implementation SHA, non-green CI, ledger mismatch, unknown prior cost, missing current pricing/account evidence, dirty protected files, and budget below the conservative single-demo ceiling.
- [ ] **Step 2: Run the focused tests and verify RED.** Run `python -m pytest tests/test_query_cloud.py tests/test_query_journal_persistence.py -k "authorization or execution_id or provider or budget" -q`. Expected: failures from the missing/insufficient run gate, with provider/client counters still zero.
- [ ] **Step 3: Implement the fail-closed gate.** Validate every gate and persist preflight before importing/constructing the provider. Require a new execution ID; do not infer authorization from `$2.9729786` shown as remaining in run 6.
- [ ] **Step 4: Verify GREEN and regressions.** Run both focused files, the shared Text-to-SQL service tests, full offline tests, and `git diff --check`. Confirm every invalid case reports `attempted=0`, `received=0`, `client_created=false`, and `$0` new cost.
- [ ] **Step 5: Commit and push.** Commit `fix(query): gate each new demo execution`, push `HEAD:master`, and require exact-SHA CI success.

### Task 3: Run at most one newly authorized demo and retain the real outcome

**Files:**
- Create conditionally: `results/evaluation_v1/text2sql_integration_v1/<new_execution_id>/`
- Do not modify source, prompt, schema, scorer, or earlier result directories during this task.

**Interfaces:**
- Consumes: Task 2 exact-SHA CI, a fresh explicit authorization naming `single_fixed_query_demo_not_calibration_or_evaluation`, hard USD limit, execution ID, and authoritative remaining balance.
- Produces: one preflight plus either one complete native run artifact set or one immutable partial/failed artifact set.

- [ ] **Step 1: Obtain the missing authority.** The owner must name the new execution ID, model scope, maximum requests, hard USD limit, authorization reference, and authoritative prior cost. Without it, record `BLOCKED_NO_SCOPE_AUTHORIZATION` and stop with zero calls.
- [ ] **Step 2: Run preflight only.** Require exact SHA/CI, clean protected tree, production identities, current pricing/account evidence, reconciled ledger, valid snapshot/worker, and a reservation inside the named limit. Expected: zero calls and no provider creation.
- [ ] **Step 3: Execute exactly once only after preflight PASS.** Keep the existing request/turn/token caps, zero retries, no fallback, and no cap increase. Persist attempt, response, usage, and cost before parsing.
- [ ] **Step 4: Independently validate the artifact.** Require the original question, native routing call, generated SQL, safety decision, real DB result, evidence lineage, assessment, exact usage/cost, and independent query replay. A semantic mismatch or invalid assessment remains `technical_incomplete`.
- [ ] **Step 5: Stop after the terminal outcome.** Do not run a rescue attempt. Commit only public-safe artifacts with their real result and exact implementation SHA; verify preservation and exact-SHA CI.

### Task 4: Complete human review and the offline E2E handoff only for a technically valid run

**Files:**
- Create conditionally: `results/evaluation_v1/text2sql_integration_v1/<new_execution_id>/human_review_receipt.json`
- Create conditionally: `results/evaluation_v1/text2sql_integration_v1/<new_execution_id>/report.html`
- Modify: `docs/evaluation/VinSOC_E2E_R2_Closeout_Status_2026-10-12.md`
- Test: `tests/test_query_cli.py`, `tests/test_query_report.py`

**Interfaces:**
- Consumes: one technically valid immutable Task 3 receipt.
- Produces: an independently entered human decision linked by receipt hash and a self-contained offline report; rendering/review performs zero model calls.

- [ ] **Step 1: Add RED tests for review eligibility and linkage.** Reject technical-incomplete input, missing reviewer identity/decision/rationale/UTC, wrong input hash, overwritten technical receipt, and HTML fields that differ from JSON.
- [ ] **Step 2: Implement only missing validation/renderer behavior and verify GREEN.** Do not synthesize assessment text or a reviewer decision.
- [ ] **Step 3: Request the real human decision.** Approved, rejected, and escalated are all valid review outcomes; only the named human enters the choice and rationale.
- [ ] **Step 4: Render and compare JSON to HTML offline.** Confirm no provider/client import or request, exact status/SQL/result/evidence/assessment/cost, and proper escaping.
- [ ] **Step 5: Publish the scoped conclusion.** Say “single fixed query E2E” only if technical validation and human review both exist. Do not call it a 32-case pipeline result or an R2 accuracy score.

### Task 5: Make a separate R2 budget and calibration decision

**Files:**
- Modify conditionally: `docs/evaluation/VinSOC_R6_Budget_Decision_2026-10-10.md` through a dated addendum, not by rewriting prior evidence.
- Create conditionally: `results/evaluation_v1/text2sql_integration_v1/<r2_release_id>/authorization_receipt.json`
- Existing test owners: `tests/test_query_release.py`, `tests/test_query_acceptance.py`

**Interfaces:**
- Consumes: canonical ledger reconciliation, current model availability/pricing, exact source/runtime identities, 48 planned calibration records, and a new authorization explicitly naming `calibration`.
- Produces: either a blocked decision with zero calls or a bounded calibration-only release. It does not authorize evaluation or pipeline.

- [ ] **Step 1: Refresh the budget evidence before approval.** Recompute complete-payload bounds and current pricing; preserve the conservative documented ceiling until a tighter bound is actually verified. The owner target of `$2–3` is not enough for the existing official full R2 conservative envelope and must not cause denominator reduction.
- [ ] **Step 2: Decide explicitly among full calibration authorization, a separately named non-official reduced pilot, or deferral.** A reduced pilot must use a new identity and cannot populate the official 48-record selection lock.
- [ ] **Step 3: Test the release gate RED→GREEN.** Missing/partial authorization, demo authorization, wrong SHA, stale price, unknown exposure, insufficient budget, or fewer than 48 planned records must fail before provider creation.
- [ ] **Step 4: If full calibration is authorized, run exactly 24 cases × E0/E3.** Retain every valid model failure and every real usage/cost record; no case retry or prompt change.
- [ ] **Step 5: Create the selection lock only from 48 authentic records.** Hash records and runtime identities; leave selection `pending` for any missing/invalid record. Commit/push evidence and require exact-SHA CI.

### Task 6: Execute official R2 evaluation and pipeline only after calibration selection is locked

**Files:**
- Create conditionally: new append-only release/result directories under `results/evaluation_v1/text2sql_integration_v1/`
- Modify conditionally: final result/status documents; never modify historical result directories.
- Existing test owners: `tests/test_query_acceptance.py`, `tests/test_query_report.py`, `tests/test_query_release_receipts.py`

**Interfaces:**
- Consumes: a valid 48-record selection lock plus two new scope-specific authorizations: evaluation and pipeline.
- Produces: 192 evaluation records for 96 fixed cases and 32 production-pipeline records, or explicit partial receipts with the planned denominator intact.

- [ ] **Step 1: Gate evaluation independently.** Require all 96 fixed IDs, both conditions, exact selection/runtime/data/scorer hashes, current account/pricing/ledger, exact-SHA CI, and an evaluation-specific budget. Pipeline authorization cannot satisfy this gate.
- [ ] **Step 2: Run the 96 × 2 evaluation once.** Preserve no-SQL, syntax, safety, execution, semantic, provider, and provenance outcomes without dropping cases. Report EX `/64`, `/32`, and `/96`, paired E0/E3 outcomes, module coverage, costs, and clustered uncertainty.
- [ ] **Step 3: Gate the 32-case pipeline independently.** Require the selected condition, all 32 IDs, production public API, assessment/replay/review contracts, and a pipeline-specific budget.
- [ ] **Step 4: Run the 32-case pipeline once.** Preserve fixed denominator and every technical/human outcome. Do not treat the four presentation cases as a new score or additional calls.
- [ ] **Step 5: Verify the final package.** Require artifact completeness and hashes, exact totals, provenance, cost reconciliation, JSON/HTML equality, human reviews where applicable, protected-history hashes, full offline suite, `git diff --check`, and exact-SHA CI.
- [ ] **Step 6: Publish only scoped conclusions.** Separate single-query demo status, R2 evaluation accuracy, and 32-case operational pipeline success. No claim of universal SQL generalization or end-to-end incident-investigation effectiveness.

## Planner Self-Review

- Spec coverage: the plan accounts for current failed demo evidence, exact-SHA CI, future demo authorization, technical validation, human review, R2 calibration selection, evaluation, pipeline, budget, and preservation.
- Separation: R1 is explicitly out of scope; demo, calibration, evaluation, and pipeline never share an implied authorization or denominator.
- Type consistency: execution IDs, authorization receipts, technical receipts, review receipts, and selection locks are produced before any consuming task.
- Review focus: each of the five listed failure classes has an explicit test or gate in Tasks 1–6.
- Proportion: implementation details stay in existing specs; this plan decides sequencing, boundaries, evidence, and release gates without duplicating the service implementation.
