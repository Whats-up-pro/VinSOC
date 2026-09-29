# VinSOC R1/R2 Finalization Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. Work directly on `master`; this plan does not authorize parallel agents or branches.

**Goal:** Close the fixed R1 and CTU-only R2 evaluations with one controlled GPT-5 Mini development series per condition, one frozen run per track, and a final mentor-facing report. A separate E2E demonstration follows project finalization.

**Architecture:** Keep benchmark, scorer, snapshot, and historical artifacts immutable. Add versioned GPT-5 Mini runners and append-only evidence/lock artifacts around the existing decision scorer and SQL scorer. Separate offline contract checks, paid inference, deterministic scoring, and post-run analysis; every paid suite has a same-SHA CI gate and a conservative cost gate before client creation.

**Tech Stack:** Python 3.11, OpenAI Chat Completions SDK, DuckDB, pytest, GitHub Actions, JSON locks and reports.

**Spec:** `docs/superpowers/specs/2026-09-28-vinsoc-r1-r2-finalization-design.md` (sections 3–14). The user also requests an E2E demonstration. It is a separate post-finalization phase after the spec's fourteen ordered tasks, final documentation, and final CI.

## Global Constraints

- Audited `master` SHA: `bba1cfe6597519a7b5ebb5d0a6da8e44c6af00e2`; CI run `36520923206` passed on that SHA. The paid E0 ran on `4fa777ed8a3fd450cef871d427df16270c8fa606` after CI `36520615263`; record the SHA again before every future paid suite and require CI success for that exact SHA.
- Preserve all pre-existing untracked files, `.env`, and historical artifacts. Never use `git clean`, broad `git add .`, or overwrite an evidence path. Stage named files only.
- R1 dev: exactly 24 `r1_a1_dev_v2` cases; split SHA-256 `d8e68968a390a09d502a3da01319611f546a6d0189a30e0fe0c316550d0aa259`; scorer SHA-256 `271aa8ba8b65548f1d17648945ac62cc18b2370fa85c4aa210c155c9154b9149`; historical GPT-4.1 Mini baseline 22/24.
- R2 dev: exactly 8 `ctu_network_public_dev_v1` cases from S5/S7; logical snapshot SHA-256 `42c8e0a62441295cc5d95329a65dc22409c37de5b26a1e37dd56fbf0164a758c`; split and builder/scorer hashes must equal `evaluation/ctu_network_public/VERSION.lock`.
- GPT-5 Mini contract: OpenAI standard endpoint, `gpt-5-mini-2025-08-07`, reasoning effort `low`, absent `temperature`, max completion tokens `1000`, SDK retries `0`, no fallback or automatic case retry. Stop on actual-model mismatch.
- R2 E0 eight-case preflight ceiling must be less than USD 0.10. Every other suite needs an explicit conservative ceiling before any API call. Keep a cumulative ledger across finalization and the later demo. The user's last stated available credit was about USD 2.00; do not treat USD 3.00 as funded or approved. Each future paid suite requires a verified usable balance covering its conservative ceiling and must stay within the user's confirmed spending limit. Do not purchase credit or raise limits.
- Paid evidence runs are manual-only on a clean Actions checkout of `master`; source/split/scorer/config/CI hashes and actual usage, cost, latency, generated SQL or native tool calls, case scores, and failures must be captured even for a partial paid attempt.
- Do not edit benchmark questions, gold, result comparators, scorer semantics, or tool gold to improve a score. Frozen outputs never inform prompt, tool, or architecture changes. R2's final claim is CTU-only network Text-to-SQL.

## Review Decisions Before Execution

1. **Spec review status:** the spec still says "Pending written-spec review before implementation planning." Record this discrepancy and obtain review of the written spec and this revised plan before the next new paid suite. The GPT-5 E0 run has already occurred; its immutable result is evaluated as evidence, not retroactively called an approved final series.
2. **Budget interpretation:** the plan's earlier USD 3.00 proposal was not a balance check. Use a per-suite conservative ceiling plus a cumulative ledger beginning with the observed GPT-5 E0 cost of USD 0.00384725. Verify available credit and the user's actual cap before the next paid call; if unknown or insufficient, stop without changing model, cap, or retry policy.
3. **E0 reuse:** the completed GPT-5 Mini run `36520685612` is the candidate E0. Reuse its original JSON only if all eight request payloads, system prompt, schema context, model/request contract, split, snapshot, scorer, and actual model match the final E0 condition. A byte-identical report file is unnecessary. The GPT-4.1 Mini CTU 0/8 and DualSQL public-dev v4 5/8 are different evidence classes.
4. **R1 improvement trigger:** allow one generic change only when the GPT-5 Mini failures demonstrate a recurring class across cases. Otherwise mark the controlled-improvement column `N/A` and lock the stronger of the two dev configurations by the spec's tie-break order.
5. **Frozen size and source:** author eight R2 frozen cases if verified S1/S4 data supports the full semantic matrix; six or seven is valid only when the matrix remains covered and the reason is recorded before lock. A failed S1/S4 checksum or provenance check is a blocker, never a reason to substitute another source.
6. **Demo evidence class:** schedule the new demo after Tasks 1-14 and final CI. R1 must let the model choose among only production tools backed by the verified snapshot, execute validated arguments, and cite rechecked evidence IDs. The separate R2 question records SQL, validator verdict, DuckDB rows, and provenance. Label live calls and replay; neither enters benchmark accuracy.

