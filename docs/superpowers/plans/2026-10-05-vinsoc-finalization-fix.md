# VinSOC Finalization Fix

Authority: user implementation plan dated 2026-10-05. Agent A is the sole writer and pushes directly to master. Task0+1 completed; the user has now authorized Task2 offline. Tasks3+ require the next review gate. No paid or frozen execution is authorized by this delivery.

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

## Task2: Typed grounding and semantic counterexamples

Initial master: bb462f30b30f29d1bba6207b4a96b2ad579875a9. Fetch verified HEAD=origin/master, ahead/behind0/0; tracked/staged clean. User approved this bounded implementation after Task0+1 review. No model calls, lock v4 or paid experiment in this task.

- [x] Correct docs/VinSOC_Demo_Script.md and docs/VinSOC_Technical_Demo_Script.md: verified full dev7/8, post-INTEGER hint no full-suite score, S1/S4 consumed, no independent holdout or100%/generalization claim. Removed pipeline-OK-as-EX/live bypass snippet; use offline audit reference. Diff/claim search checked, no historical artifact edit.
- [x] Regression RED before code:14fail31pass, plus malformed typed args/Unicode offset4fail45deselected. Arbitrary INTEGER columns slot_317/bucket_829, top-k7/3; numeric/timestamp hints and catalog provenance separated. Unknown column/wrong argument type/missing provenance already fail closed where existing; typed submitted-values and bypassed args exposed missing checks.
- [x] Real-DuckDB evaluator counterexamples for source filter, prefix/contains, case and literal wildcards, DISTINCT, microsecond time bounds, Boolean precedence, top-k ties and ordered/unordered comparators. Wrong queries score RESULT_MISMATCH; hand-counted gold fixture results checked. Synthetic fixtures only, not model scores. Targeted91pass22.65s after fixes.
- [x] Phase2 contract v4 code only after observed failures: new prompts_v4.py/tool_schemas_v4.py consumed by runner; numeric/time entries rejected from grounded_values, verified typed_columns separate. No historical DualSQL edits or cap increase. Added safety_v4.py because native LIKE/ILIKE ESCAPE AST gets schema=main and ASCII JSON serialization corrupts Unicode; narrowly normalize parser-generated operators via UTF8 token/location and reuse archived tree/connect/result boundaries. Explicit qualified functions stay rejected. Old safety.py/scorer/policies/locks unchanged; no lock v4 created.
- [x] Targeted116 pass21.74s; full820 pass1612 warnings220.86s; py_compile9files and diff checks pass. One read-only review found Unicode semicolon offsets and Python casefold/ILIKE mismatch, both regression RED->GREEN in one fix pass. Native predicate witnesses now agree with DuckDB; archived safety.py unchanged. Removed remaining Generalizes claim. No Task2 deferred minors; 287 protected hashes and snapshot binary unchanged, model calls0/cost0.
- [x] Allowlisted implementation422ba0beeda0fa8f7dce2bfefc4296c151287695 committed/pushed to master. [CI37265105043](https://github.com/Whats-up-pro/VinSOC/actions/runs/37265105043) passed on Python3.11/3.12,820 tests each. [Completion receipt](../../../results/evaluation_v1/finalization_audit/20261005/task2/completion_receipt.json) binds implementation CI and immutable hashes. Closure commit CI supplied separately in handoff. STOP FOR HUMAN REVIEW before Task3; user separately authorized an offline CLI context=None fix after this checkpoint.

Review focus: schema type cannot certify a stored literal; numeric/timestamp grounded_values cannot cross as catalog witnesses; observed provenance must match controller memory. Explicit search mode/case/escaped wildcard must describe the returned witness/predicate. Wrong but executable SQL must score false on fixture, with headline locked-dev metric unaffected. No gold/example SQL, benchmark IDs or CTU-specific mapping in runtime prompts/logic; no cap increase. Historical locks/results and production schemas unchanged.

Initial inventory: [287 protected files](../../../results/evaluation_v1/finalization_audit/20261005/task2/initial_inventory.json). Concurrent external commit5ae01e2 adds docs/VinSOC_Final_Presentation_Script.md only; preserved and excluded from this two-document task. The third document was not reviewed or changed here. All287 historical hashes and S5/S7 binary bytes remain equal after push; [verification receipt](../../../results/evaluation_v1/finalization_audit/20261005/task2/verification_receipt.json) records actual RED/GREEN commands, review, source checksums and zero inference cost. Historical logical identity is preserved by unchanged binary bytes, not rebuilt or reassigned.

## Subsequent task gates

- [x] Task 2: Generic typed grounding and semantic counterexamples; versioned prompts/schema, benchmark/core comparator unchanged. Implementation and exact-SHA matrix CI verified above.
- [ ] Task 3: Contract v4 and shared attempt/cost guards; no model calls.
- [ ] Task 4: One matched E0/E3 dev pair after explicit cost/account/identity/CI gates; no smoke/retry.
- [ ] Task 5: Production network E2E demo with two scenarios, structured factual checks and shared ledger; at most four live requests after gates.
- [ ] Task 6: Artifact-derived reproducible dev/report package, DEV_VERIFIED / HOLDOUT_PENDING.
- [ ] Task 7: Separate human holdout authorization/budget; S1/S4 may never be reused as independent holdout.

Each checkpoint records initial/implementation/final remote SHA, changed allowlist, actual commands/results, CI, immutable artifact digests, zero/actual calls, cost and blockers. Tests and replay are not new model results. Current delivery stops after Task2 for human review; Task3+ remain pending.
