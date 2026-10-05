# Phase-2 E3: immutable scored dev result

Original run: `r2_phase2_live/20261001_3f9d72d/suite`; implementation SHA `3f9d72ddc840d368b15b161881a94335c42eb03e`. Updated reporting correction: 2026-10-05.

**Execution Accuracy 7/8 (87.5%), Syntax Validity 7/8, Execution Success 7/8.** [The complete original report](../../results/evaluation_v1/ctu_network_public/r2_phase2_live/20261001_3f9d72d/suite/report.json) records 44 attempts/responses, 34 database tool calls and usage-derived cost **$0.02085850**.

| Case | Original EX | Pipeline / scored outcome |
|---|---:|---|
| ctu_sql_001 | 1 | OK |
| ctu_sql_002 | 1 | OK |
| ctu_sql_003 | 1 | OK |
| ctu_sql_004 | 1 | OK |
| ctu_sql_005 | 1 | OK |
| ctu_sql_006 | 0 | TOOL_LIMIT; generator not invoked; no final SQL |
| ctu_sql_007 | 1 | OK |
| ctu_sql_008 | 1 | OK |

Case006's linker used five tool calls in three model turns: one profiler call, a search for a source ID in integer `dst_port`, then three port-value searches before stopping at the cap. The last charged response requested five searches together; unexecuted requested calls remain in telemetry.

Later INTEGER hints changed prompts/tools/grounding. That is a different implementation. There is **no verified full suite after that change** in tracked evidence. A separate case006 prediction cannot be added to seven previous predictions to create an 8/8 headline. Pipeline `error_category=OK` establishes generation completion, not execution accuracy.

The 2026-10-05 offline scorer reuses `evaluate_sql_case()` and the unchanged comparator. It retains pipeline errors separately and validates gold infrastructure. Replay source hashes must remain identical before/after; all eight original predictions remain in the denominator. Replay is not a new model result.

[Governance and original identities](r2_phase2_governance.md), [corrected report](FINAL_EVALUATION_REPORT.md), [Task 0+1 delivery plan](../superpowers/plans/2026-10-05-vinsoc-finalization-fix.md).

Historical E0, remediation, public pilot and this phase-2 run are distinct conditions; the earlier delta/progress timeline was not a matched experiment. No independent R2 holdout is available: S1/S4 is consumed and protocol-ineligible. Status: **DEV_VERIFIED / HOLDOUT_PENDING**.
