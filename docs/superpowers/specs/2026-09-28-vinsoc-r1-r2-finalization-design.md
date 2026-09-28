# VinSOC R1/R2 Project Finalization Design

**Date:** 2026-09-28  
**Status:** Approved design for final implementation planning  
**Base commit:** `e73770529be94beded00689470a7597fd810011e`

## 1. Purpose

This design closes the internship evaluation work around the two mentor-facing objectives:

1. **R1 — Tool Calling Accuracy:** measure whether the model selects the correct production investigation tools and supplies the required arguments in one decision turn.
2. **R2 — Text-to-SQL Accuracy:** measure whether the model generates semantically correct, read-only DuckDB SQL, then test whether a DualSQL-inspired inference architecture improves execution accuracy over a one-shot baseline.

The project is complete only when both tracks have: a fixed development benchmark, an explicit error analysis, a controlled improvement experiment, a locked winning configuration, one frozen-holdout run, reproducibility/provenance evidence, and final before/after reporting.

This is a finalization program, not a new feature phase.

## 2. Current evidence baseline

### R1

The preserved R1 development benchmark is `r1_a1_dev_v2` with 24 development cases. Its benchmark split SHA-256 is:

`d8e68968a390a09d502a3da01319611f546a6d0189a30e0fe0c316550d0aa259`

Its scorer SHA-256 is:

`271aa8ba8b65548f1d17648945ac62cc18b2370fa85c4aa210c155c9154b9149`

The preserved GPT-4.1 Mini development result is **22/24 single-turn case success** using `gpt-4.1-mini-2025-04-14`. The earlier 15/24 run is historical evidence on an older benchmark/schema and MUST NOT be reported as a fixed-benchmark model improvement to 22/24.

The R1 frozen split contains 8 cases and has not been used for final model selection.

### R2

The final R2 scope is **CTU-only Network Text-to-SQL**. It does not claim full CTI/network/endpoint Text-to-SQL coverage.

The locked CTU development snapshot uses:

- `ctu13_s5`
- `ctu13_s7`
- 243,906 normalized network flows
- logical snapshot SHA-256 `42c8e0a62441295cc5d95329a65dc22409c37de5b26a1e37dd56fbf0164a758c`

The eight development cases already cover stored-value grounding, DISTINCT, microsecond time boundaries, Boolean predicates, aggregation, GROUP BY, ORDER BY/LIMIT, and source-dataset grouping.

The preserved GPT-4.1 Mini CTU E0 run is historical baseline evidence and MUST remain unchanged. The active future R2 model contract is now:

- provider: OpenAI
- model: `gpt-5-mini-2025-08-07`
- reasoning effort: `low`
- temperature field: absent from the API request
- max completion tokens: 1000
- SDK retries: 0
- E0 eight-case conservative suite budget: less than USD 0.10

The contract-hardening commit is `e73770529be94beded00689470a7597fd810011e`.

### Historical DualSQL-Lite work

The existing public-development E0-E3 series using GPT-4.1 Mini remains preserved as exploratory evidence. Its selected configuration and artifacts MUST NOT be overwritten.

The existing v4 result showed:

- E0: 5/8
- E1: 1/8
- E2: 5/8
- E3: 1/8

This does not prove that DualSQL is ineffective. E1/E3 were dominated by framework/linker failures. The final optimization series therefore uses a new version and a new GPT-5 Mini backbone.

## 3. Global finalization constraints

The following rules apply to every remaining task.