## Review Focus

- Charged response followed by malformed native tool arguments: persist validated response identity and usage before parsing; retain a bounded, sanitized call representation and parse-failure category, without raw provider exception, key, or secret.
- A runner called outside Actions or on a different SHA: fail before provider creation and retain a credential-free preflight artifact.
- A model emits multiple valid DB calls in one turn: execute each within the total call bound and preserve ordered controller-owned provenance.
- A question literal absent from DB-tool outputs: allow it as question evidence while rejecting a claimed DB-grounded value without matching controller trace.
- Frozen source content or case directory changes after lock: hash check fails before any model call.

---

### Task 1: Seal and analyze the completed R2 GPT-5 Mini E0 dev suite

**Files:** the original Actions JSON and receipt are already committed under `results/evaluation_v1/ctu_network_public/gpt5_e0/36520685612/`. Create `docs/evaluation/r2_gpt5_e0_run_review.md` for per-case diagnosis only; do not alter the eight cases, prompt, snapshot, scorer, or saved report.

**Interfaces:** `ctu-r2-result.json` from artifact `11013215781` is the candidate E0 input for Tasks 3, 6, and 8. The artifact ZIP digest is `sha256:4222b2d94d0df030842f1191bb4743c0f3497300c83d0467827b55e62cc0b0cd`; the original report SHA-256 is `33b35678171309c1a8958c1d9818499915986942e6936a03428df8fa0544bc15`.

- [x] CI `36520615263` passed on exact run SHA `4fa777ed8a3fd450cef871d427df16270c8fa606`; manual Actions run `36520685612` completed with eight attempted calls, eight responses, and eight valid usage records. The artifact was downloaded and its ZIP/report digests verified.
- [x] Original report has `run_status=complete`, `pilot_eligible=true`, Execution Accuracy `0/8`, Syntax Validity `8/8`, Execution Success `8/8`, Safety Rejection `0/8`; preflight ceiling `$0.02540325`, usage-derived cost `$0.00384725`, total usage `845` input and `1818` output tokens. All eight actual models match `gpt-5-mini-2025-08-07`; requests use `reasoning_effort=low`, omit `temperature`, cap at `1000`, and use zero SDK retries.
- [x] Commit `bba1cfe6597519a7b5ebb5d0a6da8e44c6af00e2` preserved the four original JSON files byte-for-byte with `receipt.json`; its CI `36520923206` passed. Both builds report 243906 rows and identical logical SHA `42c8e0a62441295cc5d95329a65dc22409c37de5b26a1e37dd56fbf0164a758c`. This is CTU `public_dev` evidence; `pilot_eligible` does not by itself mean final/holdout eligibility.
- [ ] Independently reconcile the committed receipt, report, run URL, lock hashes, and any final E0 condition before reuse. If an identity differs, label this run diagnostic and stop before E1-E3; never rerun E0 because of the 0/8 score.
- [ ] Diagnose the eight stored SQL queries offline against questions, gold, and snapshot. Cases 001-007 show wrong scenario/source or label grounding; 008 adds grouping/columns beyond the question. Assign one primary cause each in Task 3, without editing gold or scorer.


### Task 2: Add and run the single R1 GPT-5 Mini model-only dev suite

**Files:** create `evaluation/tool_calling/gpt5_dev_runner.py` and `.github/workflows/r1-gpt5-dev-once.yml`; modify `agent/provider.py` only as needed to omit temperature for GPT-5 Mini and preserve charged-response telemetry. Test: `tests/test_tool_calling_decision_runner.py` plus a new focused `tests/test_r1_gpt5_runner.py`. Output: `results/evaluation_v1/r1/gpt5_model_only/<run-id>/`.

**Interfaces:** retain `DecisionRunner` and production `get_tool_schemas()` semantics; new runner returns the existing R1 scorer's per-case result plus native predicted calls and provider metadata.

- [ ] Write failing tests for absent temperature and `reasoning_effort=low`, exact 24-case locked split/scorer, baseline prompt hash `21f87b197c1bf1206d4a36e111853bddf6ea623bab58a5da311ccbcb61d7780b` and production schema hash `aa214e730b1e3eb3ba03fdb08488dcfda4bc33b3c6d4c84700951f87e9c11ff0`, response/model/usage validation, append-only output, and a charged malformed-call response. The current `OpenAIProvider.generate()` adds `temperature` and parses tool JSON before recording usage; the GPT-5 adapter must fix both for this suite.
- [ ] Implement only the GPT-5 request/telemetry adapter and bounded suite wrapper; set SDK `max_retries=0` explicitly, validate actual model and usage before parsing tool arguments, record charged-response telemetry even when parsing fails, and use the pinned pricing snapshot. Keep the scorer, matcher, gold, and one-decision-turn policy unchanged. Run focused tests and the full CI command.
- [ ] Commit named code/workflow files on `master`; wait for CI success on the new exact SHA. Run a 24-request cost preflight with an explicit suite ceiling and verified available-credit/cumulative-ledger check before constructing the client.
- [ ] Dispatch one manual Actions suite; preserve full/partial immutable JSON with predicted native tool calls, matches, error flags, usage, cost, latency, prompt/schema/config hashes, and Actions URL. No case retry for an incorrect decision.

