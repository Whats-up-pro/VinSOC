# VinSOC remediation phase 2 and benchmark governance

Authority: user directive dated 2026-10-01; execute directly on master.
Initial SHA: 28abd31bcc4349874f2e702fd7510a10578d38d9, equal to fetched origin/master; tracked working tree clean. Existing untracked files and .env are preserved.

## Binding design and rulings

- Separate versioned SQL safety and grounding modules; historical v1/remediation_v1 behavior and evidence remain unchanged. The locked core scorer/comparator and dev cases are unchanged. New runs identify the new safety adapter explicitly.
- Parse SQL with DuckDB's native SELECT AST serializer in an isolated in-memory connection with external access and extension installation/loading disabled. Accept one SELECT AST, inspect every relation/function, normalize with the native deserializer. No model SQL executes during validation. Unknown functions, external relations, table functions and non-SELECT statements fail closed.
- Controller owns source metadata, typed literal classification and catalog provenance. Numeric/time literals are constraints, not text catalog values. Probe lineage must map direct projected columns to verified catalog columns; expressions/aggregates are not ground values. Truncated matches are open samples; pattern predicates retain their operator and catalog witness.
- Prompts, gold, benchmark, core scorer, comparator, old locks and predictions are not changed. Replay is a new offline observation, never a replacement live result.
- The new live series permits one E3 dev suite, no smoke or retries. Old series consumption claims remain closed. Fixed model/low/1000/retries=0/default, bound < $0.75, exact-SHA dual Python CI, verified existing S5/S7 snapshot and fresh account/pricing gates before client creation.
- R1 winner is selected by the current dev rule, with the post-model adjudication caveat and differing request contracts. Compatibility is offline only; human authorization is still required for R1 frozen.
- S1/S4 consumed holdout stays closed. No new holdout construction is authorized by this directive; report R2 as dev only.

## Ordered gates

### Task 1: SQL safety policy and immutable offline replay

- [x] Regression tests RED for SELECT whitespace/newline/tab/semicolon; deny multi-statement, writes, system/external access.
- [x] Implement separate AST policy/snapshot adapter; tests GREEN.
- [x] Replay all eight saved remediation predictions; verify source hashes unchanged and label replay scope.
- [x] Targeted tests, full pytest, compile and diff checks; commit/push, exact-SHA Python 3.11/3.12 CI. Implementation `d6675dc54c1d2dae3cadc066f202b92deb95130a`, CI 36805715250 both jobs successful; 733 local tests pass.

### Task 2: Generalized controller provenance

- [x] Counter-example fixture tests RED; implement four semantic layers, controller-owned typed provenance and open pattern domains without case rules. 43 targeted tests pass; lock checksum `7d39379cce732044d8dd9a43b2d2b57b2b7da101ee4ace0a27af9286da49e7ef`.
- [x] Freeze new contract checksum; targeted/full verification, commit/push and exact-SHA CI. `a0b4340c226c5ec1bc2cab2840b551558ad7fd1f`, CI 36807482241 both jobs successful; 747 full tests pass.

### Task 3: One gated live R2 dev suite

- [x] Separate one-consumption entrypoint and offline tests for gates/telemetry, no synthetic official eligibility; lock contract before live. Targeted 58 pass; full implementation 762 pass; contract v3 locked after one fresh review/fix pass.
- [x] Implementation commit/push and exact-SHA CI; snapshot/account/pricing/budget preflight. `3f9d72ddc840d368b15b161881a94335c42eb03e`, CI 36808862542 both Python jobs successful. Fresh owner account confirmation, manifest/snapshot/contract checks and preflight PASS; suite ceiling $0.57024 below $0.75.
- [x] One eight-case E3 suite, preserve all failures and charged usage; no retries or tuning. `20261001_3f9d72d/suite`: EX/syntax/execution 7/8, TOOL_LIMIT on 006; 44 attempts/responses, 34 database tool calls, usage-derived $0.02085850. Zero workflow model dispatch; no smoke, no rerun.

### Task 4: R1 winner and frozen governance

- [x] Verify immutable R1 dev reports and selection rule; create winner_lock.json with source hashes, caveats and offline compatibility evidence. GPT-4.1 mini 22/24 selected over GPT-5 mini 19/24; captured prompt/schema/24-case split/scorer identities verified. `python -m evaluation.tool_calling.frozen_compatibility` passed for eight cases with zero model calls. Disclose 11/24 gold adjudicated after model output; no new R1 inference/tuning.
- [x] Verify consumed S1/S4 lock; record no eligible R2 holdout and keep both frozen tracks closed. `consumed=true`, `protocol_eligible=false`; R1 winner lock has `frozen_authorized=false`. No frozen inference or replacement data construction.

### Task 5: Evidence handoff

- [x] Artifact-derived identity/error/usage/cost tables; independent historical contexts, no continuous improvement claims. New append-only receipts in `results/evaluation_v1/phase2_handoff/20261001/`; source artifacts and all 185 protected hashes verified unchanged, response IDs unique and cached-aware cost recomputed.
- [ ] Verify all original hashes unchanged, review, commit/push and final exact-SHA CI; STOP FOR HUMAN REVIEW.

## Verification record

Only observed passing commands may mark a checkbox. Local execution ledger and command logs live under `.superpowers/sdd/2026-10-01-vinsoc-remediation-phase2/` and are retained.