1. Work directly on `master`; do not create branches or pull requests.
2. Do not rewrite or overwrite historical evidence artifacts.
3. Do not tune against frozen data.
4. Do not retry a case because the model answer was wrong.
5. Provider/infrastructure failure may justify a new run only after the failure is diagnosed and the new run is recorded as a separate immutable attempt.
6. Do not change gold SQL, scorer semantics, benchmark questions, or tool gold labels to improve a model score.
7. Controlled experiments must change one declared factor at a time.
8. No fallback provider, routed provider, or silent model substitution is allowed.
9. All paid runs are manual-only, bounded, zero-retry, and provenance-recorded.
10. ThreatFox must not be used as the source for the final AI-evaluation R2 track. OTRF and the previous three-source R2 path are outside the final critical path.
11. Do not add new model families, new benchmark domains, dashboards, demos, or unrelated product features until R1/R2 finalization is complete.
12. Total remaining API spend should stay within the user's approximate USD 2–3 budget. Every paid suite must have its own conservative preflight ceiling.
13. Frozen outputs are evaluation evidence, never tuning input.
14. A run is not “official/final” merely because CI is green. Eligibility depends on the benchmark/model/config/provenance contract for that track.

## 4. Final experiment architecture

The final program has two parallel tracks.

```text
R1 Tool Calling                         R2 Text-to-SQL
---------------                         --------------
GPT-4.1 baseline                        GPT-4.1 historical baseline
        |                                       |
GPT-5 model-only dev                    GPT-5 E0 dev
        |                                       |
error analysis                          error analysis
        |                                       |
<= 1 generic improvement                stabilize DualSQL framework
        |                                       |
final R1 winner                         E1 / E2 / E3
        |                                       |
lock                                    select final R2 winner
        |                                       |
frozen exactly once                     lock
                                                |
                                        frozen exactly once
```

The final report joins these two tracks only after their frozen runs are complete.

## 5. R1 final design

### 5.1 Fixed benchmark contract

Use the existing `r1_a1_dev_v2` development split. Do not modify the 24 cases while running model comparison.

Use the exact production tool schemas returned by `agent.tools.get_tool_schemas()`.

Keep the existing decision-only semantics:

- one decision turn;
- native model `tool_calls`;
- no production skill execution;
- no tool inference from prose;
- explicit no-tool cases;
- extra/forbidden calls are penalized.

### 5.2 R1 model-only experiment

Run one GPT-5 Mini development suite on the same 24 cases.

The model-only experiment must hold constant:

- benchmark cases;
- system prompt;
- production tool schemas;
- required/critical argument policy;
- matcher;
- scorer;
- max-completion cap;
- retry policy.

Only the model/request configuration may differ as required by GPT-5 Mini API compatibility.

The implementation must preserve the historical GPT-4.1 Mini artifact and create a new immutable GPT-5 Mini artifact.

### 5.3 R1 headline metrics

The final R1 report MUST include:

- Single-Turn Case Success;
- Tool-Set Exact Match;
- Exact-Call Precision;
- Exact-Call Recall;
- Exact-Call F1;
- Required Argument Accuracy;
- Critical Argument Accuracy;
- No-Tool Accuracy;
- Forbidden-Tool Rate.

Diagnostics MUST include:

- provider-error rate;
- execution/response-error rate;
- latency;
- input/output token counts;
- calculated cost;
- per-category results;
- per-case matches and predicted calls.

### 5.4 R1 error taxonomy

Every failed development case must receive one primary cause:

- `WRONG_TOOL`
- `MISSING_TOOL`
- `EXTRA_TOOL`
- `NO_TOOL_HALLUCINATION`
- `REQUIRED_ARG_MISSING`
- `REQUIRED_ARG_WRONG_VALUE`
- `CRITICAL_ARG_WRONG`
- `FORBIDDEN_TOOL`
- `DUPLICATE_CALL`
- `PROVIDER_ERROR`
- `EXECUTION_ERROR`

The analysis must explicitly revisit the previously failed `case_002` and `case_015`, but must not create case-specific rules.

### 5.5 R1 improvement budget

After the GPT-5 model-only dev run, allow at most **one generic controlled improvement round**.

A valid improvement must target a recurring failure class, for example:

- over-investigation / extra tool selection;
- incorrect abstention/no-tool behavior;
- generic argument normalization;
- generic tool-schema ambiguity;
- generic system-prompt instruction.

Invalid improvements include:

- checking a specific case ID;
- special-casing a literal from one benchmark item;
- editing expected calls to match the model;
- changing multiple unrelated variables at once.

