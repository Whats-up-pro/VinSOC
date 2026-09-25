# VinSOC R2 DualSQL-Lite — Agent Handoff Specification

**Status:** Approved direction for external-agent implementation  
**Date:** 2026-09-25  
**Scope:** R2 Text-to-SQL optimization only  
**Primary research reference:** DualSQL: Text-to-SQL with Multi-Agent Reinforcement Learning, arXiv:2609.18135v1  
**Reference URL:** https://arxiv.org/html/2609.18135v1

## 1. Purpose

This document is the authoritative handoff specification for an implementation agent.

It defines **what must be built, measured, preserved, and delivered**.

It does **not** prescribe a line-by-line implementation plan and does not authorize architectural changes outside this specification.

The implementation agent must not infer additional project goals from the paper or from adjacent VinSOC modules.

## 2. Project objective

The R2 objective is unchanged:

> Improve and evaluate VinSOC Text-to-SQL accuracy in a reproducible way, identify why queries fail, apply a controlled optimization, and produce defensible before/after evidence without contaminating the frozen holdout.

The primary metric remains **Execution Accuracy** under the existing VinSOC R2 evaluator.

The optimization must remain compatible with the internship focus:

- Text-to-SQL Accuracy;
- reproducible benchmark;
- controlled improvement;
- error analysis;
- before/after comparison;
- real public SOC data;
- low API cost;
- no model training.

## 3. Non-negotiable constraints

The implementation must obey all of the following:

- No reinforcement learning.
- No supervised fine-tuning.
- No model training.
- No GRPO.
- No reward-model optimization.
- No synthetic training set generation for model fitting.
- No replacement of the existing R2 headline metric.
- No use of frozen holdout for prompt tuning, architecture selection, or debugging.
- No gold SQL or gold execution result may be exposed to any inference-time agent.
- No production database may be queried.
- All database interaction must remain read-only.
- All evidence runs must be reproducible and versioned.
- Existing historical result artifacts must never be overwritten.
- Public-dev results must not be presented as official benchmark results.
- A scorer-policy change must never be presented as model improvement.
- The implementation must remain within the project's API budget controls.
- Any change to model, prompt, tool behavior, scorer, benchmark, or snapshot invalidates direct before/after comparison unless a new experiment version is declared.

## 4. Research adaptation

DualSQL is used as an **architectural reference**, not as a reproduction target.

The paper combines:

- Schema Linking Agent;
- SQL Generation Agent;
- SQL Executor;
- Full Text Search;
- Database Profiler;
- multi-agent reinforcement learning.

VinSOC adopts only the inference-time architecture and database-grounding concepts.

VinSOC does not claim to reproduce the paper's trained model behavior or reported BIRD performance.

## 5. Target architecture

The required runtime architecture has two sequential roles using the **same pinned LLM configuration**.

### Stage A — Schema Linking Agent

Purpose:

- identify relevant tables;
- identify relevant columns;
- identify database literals needed to interpret the question;
- reduce schema/value ambiguity before SQL generation.

The Schema Linking Agent may use:

- Database Profiler;
- Value Search;
- SQL Probe Executor.

Its output is a structured linked-schema artifact.

It must not submit final SQL.

### Stage B — SQL Generation Agent

Purpose:

- receive the original question;
- receive the validated linked schema;
- receive grounded database values;
- produce one final SQL query.

When the experiment configuration permits it, the SQL Generation Agent may also use:

- Database Profiler;
- Value Search;
- SQL Probe Executor.

The generator must be able to recover from an incomplete initial schema link when database tools are enabled.

### Final evaluation

The SQL Generation Agent submits one final SQL statement.

Only after final submission is the SQL evaluated by the existing VinSOC R2 evaluator.

The evaluator remains the sole authority for:

- syntax validity;
- safety rejection;
- execution success;
- result comparison;
- Execution Accuracy.

## 6. Shared-model requirement

Both agent roles must use the same provider/model/configuration during a comparable experiment.

The roles differ through:

- role-specific system instructions;
- available tools;
- expected output contract.

They must not be implemented as independently trained models.

For the current public-dev evidence series, the pinned model remains:

**gpt-4.1-mini-2025-04-14**

with:

- temperature = 0;
- zero automatic SDK retries;
- fixed completion limit;
- identical provider configuration across E0-E3.

If the model is changed, the experiment series must be versioned again and E0 must be rerun.

## 7. Database tools

The implementation must provide three bounded read-only database capabilities analogous to DualSQL.

### 7.1 Database Profiler

Purpose:

