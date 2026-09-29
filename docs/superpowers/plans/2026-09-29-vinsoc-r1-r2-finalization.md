# VinSOC R1/R2 Finalization Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. Work directly on `master`; this plan does not authorize parallel agents or branches.

**Goal:** Close the fixed R1 and CTU-only R2 evaluations with one controlled GPT-5 Mini development series per condition, one frozen run per track, an evidence-backed E2E trace, and a final mentor-facing report.

**Architecture:** Keep benchmark, scorer, snapshot, and historical artifacts immutable. Add versioned GPT-5 Mini runners and append-only evidence/lock artifacts around the existing decision scorer and SQL scorer. Separate offline contract checks, paid inference, deterministic scoring, and post-run analysis; every paid suite has a same-SHA CI gate and a conservative cost gate before client creation.

**Tech Stack:** Python 3.11, OpenAI Chat Completions SDK, DuckDB, pytest, GitHub Actions, JSON locks and reports.

**Spec:** `docs/superpowers/specs/2026-09-28-vinsoc-r1-r2-finalization-design.md` (sections 3–14). Gate 4's E2E demonstration is an additional user requirement and belongs after both frozen metrics exist.

## Global Constraints

- Starting `master` and `origin/master` SHA: `38f3c444abf25caad8266804dee6c84fc2be4eba`; CI run `36515239701` passed on that SHA. Record the SHA again before every paid suite; require CI success for that exact SHA.
- Preserve all pre-existing untracked files, `.env`, and historical artifacts. Never use `git clean`, broad `git add .`, or overwrite an evidence path. Stage named files only.
- R1 dev: exactly 24 `r1_a1_dev_v2` cases; split SHA-256 `d8e68968a390a09d502a3da01319611f546a6d0189a30e0fe0c316550d0aa259`; scorer SHA-256 `271aa8ba8b65548f1d17648945ac62cc18b2370fa85c4aa210c155c9154b9149`; historical GPT-4.1 Mini baseline 22/24.
- R2 dev: exactly 8 `ctu_network_public_dev_v1` cases from S5/S7; logical snapshot SHA-256 `42c8e0a62441295cc5d95329a65dc22409c37de5b26a1e37dd56fbf0164a758c`; split and builder/scorer hashes must equal `evaluation/ctu_network_public/VERSION.lock`.
- GPT-5 Mini contract: OpenAI standard endpoint, `gpt-5-mini-2025-08-07`, reasoning effort `low`, absent `temperature`, max completion tokens `1000`, SDK retries `0`, no fallback or automatic case retry. Stop on actual-model mismatch.
- R2 E0 eight-case preflight ceiling must be less than USD 0.10. Every other suite needs an explicit conservative ceiling before any API call. Keep a cumulative ledger and stop before exceeding USD 3.00 of remaining finalization API spend, including demo calls.
- Paid evidence runs are manual-only on a clean Actions checkout of `master`; source/split/scorer/config/CI hashes and actual usage, cost, latency, generated SQL or native tool calls, case scores, and failures must be captured even for a partial paid attempt.
- Do not edit benchmark questions, gold, result comparators, scorer semantics, or tool gold to improve a score. Frozen outputs never inform prompt, tool, or architecture changes. R2's final claim is CTU-only network Text-to-SQL.

## Review Decisions Before Execution

1. **Spec review status:** the spec says “Pending written-spec review before implementation planning.” Review this plan together with the spec and record acceptance/corrections before code or paid runs. The user's request authorizes drafting the plan now.
2. **Budget interpretation:** use USD 3.00 as a hard ceiling for API spend from this finalization, including the E2E live demo; historical spend is reported separately. Each suite also has a lower local ceiling derived from its serialized worst-case requests. If that ceiling does not fit the remaining ledger, stop and request a budget decision, with no quiet cap/model change.
3. **E0 reuse:** reuse only a GPT-5 Mini E0 artifact whose request payload, prompt, schema context, split, snapshot, scorer, model identity, and cap hashes exactly match the final E0 condition. The existing GPT-4.1 Mini CTU run and public-pilot DualSQL v4 runs cannot qualify.
4. **R1 improvement trigger:** allow one generic change only when the GPT-5 Mini failures demonstrate a recurring class across cases. Otherwise mark the controlled-improvement column `N/A` and lock the stronger of the two dev configurations by the spec's tie-break order.
5. **Frozen size and source:** author eight R2 frozen cases if verified S1/S4 data supports the full semantic matrix; six or seven is valid only when the matrix remains covered and the reason is recorded before lock. A failed S1/S4 checksum or provenance check is a blocker, never a reason to substitute another source.
6. **Demo evidence class:** the R1 demo must let the model choose among only production tools backed by the verified snapshot and use its validated arguments in the production skill; it must cite rechecked evidence IDs in its own assessment. A separate R2 question must show model SQL, validator verdict, DuckDB rows, and source provenance. Label any older replay as replay; neither demo score enters benchmark accuracy.

