# DualSQL-Lite Text-to-SQL Optimization Design

**Status:** Proposed replacement design; awaiting user review before implementation planning
**Date:** 2026-09-25
**Scope:** VinSOC R2 Text-to-SQL optimization only
**Primary reference:** docs/references/dualsql-arxiv-2609.18135.md
**Supersedes:** docs/superpowers/specs/2026-09-25-chase-lite-text-to-sql-optimization-design.md

## 1. Purpose and unchanged project objective

This design changes the optimization architecture only. It does not change the internship objective, R2 evaluator, benchmark protocol, or required evidence.

VinSOC still has two mentor-facing evaluation tracks:
- R1: Tool Calling Evaluation.
- R2: Text-to-SQL Evaluation.

This specification concerns R2 only.

The unchanged R2 objective is:

> Measure Text-to-SQL accuracy reproducibly on VinSOC SOC data, identify failure modes, apply a controlled improvement, and demonstrate the effect with versioned before/after experiments without contaminating the frozen holdout.

The primary R2 metric remains Execution Accuracy under the existing deterministic DuckDB evaluator.

The required evidence remains:
- reproducible dev and frozen benchmark protocol;
- real-model results, not mock results;
- versioned model/config/prompt/snapshot/scorer identities;
- before/after comparison;
- per-case error analysis;
- cost/token/latency accounting;
- clear distinction between model-generation changes and scorer-only changes;
- frozen holdout used only after the final configuration is fixed.

No training or fine-tuning is added by this design.

## 2. Why the optimization design is changing

The previous CHASE-Lite design focused on generating multiple SQL candidates and selecting among them. That remains a valid research direction, but the active reference selected for VinSOC is now DualSQL.

DualSQL frames Text-to-SQL around two coupled tasks:
1. schema linking - identify relevant tables and columns for a question;
2. SQL generation - generate the SQL using the linked schema.

Both agents in the paper share one LLM backbone and can interact with the database through three tools:
- SQL Executor;
- Full Text Search;
- Database Profiler.

The paper jointly trains these roles with multi-agent reinforcement learning. VinSOC will not reproduce the RL training. This design adapts only the inference-time decomposition and database-grounded tool interaction.

This direction matches observed VinSOC R2 failure modes. A model can understand the user intent but still miss the stored representation, for example:

~~~
"scenario 5"
    -> source_dataset = 'ctu13_s5'

"From-Botnet"
    -> label values such as 'flow=From-Botnet-...'
~~~

These are schema/value-grounding failures before they are SQL-syntax failures.

## 3. Research question

Primary question:

> Does a DualSQL-inspired two-agent pipeline - Schema Linking Agent followed by SQL Generation Agent, both using the same pinned LLM and bounded read-only database tools - improve VinSOC R2 Execution Accuracy over the current one-shot baseline without model training?

Secondary questions:
1. Does a separate schema-linking stage improve final SQL accuracy?
2. Does interactive database tool use improve accuracy without a separate linker?
3. Does combining schema linking and interactive SQL generation provide additional benefit?
4. Which failures remain after linking and database interaction?
5. What accuracy gain is obtained for added API calls, tokens, latency, and cost?

The design does not ask whether VinSOC can reproduce the RL gains reported by DualSQL.

## 4. Research basis and adaptation boundary

DualSQL is a 2026 arXiv preprint that uses:
- one shared Qwen3 backbone;
- a Schema Linking Agent;
- a SQL Generation Agent;
- SQL Executor, Full Text Search, and Database Profiler tools;
- multi-agent reinforcement learning;
- training-time rollout guardrails;
- Robust Execution Match (REX) as part of its correctness/reward machinery.

The paper reports 68.0% Execution Accuracy for DualSQL-4B and 71.1% for DualSQL-8B on BIRD-Dev after training.

Those are paper results, not VinSOC expectations.

### 4.1 Adopted from DualSQL