- inspect available tables and columns;
- expose deterministic schema metadata;
- expose bounded statistics useful for schema linking.

Allowed information may include:

- table names;
- column names;
- data types;
- null information;
- distinct-value counts;
- numeric/timestamp range;
- bounded representative values for low-cardinality columns.

Requirements:

- deterministic for the same snapshot;
- no model-generated semantic descriptions in the initial implementation;
- no inferred foreign keys unless already explicitly represented in source metadata;
- no access to benchmark gold data;
- output must be size-bounded.

### 7.2 Value Search

Purpose:

- map natural-language mentions to real database literals;
- help resolve encoded SOC values.

Typical VinSOC examples include:

- "scenario 5" versus stored value such as "ctu13_s5";
- "From-Botnet" versus stored labels such as "flow=From-Botnet-...".

Requirements:

- search data must be derived only from the verified evaluation snapshot;
- exact source table and column must be preserved for each result;
- results must be deterministic;
- results must be bounded;
- no benchmark-case-specific hand-written answer mapping;
- no gold-derived alias table;
- search-catalog identity must be versioned and hashed.

Initial maximums:

- 5 values per column;
- 50 values per call;
- bounded serialized tool response.

### 7.3 SQL Probe Executor

Purpose:

- test read-only hypotheses;
- inspect actual values;
- verify filters, joins, aggregation assumptions, or query fragments;
- return execution errors that may help the model self-correct before final submission.

Requirements:

- SELECT-only or equivalent read-only query form;
- no INSERT, UPDATE, DELETE, CREATE, DROP, ALTER, COPY, ATTACH, INSTALL, LOAD, PRAGMA, or other state-changing operations;
- no multiple statements;
- no external files;
- no URLs;
- no external table readers/scanners;
- no network database connections;
- no internal evaluator/gold/provenance tables;
- no production systems;
- zero-row results are valid results, not errors;
- output must be row-bounded and byte-bounded.

Initial maximum:

- 20 returned rows;
- 8192 serialized bytes.

## 8. Inter-agent contract

The Schema Linking Agent must return a structured linked-schema result containing:

- selected tables;
- selected columns for each table;
- grounded values when such evidence was retrieved;
- provenance for each grounded value showing which database tool produced it.

Requirements:

- every table must exist in the evaluation snapshot;
- every column must belong to the declared table;
- grounded values must be traceable to real tool output;
- no invented value may be marked as grounded;
- final SQL must not be included;
- hidden chain-of-thought is neither required nor stored.

The SQL Generation Agent receives:

- the original natural-language question;
- the validated linked schema;
- grounded values;
- the allowed schema context required by its experiment condition;
- database tools only when enabled by that experiment.

## 9. Gold isolation

Gold isolation is mandatory.

Before the generator submits its final SQL, the following must be inaccessible to both agents:

- gold_sql;
- gold execution result;
- evaluator correctness verdict;
- current-case error label derived from comparison with gold;
- benchmark solution annotations.

Database tools must expose benchmark data only, not benchmark answers.

The implementation must include explicit verification that gold-only sentinel content cannot appear in:

- model messages;
- tool arguments;
- tool results;
- inter-agent linked-schema output;
- finalization inputs.

## 10. Agent runtime limits

Both roles are bounded.

### Schema Linking Agent

Maximum:

- 5 model turns;
- 5 database-tool calls;
- one final linked-schema submission.

Failure to submit a valid linked schema within the limit is a model-level case failure.

### SQL Generation Agent

Maximum:

- 5 model turns;
- 5 database-tool calls;
- one final SQL submission.

There is no retry after the final evaluator has judged the SQL.

Failure to submit valid final SQL within the limit is a model-level case failure.

## 11. Experiment matrix

The required public-dev experiment series contains exactly four architectural conditions.

### E0 — One-shot baseline

- no Schema Linking Agent;
- no database tools;
- same one-shot Text-to-SQL behavior used as the controlled baseline;
- one final SQL.

Purpose:

Measure the model under the current direct Text-to-SQL architecture.

### E1 — Schema Linker + static SQL Generator

- Schema Linking Agent enabled;
- linker has database tools;
- SQL Generator receives linked schema and grounded values;
- SQL Generator has no database tools.

Purpose:

Measure the effect of explicit schema/value grounding and schema pruning.

### E2 — Single agentic SQL Generator

- no separate Schema Linking Agent;
- SQL Generator has database tools;
- generator receives full schema.

Purpose:

Measure whether interactive database grounding alone explains any gain.

