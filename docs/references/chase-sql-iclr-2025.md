# CHASE-SQL Reference for VinSOC R2

## Citation

**Title:** CHASE-SQL: Multi-Path Reasoning and Preference Optimized Candidate Selection in Text-to-SQL  
**Authors:** Mohammadreza Pourreza, Hailong Li, Ruoxi Sun, Yeounoh Chung, Shayan Talaei, Gaurav Tarlok Kakkar, Yu Gan, Amin Saberi, Fatma Ozcan, Sercan Arik  
**Venue:** International Conference on Learning Representations (ICLR), 2025  
**Affiliations:** Google Cloud and Stanford University

Official sources:

- ICLR proceedings abstract: https://proceedings.iclr.cc/paper_files/paper/2025/hash/974ff7b5bf08dbf9400b5d599a39c77f-Abstract-Conference.html
- ICLR proceedings PDF: https://proceedings.iclr.cc/paper_files/paper/2025/file/974ff7b5bf08dbf9400b5d599a39c77f-Paper-Conference.pdf
- arXiv: https://arxiv.org/abs/2410.01943
- Google at ICLR 2025: https://research.google/conferences-and-events/google-at-iclr-2025/

## Why this paper matters to VinSOC

VinSOC R2 currently evaluates one generated SQL query with execution-based scoring on a read-only DuckDB snapshot. CHASE-SQL provides a research-backed pattern for spending additional inference at test time to:

1. generate diverse SQL candidates using different reasoning strategies;
2. improve schema/value grounding;
3. repair invalid candidates;
4. select a final candidate rather than trusting one first-pass generation.

The VinSOC adaptation is intentionally smaller and keeps the existing evaluator unchanged.

## CHASE-SQL Architecture

The paper combines four major ideas.

### 1. Value retrieval

The system retrieves relevant database values and schema context to help the model connect natural-language mentions with actual database content.

This is relevant to VinSOC because SOC datasets often encode values differently from user language. For example, a question may say "scenario 5" while the database stores `ctu13_s5`.

### 2. Multi-path candidate generation

CHASE-SQL uses three candidate-generation methods:

- **Query Plan CoT (QP):** reason from a database-style execution plan before producing SQL.
- **Divide-and-Conquer CoT (DC):** decompose the question into smaller logical subproblems and compose the final SQL.
- **Online Synthetic Examples (OS):** generate instance-aware examples to provide tailored few-shot demonstrations.

The paper emphasizes diversity: different generators solve different questions, so the union of their candidate pools has a higher upper bound than any single method.

### 3. Query fixer

A query fixer reviews generated SQL and attempts to repair problems. The paper reports that removing this component decreases end-to-end execution accuracy.

### 4. Selection agent

Candidates are compared pairwise. The paper's strongest selector is a fine-tuned binary selection model rather than a generic off-the-shelf judge.

This matters for VinSOC because we do not plan to fine-tune a selector. VinSOC therefore uses deterministic execution agreement first and calls an LLM judge only when needed.

## Key Quantitative Results

### End-to-end BIRD results

CHASE-SQL with Gemini 1.5 Pro reports:

| Split | Execution Accuracy |
|---|---:|
| BIRD dev | 73.01% |
| BIRD test | 73.0% |

These are CHASE-SQL results, not VinSOC targets.

### Single-candidate generator ablation on BIRD dev

With Gemini 1.5 Pro:

| Method | EX |
|---|---:|
| Baseline | 57.75% |
| Query Plan CoT | 63.62% |
| Divide-and-Conquer CoT | 63.92% |
| Online Synthetic Examples | 67.09% |
| Baseline + Query Fixer | 61.58% |
| QP + Query Fixer | 65.51% |
| DC + Query Fixer | 65.77% |
| OS + Query Fixer | 68.02% |

Interpretation for VinSOC: reasoning-path diversity is worth testing independently before adding a larger ensemble.

### Candidate-pool headroom

The paper reports:

| Candidate-picking view | EX |
|---|---:|
| Single query | 63.01% |
| Self-consistency | 68.84% |
| Oracle upper bound | 82.79% |

The 82.79% figure illustrates that correct candidates can exist without being selected. This motivates measuring **Candidate Oracle Accuracy** separately from final selected accuracy in VinSOC.

### Selector analysis

Binary selection accuracy reported in the paper:

| Selector | Binary accuracy |
|---|---:|
| Claude 3.5 Sonnet, untuned | 60.21% |
| Gemini 1.5 Pro, untuned | 63.98% |
| Tuned Gemma 2 9B | 64.28% |
| Tuned Gemini 1.5 Flash | 71.01% |

The full selection agent also outperforms self-consistency by roughly six percentage points across several candidate pools in the paper's Table 6.

VinSOC implication: a generic LLM should not automatically be trusted as the only selection mechanism.

### Component ablation

CHASE-SQL end-to-end BIRD dev ablation:

| Configuration | EX | Change |
|---|---:|---:|
| CHASE-SQL full | 73.01% | — |
| self-consistency instead of selector | 68.84% | -4.17 pp |
| ranker agent | 65.51% | -7.50 pp |
| without value-retrieval LSH | 70.09% | -2.92 pp |
| without Query Fixer | 69.23% | -3.78 pp |
| without QP | 72.36% | -0.65 pp |
| without OS | 72.16% | -0.85 pp |
| without DC | 71.77% | -1.24 pp |

These ablations justify testing retrieval, generation, selection, and repair as separate VinSOC experiments.

## What VinSOC Adopts

The VinSOC design adopts the following ideas, not the full implementation. In particular, E4 preserves a majority/self-consistency baseline while E5 tests pairwise selection on every non-unanimous executable candidate set:

1. **Test-time compute instead of model training** for the first optimization phase.
2. **Multiple reasoning paths** to create candidate diversity.
3. **Value grounding** before generation.
4. **Separate generation quality from selection quality.**
5. **Pairwise selection** when executable result groups disagree; only unanimous agreement or a single executable group bypasses the LLM selector.
6. **Execution Accuracy** remains the final headline metric.
7. **Ablations** isolate which component actually contributes.

## What VinSOC Does Not Adopt Initially

### No online synthetic-example generator

Reason: it adds another generation pipeline and makes attribution harder on a small SOC benchmark.

### No fine-tuned selector

Reason: the internship objective is evaluation and controlled improvement, not training a new selection model.

### No 21-candidate pool

The paper generates seven candidates per generator in part of its candidate-pool analysis. VinSOC starts with one candidate from each of three generators.

Reason: lower cost, simpler attribution, and a much smaller benchmark.

### No high-temperature sampling

VinSOC keeps temperature 0 for reproducibility in the first experiment.

### No three-round fixer

VinSOC defers repair to a later ablation and allows at most one repair attempt.

## Mapping CHASE-SQL to VinSOC

| CHASE-SQL concept | VinSOC CHASE-Lite |
|---|---|
| Value retrieval / LSH | Deterministic bounded value hints from DuckDB |
| Query Plan CoT | Query Plan generator |
| Divide-and-Conquer CoT | Divide-and-Conquer generator |
| Online synthetic examples | Deferred |
| Multiple samples per generator | One per generator initially |
| Query fixer | Deferred to E6; one attempt |
| Fine-tuned pairwise selector | E4 majority baseline; E5 unanimous early-exit + untuned pairwise selector on any executable disagreement |
| BIRD execution accuracy | Existing VinSOC R2 execution evaluator |
| Candidate upper bound | Candidate Oracle Accuracy / Pass@3 |

## VinSOC Experimental Interpretation

A useful result is not only:

```text
Baseline EX -> CHASE-Lite EX
```

The analysis should also answer:

```text
Did a correct candidate exist?
        |
        +-- no  -> generation failure
        |
        +-- yes -> did selector choose it?
                    |
                    +-- no  -> selector failure
                    +-- yes -> end-to-end success
```

This separates the two bottlenecks that candidate-generation systems otherwise mix together.

## Important Caveats

1. CHASE-SQL results are measured on BIRD/Spider, not SOC telemetry.
2. VinSOC's public pilot has only eight R2 cases and cannot support broad statistical claims.
3. Execution equality on one finite snapshot does not prove semantic equivalence.
4. The paper's strongest selector is fine-tuned; VinSOC's untuned selector should be treated as an experiment, not assumed to reproduce paper performance.
5. VinSOC's deterministic value hints are an adaptation, not a reproduction of CHASE-SQL's LSH-based retrieval.

## Related VinSOC Design

See:

`docs/superpowers/specs/2026-09-25-chase-lite-text-to-sql-optimization-design.md`