## Review Focus

- Charged response followed by malformed native tool arguments: persist response identity, usage, raw safe call payload, and parse failure before stopping or scoring the case.
- A runner called outside Actions or on a different SHA: fail before provider creation and retain a credential-free preflight artifact.
- A model emits multiple valid DB calls in one turn: execute each within the total call bound and preserve ordered controller-owned provenance.
- A question literal absent from DB-tool outputs: allow it as question evidence while rejecting a claimed DB-grounded value without matching controller trace.
- Frozen source content or case directory changes after lock: hash check fails before any model call.

---

### Task 1: Run the single R2 GPT-5 Mini E0 dev suite

**Files:** modify `evaluation/ctu_network_public/run_model.py` and `.github/workflows/ctu-network-public-r2.yml` only for missing evidence/gate behavior; verify `evaluation/ctu_network_public/{contract.py,VERSION.lock,MODEL_CONFIG_GPT5MINI.lock}`; create an immutable run directory under `results/evaluation_v1/ctu_network_public/gpt5_e0/<run-id>/` and a credential-free full/partial report. Test: `tests/test_ctu_network_runner.py`.

**Interfaces:** `contract.validate(snapshot, LOCK)` verifies the existing split/snapshot; `run_model.run(snapshot_path, output, preflight_only=...)` produces one E0 report with exact request payloads and per-case SQL/score/usage. Later tasks consume its report SHA-256.

- [ ] Verify current `master` SHA, clean tracked checkout, dev lock hashes, official S5/S7 source SHA-256, and snapshot logical hash; inspect prior run registry so a valid GPT-5 Mini E0 is never duplicated.
- [ ] Write failing focused tests for append-only output, run ID, prompt/config hashes, SQL and latency per response, charged partial response, exact Actions SHA, and preflight rejection before client creation; make the minimum runner/workflow changes without altering its prompt, schema context, scorer, or eight cases.
- [ ] Commit the named hardening files on `master`, obtain CI success on that exact SHA, then run offline preflight; confirm eight serialized requests, the exact model contract, no `temperature`, zero retries, and ceiling `< $0.10`.
- [ ] Dispatch exactly one manual Actions E0 suite on the proven SHA; inspect run log/artifact for actual model on each response, eight distinct case IDs, all SQL, syntax/execution/accuracy, usage/cost/latency, and any partial failure. Never retry a wrong case.
- [ ] Import the original Actions JSON and its SHA-256 under a new append-only path; record run URL and exact Git SHA. Do not replace the historical GPT-4.1 Mini artifact.

### Task 2: Add and run the single R1 GPT-5 Mini model-only dev suite

**Files:** create `evaluation/tool_calling/gpt5_dev_runner.py` and `.github/workflows/r1-gpt5-dev-once.yml`; modify `agent/provider.py` only as needed to omit temperature for GPT-5 Mini and preserve charged-response telemetry. Test: `tests/test_tool_calling_decision_runner.py` plus a new focused `tests/test_r1_gpt5_runner.py`. Output: `results/evaluation_v1/r1/gpt5_model_only/<run-id>/`.

**Interfaces:** retain `DecisionRunner` and production `get_tool_schemas()` semantics; new runner returns the existing R1 scorer's per-case result plus native predicted calls and provider metadata.

