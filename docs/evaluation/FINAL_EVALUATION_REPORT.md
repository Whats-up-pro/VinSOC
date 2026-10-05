# VinSOC evaluation evidence status

Updated 2026-10-05. Status: **DEV_VERIFIED / HOLDOUT_PENDING**.

This correction supersedes the earlier COMPLETE / Perfect / 8-of-8 / proof-of-generalization headlines in this document. They exceeded the recorded evidence. Historical JSON, questions, gold SQL, comparators and consumption locks remain unchanged.

## Artifact-backed results

| Track / condition | Metric | Recorded cost USD | Evidence and limits |
|---|---|---:|---|
| R1 dev-v2 GPT-4.1 mini winner | 22/24 case success; exact-call F1 0.9508; no-tool 5/5 | 0.01013120 | [Winner lock](../../evaluation/tool_calling/winner_lock.json); decision-only, no tool execution |
| R1 dev-v2 GPT-5 mini model-only | 19/24; exact-call F1 0.9355; no-tool 4/5 | 0.01595000 | [Source report](../../results/evaluation_v1/r1/gpt5_model_only/36531679435/r1-gpt5-result.json); different model/request contract |
| R2 CTU E0, run 36520685612 | EX 0/8; syntax/execution 8/8 | 0.00384725 | [Immutable report](../../results/evaluation_v1/ctu_network_public/gpt5_e0/36520685612/ctu-r2-result.json) |
| R2 previous remediation E3 | EX 1/8; syntax 4/8; execution 3/8 | 0.01884615 suite only | [Original evidence](../../results/evaluation_v1/ctu_network_public/dualsql_v2_remediation_live/20260930_90acf451/suite/report.json) |
| R2 phase-2 E3, implementation 3f9d72d | **EX 7/8 (87.5%); syntax/execution 7/8** | **0.02085850** | [Original full suite](../../results/evaluation_v1/ctu_network_public/r2_phase2_live/20261001_3f9d72d/suite/report.json); 44 attempted/received API calls |
| Post-INTEGER-hint version | **No verified full-suite score** | Not established as a complete suite | Separate case006 output cannot replace a failed prediction in the older suite |
| R2 S1/S4 | **No independent, protocol-eligible holdout result** | Historical cost incomplete | [CONSUMED.lock](../../evaluation/ctu_network_frozen/CONSUMED.lock): consumed=true, protocol_eligible=false |

Conditions differ in prompts, tool/controller interaction and safety contracts. The earlier public-dev pilot used a different snapshot; it is not a matched control. The rows above are separate observations and do not establish a causal improvement sequence. DualSQL here is inference-inspired architecture, not a reproduced training or multi-agent reinforcement-learning result.

**R1 caveat:** 11/24 dev-v2 gold cases were adjudicated after seeing the original model output. This is development evidence, not an independent holdout. GPT-4.1 mini used temperature=0; GPT-5 mini omitted temperature and used reasoning_effort=low. No new tuning or dev run is needed to confirm these historical counts. R1 frozen compatibility passed offline; frozen inference still requires separate human authorization.

## Case006 and the scoring correction

The official phase-2 suite preserves case006 as **TOOL_LIMIT**: three linker turns, five executed tool calls, generator not invoked, final_sql=null, EX=false. Its charged responses are retained. Searching integer ports exhausted the tool cap, but a later separately generated SQL statement does not change that run's denominator or numerator.

The old `test_case006_integer_fix.py` printed execution_accurate from `error_category == 'OK'`. `run_case()` uses OK to mean the pipeline produced SQL; execution scoring occurs separately. The wrapper is now offline-only and delegates to `evaluation/r2_phase2/scoring.py`, which calls the unchanged `evaluate_sql_case()` and comparator through the versioned read-only snapshot policy.

Replay preserves both `pipeline_error_category` and `scoring_error_category`. Executable wrong SQL receives EX=false / RESULT_MISMATCH. Missing final SQL preserves TOOL_LIMIT and scores false. Missing snapshot or invalid gold has `scoring_status=unscored`, null score flags and failed validation; infrastructure errors are not model failures.

