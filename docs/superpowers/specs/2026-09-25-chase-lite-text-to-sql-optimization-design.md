# CHASE-Lite Text-to-SQL Optimization Design

**Status:** Approved design, implementation not started  
**Date:** 2026-09-25  
**Scope:** VinSOC R2 Text-to-SQL optimization only  
**Primary reference:** [CHASE-SQL, ICLR 2025](../../references/chase-sql-iclr-2025.md)

## 1. Problem

VinSOC R2 already has a deterministic execution-based evaluator, a read-only DuckDB boundary, versioned public pilot cases, and preserved run artifacts. The current one-shot generator can still fail for reasons that are separable:

1. **Value/schema linking** — the model does not know how natural-language phrases map to encoded values such as `ctu13_s5` or labels prefixed with `flow=`.
2. **Reasoning/generation** — a single prompt may produce a semantically wrong query even when the schema is known.
3. **Selection** — a correct SQL candidate may exist among several candidates but not be selected.
4. **Repair** — syntax or execution failures may be fixable without changing the benchmark or scorer.

The design must improve generation while keeping the evaluator independent. It must not leak gold SQL or gold results into generation, selection, or repair.

## 2. Research Question

> Does multi-path SQL generation with lightweight value hints and execution-aware selection improve VinSOC R2 Execution Accuracy over a one-shot baseline when model, benchmark, snapshot, and scorer are held fixed?

Secondary questions:

- Do lightweight value hints reduce value/schema-linking errors?
- Do diverse generation paths increase the probability that at least one correct candidate exists?
- When a correct candidate exists, how often does the selector choose it?
- What accuracy gain is obtained per additional API call, token, dollar, and unit of latency?

## 3. Goals

- Preserve **Execution Accuracy** as the primary R2 headline metric.
- Add a CHASE-inspired optimization layer without replacing `evaluation/text_to_sql.py`.
- Generate exactly three initial candidates per case:
  - Direct SQL
  - Query Plan CoT
  - Divide-and-Conquer CoT
- Add deterministic, query-relevant value hints from the verified snapshot.
- Validate and execute candidates in the existing read-only DuckDB environment.
- Prefer deterministic selection only when executable candidates are unanimous or only one executable candidate remains.
- Use an LLM pairwise selector whenever two or more executable result groups disagree, including 2-vs-1 splits.
- Add one optional repair attempt only in a later phase and only for syntax/execution failures.
- Measure candidate quality, selector quality, diversity, cost, and latency separately.
- Keep `public_dev`, official dev, and frozen holdout roles clearly separated.
- Preserve full run provenance and never overwrite prior result artifacts.

## 4. Non-Goals

The first implementation will **not**:

- fine-tune a selection model;
- implement CHASE-SQL's online synthetic-example generator;
- generate 20+ candidates per case;
- use high-temperature sampling to manufacture diversity;
- perform three repair rounds;
- use the frozen split for prompt or architecture selection;
- expose gold SQL or gold execution results to any generation/selection step;
- allow model-issued SQL to escape the offline read-only evaluation boundary;
- claim statistical generalization from the eight-case public pilot.

## 5. Existing VinSOC R2 Baseline

The merged public pilot provides a reproducible diagnostic sandbox:

- Benchmark version: `r1_r2_network_endpoint_public_dev_v1`
- R2 public cases: 8
- Snapshot tables:
  - `network_flows`
  - `sysmon_process_events`
- Verified logical snapshot content SHA-256:
  `8dc07dd60d9222776ff3438bedd8488582e95f53d7b8052bbd510adad73cc42e`
- Model used by the preserved pilot:
  `gpt-4.1-mini-2025-04-14`
- Preserved v1 model run: 2/8 Execution Accuracy
- Offline replay of the same saved predictions under scorer v2: 5/8 Execution Accuracy
- The 5/8 replay is **not** a new model result and must never be reported as model improvement.

Internal evidence:
- `docs/public_pilot_results_2026-09-25.md`
- `docs/public_pilot_r2_scorer_v2_replay_2026-09-25.md`
- `results/evaluation_v1/public_pilot/public-r2.json`
- `results/evaluation_v1/public_pilot/r2-replay-scorer-v2.json`

## 6. Research Basis