If there is no defensible generic improvement, skip this round and select between the preserved GPT-4.1 Mini baseline and the GPT-5 Mini model-only result.

### 5.6 R1 selection rule

Select the final R1 configuration by:

1. higher Single-Turn Case Success;
2. higher Critical Argument Accuracy;
3. higher Exact-Call F1;
4. lower Forbidden-Tool Rate;
5. lower calculated API cost;
6. lower latency;
7. simpler configuration.

Do not rerun tied configurations to obtain a preferred score.

## 6. R2 final design

### 6.1 Final scope

The final R2 claim is:

> VinSOC Network Text-to-SQL evaluation on public CTU-13 network telemetry.

It must not be described as full multi-source SOC Text-to-SQL.

### 6.2 GPT-5 Mini E0 baseline

Run exactly one paid GPT-5 Mini E0 development suite on the existing eight CTU dev cases.

The experiment must preserve:

- CTU source bytes;
- snapshot logical identity;
- eight questions;
- gold SQL;
- result comparators;
- scorer;
- schema context;
- system prompt.

The only intended experimental change relative to the active runner's predecessor is the model/request configuration.

The E0 artifact must record:

- exact requested and actual model;
- model-config SHA-256;
- evaluator Git SHA;
- logical snapshot SHA-256;
- source hashes;
- split SHA-256;
- scorer/builder hashes;
- generated SQL per case;
- syntax/execution/accuracy result per case;
- error category;
- usage, calculated cost, and latency;
- preflight ceiling;
- partial evidence if a charged response is received before later failure.

### 6.3 R2 headline and diagnostic metrics

Primary metric:

- **Execution Accuracy**

Diagnostics:

- Syntax Validity;
- Execution Success;
- Safety Rejection Rate;
- provider-error rate;
- input/output tokens;
- calculated cost;
- latency;
- model calls;
- DB-tool calls for agentic conditions;
- per-case and per-semantic-category Execution Accuracy.

### 6.4 R2 semantic error taxonomy

Every incorrect development case must receive one primary semantic cause:

- `VALUE_GROUNDING`
- `SCHEMA_SELECTION`
- `PREDICATE_ERROR`
- `BOOLEAN_LOGIC`
- `DISTINCT_ERROR`
- `TIME_BOUNDARY`
- `AGGREGATION`
- `ORDERING_LIMIT`
- `DIALECT`
- `SYNTAX_ERROR`
- `EXECUTION_ERROR`
- `SAFETY_REJECTION`
- `PROVIDER_ERROR`

`RESULT_MISMATCH` may remain the deterministic scorer category, but the human-readable error-analysis artifact must refine it into one of the semantic causes above where evidence permits.

### 6.5 DualSQL-Lite final optimization series

Create a new versioned series; do not mutate historical v1-v4 evidence.

Recommended series identity:

`dualsql_lite_ctu_gpt5_v1`

Conditions:

- **E0:** one-shot generator, no schema linker, no DB tools;
- **E1:** schema linker, then one-shot generator, no generator-side DB tools;
- **E2:** no linker, bounded agentic generator with DB tools;
- **E3:** schema linker plus bounded agentic generator with DB tools.

All conditions use the same GPT-5 Mini backbone and the same benchmark/scorer/snapshot contract.

If the paid GPT-5 E0 artifact is byte-for-byte/configuration-equivalent to the E0 condition in the final series, reuse that artifact instead of paying for a duplicate E0 run.

### 6.6 DualSQL framework stabilization

Before E1/E2/E3 paid runs, fix only framework defects that are independent of any individual benchmark answer.

Required behavior:

1. **Question literals and DB-grounded values are distinct evidence classes.**
   - A literal explicitly present in the user question does not need a DB-tool trace merely to be legal.
   - A value inferred from the database must carry tool/controller provenance.

2. **Grounding provenance is controller-owned.**
   - The model must not be forced to “prove” grounding by copying every value into a self-declared list.
   - The controller records values returned by database tools.