## Offline audit and reproduction

Task 0+1 uses zero new model calls and zero API inference spend. Tests use explicitly synthetic DuckDB fixtures. Replay is deterministic evaluation of archived predictions, not a new model run.

```powershell
python -m scripts.audit_r2_saved_outputs --input results/evaluation_v1/ctu_network_public/r2_phase2_live/20261001_3f9d72d/suite --cases-dir evaluation/ctu_network_public/dev --snapshot data/ctu_network_public/snapshots/ctu_dev.duckdb --output results/evaluation_v1/finalization_audit/20261005/dev_replay
```

Output must be a fresh directory. A rerun for reviewer reproduction needs another new output path; source files are never overwritten. Full-suite source report and per-case files must agree; separate predictions cannot be spliced into an archived report. A single saved file produces a single-prediction diagnostic, not a full suite.

The verified S5/S7 snapshot has 243,906 flows (S5=129,831; S7=114,075), logical SHA-256 `42c8e0a62441295cc5d95329a65dc22409c37de5b26a1e37dd56fbf0164a758c`. Its manifest, source bytes, gold checksums and unchanged scorer are checked with the existing CTU validator. Runtime prediction SQL is evaluated offline; production models are not offered raw SQL access.

The new S1/S4 prediction files under `r2_phase2_frozen_v1/` do not record the execution-scoring flags or a verified run snapshot/case identity. They receive an **unscored / SNAPSHOT_IDENTITY_UNVERIFIED** diagnostic receipt. No frozen snapshot is queried when that identity is missing, no data is downloaded, and CONSUMED.lock remains unchanged. Even a future offline replay would remain consumed-frozen diagnostic evidence, never an independent holdout score.

Initial inventory: [188 protected tracked files](../../results/evaluation_v1/finalization_audit/20261005/initial_inventory.json), raw checkout hashes, no .env/raw dataset files. Current replay receipts and exact implementation/evidence CI are linked after their actual verification in [the delivery plan](../superpowers/plans/2026-10-05-vinsoc-finalization-fix.md).

Task0+1 replay implementation: `c348c01eecef2b4cc989daf3f02af822176c7e8f`. [CI](https://github.com/Whats-up-pro/VinSOC/actions/runs/37256566038) passed774 tests on each Python3.11/3.12. The [dev replay](../../results/evaluation_v1/finalization_audit/20261005/dev_replay/report.json) confirms7/8; the [consumed-frozen receipt](../../results/evaluation_v1/finalization_audit/20261005/consumed_frozen_unscored/report.json) leaves all8 unscored. Source hashes match before/after. [Verification receipt](../../results/evaluation_v1/finalization_audit/20261005/verification_receipt.json) records commands, hashes, zero model calls/cost and deferred diagnostic limitations.

Evidence commit `88bfb10e09904f376036b7a98fc551ca7994e67d` also passed774 tests on each Python3.11/3.12 in [CI37257505644](https://github.com/Whats-up-pro/VinSOC/actions/runs/37257505644). [Completion receipt](../../results/evaluation_v1/finalization_audit/20261005/completion_receipt.json) closes Task0+1 only. **STOP FOR HUMAN REVIEW**; Tasks2+ and all new inference remain unexecuted.

## Remaining gates

The approved next tasks are generic typed/semantic counterexamples, contract v4 and common paid guards, a matched E0/E3 dev pair, a production network demo with checked factual observations, and an artifact-derived reporting package. They require the requested Task 0+1 review and their own checks before execution. Holdout is a separate human-authorized task and budget; S1/S4 cannot be relabeled as fresh holdout.

Token-derived costs are not billing invoices. Historical spend remains a lower bound where usage is missing. Demo traces, valid citation IDs and green CI do not supply benchmark accuracy or prove generalization. No final E2E success is claimed by this report.