### E3 — DualSQL-Lite

- Schema Linking Agent enabled;
- linker has database tools;
- SQL Generator receives linked schema and grounded values;
- SQL Generator also has database tools.

Purpose:

Measure the combined two-stage inference architecture.

## 12. Required experiment interpretation

The report must support these comparisons:

- E1 versus E0: effect of explicit schema linking.
- E2 versus E0: effect of generator-side database interaction.
- E3 versus E1: effect of generator-side recovery after schema linking.
- E3 versus E2: effect of adding a separate schema-linking stage when the generator already has tools.

The implementation must not assume E3 is the winner.

The winning configuration is selected from measured results.

## 13. Benchmark protocol

### 13.1 Public dev

Use the existing R2 public-dev benchmark as the architecture-development sandbox.

Current public-dev size:

**8 cases**

During the E0-E3 comparison, the following must remain fixed:

- question text;
- gold SQL;
- comparator;
- logical snapshot content;
- scorer;
- model;
- temperature;
- prompt versions;
- tool implementation;
- tool limits;
- search-catalog construction.

Because there are only 8 cases, every case equals 12.5 percentage points.

Public-dev results are diagnostic.

A gain of at least **2 additional correct cases out of 8** over the newly run E0 is considered a **strong pilot signal**, not statistical proof.

### 13.2 Official dev

The official R2 development benchmark must use the planned three-source SOC snapshot:

- ThreatFox;
- CTU-13;
- OTRF endpoint telemetry.

Official dev may start only after:

- all sources are verified;
- source hashes are preserved;
- snapshot manifest exists;
- snapshot binary hash exists;
- logical snapshot hash exists;
- dev split is frozen;
- gold SQL is validated;
- scorer identity is frozen.

Only E0 and the public-dev-selected configuration are required for official-dev comparison.

### 13.3 Frozen holdout

Frozen is not used during:

- tool design;
- prompt design;
- architecture selection;
- public-dev experiments;
- official-dev tuning;
- error-driven changes.

Before frozen is opened, the final configuration must be locked with:

- git commit;
- model/configuration;
- role prompts;
- tool schemas;
- tool implementation identities;
- search-catalog identity;
- snapshot identity;
- benchmark identity;
- scorer identity.

Frozen is then run once, except for a documented infrastructure/provider failure that invalidates the run.

Frozen results must not be used to modify the system.

## 14. Metrics

### 14.1 Primary metric

**Execution Accuracy**

This remains the headline metric.

Definition:

Number of final generated SQL queries whose accepted execution result matches the gold result under the existing R2 comparator, divided by total valid benchmark cases.

### 14.2 Existing diagnostics

Continue reporting:

- Syntax Validity;
- Execution Success;
- Safety Rejection;
- per-category performance;
- per-difficulty performance when sample size permits.

### 14.3 Agentic diagnostics

The implementation must also collect:

- linker completion rate;
- linker turns;
- linker database-tool calls;
- generator turns;
- generator database-tool calls;
- Database Profiler usage rate;
- Value Search usage rate;
- SQL Probe usage rate;
- number of linked tables;
- number of linked columns;
- generator recovery events when additional schema is discovered after linking;
- malformed agent-output count.

These are diagnostic metrics only.

They do not replace Execution Accuracy.

### 14.4 Optional schema-linking metrics

Schema-linking precision/recall/F1 may be added only if a reviewer-authored schema-gold annotation set is created.

If added:

- it must be frozen before evidence runs;
- it must remain separate from inference inputs;
- it must never be exposed to either agent.

Optional metrics:

- table precision;
- table recall;
- table F1;
- column precision;
- column recall;
- column F1;
- complete schema recall.

These are not required for the primary R2 deliverable.

### 14.5 Efficiency metrics

Every experiment must report:

- model calls;
- database-tool calls;
- input tokens;
- output tokens;
- API cost;
- cost per case;
- latency;
- average turns.

Accuracy must always be presented together with compute cost.

## 15. Failure taxonomy

Post-hoc error analysis must be able to classify failures using categories such as:

- LINKER_TABLE_OMISSION;
- LINKER_COLUMN_OMISSION;
- VALUE_GROUNDING_MISS;
- LINKER_FORMAT_OR_LIMIT_FAILURE;
- SQL_SCHEMA_RECOVERY_FAILURE;
- PREDICATE_ERROR;
- BOUNDARY_ERROR;
- AGGREGATION_ERROR;
- DISTINCT_ERROR;
- BOOLEAN_LOGIC;
- ORDERING_LIMIT;
- DIALECT_ERROR;
- SAFETY_REJECTION;
- EXECUTION_ERROR;
- GENERATOR_FORMAT_OR_LIMIT_FAILURE;
- PROVIDER_OR_INFRASTRUCTURE_FAILURE.