VinSOC adopts:
- explicit separation of schema linking from SQL generation;
- the same model configuration for both roles;
- multi-turn database-grounded reasoning;
- three analogous database-access capabilities:
  - database profiling;
  - value/schema search;
  - SQL execution/probing;
- generator recovery when the initial linked schema is incomplete;
- controlled ablation between one-shot, one-agent tool use, two-stage linking, and the combined pipeline.

### 4.2 Not adopted

VinSOC does not adopt in the current project:
- reinforcement learning;
- GRPO or policy optimization;
- Qwen3 training;
- supervised fine-tuning;
- reward shaping;
- rollout-loss masking;
- RL-specific collapse-prevention mechanisms;
- paper-scale training data preparation;
- REX as a training reward;
- any claim that the inference-only adaptation reproduces DualSQL trained behavior.

REX is not a replacement for VinSOC headline scoring in this design. Existing Execution Accuracy remains authoritative.

## 5. Existing VinSOC R2 baseline

The merged public pilot remains the diagnostic sandbox.

Current preserved evidence includes:
- 8 R2 public-dev cases;
- a verified DuckDB snapshot built from CTU-13 scenarios 5 and 7 plus OTRF APT29 Day 1 Sysmon data;
- logical snapshot content SHA-256: 8dc07dd60d9222776ff3438bedd8488582e95f53d7b8052bbd510adad73cc42e;
- preserved model-run output using gpt-4.1-mini-2025-04-14;
- original scorer-v1 model-run Execution Accuracy: 2/8;
- offline scorer-v2 replay on the same saved SQL: 5/8.

The 5/8 replay is a scorer-policy result, not a new model-generation result.

For optimization experiments, E0 must therefore be a new baseline run under the same experiment contract as E1-E3. The historical 5/8 replay must never be used as the optimization baseline.

## 6. Design principles

### 6.1 Existing evaluator stays independent

evaluation/text_to_sql.py remains the source of truth for final correctness.

The optimization pipeline may inspect the database during inference, but it may not:
- modify evaluator semantics;
- read gold SQL;
- read gold result rows;
- read the current-case correctness verdict;
- change a failed answer after seeing evaluator output.

Final scoring occurs only after the SQL Generation Agent submits its final SQL.

### 6.2 Gold blindness

Before final submission:
- Schema Linking Agent does not receive gold_sql;
- SQL Generation Agent does not receive gold_sql;
- database tools do not expose gold data;
- no agent receives execution-accuracy labels;
- no tool response contains benchmark solution annotations.

Gold data is available only to post-hoc evaluation and diagnostic analysis.

### 6.3 Same model, different roles

Both agents use the same pinned provider/model/configuration.

The distinction is created by:
- different system prompts;
- different task contracts;
- different final output formats.

No separate trained model is required.

### 6.4 Database interaction is bounded

Tool access is read-only, deterministic at the tool layer, size-bounded, and fully logged.

The model may choose which tool to call, but cannot bypass:
- SQL safety validation;
- table allowlists;
- row/output limits;
- turn limits;
- tool-call limits;
- cost gates.

### 6.5 Controlled experiments, not architecture shopping on frozen

Public-dev is used to compare architectures.
Official dev is used to validate the chosen approach on the official three-source snapshot.
Frozen holdout remains sealed until the full configuration is frozen.

## 7. Target architecture

~~~
Natural-language question
          |
          v
+-----------------------------+
| Schema Linking Agent        |
| same pinned LLM             |
|                             |
| tools:                      |
| - Database Profiler         |
| - Value Search              |
| - SQL Probe Executor        |
+-------------+---------------+
              |
              v
       LinkedSchemaResult
       - relevant tables
       - relevant columns
       - grounded values
              |
              v
+-----------------------------+
| SQL Generation Agent        |
| same pinned LLM             |
| receives linked schema      |
|                             |
| tools:                      |
| - Database Profiler         |
| - Value Search              |
| - SQL Probe Executor        |
+-------------+---------------+
              |
              v
          Final SQL
              |
              v
