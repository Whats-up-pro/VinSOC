# DualSQL Reference for VinSOC R2

## Citation

**Title:** DualSQL: Text-to-SQL with Multi-Agent Reinforcement Learning
**Authors:** Shijie Chen, Yu Gan, Yeounoh Chung, Jiani Zhang, Quannan Li, Sravan Babu Bodapati, Cody J. Greer, Yu Su, Fatma Ozcan
**Version used:** arXiv:2609.18135v1
**Submitted:** 2026-09-16
**Primary URL:** https://arxiv.org/abs/2609.18135
**Project-owner source:** https://arxiv.org/html/2609.18135v1

## Source-derived notes

DualSQL organizes Text-to-SQL around two agents:
1. Schema Linking Agent.
2. SQL Generation Agent.

Both roles use one shared LLM backbone and the same agentic scaffold in the paper.

The agents can interact with the database using three tools.

### SQL Executor

Used for execution feedback, literal/entity grounding, and ad-hoc database/schema exploration. The paper bounds/truncates tool outputs to control context size.

### Full Text Search

Uses fuzzy search over schema names and database cell values to connect ambiguous natural-language mentions with literal database content. The paper returns up to five matched values per column.

### Database Profiler

Uses precomputed database metadata. The paper describes:
- semantic descriptions for tables/columns;
- inferred foreign-key relationships;
- column statistics such as distinct counts, data types, and null ratios.

The semantic descriptions and inferred relationships are generated offline in the paper.

## Agent behavior

### Schema Linking

The linker receives the natural-language question and complete database schema and identifies a relevant subset of tables/columns.

The paper evaluates schema linking using precision, recall, F1, and Complete Recall.

DualSQL-8B reports schema-linking F1 of 90.8 and Complete Recall of 65.8 on BIRD-Dev.

### SQL Generation

The SQL generator receives linked context and can continue using database tools during multi-turn reasoning.

The paper notes that generator-side interaction can recover from imperfect initial schema linking.

Reported average tool calls for DualSQL-8B on BIRD-Dev:

| Stage | SQL Execution | Full Text Search | Database Profiler | Total |
|---|---:|---:|---:|---:|
| Schema Linking | 0.25 | 0.00 | 1.00 | 1.26 |
| SQL Generation | 1.22 | 0.05 | 0.49 | 1.76 |

## Training components

DualSQL jointly optimizes schema linking and SQL generation using multi-agent reinforcement learning.

The paper also introduces:
- rollout guardrail mechanisms for stable training;
- Robust Execution Match (REX) as a SQL correctness/reward metric.

These are important parts of the paper contribution.

## Reported BIRD-Dev results

| Model | Execution Accuracy |
|---|---:|
| DualSQL-4B | 68.0% |
| DualSQL-8B | 71.1% |

These are DualSQL paper results and must not be presented as VinSOC results.

## VinSOC adaptation

VinSOC uses DualSQL as an architecture reference, not as a reproduction target.

### Adopt
- two roles: schema linker + SQL generator;
- one shared/pinned LLM configuration for both roles;
- multi-turn database grounding;
- profiler, value-search, and SQL-probe capabilities;
- generator-side recovery when initial schema linking is incomplete;
- ablation against one-shot and one-agent baselines.

### Do not adopt in current scope
- RL training;
- Qwen3 fine-tuning;
- GRPO;
- reward shaping;
- training rollout-loss masking;
- REX as a training reward;
- paper-scale training pipeline.

### DuckDB adaptations

The paper implementation is not copied literally.

VinSOC uses DuckDB and adapts:
- SQL Executor -> read-only execute_sql_probe;
- Full Text Search -> deterministic DuckDB-derived value catalog/search;
- Database Profiler -> deterministic DuckDB schema/statistics metadata.

The first VinSOC version intentionally omits LLM-generated profiler descriptions and inferred foreign keys so the experiment does not introduce another unmeasured model dependency.

## Why this fits VinSOC

VinSOC public-dev already exposes value-grounding problems such as mapping user language to stored dataset IDs and labels.

A dedicated schema/value-linking stage gives the system a specific place to resolve these mismatches before final SQL generation.

It also makes error analysis clearer:

~~~
final SQL wrong
   |
   +-- linker missed table/column/value
   |
   +-- linker was adequate
           |
           +-- generator logic error
           +-- SQL dialect/error
           +-- execution/safety issue
~~~

## Metrics for VinSOC

Primary metric remains existing VinSOC Execution Accuracy.

Agentic diagnostics may include:
- linker completion;
- linked schema size;
- tool usage;
- turn counts;
- generator recovery events;
- tokens/cost/latency.

Schema-linking precision/recall can be added only as a separate diagnostic if reviewer-authored schema-gold annotations are frozen and kept outside agent inputs.

## Active VinSOC design

docs/superpowers/specs/2026-09-25-dualsql-lite-text-to-sql-optimization-design.md

The earlier CHASE-Lite design is retained only as design history and a secondary research reference. It is not the active implementation direction.