3. **Multiple native tool calls may be valid.**
   - Do not fail only because a model emits more than one valid DB tool call in a turn.
   - Preserve a hard total tool-call and turn limit.

4. **Typed schema is mandatory.**
   - Agents see table, column, and type information.

5. **Value Search must support actual CTU stored representations.**
   - Particularly `source_dataset`, `label`, and `protocol`.
   - No hand-written case-specific alias table is allowed.

6. **Gold isolation remains strict.**
   - Gold SQL and expected results are visible only to the deterministic scorer after the final SQL is submitted.

7. **All DB tools remain read-only and bounded.**

The final implementation must preserve or strengthen the existing safety boundary.

### 6.7 R2 selection rule

Select the final R2 configuration by:

1. higher Execution Accuracy;
2. lower calculated API cost;
3. fewer model calls;
4. lower latency;
5. simpler architecture, ordered E0, E1, E2, E3 for a complete tie.

Do not choose E3 merely because it is the fullest DualSQL-style architecture.

## 7. Frozen holdout design

### 7.1 R1 frozen

Use the existing eight R1 frozen cases.

Before the paid frozen run, perform only compatibility validation:

- files parse;
- schema/tool names still exist;
- scorer can load cases;
- no model execution;
- no gold changes;
- no prompt tuning.

Run the selected R1 winner once after its config lock is committed.

### 7.2 R2 frozen

The current CTU dev uses scenarios 5 and 7. The final frozen benchmark must use CTU source scenario/session data that is not part of dev.

Preferred frozen source pair:

- CTU-13 Scenario 1;
- CTU-13 Scenario 4.

These provide source-session separation from S5/S7 and different botnet behavior.

If either official source is unavailable, checksum-invalid, or cannot be provenance-verified, STOP and report the blocker. Do not silently substitute another scenario.

The R2 frozen set should contain **6–8 cases** and collectively cover:

- scalar filtering/count;
- DISTINCT;
- Boolean conjunction/precedence;
- bounded time interval;
- aggregation/GROUP BY;
- ORDER BY/LIMIT;
- stored-value grounding;
- multi-row comparison.

Frozen authoring may use deterministic offline SQL validation. It must not use final model outputs to select or rewrite cases.

Before any frozen model call, lock:

- source URLs;
- source SHA-256 values;
- normalized row counts;
- logical snapshot SHA-256;
- frozen case directory SHA-256;
- gold/scorer SHA-256;
- builder SHA-256;
- result-comparator contract;
- selected final model/config hash.

After this lock is committed, frozen questions, gold, scorer, prompt, tool schema, model configuration, and snapshot contract are immutable for that final run.

## 8. Paid-run policy

Remaining paid suites are limited to the following intended runs:

1. R2 GPT-5 Mini E0 dev;
2. R1 GPT-5 Mini dev;
3. R2 E1 dev;
4. R2 E2 dev;
5. R2 E3 dev;
6. optional one improved R1 dev suite, only if a generic improvement is approved;
7. R1 frozen once;
8. R2 frozen once.

A separate smoke is allowed only when the exact model/API contract has not yet been proven callable. Once one valid provider response confirms the contract, do not repeatedly smoke-test.

For every paid suite:

- preflight before provider creation;
- explicit suite cost ceiling;
- zero SDK retries;
- no automatic case retries;
- standard OpenAI endpoint only;
- no fallback/routing;
- preserve partial credential-free evidence;
- stop on provider/model identity mismatch;
- record actual usage from provider metadata.

## 9. Provenance and artifact contract

Every final dev/frozen report must record enough identity to reconstruct what was scored.

Required fields where applicable:

- run ID;
- track;
- split;
- benchmark version;
- case IDs;
- benchmark/split SHA-256;
- provider;
- requested model;
- actual model;
- model configuration;
- model-config SHA-256;
- reasoning effort or temperature semantics;
- completion cap;
- retry count;
- system-prompt SHA-256;
- production tool-schema SHA-256 for R1;
- snapshot logical SHA-256 for R2;
- source-file SHA-256 values for R2;
- scorer SHA-256;
- implementation/evaluator Git SHA;
- clean/expected Actions checkout identity;
- per-case prediction;
- per-case score;
- per-case error cause;
- token usage;
- calculated cost;
- latency.