+-----------------------------+
| Existing VinSOC R2 Evaluator|
| syntax / safety / DuckDB    |
| result comparator           |
+-------------+---------------+
              |
              v
       Execution Accuracy
~~~

The SQL Generation Agent can access database tools after schema linking. This is intentional: if the linker's subset is incomplete, the generator can recover missing context before final submission.

## 8. Gold-blind inter-agent contract

The Schema Linking Agent must finish with a strict JSON object.

Conceptual shape:

~~~json
{
  "tables": {
    "network_flows": [
      "source_dataset",
      "label",
      "protocol",
      "dst_port"
    ]
  },
  "value_evidence": [
    {
      "table": "network_flows",
      "column": "source_dataset",
      "value": "ctu13_s7",
      "source_tool": "value_search"
    }
  ]
}
~~~

Required properties:
- every table exists in the verified snapshot;
- every column belongs to the stated table;
- every value-evidence entry is traceable to a tool response;
- no SQL solution is included;
- hidden reasoning is not required;
- output order is canonicalized before hashing.

Unknown or invalid tables/columns make the link result invalid for that case.

The SQL Generation Agent receives:
- original question;
- linked tables/columns;
- linked value evidence;
- compact linked-schema rendering;
- database tools when the experiment permits them.

It does not receive hidden linker reasoning.

## 9. Database access tools

DualSQL uses SQL Executor, Full Text Search, and Database Profiler. VinSOC adapts those concepts to DuckDB.

### 9.1 Database Profiler

VinSOC tool name: profile_database

Purpose:
- inspect available tables and columns;
- retrieve deterministic metadata;
- reduce hallucination about schema shape.

Returned metadata may include:
- table name;
- column name;
- DuckDB data type;
- null count or ratio;
- distinct-value count;
- numeric/timestamp min/max when safe;
- bounded top values only for low-cardinality columns.

The first implementation does not use another LLM to generate semantic descriptions or infer foreign keys. This differs from DualSQL and avoids another unmeasured model dependency.

Profiler output is deterministic for a fixed verified snapshot.

### 9.2 Value Search

VinSOC tool name: search_database_values

Purpose:
- connect natural-language mentions to actual stored literals;
- expose bounded examples such as dataset IDs, labels, hostnames, or image paths.

VinSOC does not require SQLite FTS5 because the evaluation database is DuckDB.

Implementation contract:
- build a deterministic searchable catalog from approved textual columns;
- search table/column names and cataloged values using normalized token, substring, and bounded fuzzy matching;
- return at most 5 matched values per column;
- return at most 50 values total per tool call;
- preserve exact database literals;
- record source table and column for every value;
- hash the catalog used by the run.

The search catalog is derived only from the evaluation snapshot. It contains no gold-query information.

### 9.3 SQL Probe Executor

VinSOC tool name: execute_sql_probe

Purpose:
- inspect literal representations;
- validate assumptions;
- test candidate filters/joins/aggregations;
- provide execution errors for self-correction.

Constraints:
- only SELECT or WITH ... SELECT;
- same read-only policy as existing VinSOC DuckDB execution;
- no DDL/DML/PRAGMA/ATTACH/INSTALL/LOAD;
- benchmark data tables only;
- no access to internal solution artifacts;
- maximum 20 returned rows;
- maximum serialized response size 8192 bytes;
- deterministic truncation marker;
- every query and response metadata recorded.

A zero-row result is not considered an error.

## 10. Agent runtime contract

### 10.1 Shared configuration

For evidence runs:
- provider: OpenAI;
- model: gpt-4.1-mini-2025-04-14 unless explicitly re-frozen before the experiment series;
- temperature: 0;
- SDK retries: 0;
- fixed completion cap;
- same model/config for both agent roles.

A model change requires a new experiment version and restarts the before/after comparison.

### 10.2 Schema Linking Agent

Input:
- user question;
- complete schema rendering;
- tool schemas.

Responsibilities:
1. identify likely tables and columns;
2. use profiler/search/probe tools when needed;
3. ground database literals when the question refers to encoded values;
4. submit LinkedSchemaResult.