These labels are for analysis only.

They must not be fed back into the same benchmark run.

## 16. Model failures versus invalid runs

### Model-level failures

These remain valid benchmark observations and count against accuracy:

- linker produces invalid output;
- linker reaches turn/tool limit;
- generator produces no final SQL;
- generator reaches turn/tool limit;
- unsafe SQL;
- syntax error;
- execution error caused by generated SQL;
- incorrect execution result.

### Run-invalidating failures

These invalidate the evidence run:

- wrong provider;
- wrong actual model;
- missing or unverifiable usage telemetry required by the evidence protocol;
- provider outage or timeout preventing completion;
- snapshot hash mismatch;
- benchmark hash mismatch;
- scorer hash mismatch;
- changed prompt/tool/catalog identity inside a fixed experiment series;
- dirty or unpinned evidence checkout;
- budget gate failure;
- duplicate or missing benchmark cases.

An invalid run must not be compared as an official E0-E3 result.

## 17. Security requirements

The implementation must preserve a strict offline evaluation boundary.

Required:

- evaluation snapshot only;
- read-only DuckDB access;
- no production telemetry stores;
- no write SQL;
- no external file readers;
- no network URLs inside SQL;
- no extension loading;
- no remote database scans;
- no internal solution tables;
- no secrets in artifacts;
- no API key logging;
- bounded tool outputs.

The presence of an SQL Probe tool must not weaken the existing final SQL safety policy.

## 18. Reproducibility and provenance

Every evidence run must record enough information to reproduce the experiment.

Required run identity includes:

- run ID;
- experiment ID;
- git commit;
- provider;
- requested model;
- actual model;
- temperature;
- completion limit;
- retry policy;
- benchmark version/hash;
- snapshot binary hash;
- snapshot logical-content hash;
- scorer hash;
- linker prompt version/hash;
- generator prompt version/hash;
- database tool schema identity;
- database tool implementation identity;
- value-search catalog builder version/hash;
- budget/preflight configuration;
- pricing snapshot;
- total usage;
- total cost;
- run status;
- eligibility status.

Per-case evidence must include:

- case ID;
- question identity/hash;
- linked schema;
- grounded value evidence;
- bounded tool trajectory;
- linker turn/tool counts;
- generator turn/tool counts;
- final SQL;
- syntax validity;
- safety status;
- execution status;
- execution correctness;
- error category;
- token usage;
- cost;
- latency.

Do not store private hidden reasoning or chain-of-thought.

## 19. Cost constraints

The system must remain suitable for a low-budget internship experiment.

Before every paid evidence run:

- estimate worst-case model turns;
- estimate worst-case tool-result context;
- estimate maximum input/output usage;
- calculate a conservative spend ceiling;
- abort before the first API call if the configured budget would be exceeded.

During a paid run:

- known spend plus the conservative remaining bound must remain below the limit before the next API call;
- automatic retry is disabled;
- partial evidence must be preserved if the run stops.

The public-dev experiment series must use an explicit budget ceiling.

## 20. Historical result handling

Current preserved R2 public-pilot evidence includes:

- model run under scorer v1: 2/8 Execution Accuracy;
- offline replay of the same saved SQL under scorer v2: 5/8 Execution Accuracy.

The 5/8 result is not a new model run.

Therefore:

- it must not be used as the E0 optimization baseline;
- it must not be described as model improvement;
- E0 must be generated again under the same experimental contract as E1-E3.

The final report must make this distinction explicit.

## 21. Required implementation outputs

The implementation agent must deliver the following classes of output.

### 21.1 Runtime capability

A working inference-time system that supports:

- E0;
- E1;
- E2;
- E3;
- bounded Schema Linking Agent;
- bounded SQL Generation Agent;
- Database Profiler;
- Value Search;
- SQL Probe Executor;
- final evaluation through the existing R2 evaluator.

### 21.2 Verification capability

Automated verification must cover at minimum:

- gold isolation;
- read-only SQL safety;
- external-data access rejection;
- internal/provenance table rejection;
- turn limits;
- tool-call limits;
- malformed tool calls;
- invalid linked schema;
- invented grounded values;
- experiment-specific tool availability;
- deterministic profiler output;
- deterministic value-search catalog;
- bounded tool outputs;
- budget rejection before paid inference;
- provenance/hash consistency.

