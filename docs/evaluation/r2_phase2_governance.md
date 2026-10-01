# R2 phase 2: SQL policy and benchmark governance

## Initial state and scope

Fetched origin/master: `28abd31bcc4349874f2e702fd7510a10578d38d9`; HEAD matched and tracked working tree was clean. Existing untracked files, `.env`, frozen consumption locks and historical artifacts are preserved. New policy: `r2_snapshot_select_ast_v2`, implemented separately in `evaluation/r2_phase2/safety.py`. The historical SQL adapter, benchmark/gold, snapshot builder, comparator and core scorer remain unchanged.

Validation parses one SELECT AST with DuckDB in an isolated connection, recursively checks relations/functions, and normalizes SQL. Every table function and unapproved scalar function is rejected. Native parsing failures, non-SELECT statements, multiple statements and external/system relations fail closed. Snapshot execution is read-only with external access and extension installation/loading disabled. This is a versioned policy change, so its observations do not replace historical scores.

## Offline prediction replay

[Immutable replay report](../../results/evaluation_v1/ctu_network_public/r2_phase2_policy_replay/20261001/report.json) uses the exact stored SQL from the previous remediation suite, not new predictions. Source file hashes before/after are identical. **Zero API/model calls; zero token cost.** Syntax 4/8, execution 4/8, EX 1/8, safety rejection 0/8.

| Case | Historical error | Replay outcome |
|---|---|---|
| ctu_sql_001 | RESULT_MISMATCH | Executes; result mismatch |
| ctu_sql_002 | RESULT_MISMATCH | Executes; result mismatch |
| ctu_sql_003 | TURN_LIMIT | No SQL; syntax invalid |
| ctu_sql_004 | OK | Executes; matches gold |
| ctu_sql_005 | TURN_LIMIT | No SQL; syntax invalid |
| ctu_sql_006 | INVALID_TOOL_PROVENANCE | No SQL; syntax invalid |
| ctu_sql_007 | INVALID_TOOL_PROVENANCE | No SQL; syntax invalid |
| ctu_sql_008 | SAFETY_REJECTION | Now executes; result mismatch |

The boundary change removes a false rejection, without changing the SQL or making it semantically correct. Replay is an offline policy diagnostic, not a live accuracy result or evidence of generalization.

## Distinct historical conditions

| Evidence | Scope | Result | Comparison limit |
|---|---|---|---|
| public-dev pilot | Earlier public snapshot/schema/evaluation contract | 5/8 | Not a direct control for CTU S5/S7 |
| CTU E0 run 36520685612 | Locked S5/S7, historical one-shot contract | EX 0/8 | Immutable negative finding; different generation contract |
| remediation live 20260930_90acf451 | S5/S7, remediation_v1 controller and historical safety adapter | EX 1/8 | Original evidence stays 1/8; not replaced by replay |
| phase-2 prediction replay | Same saved remediation predictions, new safety policy | EX 1/8 | Offline replay only; no new inference |

These are distinct experimental conditions, not a continuous improvement series. Some CTU snapshot/scorer hashes match where verified; prompt, tools, policy and inference contracts differ. Do not assert that every CTU evaluator or snapshot is different when artifacts show otherwise.

## Frozen governance

`evaluation/ctu_network_frozen/CONSUMED.lock` records `consumed=true`, `protocol_eligible=false`, incomplete historical cost/provenance. S1/S4 remain closed. The project currently has **no protocol-eligible R2 holdout result**. New independent holdout construction/locking and human authorization would be required to claim generalization; this task does not construct a replacement holdout.

## Generalized grounding contract

The new controller/tool namespace is `evaluation/r2_phase2/`, reusing the recovered `V2DatabaseTools` source-metadata adapter. Contract identity: `r2_generalized_controller_provenance_v2`; lock SHA-256: `7d39379cce732044d8dd9a43b2d2b57b2b7da101ee4ace0a27af9286da49e7ef`.