Hard limits:
- maximum 5 model turns;
- maximum 5 tool calls;
- maximum one final schema submission;
- no final SQL.

If the model fails to submit a valid link result before the limit, record LINKER_FORMAT_OR_LIMIT_FAILURE for the case.

This is a model outcome, not an infrastructure-invalid run.

### 10.3 SQL Generation Agent

Input:
- user question;
- validated linked schema;
- linked value evidence;
- linked-schema rendering;
- tool schemas when experiment permits tool use.

Responsibilities:
1. interpret the question against linked schema/value evidence;
2. recover missing schema context through tools when allowed;
3. test hypotheses with read-only execution when useful;
4. submit exactly one final SQL statement.

Hard limits:
- maximum 5 model turns;
- maximum 5 tool calls;
- one final SQL;
- no post-evaluator retry.

If no valid final SQL is submitted by the limit, the case is a Text-to-SQL failure.

### 10.4 Infrastructure vs model failures

Model-behavior failures count against the experiment:
- malformed link result;
- no final SQL;
- unsafe generated SQL;
- syntax failure;
- execution failure;
- incorrect result.

Run-invalidating failures include:
- wrong actual provider/model;
- missing or unverifiable provider usage when usage is required;
- snapshot/hash mismatch;
- scorer/hash mismatch;
- benchmark case mismatch;
- provider outage preventing completion of the fixed run;
- dirty/unpinned evidence checkout;
- budget gate failure.

Invalid runs are not scored as official comparable experiments.

## 11. Experiment matrix

The optimization study is intentionally smaller than the superseded CHASE-Lite matrix.

| ID | Separate Schema Linker | Linker DB Tools | SQL Generator DB Tools | Purpose |
|---|---:|---:|---:|---|
| E0 | No | No | No | One-shot baseline under new contract |
| E1 | Yes | Yes | No | Test explicit schema linking and pruning |
| E2 | No | N/A | Yes | Test interactive DB grounding without two-agent split |
| E3 | Yes | Yes | Yes | Full DualSQL-Lite inference architecture |

### 11.1 E0 - One-shot baseline

~~~
question + full schema
        |
        v
one model call
        |
        v
final SQL
~~~

No database tools are exposed.

### 11.2 E1 - Schema Linker + static SQL Generator

~~~
question + full schema
        |
        v
Schema Linking Agent + tools
        |
        v
linked schema/value evidence
        |
        v
one-shot SQL Generator
(no DB tools)
        |
        v
final SQL
~~~

This measures explicit schema/value grounding plus context pruning.

### 11.3 E2 - Single Agentic SQL Generator

~~~
question + full schema
        |
        v
SQL Generation Agent + tools
        |
        v
final SQL
~~~

No separate schema-linker stage.

This measures whether tool-grounded multi-turn SQL generation alone explains improvement.

### 11.4 E3 - DualSQL-Lite

~~~
question + full schema
        |
        v
Schema Linking Agent + tools
        |
        v
linked schema/value evidence
        |
        v
SQL Generation Agent + tools
        |
        v
final SQL
~~~

This is the closest inference-only VinSOC adaptation of DualSQL.

### 11.5 Interpretation

Useful comparisons:
- E1 vs E0: effect of explicit schema linking;
- E2 vs E0: effect of interactive DB tools in SQL generation;
- E3 vs E1: added value of generator-side tool recovery;
- E3 vs E2: added value of a separate schema-linking stage when generator tools exist.

Do not assume E3 must win. Final configuration is selected from measured results.

## 12. Metrics

### 12.1 Primary metric

Execution Accuracy from the existing VinSOC R2 evaluator.

### 12.2 Existing diagnostics

Continue reporting:
- Syntax Validity;
- Execution Success;
- Safety Rejection;
- per-category accuracy;
- per-difficulty accuracy when case counts permit.

### 12.3 Agentic diagnostics

