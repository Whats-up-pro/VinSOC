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

## Verification ledger

- Regression RED against predecessor: 7 failed, 22 passed (layout, quoted identifiers/literals, unknown function and malformed syntax).
- AST policy GREEN: `python -m pytest tests/test_r2_phase2_safety.py -q`: 29 passed (sandbox cache warnings recorded).
- `python -m scripts.replay_r2_phase2_policy --output results/evaluation_v1/ctu_network_public/r2_phase2_policy_replay/20261001`: counts above; input hashes unchanged.
- `python -m py_compile evaluation/r2_phase2/safety.py scripts/replay_r2_phase2_policy.py`: exit 0.
- `git diff --check`: exit 0.
- Protected inventory: 185 historical/locked files, zero changed hashes.
- Initial full suite inside sandbox: 349 passed, 384 fixture errors (temporary directory permission failures), not a pass. Full verification outside sandbox is required before closing this gate.
- Full suite outside sandbox: `python -m pytest -q`: **733 passed, 1612 warnings, 134.81s**, exit 0. Warnings are existing datetime deprecations. No product code change was needed for the sandbox fixture failures.