### Task 3: Analyze R1 and R2 development errors

**Files:** create `docs/evaluation/r1_gpt5_dev_error_analysis.md` and `docs/evaluation/r2_gpt5_e0_error_analysis.md`; consume Tasks 1–2 artifacts without changing them.

**Interfaces:** one primary R1 cause from section 5.4 of the spec per failed case; one primary R2 semantic cause from section 6.4 per incorrect case. Preserve deterministic scorer labels separately.

- [ ] Build a per-case matrix with prediction/SQL, gold comparison, category, error cause, model/provider errors, calls, usage, cost, and latency; explicitly revisit R1 `case_002` and `case_015`.
- [ ] Independently check cause assignments against stored calls/SQL/results and cite artifact paths plus hashes. For R2, show the actual wrong `source_dataset`/`label` values in cases 001-007 and the overbroad projection/grouping in 008, then assign one primary semantic cause per case without editing gold. Record whether a recurring R1 cause supports one generic improvement.
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

- [ ] Write/run offline tests for per-suite conservative turn/tool-context cost bounds, verified credit and cumulative ledger gate, exact Actions SHA/CI/model identity, zero retry, and append-only partial evidence.
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

### Task 13: Freeze evidence and write the final evaluation report

**Files:** create `docs/evaluation/vinsoc_r1_r2_final.md` and an append-only evidence index. Do not add demo code or new paid demo calls in this task.

**Interfaces:** reports for historical baseline, model-only dev, controlled improvement, and frozen are reconciled by artifact hashes. The result table is the input for Task 14 documentation.

- [ ] Recalculate every raw numerator/denominator, category, error class, token, cost, call, and latency claim from immutable source JSON; distinguish R1 22/24 on dev v2, historical CTU GPT-4.1 Mini 0/8, GPT-5 E0 0/8 on the same CTU split, and DualSQL public-dev v4 5/8 on a different split/snapshot.
- [ ] Write the four-column R1/R2 historical/model-only/controlled/frozen table, source-session and snapshot limitations, selected configuration, per-case errors, and exact artifact/run/hash references. Do not infer significance from eight cases or call a scorer replay a model gain.
- [ ] Freeze a machine-readable evidence index, check every link/hash, and commit the report with full CI on its exact SHA.

### Task 14: Reconcile README and evaluation documentation

**Files:** update `README.md`, `evaluation/tool_calling/README.md`, `evaluation/text_to_sql_benchmarks/README.md`, and any evaluation summary contradicting the final artifacts.

**Interfaces:** documentation links to the Task 13 evidence index; no metric is recomputed from prose.

- [ ] Update only claims proved by final artifacts: CTU-only R2 scope, fixed-benchmark R1 baseline distinction, dev/frozen separation, and exact source-session limitations.
- [ ] Run documentation link/hash checks, focused tests, and full CI on the final named-file commit. Confirm the only remaining untracked files are the original untouched files and there is no tracked diff.

### Task 15: Demonstrate product E2E after finalization

**Files:** only after Task 14 and its CI, create a versioned demo trace under `results/evaluation_v1/ctu_network_public/demo/<run-id>/` and `docs/evaluation/e2e_ctu_trace.md`; adapt `scripts/demo_ctu_network_public_model_driven.py` and add a narrow R2 question-to-SQL trace only where necessary. Keep the benchmark and its frozen locks untouched.

**Interfaces:** the verified CTU snapshot supplies one Botnet and one Normal R1 situation; a separate R2 question flows through model SQL, the existing SQL safety validator, read-only DuckDB, and provenance. The forced-tool historical demo is replay evidence only.

- [ ] First implement offline tests for allowed tools, model-chosen arguments, bounded source-backed tool execution, evidence-ID/source-row validation, cited assessment, SQL safety, and truthful live/replay flags. A forced `tool_choice` cannot prove dynamic selection.
- [ ] After focused/full CI and a fresh cost/credit gate, perform only the minimal declared live calls. Preserve full/partial JSON with run SHA, source hashes, actual model, usage, cost, trace, and failure categories.
- [ ] Present the two R1 situations and one R2 question as product traces. Keep demo outcomes out of R1/R2 benchmark numerators and explicitly state CTU-only coverage.

## Stop and Evidence Rules

At every task boundary, stop and report the exact blocker if model snapshot/actual identity, preflight or verified credit/cumulative budget, same-SHA CI, frozen S1/S4 provenance, immutable artifact path, or frozen lock validation fails. The completed E0 score of 0/8 is evaluation evidence and never authorizes another E0 run. Provider/infrastructure failure may permit a new immutable attempt only after diagnosis; it never permits rerunning an incorrect answer. Do not silently substitute another source, model, endpoint, or scorer.