- [ ] Write failing tests for absent temperature, exact 24-case locked split/scorer, same prompt/tool schema hash as the baseline, response/model/usage validation, append-only output, and a charged malformed-call response.
- [ ] Implement only the GPT-5 request/telemetry adapter and bounded suite wrapper; keep the scorer, matcher, gold, and one-decision-turn policy unchanged. Run focused tests and the full CI command.
- [ ] Commit named code/workflow files on `master`; wait for CI success on the new exact SHA. Run a 24-request cost preflight with an explicit suite ceiling and cumulative USD 3.00 ledger check before constructing the client.
- [ ] Dispatch one manual Actions suite; preserve full/partial immutable JSON with predicted native tool calls, matches, error flags, usage, cost, latency, prompt/schema/config hashes, and Actions URL. No case retry for an incorrect decision.

### Task 3: Analyze R1 and R2 development errors

**Files:** create `docs/evaluation/r1_gpt5_dev_error_analysis.md` and `docs/evaluation/r2_gpt5_e0_error_analysis.md`; consume Tasks 1–2 artifacts without changing them.

**Interfaces:** one primary R1 cause from section 5.4 of the spec per failed case; one primary R2 semantic cause from section 6.4 per incorrect case. Preserve deterministic scorer labels separately.

- [ ] Build a per-case matrix with prediction/SQL, gold comparison, category, error cause, model/provider errors, calls, usage, cost, and latency; explicitly revisit R1 `case_002` and `case_015`.
- [ ] Independently check cause assignments against stored calls/SQL/results and cite artifact paths plus hashes; record whether a recurring R1 cause supports one generic improvement.
- [ ] Verify totals reconcile to the scorer outputs and commit analysis only after the evidence has been checked.

### Task 4: Lock R1 frozen compatibility offline

**Files:** create `evaluation/tool_calling/benchmarks/frozen/COMPATIBILITY.lock` and `tests/test_r1_frozen_compatibility.py`; read the existing eight `frozen_*.json` without editing them.

**Interfaces:** offline checker parses cases, validates referenced production tool names and scorer loading, and emits case-directory/scorer/schema SHA-256; it never creates an OpenAI client.

- [ ] Write and run failing tests for missing tool, malformed case, duplicate ID, and no-provider path; implement checker, run it on all eight cases, and commit the lock.
- [ ] Confirm no frozen model output exists for this version; record the compatibility result without inspecting frozen answers for prompt tuning.

### Task 5: Build and lock source-separated R2 frozen offline

**Files:** create `evaluation/ctu_network_frozen/{dataset_manifest.json,VERSION.lock,contract.py,frozen/*.json}`, `scripts/build_ctu_network_frozen_snapshot.py`, and `tests/test_ctu_network_frozen.py`; reuse the existing CTU normalization and SQL scorer without changing dev inputs.

**Interfaces:** frozen `contract.validate(snapshot, lock)` verifies official S1/S4 URLs/source hashes, normalized row counts, schema, logical snapshot hash, 6–8 case hashes, gold-result hashes, scorer/builder hashes, and comparator contract.

- [ ] Obtain official CTU S1/S4 bytes and receipts; verify source URLs and SHA-256. If either fails, stop here and report the blocker without substitution.
- [ ] Build the independent snapshot twice and prove identical logical hash, source-session separation from S5/S7, unique source-row IDs, provenance rows, and deterministic normalized counts.
- [ ] Author eight frozen questions/gold offline to cover all section 7.2 semantics; validate gold and counterexamples in DuckDB without any model output. If only six or seven satisfy coverage, document that choice before lock.
- [ ] Add tests for source/hash mismatch, changed case file, gold/comparator mismatch, and no-provider execution; commit the complete frozen lock before any frozen model call.

### Task 6: Stabilize only generic DualSQL framework defects

**Files:** create a versioned CTU GPT-5 series under `evaluation/dualsql_lite_ctu_gpt5/` (runner, agents, tools, contract, prompts); keep `evaluation/dualsql_lite/` v1–v4 and its `SELECTED_CONFIG.lock` intact. Tests: `tests/test_dualsql_ctu_gpt5.py` and existing DualSQL safety tests.

**Interfaces:** `run_case(case, condition, snapshot, client, gate) -> case_result` accepts E1/E2/E3; `value_search()` returns bounded snapshot-derived values and trace IDs; final SQL reaches the unchanged `evaluate_sql_case()` only after model submission.