Add non-headline diagnostics:
- linker completion rate;
- average linker turns;
- average linker tool calls;
- average SQL-generator turns;
- average SQL-generator tool calls;
- profiler usage rate;
- value-search usage rate;
- SQL-probe usage rate;
- linked table count;
- linked column count;
- generator schema-recovery count;
- malformed agent-output count.

These explain behavior; they do not replace Execution Accuracy.

### 12.4 Optional schema-linking diagnostics

If reviewer-authored schema-gold annotations are added, they must be:
- stored separately from model inputs;
- frozen before paid evidence runs;
- derived only for evaluation;
- never exposed to either agent.

Possible metrics:
- table precision/recall/F1;
- column precision/recall/F1;
- complete schema recall.

These are optional and not required for the R2 headline result.

### 12.5 Efficiency

Every experiment reports:
- model calls per case;
- tool calls per case;
- input tokens;
- output tokens;
- total cost;
- cost per case;
- latency;
- average turns.

Accuracy must be presented with compute/cost.

## 13. Error taxonomy

Post-hoc analysis may use:
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

Taxonomy annotations are analysis only and never scorer inputs.

## 14. Benchmark protocol

### 14.1 Stage A - public_dev

Use the existing 8 public R2 cases as a diagnostic sandbox.

During E0-E3 keep fixed:
- case questions;
- gold SQL;
- comparators;
- logical snapshot content;
- scorer;
- model;
- temperature;
- tool implementations;
- tool response limits.

Each case is 12.5 percentage points. Public-dev is not sufficient for broad statistical claims.

A gain of at least 2/8 cases over the newly generated E0 remains the threshold for a strong pilot signal, not statistical proof.

### 14.2 Stage B - official dev

Once the official three-source snapshot is complete:
1. freeze snapshot and manifest;
2. freeze benchmark cases;
3. freeze scorer;
4. freeze model/config;
5. freeze agent prompts;
6. freeze tool implementations and search-catalog construction;
7. run E0 and the public-dev winning architecture on official dev;
8. perform error analysis.

The official dataset remains the planned ThreatFox + CTU-13 + OTRF composition.

### 14.3 Stage C - frozen holdout

Frozen remains sealed through public-dev and official-dev tuning.

Before opening frozen, record:
- git SHA;
- model;
- temperature;
- role prompts and hashes;
- tool schemas;
- tool implementation hashes;
- search-catalog hash;
- snapshot hash;
- benchmark hash;
- scorer hash;
- final selected experiment configuration.

Frozen is then run once unless a documented infrastructure/provider failure invalidates the run.

## 15. Tool data and snapshot integrity

Database tools operate on the same verified evaluation snapshot and may not mutate it.

Derived artifacts such as the value-search catalog must record:
- source snapshot content SHA;
- builder version;
- catalog SHA;
- row/value counts;
- deterministic construction parameters.

Changing catalog construction changes the experiment version.

## 16. Security and safety boundary

All generated/probe SQL remains offline.

Requirements:
- read-only DuckDB;
- existing SELECT-only policy;
- no multi-statement execution;
- no ATTACH/INSTALL/LOAD/PRAGMA;
- no production database connection;
- no network access from SQL;
- bounded row output;
- bounded serialized tool output;
- agent tools expose only benchmark data;
- no secrets/API keys written to results.

The SQL Generation Agent may execute candidate SQL for feedback, but final correctness still comes from the existing evaluator.

## 17. Prompt and tool versioning

Each role prompt is versioned independently:
- schema_linker_prompt_v1;
- sql_generator_prompt_v1.

Each evidence report records prompt SHA-256 values.

Tool interfaces are versioned:
- profile_database_v1;
- search_database_values_v1;
- execute_sql_probe_v1.

Changes to prompt text, tool schema, tool behavior, limits, or search algorithm require a new experiment version.

## 18. Cost and budget gate

Before a paid run, preflight must estimate a conservative worst case using:
- 5 model turns for linker when present;
- 5 model turns for generator;
- maximum completion cap per turn;
- maximum tool-response sizes;
- every case in the split.