| Layer | Ownership and checks |
|---|---|
| Question literals | Analyst text: quoted strings, numeric constraints and timestamp constraints; no catalog lookup is required to establish numeric/time constants. This extraction is not a claim of complete natural-language intent understanding. |
| Source metadata | Controller maps manifest-backed source aliases to stored dataset IDs. A wrong selected source column still fails closed; metadata no longer requires a redundant model search. |
| Catalog values | Observed tool evidence is checked against the controller registry and typed catalog. SQL probe grants values only for direct, unique column projections; aggregate, computed literal, duplicate alias and uncertain relation lineage cannot mint provenance. |
| Grouping/domain predicates | Search returns an explicit case-insensitive contains predicate (`ILIKE`, escaped wildcards) and catalog witness. Truncated search remains an open sample; it cannot establish an exhaustive IN list. Complete low-cardinality domains are independently counted. |

No case-ID rules, question edits, gold edits, comparator changes or prompt tuning are present. Existing prompt instruction bytes are preserved; the new runtime schema context describes the controller contract and source metadata. Verified type/column lineage proves provenance, not analyst intent or final SQL correctness. TURN_LIMIT and wrong semantic SQL remain possible, valid negative findings; the controller does not fabricate a successful linker response.

Counterexamples use synthetic alpha/beta captures, arbitrary quantities, a mixed-case label family and duplicate projected aliases. Initial predecessor run: 8 failures (after moving pytest temp files into a writable directory); further counterexamples reproduced two failures for numeric lookup/duplicate aliases, then two for operator semantics/domain fallback. Final targeted command: `python -m pytest tests/test_r2_phase2_grounding.py tests/test_r2_phase2_safety.py -q --basetemp <fresh-workspace-temp> -o cache_dir=<workspace-cache>`: **43 passed**. Full exact-code verification and CI are recorded before this gate is closed.

Task 2 full suite on the final contract: `python -m pytest -q`: **747 passed, 1612 existing warnings, 201.86s**, exit 0. The earlier 745-pass run preceded the last two regression fixes and is not used as final verification. Compile, diff and 185 protected hash checks passed. Contract byte preservation is scoped to the new lock in `.gitattributes`.

### Pre-live fresh review and version 3

The fresh whole-branch reviewer confirmed a provenance defect for wildcard projection collisions and relation column aliases, where overlapping catalog values could mask a wrong column mapping. Both synthetic cases failed before the fix, then passed. Version 3 withholds probe lineage for wildcard projections or relation column aliases rather than guessing mappings; direct unique projections still work. The committed v2 lock remains unchanged at checksum `7d39379cce732044d8dd9a43b2d2b57b2b7da101ee4ace0a27af9286da49e7ef`; it was never used for paid inference.

Live contract: `r2_generalized_controller_provenance_v3`, [CONTRACT_v3.lock.json](../../evaluation/r2_phase2/CONTRACT_v3.lock.json), SHA-256 `a8d43578b892d93c41c723ff8841f24e0b02aa2861048b5c92661d01f46ff132`. Source hashes and lock bytes are checked before client creation. A cleanup exception is also retained as `CLIENT_CLEANUP_ERROR`, with the final partial report and charged response usage preserved. The reviewer called it Minor; it was upgraded to Important because the handoff contract requires final/partial cost reporting. One fix pass, no second review, no deferred findings.

Reviewer declined billing/account, real-provider availability, remote CI, full-suite validation, future evidence closure and independent historical rehashing. The parent verifies these gates: owner-confirmed credit (not independent Billing), provider/model guards fail closed, exact-SHA CI before inference, full tests before commit, and immutable inventories before/after. Future R1 lock and evidence closure remain work items, not completion claims.

Final pre-live implementation verification: **58 targeted tests pass, 762 full tests pass / 1612 existing warnings / 138.07s**, compile checks and `git diff --check` exit 0; 185 protected hashes unchanged. New suite bound $0.57024 (80 calls maximum), window cap $0.75, fixed 20KB serialized request limit plus 512 framing tokens per call. Account gate is fresh owner confirmation for the correct project; no independent Billing lookup or credit purchase. Exact-SHA CI is required before the new live entrypoint can create the SDK client.