- [ ] Write failing tests for the five Review Focus failure modes and section 6.6: question literals, controller-owned grounded values, multiple calls in one turn within hard limits, typed schema, real CTU values for `source_dataset`/`label`/`protocol`, gold isolation, and read-only bounded tools.
- [ ] Implement the minimum general fixes in the new versioned series; no case-ID/literal alias rules and no benchmark/gold/scorer edits. Preserve a hard five-turn/five-tool-call limit per role and no retry after final SQL.
- [ ] Verify E0 request/prompt/schema/scorer identity against Task 1; if any identity differs, stop and resolve the controlled comparison before paying for E1–E3. Run focused tests and CI on the exact code SHA.

### Task 7: Run E1, E2, and E3 on the same CTU dev contract

**Files:** create `.github/workflows/r2-dualsql-ctu-gpt5.yml`; append `results/evaluation_v1/ctu_network_public/dualsql_lite_ctu_gpt5_v1/<run-id>/{E1,E2,E3}.json` and partial files.

**Interfaces:** each condition uses the Task 1 E0 backbone and Task 6 fixed framework; common benchmark/snapshot/scorer/model hashes make all four conditions comparable.

- [ ] Write/run offline tests for per-suite conservative turn/tool-context cost bounds, cumulative USD 3.00 gate, exact Actions SHA/CI/model identity, zero retry, and append-only partial evidence.
- [ ] Commit workflow and versioned runner; obtain same-SHA CI success; preflight E1, then dispatch exactly one E1 suite and save its full/partial artifact.
- [ ] Repeat the same gate for E2 and E3 separately, once each, without changing framework/prompt/tool contracts between conditions. Stop on identity/cost/source failure; keep wrong SQL as scored evidence.
- [ ] Reconcile per-case SQL, tool trajectory, syntax/execution/accuracy, semantic errors, model/DB call counts, usage, cost, and latency against provider metadata.

### Task 8: Select and commit the R2 winner lock

**Files:** create `evaluation/dualsql_lite_ctu_gpt5/SELECTED_CONFIG.lock`, `docs/evaluation/r2_dualsql_ctu_gpt5_dev.md`, and a focused selection test.

**Interfaces:** `build_selection(E0, E1, E2, E3)` rejects non-comparable or partial reports and chooses by Execution Accuracy, cost, model calls, latency, then E0/E1/E2/E3 simplicity.

- [ ] Test all tie-break levels and hash mismatch rejection; calculate per-case/category errors, cost, calls, and latency from immutable reports.
- [ ] Commit winner config hash and all four artifact hashes without consulting frozen outputs; record the exact deployable prompt/tool/catalog identity.

### Task 9: Use at most one generic R1 improvement, if justified

**Files:** if justified, create a versioned R1 prompt/schema config and one manual workflow plus focused tests; otherwise create `docs/evaluation/r1_selection_rationale.md` with `improvement=N/A`.

**Interfaces:** one declared change factor targets the recurring error class found in Task 3; fixed 24 cases, tool gold, scorer, cap, and retry policy remain unchanged.

- [ ] Decide from Task 3 evidence whether a recurring cause exists; record the single proposed factor before coding or running.
- [ ] If justified, test the changed prompt/schema contract, preflight cost and same-SHA CI, then run exactly one improved 24-case dev suite and preserve its immutable artifact. Never add case-specific wording or a second tuning round.
- [ ] If unjustified, make no paid call and select between historical 22/24 and GPT-5 Mini model-only using the spec's ordered R1 metrics.

### Task 10: Commit the final R1 winner lock

**Files:** create `evaluation/tool_calling/SELECTED_CONFIG_FINAL.lock` and update `docs/evaluation/r1_selection_rationale.md`; add a focused lock test.

**Interfaces:** lock records the winning run/config hash, prompt and production schema hashes, split/scorer hashes, metric tie-break evidence, and frozen compatibility hash.

- [ ] Verify Single-Turn Case Success, Critical Argument Accuracy, Exact-Call F1, Forbidden-Tool Rate, calculated cost, latency, and simplicity in that order; reject partial/ineligible reports.
- [ ] Commit the R1 winner and confirm clean exact-SHA CI before frozen execution.