CHASE-SQL (ICLR 2025, Google Cloud + Stanford) improves Text-to-SQL through test-time compute: multiple candidate-generation strategies, value retrieval, query fixing, and candidate selection.

Relevant findings used by this design:

- On BIRD dev with Gemini 1.5 Pro, the paper reports:
  - baseline: 57.75% EX;
  - Query Plan CoT: 63.62%;
  - Divide-and-Conquer CoT: 63.92%;
  - online synthetic examples: 67.09%.
- CHASE-SQL reaches 73.01% EX on BIRD dev and 73.0% on BIRD test.
- Removing value retrieval reduces CHASE-SQL from 73.01% to 70.09%.
- Removing the query fixer reduces it to 69.23%.
- The combined candidate pool has an 82.79% oracle upper bound in the paper's analysis.
- Untuned pairwise selectors are materially weaker than the tuned selector, motivating VinSOC's deterministic-first selection policy.

These numbers are paper evidence, not expected VinSOC outcomes.

## 7. Design Principles

### 7.1 Evaluation and optimization remain separate

The optimization layer outputs one final SQL statement. The existing R2 evaluator remains responsible for:

- syntax validity;
- safety rejection;
- execution success;
- result comparison;
- Execution Accuracy.

Optimization code must not redefine correctness.

### 7.2 Gold blindness

Before final SQL selection:

- no generator sees `gold_sql`;
- no selector sees `gold_sql`;
- no selector sees gold results;
- no repair step sees gold results;
- no component uses Execution Accuracy feedback from the current case.

Gold data is visible only to the final evaluator.

### 7.3 Deterministic-first filtering, selector-aware disagreement

Use database execution to eliminate invalid candidates and collapse execution-equivalent candidates before spending another LLM call. However, do not treat a 2-vs-1 result majority as correctness: CHASE-SQL shows majority/self-consistency can miss a correct minority candidate. E5 therefore invokes the LLM selector whenever two or more executable result groups disagree.

### 7.4 One variable at a time

The experiment matrix isolates value hints, reasoning strategy, multi-path generation, selection, and repair. A single jump from baseline to the complete pipeline is not enough for causal interpretation.

## 8. Architecture

```text
Question
   |
   v
Schema + Value Hint Builder
   |
   +-------------------+-------------------+
   |                   |                   |
   v                   v                   v
Direct SQL        Query Plan CoT    Divide-and-Conquer CoT
   |                   |                   |
   +-------------------+-------------------+
                       |
                       v
              Candidate Normalizer
                       |
                       v
             Syntax + Safety Gate
                       |
                       v
             Read-only DuckDB Execute
                       |
                       v
              Result Fingerprinting
                       |
                       v
           Execution-aware Selector
              |                 |
       unanimous/one       pairwise LLM
        executable          on disagreement
              +--------+--------+
                       |
                       v
                   Final SQL
                       |
                       v
             Existing R2 Evaluator
```

## 9. Component Design

### 9.1 Context and Value Hint Builder

**Responsibility:** Produce deterministic schema context plus a small set of query-relevant values.

The first version will not use embeddings, LSH, or a vector database. It will query only bounded metadata/value summaries from the verified DuckDB snapshot.

Allowed hints:

- low-cardinality categorical values;
- identifiers that directly overlap query tokens or normalized aliases;
- bounded examples from columns explicitly referenced by the question category.

Examples:

```text
network_flows.source_dataset:
- ctu13_s5
- ctu13_s7

network_flows.label examples:
- flow=From-Botnet-TCP-HTTP
- flow=Background-TCP-Established
```

Requirements:

- deterministic ordering;
- hard per-column and total hint limits;
- no full-table dumps;
- no raw arbitrary telemetry rows;
- no gold-derived values;
- no benchmark-case-specific hand-written alias mappings;
- same question + same snapshot => same hints;
- hash the final context for provenance.

### 9.2 Candidate Generators

All generators consume the same question, schema, and value hints.

#### Direct

Produces one SQL query with minimal reasoning instructions. This is the control generator for value-hint experiments.

#### Query Plan

Produces a compact logical plan covering:

1. relevant table(s);
2. filters;
3. grouping/aggregation;
4. ordering/limit;
5. final SQL.