Historical artifacts remain immutable.

## 10. Reporting rules

The final report must distinguish four evidence classes:

1. historical baseline;
2. model-only upgrade;
3. architecture/prompt controlled improvement;
4. frozen holdout.

Do not report:

- 15/24 to 22/24 as model improvement;
- scorer replay 2/8 to 5/8 as model improvement;
- public-dev DualSQL v4 as final R2 evidence;
- CTU-only R2 as full SOC/multi-source Text-to-SQL;
- a frozen score as a development-selection result.

For small N, report raw counts with rates. For example, write `7/8 (87.5%)`, not only `87.5%`.

Do not make statistical-significance claims from the eight-case development set.

## 11. Final mentor-facing output

The final top-level comparison table should have this structure:

| Track | Historical baseline | Model-only upgrade | Controlled optimization | Frozen |
| --- | --- | --- | --- | --- |
| R1 Tool Calling | GPT-4.1 Mini 22/24 | GPT-5 Mini x/24 | y/24 or N/A | x/8 |
| R2 Network Text-to-SQL | GPT-4.1 historical CTU baseline | GPT-5 Mini E0 x/8 | DualSQL winner y/8 | x/N |

Accompany it with:

- per-scenario/category breakdown;
- before/after error-class counts;
- selected configuration;
- cost and latency;
- limitations;
- exact artifact/run references.

## 12. Execution order

The implementation plan MUST follow this order unless a hard blocker forces a stop:

1. Run one GPT-5 Mini R2 E0 development suite.
2. Add/execute one GPT-5 Mini R1 model-only development suite.
3. Produce R1 and R2 development error-analysis artifacts.
4. Lock R1 frozen compatibility without model execution.
5. Build and lock source-separated R2 frozen benchmark without model execution.
6. Stabilize the generic DualSQL framework defects.
7. Execute E1/E2/E3 GPT-5 Mini development conditions.
8. Select and commit the final R2 winner lock.
9. Apply at most one generic R1 improvement if justified; otherwise select the existing best dev configuration.
10. Commit the final R1 winner lock.
11. Execute R1 frozen exactly once.
12. Execute R2 frozen exactly once.
13. Freeze final evidence and write the final evaluation report.
14. Reconcile README/evaluation documentation only after evidence is stable.

## 13. Stop conditions

STOP and request human review if any of these occurs:

- exact GPT-5 Mini snapshot is unavailable or provider identity differs;
- a paid-suite preflight exceeds its budget;
- frozen source provenance cannot be verified;
- a proposed improvement requires changing gold/scorer/case wording to raise accuracy;
- a model call would require fallback/routed provider;
- frozen has already been executed for the current version and someone proposes further tuning;
- historical evidence would need to be overwritten;
- a new requirement would expand scope beyond R1/R2 finalization.

A wrong model answer is not a stop condition. It is evaluation evidence.

## 14. Definition of done

### R1 done

- preserved 22/24 GPT-4.1 Mini baseline;
- one GPT-5 Mini model-only dev result;
- inspectable error analysis;
- no more than one generic controlled improvement;
- final winner lock;
- one eight-case frozen run;
- complete provenance and per-case evidence.

### R2 done

- one valid GPT-5 Mini E0 dev result;
- semantic error analysis;
- stabilized DualSQL framework;
- E1/E2/E3 controlled dev results;
- final winner lock;
- independent CTU frozen snapshot and 6–8 frozen cases;
- one frozen run;
- complete provenance and per-case evidence.

### Project done

- both tracks satisfy their done criteria;
- final before/after/frozen comparison table exists;
- cost and latency are reported;
- limitations and scope are explicit;
- README/evaluation docs match actual evidence;
- CI is green on the final evidence/documentation commit;
- no frozen contamination or historical artifact rewrite occurred.