### 21.3 Evidence artifacts

Results must be stored under the existing R2 evaluation-results area as immutable versioned artifacts.

At minimum preserve one valid public-dev run for each:

- E0;
- E1;
- E2;
- E3.

Artifacts must be append-only.

### 21.4 Public-dev result document

Required contents:

- exact architecture of E0-E3;
- correct-case count for each experiment;
- Execution Accuracy;
- Syntax Validity;
- Execution Success;
- Safety Rejection;
- tool/turn diagnostics;
- token usage;
- API cost;
- latency;
- per-case result table;
- error analysis;
- exact provenance;
- limitations;
- explicit statement that public-dev is diagnostic.

### 21.5 Official-dev configuration lock

After public-dev:

- select the winning configuration using only public-dev;
- record exact configuration;
- freeze prompts/tools/model/catalog/scorer/snapshot contract;
- preserve the lock before official-dev evaluation.

### 21.6 Official-dev evidence

After the real three-source official snapshot is available:

- run E0;
- run the frozen winning configuration;
- compare results;
- perform per-case error analysis;
- do not change architecture during the comparison.

### 21.7 Frozen final evidence

After official-dev review and final lock:

- run frozen holdout once;
- preserve results;
- do not tune using frozen;
- include frozen outcome in final internship report.

## 22. Public-dev architecture selection rule

Select the configuration using this deterministic priority:

1. highest Execution Accuracy;
2. lower total API cost;
3. fewer total model calls;
4. lower total latency;
5. if still tied, simpler architecture in the order E0, E1, E2, E3.

The selection rule must be recorded before frozen evaluation.

## 23. Acceptance criteria

The work is acceptable only when all applicable conditions below are satisfied.

### Methodology

- Execution Accuracy remains the primary metric.
- E0-E3 are directly comparable.
- No gold leakage exists.
- Frozen was not used for tuning.
- Scorer changes are separated from model changes.

### Architecture

- Schema Linker and SQL Generator are separate roles.
- Same pinned model configuration is used by both roles.
- Database tools are bounded and read-only.
- E0/E1/E2/E3 differ exactly according to the experiment matrix.

### Safety

- Probe SQL cannot modify data.
- Probe SQL cannot read external files or URLs.
- Probe SQL cannot access internal solution/provenance data.
- Production systems cannot be contacted.

### Reproducibility

- prompts are versioned;
- tools are versioned;
- search catalog is versioned;
- snapshot is hashed;
- benchmark is hashed;
- scorer is hashed;
- model identity is verified;
- run artifacts are immutable.

### Experimental output

- new E0 baseline exists;
- E1 result exists;
- E2 result exists;
- E3 result exists;
- accuracy and absolute counts are reported;
- cost and latency are reported;
- failures are analyzed;
- public-dev limitations are stated.

### Progression gates

- official dev does not start before three-source data gate passes;
- frozen does not open before final configuration lock;
- frozen is never used to select architecture.

## 24. What the implementation agent must not do

The agent must not:

- introduce RL because it appears in the DualSQL paper;
- fine-tune a model;
- replace the VinSOC scorer with REX;
- silently change benchmark cases;
- silently change gold SQL;
- create mock official benchmark data;
- open frozen early;
- tune prompts against frozen;
- compare new runs against the historical 5/8 replay as if that were a model baseline;
- add CHASE-style multi-candidate voting into E0-E3;
- add unrelated SOC features;
- modify R1;
- modify triage methodology;
- redesign VinSOC architecture outside the R2 optimization boundary;
- claim paper-level performance;
- claim statistical significance from 8 public-dev cases.

## 25. Secondary research direction

CHASE-SQL remains a secondary reference only.

Multi-candidate generation or selection may be studied later if DualSQL-Lite experiments expose a separate candidate-selection bottleneck.

It must not be mixed into the first E0-E3 DualSQL-Lite experiment series because that would prevent clear attribution of the observed improvement.

## 26. Final expected conclusion

At the end of the work, the evidence should allow an independent reviewer to answer:

- What was the controlled one-shot baseline?
- Did schema linking improve Text-to-SQL accuracy?
- Did database interaction improve accuracy?
- Did the combined two-agent architecture improve accuracy?
- Which specific error classes changed?
- What additional inference cost was required?
- Did the selected architecture remain effective on official dev?
- What was the final frozen-holdout result?
- Were all claims reproducible from preserved artifacts?

If the answer to these questions cannot be derived from the produced artifacts, the implementation is incomplete.