Only the final SQL is required downstream. If a provider returns a concise structured plan, it may be retained as ordinary debug output; hidden/internal reasoning is never required or depended on by the evaluator.

#### Divide and Conquer

Decomposes the question into logical subproblems, resolves them, and composes one final SQL statement.

The generator must still return exactly one executable SQL candidate.

### 9.3 Candidate Normalizer

Normalizes presentation-only differences without changing query semantics.

Allowed:

- strip code fences;
- trim surrounding whitespace;
- accept exactly one terminal semicolon under the pinned scorer policy.

Not allowed:

- rewrite predicates;
- inject missing filters;
- change operators;
- repair semantic logic.

### 9.4 Candidate Executor and Fingerprint

For each candidate:

1. parse using the same DuckDB-compatible syntax checks;
2. run the existing safety gate;
3. execute in read-only DuckDB when allowed;
4. canonicalize the returned rows using the existing comparator semantics;
5. generate a deterministic result fingerprint.

A candidate record stores:

- generator strategy;
- SQL;
- syntax validity;
- safety status;
- execution status;
- result fingerprint when execution succeeds;
- provider token/cost/latency metadata.

### 9.5 Deterministic Selector

Selection order:

1. Remove unsafe candidates.
2. Remove candidates with syntax or execution failure if at least one executable candidate remains.
3. Group executable candidates by result fingerprint.
4. If only one executable result group remains, choose a stable representative without another model call.
5. If two or more executable result groups remain, mark the case as disagreement and hand one stable representative per result group to the next selection stage.

For E4 only, use strict-majority result agreement as a self-consistency baseline; a 2-vs-1 split chooses the majority group. For E5, any disagreement proceeds to the LLM selector so that a correct minority candidate can still win.

Stable representative order is fixed:
`direct > query_plan > divide_and_conquer`.

This ordering is a reproducibility rule, not a claim that Direct is more accurate.

### 9.6 LLM Pairwise Selector

Invoked in E5 whenever two or more executable result groups disagree, including strict 2-vs-1 majorities.

Input contains:

- user question;
- schema;
- value hints;
- candidate SQL A;
- candidate SQL B.

Input does **not** contain:

- gold SQL;
- gold result;
- scorer verdict;
- current-case correctness labels.

Three candidates use a tournament:

```text
A vs B -> winner
winner vs C -> final
```

Maximum tie-breaker calls per case: 2.

The tie-breaker returns only the winning candidate ID plus a concise machine-readable reason code. The winning SQL is copied from the candidate record rather than regenerated.

### 9.7 Query Fixer — Phase 2 Only

The fixer is excluded from the first multi-path experiment.

When enabled later, it may run exactly once and only for:

- `SYNTAX_ERROR`;
- `EXECUTION_ERROR`.

It must not trigger solely because:

- the query returns zero rows;
- the candidate result differs from another candidate;
- the final evaluator reports a result mismatch.

This prevents the fixer from using correctness feedback that would not exist in production.

## 10. Experimental Matrix

| ID | Value hints | Generator(s) | Selector | Fixer |
|---|---|---|---|---|
| E0 | No | Direct | None | No |
| E1 | Yes | Direct | None | No |
| E2 | Yes | Query Plan | None | No |
| E3 | Yes | Divide & Conquer | None | No |
| E4 | Yes | Direct + QP + DC | Majority/self-consistency | No |
| E5 | Yes | Direct + QP + DC | Unanimous early-exit + LLM pairwise selector on disagreement | No |
| E6 | Yes | Best generator set | Best selector | One repair attempt |

Rules:

- E0–E5 use the same pinned model and temperature.
- E0 is re-run under the new experimental contract; the old 5/8 replay is not the optimization baseline.
- E6 is evaluated only after E0–E5 artifacts are frozen and reviewed.
- Prompts are versioned and hashed.
- No experiment modifies benchmark gold data.

## 11. Metrics

### 11.1 Primary metric

**Execution Accuracy**

```text
number of final selected SQL queries whose accepted result matches gold
-----------------------------------------------------------------------
                              case count
```

### 11.2 Candidate Oracle Accuracy (Oracle@3)

A case is an oracle success if at least one generated candidate is correct under the existing evaluator.

This metric is calculated **after** generation and selection are complete, using evaluator labels only for analysis.