Public-dev evidence uses an explicit experiment budget ceiling and fails before the first provider call if the ceiling is exceeded.

During execution, known cost plus conservative remaining-call cost must remain below the ceiling before the next model call.

No automatic retry is allowed in evidence mode.

## 19. Run artifact contract

Each experiment writes an append-only JSON artifact.

Required run-level fields:
- run_id;
- experiment_id;
- git_sha;
- benchmark_version;
- benchmark_split_sha256;
- snapshot_content_sha256;
- scorer_sha256;
- provider;
- requested_model;
- actual_model;
- temperature;
- completion_cap;
- schema_linker_prompt_sha256;
- sql_generator_prompt_sha256;
- tool_schema_sha256;
- tool_implementation_sha256;
- search_catalog_sha256;
- preflight;
- aggregate_metrics;
- total_usage;
- total_cost;
- run_status;
- eligibility.

Required per-case fields:
- case_id;
- question_hash;
- linked_schema;
- value_evidence;
- linker_turn_count;
- linker_tool_calls;
- generator_turn_count;
- generator_tool_calls;
- tool_trajectory_summary;
- final_sql;
- syntax_valid;
- safety_rejected;
- execution_success;
- execution_accurate;
- error_category;
- input_tokens;
- output_tokens;
- cost;
- latency.

Do not store hidden chain-of-thought. Persist only tool calls, bounded tool results, final structured schema output, final SQL, and concise explicit reason/error codes.

## 20. Required experiment outputs

The required deliverables remain unchanged in purpose.

### Code/evaluation output
- reproducible E0-E3 runner;
- deterministic database tools;
- fail-closed budget/provenance gates;
- tests for gold isolation, SQL safety, turn limits, tool limits, and reproducibility.

### Evidence output

results/evaluation_v1/r2_optimization/

with immutable run JSON files.

### Documentation output

A result document must contain:
- baseline Execution Accuracy;
- optimized Execution Accuracy;
- absolute case counts;
- percentage-point delta;
- syntax/execution/safety diagnostics;
- API/tool calls;
- tokens/cost/latency;
- per-case error analysis;
- limitations;
- exact version/provenance identifiers.

### Mentor-facing conclusion

The final report must answer:
1. What was the original R2 baseline?
2. What architecture change was tested?
3. Which part - schema linking, tool interaction, or both - changed performance?
4. Which errors were fixed?
5. Which errors remain?
6. What did the improvement cost?
7. Did the result hold on official dev and frozen holdout?

## 21. Proposed code boundaries

Proposed structure:

~~~
evaluation/
  text_to_sql.py
  text_to_sql_agentic/
    __init__.py
    models.py
    prompts.py
    profiler.py
    value_search.py
    tools.py
    schema_linker.py
    sql_generator.py
    runner.py
    metrics.py
    budget.py
    provenance.py

scripts/
  run_r2_agentic_optimization.py

tests/
  test_text_to_sql_agentic_models.py
  test_text_to_sql_agentic_profiler.py
  test_text_to_sql_agentic_value_search.py
  test_text_to_sql_agentic_tools.py
  test_text_to_sql_agentic_schema_linker.py
  test_text_to_sql_agentic_sql_generator.py
  test_text_to_sql_agentic_runner.py
  test_text_to_sql_agentic_budget.py
  test_text_to_sql_agentic_gold_isolation.py
~~~

The implementation plan may adjust filenames to follow repository patterns, but responsibilities and isolation boundaries remain.

## 22. Critical tests required before paid runs

### Gold isolation

Use a poison gold literal and prove it never appears in:
- linker messages;
- generator messages;
- tool calls;
- tool results.

### Tool safety

Verify:
- DELETE/UPDATE/INSERT/DDL are rejected;
- multiple statements are rejected;
- terminal semicolon remains allowed under current policy;
- internal non-benchmark tables are unavailable;
- output limits are enforced.

### Schema contract