### Task 11: Execute R1 frozen exactly once

**Files:** create a manual frozen workflow/runner and append one immutable `results/evaluation_v1/r1/frozen/<run-id>/report.json` plus partial evidence.

**Interfaces:** read Task 10 winner lock and Task 4 compatibility lock; use the existing R1 scorer without gold/prompt/schema changes.

- [ ] Offline verify all lock hashes, no prior frozen run for this version, eight cases, same-SHA CI, actual model contract, cost ceiling, zero retries, and cumulative budget before client creation.
- [ ] Dispatch once; preserve native calls, matches, errors, provider usage/cost/latency, and run URL. Treat result only as frozen evidence and make no further R1 changes.

### Task 12: Execute R2 frozen exactly once

**Files:** create a manual frozen workflow/runner and append one immutable `results/evaluation_v1/ctu_network_public/frozen/<run-id>/report.json` plus partial evidence.

**Interfaces:** read Task 8 selected config and Task 5 S1/S4 frozen lock; use the locked SQL validator/scorer and no dev-case data.

- [ ] Offline verify official source bytes and all lock hashes, no prior frozen run for this version, 6–8 cases, same-SHA CI, actual model, preflight cost, zero retries, and cumulative budget.
- [ ] Dispatch once; preserve SQL, validator verdict, DuckDB result score, trajectory, provenance, per-case usage/cost/latency, and run URL. Make no changes based on frozen outcomes.

### Task 13: Freeze evidence, demonstrate E2E, and write the final evaluation report

**Files:** create `docs/evaluation/vinsoc_r1_r2_final_2026-09-29.md`, `docs/evaluation/e2e_ctu_trace.md`, and append-only demo JSON under `results/evaluation_v1/ctu_network_public/demo/<run-id>/`; adapt `scripts/demo_ctu_network_public_model_driven.py` and add a versioned R2 SQL trace runner only after both frozen metrics exist. Tests: focused demo tests.

**Interfaces:** verified CTU snapshot supplies one Botnet and one Normal scenario for R1; the model chooses allowed data-backed production tool calls, production skill returns evidence IDs/source-row pairs, and a separate R2 request passes model → SQL validator → DuckDB → result/provenance.

- [ ] Test tool allowance, absence of forced tool choice, model-chosen argument execution, evidence-ID/source-row verification, cited assessment claims, and explicit live/replay labels. Run cost/model/CI preflight before any new live demo call.
- [ ] Execute exactly the two R1 situations and one R2 question; preserve full/partial trace with source hashes, live-call usage/cost, SQL and validator output. Mark any reused historical trace as replay artifact, and never count three demo examples as benchmark accuracy.
- [ ] Verify all historical, model-only, controlled-improvement, and frozen counts from immutable source JSON; write the required R1/R2 four-column table, per-case errors, category breakdown, cost/token/call/latency, snapshot and artifact hashes, limitations, and exact links.
- [ ] Reconcile every report claim to an artifact/hash and freeze the final evidence index; run full CI on the final evidence/report commit.

### Task 14: Reconcile README and evaluation documentation

**Files:** update `README.md`, `evaluation/tool_calling/README.md`, `evaluation/text_to_sql_benchmarks/README.md`, and any existing evaluation summary that would contradict the frozen evidence.

**Interfaces:** documentation links to the Task 13 evidence index; no metric is recomputed from prose.

- [ ] Update only claims that the final artifact table proves: CTU-only R2 scope, fixed-benchmark R1 baseline distinction, dev/frozen separation, and live/replay demo labels.
- [ ] Run documentation link/hash checks, focused tests, and full CI on the final named-file commit. Confirm `git status` contains only the original untouched untracked files and no tracked diff.

## Stop and Evidence Rules

At every task boundary, stop and report the exact blocker if model snapshot/actual identity, preflight or cumulative budget, same-SHA CI, frozen S1/S4 provenance, immutable artifact path, or frozen lock validation fails. Provider/infrastructure failure may permit a new immutable attempt only after diagnosis; it never permits rerunning an incorrect answer. Do not silently substitute another source, model, endpoint, or scorer.