Purpose: determine whether generation produced a correct answer even when selection failed.

### 11.3 Selector Conditional Accuracy

Population:

- at least one correct candidate exists; and
- at least one incorrect candidate exists.

Metric:

```text
selector chose a correct candidate
-----------------------------------
        selectable cases
```

### 11.4 Diversity

Per case:

- unique normalized SQL count / candidate count;
- unique execution-result fingerprints / executable candidate count.

### 11.5 Existing diagnostics

Continue to report:

- syntax validity;
- execution success;
- safety rejection;
- error category.

### 11.6 Efficiency

Per experiment and per case:

- API calls;
- input tokens;
- output tokens;
- calculated cost;
- latency;
- selector-call rate;
- repair-call rate.

Accuracy must always be reported together with cost.

## 12. Error Taxonomy

Optimization analysis uses:

- `VALUE_LINKING`
- `SCHEMA_LINKING`
- `PREDICATE_ERROR`
- `BOUNDARY_ERROR`
- `AGGREGATION_ERROR`
- `DISTINCT_ERROR`
- `BOOLEAN_LOGIC`
- `ORDERING_LIMIT`
- `DIALECT_ERROR`
- `SAFETY_REJECTION`
- `EXECUTION_ERROR`
- `SELECTOR_ERROR`
- `MAJORITY_WRONG_MINORITY_CORRECT`
- `NO_CORRECT_CANDIDATE`

The taxonomy is diagnostic. The scorer remains deterministic and does not depend on manually assigned taxonomy labels.

## 13. Benchmark Protocol

### 13.1 Stage A — public_dev diagnostic sandbox

Use the existing eight public R2 cases and the current verified public snapshot.

Do not change during E0–E6:

- question text;
- gold SQL;
- comparators;
- snapshot logical content;
- scorer version within one comparison;
- model within one comparison.

Because 8 cases are small, each case is 12.5 percentage points. Public pilot changes are treated as diagnostic evidence, not proof of generalization.

A gain of at least two cases over E0 is considered a **strong pilot signal**, not a statistically conclusive result.

### 13.2 Stage B — official dev

After the official three-source snapshot is ready, freeze:

- snapshot and manifest;
- benchmark cases;
- scorer;
- model;
- context-builder rules;
- generator prompts;
- selector policy.

Run baseline and the winning public-pilot configuration on official dev.

### 13.3 Stage C — frozen holdout

Frozen is opened only after:

- official dev error analysis is complete;
- final configuration is selected;
- prompt/config/scorer/snapshot hashes are recorded;
- no further architecture tuning is allowed.

Frozen is run once for the final report unless a run is invalidated by a documented infrastructure/provider failure.

## 14. Stability Check

After selecting the best public-dev configuration, run:

- E0 three times;
- E_best three times.

Keep model, temperature, prompts, snapshot, and scorer fixed.

Purpose: measure provider/server nondeterminism even at temperature 0.

Do not repeat all ablations three times.

## 15. Provenance and Artifacts

Every run artifact must include:

- experiment ID;
- git commit SHA;
- benchmark version and split hash;
- snapshot content SHA;
- scorer SHA;
- model/provider;
- temperature;
- prompt hashes;
- context/value-hint hash;
- candidate SQLs;
- candidate strategy;
- syntax/safety/execution status;
- result fingerprints;
- selection path;
- tie-breaker calls and winner;
- final SQL;
- final evaluator verdict;
- token usage;
- latency;
- calculated cost.

Artifacts are append-only. A new run uses a new filename/run ID.

Target directory:

```text
results/evaluation_v1/r2_optimization/
```

## 16. Cost Gate

Before any paid run:

1. serialize all expected generator and worst-case selector requests;
2. compute a conservative token/cost ceiling;
3. include the maximum two tie-break calls per case;
4. include one repair call only for E6;
5. abort before the first API call if the configured experiment budget would be exceeded.

The budget mechanism should reuse the fail-closed behavior established by the public pilot runner.

## 17. Security Boundary

- DuckDB remains read-only.
- Existing SELECT-only/multi-statement safety controls remain authoritative.
- Candidate execution occurs only in the evaluation snapshot.
- No candidate SQL is executed against production systems.
- Value hints are bounded and derived from the evaluation snapshot.
- No secrets, API keys, or private telemetry are written to artifacts.

