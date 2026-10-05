# VinSOC Finalization Fix

Authority: user implementation plan dated 2026-10-05. Agent A is the sole writer and pushes directly to master. This delivery is Task 0+1; later tasks require the requested review gate. No paid or frozen execution is authorized by this delivery.

Spec: `docs/superpowers/specs/2026-09-28-vinsoc-r1-r2-finalization-design.md`, superseded where the user's updated plan explicitly changes experiment order, consumed-holdout policy, demo scope or budget.

Initial checkout: `f841bc926b0f00fdd2ba9d1c87b521851fd2dc74`. Historical scored phase-2 suite: implementation `3f9d72ddc840d368b15b161881a94335c42eb03e`, EX 7/8, 44 responses, usage-derived $0.02085850. R1 winner remains GPT-4.1 mini 22/24; 11/24 gold cases adjudicated after original model output. S1/S4 consumed and protocol-ineligible.

During setup HEAD advanced to `9b98b51e8e3f7ae8593122521ee63fe6417c5b8a`, already matching origin/master; the only added file was `docs/VinSOC_Technical_Demo_Script.md`. It is preserved. Inventory base is that newer SHA; initial observation remains f841bc9. Inventory commit `e5e9f167385fea313f43a1c8265d0c10e5bf9611` contains only the two new setup receipts.

## Review focus

1. Pipeline OK with wrong SQL must score EX=false / RESULT_MISMATCH.
2. Missing snapshot or broken gold is infrastructure validation failure, not model failure or a zero/pass score.
3. Historical source bytes, locks and case questions/gold remain immutable; stale source locks are never rewritten.
4. New offline receipts describe current replay validation, never reconstruct historical run identities.
5. Offline audit cannot create providers, overwrite input or merge a separate case rerun into an older suite.

## Task 0: Sync and evidence inventory

- [x] Record separate status, branch, remote and initial SHA commands; fetch and compare master/origin/master. Initial f841bc9; inventory snapshot9b98b51; origin matches and ahead/behind=0/0. Missing master upstream metadata was set and verified.
- [x] Preserve unrelated tracked/staged/user/untracked data. Initial tracked/staged clean; new incoming demo document preserved. No merge/rebase/reset/clean/branch/PR.
- [x] Inventory 188 relevant tracked historical results, locks, manifests, cases and unchanged core scorer; no .env/raw data. Inventory-only e5e9f16 pushed.
- [x] Existing CTU validator passed on S5/S7 source bytes/snapshot: logical SHA `42c8e0a62441295cc5d95329a65dc22409c37de5b26a1e37dd56fbf0164a758c`, source row counts129831/114075, unchanged gold checksums and semantic traps.

## Task 1: Real scoring and headline correction

Interface: `score_prediction(case: SQLBenchmarkCase, record: dict, snapshot) -> dict` returns a copy with evaluator-supplied syntax/execution/accuracy/safety flags, separate pipeline and scoring error categories. `audit_saved_outputs(input_dir, cases_dir, snapshot_path, output_dir) -> dict` is offline-only.

- [x] RED8 tests: missing helper interfaces and actual predecessor client-creation bug. First wrapper run hit pytest importer fixture issue, corrected before RED proof. Three extra RED boundary tests catch prediction splicing, single-file CLI scoring and output path traversal. GREEN11 tests.
- [x] Evaluator/comparator reused; invalid/missing/truncated gold gives unscored validation failure, controller errors preserved. Correct/wrong/no-SQL/missing-snapshot fixtures verified.
- [x] case006 wrapper is offline-only --input/--snapshot/--output; missing input exits INPUT_MISSING, existing saved wrong SQL scores RESULT_MISMATCH with zero client creation.
- [x] Replay the original eight-case dev suite on verified S5/S7; EX remains 7/8; source hashes match before/after. [Dev receipt](../../../results/evaluation_v1/finalization_audit/20261005/dev_replay/report.json), replay implementation c348c01. Case006 pipeline TOOL_LIMIT / scoring NO_FINAL_SQL / EX=false.
- [x] Frozen saved predictions: eight unscored / SNAPSHOT_IDENTITY_UNVERIFIED, missing archived run identity. [Diagnostic receipt](../../../results/evaluation_v1/finalization_audit/20261005/consumed_frozen_unscored/report.json). Nonzero CLI outcome is the intended failed identity gate, not a scored zero. No snapshot/gold query, download, model call or consumption-lock edit.
- [x] Corrected final report, phase-2 results and README: scored full dev=7/8; no verified full suite after INTEGER fix; independent R2 holdout pending. Root PLAN.md also repeated the same unsupported headline and was added to the documentation allowlist. Historical JSON remains unchanged.
- [x] Verification/review and implementation commit/push: targeted12 pass after review fix, full774 pass; py_compile and git diff --check pass. Implementation c348c01eecef2b4cc989daf3f02af822176c7e8f; [exact-SHA CI](https://github.com/Whats-up-pro/VinSOC/actions/runs/37256566038): Python3.11 774 pass, Python3.12 774 pass. Reviewer independently checked188 unchanged hashes; incomplete frozen identity regression RED->GREEN; two CLI diagnostic minors deferred.
- [x] Evidence commit/push and exact-SHA CI:88bfb10e09904f376036b7a98fc551ca7994e67d, [CI37257505644](https://github.com/Whats-up-pro/VinSOC/actions/runs/37257505644),774 pass on each Python3.11/3.12. Checked only after the actual successful jobs/logs. [Completion receipt](../../../results/evaluation_v1/finalization_audit/20261005/completion_receipt.json) records this tested evidence SHA separately from implementation; the final documentation closure SHA and its CI are supplied in handoff after push.

Checkpoint details, commands, artifact digests and rulings: [verification receipt](../../../results/evaluation_v1/finalization_audit/20261005/verification_receipt.json). Initial f841bc9; preserved incoming demo/CLI commits9ff6ce3 and9093f93. New attempted/received model calls0/0, new inference cost $0, no workflow dispatch. Historical predictions and v3 locks remain unchanged, including the previously recorded source-lock mismatch. Frozen remains closed; stop for human review before Task2.

## Subsequent tasks (not executed before Task 0+1 review)

- [ ] Task 2: Generic typed grounding and semantic counterexamples; versioned prompts/schema, benchmark/core comparator unchanged.
- [ ] Task 3: Contract v4 and shared attempt/cost guards; no model calls.
- [ ] Task 4: One matched E0/E3 dev pair after explicit cost/account/identity/CI gates; no smoke/retry.
- [ ] Task 5: Production network E2E demo with two scenarios, structured factual checks and shared ledger; at most four live requests after gates.
- [ ] Task 6: Artifact-derived reproducible dev/report package, DEV_VERIFIED / HOLDOUT_PENDING.
- [ ] Task 7: Separate human holdout authorization/budget; S1/S4 may never be reused as independent holdout.

Each checkpoint records initial/implementation/final remote SHA, changed allowlist, actual commands/results, CI, immutable artifact digests, zero/actual calls, cost and blockers. Tests and replay are not new model results. Stop after Task 0+1 for its requested review gate.