## One phase-2 E3 dev live suite

Implementation SHA **`3f9d72ddc840d368b15b161881a94335c42eb03e`**, equal to origin/master and tracked clean before inference. [CI 36808862542](https://github.com/Whats-up-pro/VinSOC/actions/runs/36808862542) passed full tests on Python 3.11 and 3.12 before client creation. The preceding offline checkpoints also passed: [Task 1 CI](https://github.com/Whats-up-pro/VinSOC/actions/runs/36805715250), [Task 2 CI](https://github.com/Whats-up-pro/VinSOC/actions/runs/36807482241). No commit or execution-code edit occurred between implementation CI and the suite.

Commands actually run:

```powershell
python -m scripts.run_r2_phase2_dev_live --preflight-only --output results/evaluation_v1/ctu_network_public/r2_phase2_live/20261001_3f9d72d/suite
python -m scripts.run_r2_phase2_dev_live --output results/evaluation_v1/ctu_network_public/r2_phase2_live/20261001_3f9d72d/suite
```

Preflight PASS; live exited 0 and recorded `status=complete`, `official_eligible=true`, no infrastructure or identity errors. Exactly one suite, eight cases, **no smoke, case retry, suite retry or model workflow dispatch**. Model returned **`gpt-5-mini-2025-08-07`** on all 44 responses; request low/1000/retries=0/default, no temperature. Persisted claim prevents another run under `r2_phase2_live_e3_v1`.

[Live report](../../results/evaluation_v1/ctu_network_public/r2_phase2_live/20261001_3f9d72d/suite/report.json), [full journal](../../results/evaluation_v1/ctu_network_public/r2_phase2_live/20261001_3f9d72d/suite/partial.jsonl), [acceptance receipt](../../results/evaluation_v1/phase2_handoff/20261001/live_acceptance.json), [artifact hashes](../../results/evaluation_v1/phase2_handoff/20261001/artifact_inventory.json). Every charged raw SDK response, tool call/result, final SQL and usage are retained before controller parsing. Aggregate denominator remains eight, including the framework failure.

| Case | EX | Syntax | Execution | Error | API attempts/responses | DB tool calls | Usage-derived cost USD |
|---|---:|---:|---:|---|---:|---:|---:|
| ctu_sql_001 | 1 | 1 | 1 | OK | 6/6 | 4 | 0.00262280 |
| ctu_sql_002 | 1 | 1 | 1 | OK | 6/6 | 4 | 0.00264240 |
| ctu_sql_003 | 1 | 1 | 1 | OK | 4/4 | 3 | 0.00185450 |
| ctu_sql_004 | 1 | 1 | 1 | OK | 6/6 | 5 | 0.00309055 |
| ctu_sql_005 | 1 | 1 | 1 | OK | 8/8 | 6 | 0.00296115 |
| ctu_sql_006 | 0 | 0 | 0 | TOOL_LIMIT, linker; no SQL | 3/3 | 5 | 0.00153075 |
| ctu_sql_007 | 1 | 1 | 1 | OK | 5/5 | 3 | 0.00313930 |
| ctu_sql_008 | 1 | 1 | 1 | OK | 6/6 | 4 | 0.00301705 |
| Total | **7/8** | **7/8** | **7/8** | Framework failures **1/8** | **44/44** | **34** | **0.02085850** |

EX/syntax/execution rates are **87.5%**. TURN_LIMIT, RESULT_MISMATCH, SAFETY_REJECTION and INVALID_TOOL_PROVENANCE counts are each zero in this new suite; TOOL_LIMIT is its own category, not relabeled. Database calls here count bounded profiler/search/probe tool executions; they do not claim to count every underlying catalog, validator or scorer SQL query. Sum of measured model-response latency: **85,576.4986 ms**, not end-to-end wall-clock latency.

Case 006's linker used three model turns; its last charged response requested five searches together after two prior tool calls. Three were executed before the fixed five-tool cap stopped the role. Remaining requested tools and the entire charged response stay in telemetry; the generator was not called. No cap, prompt or contract adjustment was made after this outcome.

Input **47,802** tokens including **8,960 cached**, output **5,462** tokens. Cached-aware pricing: `(input-cached)*0.25 + cached*0.025 + output*2`, divided by one million; [official model pricing](https://developers.openai.com/api/docs/models/gpt-5-mini.md). The receipt independently recomputes **$0.02085850**, below preflight bound **$0.57024** and authorized new window **$0.75**. This is token-derived cost, not a billing invoice. Known historical lower bound $0.08693465 plus this run gives **$0.10779315**; history remains incomplete and is not represented as exact total spend. No credit purchase or limit increase.

This condition is **dev only**, under a new controller and SQL policy. Public pilot 5/8, CTU E0 0/8, previous remediation 1/8 and this run 7/8 are distinct experiments, not a continuous improvement series or proof of generalization. Old negative evidence is retained.

### Locked identities

| Identity | SHA-256 / source |
|---|---|
| Live Git SHA | `3f9d72ddc840d368b15b161881a94335c42eb03e` |
| Controller contract v3 | `a8d43578b892d93c41c723ff8841f24e0b02aa2861048b5c92661d01f46ff132` |
| SQL policy, normalized source | `302ab40bbe9af137fae53069930e2aa2f52d97125fcce1bfd1c8b1a2b9f4b590` |
| DuckDB snapshot, raw binary | `0b29765b9a175d00e0a193039a1b058691406e28a434e10030ae78265cfa67b9` |
| Logical snapshot | `42c8e0a62441295cc5d95329a65dc22409c37de5b26a1e37dd56fbf0164a758c` |
| Dataset manifest | `a1cdc77fc9ca697f336242254441d11c48ad3bb1cd656fd109001fb979205bdf` |
| Source S5 | `ef5c9ed6895d4ca5aec723449dae30054ccd1f6b091713a52ffcb681ff78a02c` |
| Source S7 | `df0b5338190b967bd340a0d6c1bb3c34d1bbfb4b7ffa764c2dd26f77f1a26680` |
| Core scorer, unchanged normalized source | `bd3d9da9e78bbcab560cefabae93a8c5592757a53375bdd31b7ee613d0c66fdf` |

Full case, prompt, tool, schema, runtime and code identities are in the original live report. New receipts explicitly distinguish current checks from archived provenance; current hashes never backfill old runs.

## R1 winner and human gate

[winner_lock.json](../../evaluation/tool_calling/winner_lock.json) selects pinned **`gpt-4.1-mini-2025-04-14`** by the existing rule's first metric, case success. No new proposal or prompt tuning; no R1 inference in this task. [Offline compatibility receipt](../../results/evaluation_v1/phase2_handoff/20261001/r1_compatibility.json) verifies the unchanged eight-case frozen structural lock, production schema and scorer, and checks current dev prompts against captured historical inputs. This does not measure frozen performance or reconstruct historical provenance.

| Track / condition | Dev case success | Exact-call F1 | No-tool accuracy | Recorded usage cost USD | Frozen status |
|---|---:|---:|---:|---:|---|
| R1 historical baseline / selected GPT-4.1 mini | 22/24 (91.67%) | 0.9508 | 5/5 | 0.01013120 | Compatibility only; new human approval required |
| R1 model-only GPT-5 mini | 19/24 (79.17%) | 0.9355 | 4/5 | 0.01595000 | No inference authorized |
| R2 CTU historical E0 one-shot | EX 0/8 | N/A | N/A | 0.00384725 | Historical evidence, not holdout |
| R2 previous remediation E3 | EX 1/8 | N/A | N/A | 0.01884615 suite only | Old S1/S4 consumed/ineligible |
| R2 phase-2 controlled E3 | EX 7/8 | N/A | N/A | 0.02085850 | Dev only; no valid R2 holdout result |

**11/24 R1 gold cases were adjudicated after seeing the original model output** (001, 003, 004, 006, 007, 009, 010, 011, 017, 018, 019); dev-v2 selection is not independent holdout evidence. Both reports match the same locked dev-v2 split/prompt/schema/scorer; model and request contracts differ: GPT-4.1 mini temperature=0 versus GPT-5 mini no temperature / reasoning low. Gold was not changed in this task. Captured historical evaluator SHAs and raw artifact digests are recorded in the winner lock.

`python -m evaluation.tool_calling.frozen_compatibility` actually passed: eight cases, model_calls=0, case-directory digest `50e52b226f886fd04e6c856614d2df7ef9c2ce27e1cea5a78fecfafc072accf7`. Winner lock declares `frozen_authorized=false`; it is a governance selection record, not runtime permission. S1/S4 `CONSUMED.lock` remains `consumed=true`, `protocol_eligible=false`. No frozen inference, new holdout, dataset download, snapshot rebuild or demo.

Historical R1 usage: selected GPT-4.1 mini **18,088 input / 1,810 output** tokens; GPT-5 mini **20,104 input / 5,462 output**. Winner failed cases 002/015; other candidate failed cases 002/005/009/019/020. Predictions, individual matching errors and category/difficulty breakdown remain in their source reports, referenced and raw-hashed by the lock; no new scoring or inference replaced those reports.

## Evidence preservation and closure

[Historical audit](../../results/evaluation_v1/phase2_handoff/20261001/historical_hash_audit.json) contains before/after raw checkout hashes for **185 protected files; all unchanged**. New inference files were audited read-only; report/case equality, unique response IDs, journal counts and usage-derived cost passed. The offline receipt generator initially rejected the baseline's archived status spelling `completed`; accepting the two existing status spellings (`completed`/`complete`) allowed validation without editing any report. This was not a paid rerun.

No `.env` writes, untracked cleanup, reset, branch, PR or historical artifact edits were performed. No benchmark/gold/comparator/core scorer/old selection-lock changes. The sole new inference was the recorded E3 suite; offline phases used synthetic clients/fixtures and the verified existing snapshot.

Raw digest of live report: `cb14da306ba0cd4bc92f0d239b037da976ef2867cde61e57395fa5f570dc039a`; winner lock: `dd520c4d9da7430d55d083cc66246f4de4a432aaf536108565bae070745269e9`; offline replay report: `9cb225ead5a23e4c088562c78b5fe38af751de9d434f7a4e895401ef774015f0`. New artifact inventory currently covers 19 files, independently rehashed after creation; immutable inference bytes are preserved with scoped Git attributes.

Final evidence commit and its exact-SHA CI are post-commit gates; completion is reported only after both Python jobs are green. **STOP FOR HUMAN REVIEW** after this handoff; no additional experiments or E2E.

Handoff verification actually run: `python -m pytest -q` **762 passed, 1612 existing warnings, 136.51s**, exit 0. `python -m py_compile` on all three phase-2 modules, both entrypoints, three regression-test files and the offline receipt generator: exit 0. `git diff --check`: exit 0. Read-only rehash of the 19 new artifact files: PASS; read-only check that both R1 reports cover exactly the same 24 unique dev IDs: PASS. No implementation source changed after the paid suite.

## Verification ledger

- Regression RED against predecessor: 7 failed, 22 passed (layout, quoted identifiers/literals, unknown function and malformed syntax).
- AST policy GREEN: `python -m pytest tests/test_r2_phase2_safety.py -q`: 29 passed (sandbox cache warnings recorded).
- `python -m scripts.replay_r2_phase2_policy --output results/evaluation_v1/ctu_network_public/r2_phase2_policy_replay/20261001`: counts above; input hashes unchanged.
- `python -m py_compile evaluation/r2_phase2/safety.py scripts/replay_r2_phase2_policy.py`: exit 0.
- `git diff --check`: exit 0.
- Protected inventory: 185 historical/locked files, zero changed hashes.
- Initial full suite inside sandbox: 349 passed, 384 fixture errors (temporary directory permission failures), not a pass. Full verification outside sandbox is required before closing this gate.
- Full suite outside sandbox: `python -m pytest -q`: **733 passed, 1612 warnings, 134.81s**, exit 0. Warnings are existing datetime deprecations. No product code change was needed for the sandbox fixture failures.