## 18. Proposed Code Boundaries

```text
evaluation/
  text_to_sql.py                       # existing scorer/evaluator; keep stable
  text_to_sql_optimization/
    __init__.py
    models.py                          # candidate and selection data models
    context.py                         # schema + deterministic value hints
    generators.py                      # Direct / Query Plan / Divide & Conquer
    executor.py                        # validate, execute, result fingerprint
    selector.py                        # grouping, E4 majority, E5 pairwise selector
    fixer.py                           # phase-2 one-shot repair
    metrics.py                         # oracle, selector, diversity, efficiency
    runner.py                          # experiment orchestration

tests/
  test_text_to_sql_optimization_context.py
  test_text_to_sql_optimization_generators.py
  test_text_to_sql_optimization_executor.py
  test_text_to_sql_optimization_selector.py
  test_text_to_sql_optimization_metrics.py
  test_text_to_sql_optimization_runner.py
```

The implementation plan may adjust filenames only if repository inspection reveals an existing pattern that provides a clearer boundary. The architectural responsibilities above remain fixed.

## 19. Success Criteria

### Correctness gate

- zero gold leakage;
- frozen remains unopened during tuning;
- safety/read-only boundary unchanged;
- existing R2 scorer tests stay green.

### Candidate-quality gate

`Oracle@3 > E0 Execution Accuracy`.

If not, multi-path generation provides no measurable candidate-pool benefit on that benchmark.

### Selection gate

The selected final accuracy must recover a meaningful fraction of the oracle gain. A larger oracle score with unchanged final accuracy is classified as a selector bottleneck, not a successful end-to-end improvement.

### Public-pilot signal

E_best should improve by at least 2/8 cases over the newly run E0 to be described as a strong pilot signal.

### Efficiency gate

The final report must show accuracy alongside API calls, tokens, cost, and latency. A configuration may be rejected even if more accurate when compute growth is disproportionate to the gain.

## 20. Risks and Mitigations

### Small benchmark

Eight public cases are diagnostic only.

**Mitigation:** use public_dev for architecture selection, then validate on a larger official dev before frozen.

### Execution-equivalent but semantically wrong SQL

Different SQL can return the same result on one finite snapshot.

**Mitigation:** keep semantic counterexample tests, preserve result-vs-semantic caveat, and expand official snapshot diversity.

### Selector over-trust

An untuned LLM selector may choose incorrect candidates.

**Mitigation:** deterministic result agreement first; LLM only for unresolved disagreement; report selector conditional accuracy.

### Value-hint leakage or overexposure

Dumping too many values can make the benchmark easier in an unrealistic way.

**Mitigation:** bounded deterministic retrieval rules, prompt/context hashes, and separate E0/E1 ablation.

### Cost explosion

Three generators plus selector calls can multiply inference cost.

**Mitigation:** exactly three initial candidates, deterministic early exit, maximum two selector calls, no fixer until E6, fail-closed preflight.

## 21. Rollout Order

1. Add CHASE-SQL reference note.
2. Implement data models and deterministic context/value hints.
3. Implement the three generators.
4. Implement candidate execution/fingerprinting.
5. Implement deterministic selector.
6. Add LLM tie-breaker.
7. Add optimization metrics and run artifacts.
8. Run E0–E5 on public_dev under a pinned experimental contract.
9. Review error taxonomy and cost.
10. Add one-shot fixer as E6 only if the first experiment justifies it.
11. Run stability check for E0 and E_best.
12. Freeze the winning architecture before official dev.
13. After official dev review, freeze final configuration and run frozen holdout.

## 22. Decision Summary

VinSOC will implement **CHASE-Lite**, not a full CHASE-SQL reproduction.

Adopted:

- lightweight value retrieval;
- Direct + Query Plan + Divide-and-Conquer candidate generation;
- test-time multi-path generation;
- execution-aware selection;
- pairwise LLM selection on executable disagreement;
- later one-shot repair;
- oracle/selector/diversity metrics.

Deferred:

- online synthetic-example generator;
- trained selector;
- large candidate pools;
- repeated repair;
- high-temperature sampling.

The existing R2 evaluator remains the single source of truth for correctness.