Verify:
- nonexistent tables/columns are rejected;
- value evidence is tied to a real table/column/tool result;
- duplicate schema items canonicalize deterministically.

### Recovery

Build a fixture where the linker omits one required column.

E1 must remain constrained by the linked schema and fail or produce the corresponding wrong answer.

E3 must be able to use a database tool to recover missing schema and produce correct SQL in the controlled fixture.

### Experiment isolation

Prove:
- E0 exposes no tools;
- E1 uses linker tools but generator has no tools;
- E2 skips linker and gives tools to generator;
- E3 uses both stages and permits generator recovery.

### Budget

Prove a worst-case run reaching the budget ceiling fails before the first paid API call.

## 23. Success criteria

### Correctness gate
- no gold leakage;
- existing R2 scorer remains authoritative;
- SQL safety is unchanged or stricter;
- frozen remains unopened during tuning.

### Public-dev optimization signal

E_best improves by at least 2/8 cases over newly run E0 to qualify as a strong pilot signal.

If the gain is smaller, report the exact result without claiming strong improvement.

### Interpretability gate

The experiment matrix must distinguish:
- benefit from schema linking;
- benefit from SQL-agent database tools;
- benefit from combining both.

### Efficiency gate

Accuracy is always paired with model calls, tool calls, tokens, cost, and latency.

### Reproducibility gate

All evidence identifies model/config, prompts, tool versions, search catalog, snapshot, benchmark, scorer, and git commit.

## 24. Risks and mitigations

### Inference-only adaptation may not reproduce DualSQL gains

DualSQL includes joint RL training.

Mitigation: label VinSOC explicitly as an inference-time architectural adaptation and compare only against VinSOC own baseline.

### Tool use can increase cost and latency

Mitigation: five-turn/five-tool hard caps, early completion, preflight, and per-call budget guards.

### Value search can expose too much database content

Mitigation: approved textual columns, five values per column, fifty values total, output-byte limits, catalog hashing.

### SQL probing can overfit to one finite snapshot

Mitigation: semantic-trap tests, official three-source dev validation, frozen holdout, explicit limitation.

### Schema linker can remove required information

Mitigation: E1 measures this directly; E3 allows generator-side recovery; omission errors are tracked.

### Public benchmark is small

Mitigation: no broad generalization claims; confirm the winning design on official dev before frozen.

## 25. Rollout order

After this spec is approved:
1. write a new implementation plan for DualSQL-Lite;
2. do not execute the superseded CHASE-Lite implementation plan;
3. implement deterministic database tools;
4. implement strict gold-blind agent contracts;
5. implement E0;
6. implement E1;
7. implement E2;
8. implement E3;
9. verify offline tests and CI;
10. freeze one code/config commit;
11. run public-dev E0-E3;
12. perform per-case/error/cost analysis;
13. select E_best without looking at frozen;
14. freeze official-dev configuration;
15. run official dev after three-source snapshot completion;
16. only then freeze and open final holdout.

## 26. Relationship to CHASE-SQL

CHASE-SQL remains a secondary reference for candidate diversity and selection.

It is not part of the first DualSQL-Lite implementation.

If later evidence shows selection or candidate-diversity headroom, CHASE-style multi-candidate generation may be investigated as a separate experiment. It must not be mixed into E0-E3 because that would make attribution unclear.

## 27. Decision summary

The active R2 optimization direction is DualSQL-Lite:

~~~
same pinned LLM
    |
    +--> Schema Linking Agent
    |      + profiler
    |      + value search
    |      + SQL probe
    |
    +--> SQL Generation Agent
           + linked schema/value evidence
           + profiler
           + value search
           + SQL probe
                    |
                    v
                final SQL
                    |
                    v
          existing R2 evaluator
~~~

The project does not train a model.
The primary metric does not change.
The benchmark protocol does not change.
The required result/evidence outputs do not change.

Only the optimization mechanism changes from CHASE-style multi-candidate selection to DualSQL-style schema-linking plus database-grounded agentic SQL generation.
