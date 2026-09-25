> **SUPERSEDED - DO NOT IMPLEMENT**
>
> The active VinSOC R2 optimization direction changed on 2026-09-25 after adopting DualSQL (arXiv:2609.18135v1) as the primary architecture reference.
> Active design: docs/superpowers/specs/2026-09-25-dualsql-lite-text-to-sql-optimization-design.md
> This file is retained only for design history and CHASE-SQL comparison.

# CHASE-Lite Text-to-SQL Optimization Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a CHASE-SQL-inspired, gold-blind Text-to-SQL optimization pipeline to VinSOC R2 that tests value hints, three reasoning paths, majority/self-consistency, pairwise selection, and later one-shot repair while preserving the existing execution scorer.

**Architecture:** Keep `evaluation/text_to_sql.py` as the correctness authority. A new `evaluation/text_to_sql_optimization/` package builds deterministic schema/value context, generates Direct / Query-Plan / Divide-and-Conquer SQL candidates with the same pinned model, validates and executes them read-only, groups candidates by execution-result fingerprint, selects a final SQL, and only then asks the existing evaluator to score final and candidate SQL for analysis. Public-dev optimization is a versioned diagnostic experiment; official dev and frozen remain separate gates.

**Tech Stack:** Python 3.11/3.12, DuckDB 1.1–<2.0, existing `agent.provider.LLMProvider`, OpenAI Chat Completions through the existing provider adapter, pytest.

**Spec:** `docs/superpowers/specs/2026-09-25-chase-lite-text-to-sql-optimization-design.md`

## Global Constraints

- Work directly on `master`; do not create a feature branch or PR.
- Preserve `evaluation/text_to_sql.py` scoring semantics; any refactor there must be behavior-preserving and covered by existing semantic-trap tests.
- Public optimization model is pinned to `gpt-4.1-mini-2025-04-14`, temperature `0`, zero SDK retries, and a fixed completion cap.
- Generate exactly three initial candidates per E4/E5 case: `direct`, `query_plan`, `divide_and_conquer`.
- No generator, selector, context builder, or fixer may receive `gold_sql`, gold result rows, or a current-case correctness label.
- Value hints are deterministic, bounded, snapshot-derived, and may not use benchmark-case-specific alias maps.
- DuckDB remains read-only; all candidate execution must pass the existing read-only SQL policy.
- E0–E5 must keep question text, gold SQL, comparator, logical snapshot content, scorer, model, and temperature fixed.
- E4 is the majority/self-consistency baseline; E5 invokes pairwise LLM selection on every non-unanimous executable result set.
- E6 is implemented and run only after E0–E5 artifacts are reviewed; it allows one repair attempt only for syntax/execution failures.
- Frozen holdout is not opened during implementation, public-dev tuning, or official-dev configuration selection.
- Paid workflows are manual-only; ordinary `push` CI must never call the model.
- Every paid run must pass a fail-closed budget preflight before the first API request and preserve partial provenance if interrupted.
- Never overwrite prior result JSON; run IDs and filenames are append-only.

## Review Focus

1. **Gold leakage:** an optimizer input constructed from `SQLBenchmarkCase` must exclude `gold_sql`; tests must prove provider prompts and selector inputs cannot contain a poison gold literal.
2. **Wrong-majority selection:** E4 must choose a 2-vs-1 majority, while E5 must still invoke the pairwise selector so a correct minority candidate can win.
3. **Execution-equivalent SQL:** ordered vs unordered/multiset/scalar/boolean fingerprints must match existing R2 comparator semantics, including duplicate multiplicity and ordering.
4. **Value-hint explosion:** high-cardinality columns and raw telemetry must remain bounded; deterministic hint output must stay identical across repeated builds.
5. **Provider/budget failure:** malformed selector output, provider failure, missing usage/cost metadata, or preflight overflow must invalidate/stop the paid run rather than silently falling back to a score.

---

## File Structure

Create:

```text
evaluation/text_to_sql_optimization/
  __init__.py
  models.py
  context.py
  prompts.py
  generators.py
  executor.py
  selector.py
  metrics.py
  budget.py
  runner.py
  fixer.py

scripts/run_r2_optimization.py

tests/test_text_to_sql_optimization_models.py
tests/test_text_to_sql_optimization_context.py
tests/test_text_to_sql_optimization_generators.py
tests/test_text_to_sql_optimization_executor.py
tests/test_text_to_sql_optimization_selector.py
tests/test_text_to_sql_optimization_metrics.py
tests/test_text_to_sql_optimization_budget.py
tests/test_text_to_sql_optimization_runner.py
tests/test_text_to_sql_optimization_fixer.py

.github/workflows/public-pilot-r2-optimization.yml
```

Modify:

```text
evaluation/text_to_sql.py
docs/public_pilot_results_2026-09-25.md
README.md
```

Responsibilities:

- `models.py`: immutable gold-blind optimizer inputs and run records.
- `context.py`: schema rendering and deterministic bounded value hints.
- `prompts.py`: versioned prompt templates and prompt hashing.
- `generators.py`: one candidate per strategy through `LLMProvider`.
- `executor.py`: safety, execution, canonical fingerprinting.
- `selector.py`: E4 majority and E5 pairwise tournament.
- `metrics.py`: Oracle@3, selector conditional accuracy, diversity, efficiency.
- `budget.py`: conservative request bounds and fail-closed experiment budget.
- `runner.py`: experiment orchestration, gold isolation, final evaluation, provenance.
- `fixer.py`: E6-only one-shot syntax/execution repair.
- `scripts/run_r2_optimization.py`: CLI over the public-dev benchmark/snapshot.
- workflow: manual paid execution only.

---

### Task 1: Establish Gold-Blind Models and Shared Result Canonicalization

**Files:**
- Create: `evaluation/text_to_sql_optimization/__init__.py`
- Create: `evaluation/text_to_sql_optimization/models.py`
- Create: `tests/test_text_to_sql_optimization_models.py`
- Modify: `evaluation/text_to_sql.py`
- Modify: `tests/test_text_to_sql_runner.py`

**Interfaces:**
- Produces: `OptimizationCase.from_benchmark(case) -> OptimizationCase`
- Produces: `canonical_result(rows, comparator) -> tuple`
- Produces: `CandidateRecord`, `SelectionRecord`, `OptimizationCaseResult`
- Consumes: existing `SQLBenchmarkCase`, `ComparatorName`

- [ ] **Step 1: Write a failing test that proves optimizer inputs contain no gold**

```python
from dataclasses import asdict
from evaluation.text_to_sql import SQLBenchmarkCase
from evaluation.text_to_sql_optimization.models import OptimizationCase

def test_optimization_case_strips_gold_sql():
    source = SQLBenchmarkCase(
        case_id="leak_001",
        question="Count flows",
        database_snapshot="snapshot.duckdb",
        gold_sql=("SELECT 'POISON_GOLD_LITERAL'",),
        category="aggregation",
        difficulty="basic",
        result_comparator="scalar",
    )
    optimized = OptimizationCase.from_benchmark(source)

    payload = asdict(optimized)
    assert "gold_sql" not in payload
    assert "POISON_GOLD_LITERAL" not in repr(payload)
    assert optimized.case_id == "leak_001"
    assert optimized.result_comparator == "scalar"
```

- [ ] **Step 2: Write regression tests for public canonicalization semantics**

Add to `tests/test_text_to_sql_runner.py`:

```python
from evaluation.text_to_sql import canonical_result

def test_canonical_result_preserves_order_only_when_required():
    rows = [{"v": 2}, {"v": 1}]
    assert canonical_result(rows, "ordered_rows") != canonical_result(
        list(reversed(rows)), "ordered_rows"
    )
    assert canonical_result(rows, "unordered_rows") == canonical_result(
        list(reversed(rows)), "unordered_rows"
    )

def test_canonical_result_preserves_duplicate_multiplicity():
    two = [{"v": 1}, {"v": 1}]
    one = [{"v": 1}]
    assert canonical_result(two, "multiset_rows") != canonical_result(one, "multiset_rows")
```

- [ ] **Step 3: Run the tests to verify they fail**

Run:

```bash
python -m pytest tests/test_text_to_sql_optimization_models.py tests/test_text_to_sql_runner.py -q
```

Expected: import failures for `OptimizationCase` and `canonical_result`.

- [ ] **Step 4: Implement a behavior-preserving public canonicalizer**

In `evaluation/text_to_sql.py`, expose a helper and have `_equivalent` use it:

```python
def canonical_result(rows: list[dict[str, Any]], comparator: ComparatorName) -> tuple[Any, ...]:
    canonical = _canonical_rows(rows)
    if comparator in {"scalar", "boolean", "ordered_rows"}:
        return tuple(canonical)
    if comparator in {"unordered_rows", "multiset_rows"}:
        return tuple(sorted(Counter(canonical).items(), key=repr))
    raise ValueError(f"Unsupported result comparator: {comparator}")


def _equivalent(predicted, gold, comparator):
    return canonical_result(predicted, comparator) == canonical_result(gold, comparator)
```

Do not change any accepted SQL, safety, or execution behavior.

- [ ] **Step 5: Implement immutable optimizer models**

`models.py` must define at least:

```python
from dataclasses import dataclass, field
from typing import Any, Literal
from evaluation.text_to_sql import ComparatorName

StrategyName = Literal["direct", "query_plan", "divide_and_conquer"]
ExperimentName = Literal["E0", "E1", "E2", "E3", "E4", "E5", "E6"]

@dataclass(frozen=True)
class OptimizationCase:
    case_id: str
    question: str
    category: str
    difficulty: str
    result_comparator: ComparatorName

    @classmethod
    def from_benchmark(cls, case):
        return cls(
            case_id=case.case_id,
            question=case.question,
            category=case.category,
            difficulty=case.difficulty,
            result_comparator=case.result_comparator,
        )

@dataclass(frozen=True)
class CandidateRecord:
    candidate_id: str
    strategy: StrategyName
    sql: str
    syntax_valid: bool = False
    safety_rejected: bool = False
    execution_success: bool = False
    result_fingerprint: str | None = None
    error: str | None = None
    input_tokens: int = 0
    output_tokens: int = 0
    latency_ms: float = 0.0
    estimated_cost_usd: float | None = None

@dataclass(frozen=True)
class SelectionRecord:
    mode: str
    selected_candidate_id: str | None
    disagreement: bool
    selector_calls: int = 0
    reason_code: str | None = None

@dataclass
class OptimizationCaseResult:
    case_id: str
    candidates: list[CandidateRecord] = field(default_factory=list)
    selection: SelectionRecord | None = None
    final_sql: str | None = None
    final_execution_accurate: bool = False
    candidate_correctness: dict[str, bool] = field(default_factory=dict)
```

- [ ] **Step 6: Run focused tests**

```bash
python -m pytest tests/test_text_to_sql_optimization_models.py tests/test_text_to_sql_runner.py -q
```

Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add evaluation/text_to_sql.py evaluation/text_to_sql_optimization/__init__.py evaluation/text_to_sql_optimization/models.py tests/test_text_to_sql_runner.py tests/test_text_to_sql_optimization_models.py
git commit -m "feat(eval): add gold-blind R2 optimization models"
git push origin master
```

---

### Task 2: Build Deterministic Schema and Value Hints

**Files:**
- Create: `evaluation/text_to_sql_optimization/context.py`
- Create: `tests/test_text_to_sql_optimization_context.py`

**Interfaces:**
- Consumes: `DuckDBSnapshot`, `OptimizationCase`
- Produces: `OptimizationContext(schema: str, value_hints: str, sha256: str)`
- Produces: `build_context(snapshot, case) -> OptimizationContext`

- [ ] **Step 1: Write a fixture with low- and high-cardinality SOC values**

Build a temporary snapshot containing:

```python
# low-cardinality values that must be visible
source_dataset = ["ctu13_s5", "ctu13_s7"]
protocol = ["TCP", "UDP"]
label = ["flow=From-Botnet-TCP-HTTP", "flow=Background-TCP-Established"]

# many host-like values to prove bounding
host = [f"HOST-{i:03d}" for i in range(100)]
```

- [ ] **Step 2: Write failing tests for deterministic bounded hints**

```python
def test_context_includes_low_cardinality_dataset_values(snapshot):
    case = OptimizationCase(
        "c1", "Count scenario 5 From-Botnet flows", "network", "basic", "scalar"
    )
    ctx = build_context(snapshot, case)
    assert "ctu13_s5" in ctx.value_hints
    assert "ctu13_s7" in ctx.value_hints
    assert "flow=From-Botnet" in ctx.value_hints

def test_context_is_deterministic_and_bounded(snapshot):
    case = OptimizationCase("c2", "Count TCP flows", "network", "basic", "scalar")
    first = build_context(snapshot, case)
    second = build_context(snapshot, case)
    assert first == second
    assert len(first.value_hints.encode("utf-8")) <= 8192

def test_context_does_not_dump_high_cardinality_column(snapshot):
    case = OptimizationCase("c3", "Count process events", "endpoint", "basic", "scalar")
    ctx = build_context(snapshot, case)
    assert ctx.value_hints.count("HOST-") <= 12
```

- [ ] **Step 3: Run tests and confirm failure**

```bash
python -m pytest tests/test_text_to_sql_optimization_context.py -q
```

Expected: missing `build_context`.

- [ ] **Step 4: Implement the context builder**

Use constants:

```python
LOW_CARDINALITY_LIMIT = 32
HIGH_CARDINALITY_SAMPLE_LIMIT = 64
HIGH_CARDINALITY_HINT_LIMIT = 12
MAX_HINT_BYTES = 8192

HINT_COLUMNS = {
    "cti_indicators": ("source_dataset", "indicator_type", "threat_type", "malware_printable"),
    "network_flows": ("source_dataset", "protocol", "action", "label"),
    "sysmon_process_events": ("source_dataset", "host", "image", "parent_image"),
}
```

Algorithm per allowed column:

1. Verify table/column exists from `information_schema.columns`.
2. Query `count(DISTINCT column)`.
3. If count <= 32, retrieve all non-null distinct values ordered by text.
4. Otherwise retrieve at most 64 deterministic values ordered by `count(*) DESC, CAST(value AS VARCHAR) ASC`.
5. Normalize question/value tokens with lowercased alphanumerics; rank sampled values by overlap count, then frequency, then lexical value.
6. Retain at most 12 high-cardinality values.
7. Render sections in sorted table/column order.
8. Truncate only at section boundaries to `MAX_HINT_BYTES`; never cut a value mid-string.
9. Compute SHA-256 over `schema + "\n\n" + value_hints`.

Do not create aliases such as `"scenario 5" -> "ctu13_s5"`. The model sees actual low-cardinality values and performs the mapping.

- [ ] **Step 5: Add a no-gold poison test**

```python
def test_context_never_receives_gold_sql(snapshot):
    case = OptimizationCase("poison", "Count flows", "network", "basic", "scalar")
    ctx = build_context(snapshot, case)
    assert "POISON_GOLD_LITERAL" not in ctx.schema
    assert "POISON_GOLD_LITERAL" not in ctx.value_hints
```

The test intentionally uses `OptimizationCase`, which has no gold field.

- [ ] **Step 6: Run tests**

```bash
python -m pytest tests/test_text_to_sql_optimization_context.py -q
```

Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add evaluation/text_to_sql_optimization/context.py tests/test_text_to_sql_optimization_context.py
git commit -m "feat(eval): add deterministic R2 value hints"
git push origin master
```

---

### Task 3: Add Versioned Direct, Query-Plan, and Divide-and-Conquer Generators

**Files:**
- Create: `evaluation/text_to_sql_optimization/prompts.py`
- Create: `evaluation/text_to_sql_optimization/generators.py`
- Create: `tests/test_text_to_sql_optimization_generators.py`

**Interfaces:**
- Consumes: `LLMProvider`, `OptimizationCase`, `OptimizationContext`
- Produces: `generate_candidate(strategy, ...) -> CandidateDraft`
- Produces: stable prompt hash per strategy
- Constraint: provider receives only question/schema/value hints, never benchmark gold

- [ ] **Step 1: Write a sequential fake provider**

```python
class SequenceProvider:
    def __init__(self, outputs):
        self.outputs = iter(outputs)
        self.calls = []

    def generate(self, messages, tools=None, system_prompt=None, temperature=0.0):
        self.calls.append((messages, system_prompt, temperature))
        return LLMResponse(
            content=next(self.outputs),
            tool_calls=[],
            raw={},
            metadata={
                "input_tokens": 100,
                "output_tokens": 25,
                "latency_ms": 5.0,
                "estimated_cost_usd": 0.00008,
            },
        )
```

- [ ] **Step 2: Write failing strategy and leakage tests**

```python
@pytest.mark.parametrize("strategy", ["direct", "query_plan", "divide_and_conquer"])
def test_generator_returns_exactly_one_sql_candidate(strategy, case, context):
    provider = SequenceProvider(["SELECT count(*) FROM network_flows;"])
    draft = generate_candidate(strategy, case, context, provider, temperature=0.0)
    assert draft.strategy == strategy
    assert draft.sql == "SELECT count(*) FROM network_flows;"
    assert len(provider.calls) == 1

def test_generator_prompt_is_gold_blind(case, context):
    provider = SequenceProvider(["SELECT 1"])
    generate_candidate("direct", case, context, provider)
    serialized = repr(provider.calls)
    assert "POISON_GOLD_LITERAL" not in serialized
```

- [ ] **Step 3: Run tests and verify failure**

```bash
python -m pytest tests/test_text_to_sql_optimization_generators.py -q
```

- [ ] **Step 4: Implement prompt templates**

Each strategy must instruct the model to reason using its strategy **internally** and return SQL only:

```python
COMMON = """You generate DuckDB SQL for the VinSOC SOC benchmark.
Use only the supplied schema and value hints.
Return exactly one read-only SELECT statement; WITH ... SELECT is allowed.
Do not emit prose, Markdown, comments, DDL, DML, PRAGMA, ATTACH, INSTALL, or LOAD.
"""

DIRECT = COMMON + "\nSolve the question directly and return only the final SQL."
QUERY_PLAN = COMMON + """
Before answering, internally construct a query plan covering tables, filters,
aggregation, ordering and limits. Return only the final SQL; do not reveal the plan.
"""
DIVIDE_CONQUER = COMMON + """
Internally decompose the question into independent constraints, resolve each
constraint against the supplied schema/value hints, then compose them into one SQL
query. Return only the final SQL; do not reveal the decomposition.
"""
```

Prompts include `context.schema`, `context.value_hints`, and the user question. Hash the exact system+user message payload with the existing canonical SHA helper or a local SHA-256 JSON canonicalizer.

- [ ] **Step 5: Implement strict output extraction**

Use existing `evaluation.text_to_sql._extract_sql`, then enforce:

```python
MAX_SQL_CHARS = 16_000
if not sql or len(sql) > MAX_SQL_CHARS:
    raise ProviderError("Generated SQL is empty or exceeds 16000 characters", ...)
```

Do not repair or rewrite SQL in the generator.

- [ ] **Step 6: Test prompt distinction and temperature**

```python
def test_three_strategy_prompts_are_distinct(case, context):
    provider = SequenceProvider(["SELECT 1", "SELECT 1", "SELECT 1"])
    hashes = {
        generate_candidate(s, case, context, provider, temperature=0.0).prompt_sha256
        for s in ("direct", "query_plan", "divide_and_conquer")
    }
    assert len(hashes) == 3
    assert all(call[2] == 0.0 for call in provider.calls)
```

- [ ] **Step 7: Run tests**

```bash
python -m pytest tests/test_text_to_sql_optimization_generators.py -q
```

Expected: PASS.

- [ ] **Step 8: Commit**

```bash
git add evaluation/text_to_sql_optimization/prompts.py evaluation/text_to_sql_optimization/generators.py tests/test_text_to_sql_optimization_generators.py
git commit -m "feat(eval): add CHASE-Lite SQL generators"
git push origin master
```

---

### Task 4: Validate, Execute, and Fingerprint Candidates

**Files:**
- Create: `evaluation/text_to_sql_optimization/executor.py`
- Create: `tests/test_text_to_sql_optimization_executor.py`

**Interfaces:**
- Consumes: candidate draft, `DuckDBSnapshot`, comparator
- Produces: `CandidateRecord`
- Uses: `validate_read_only_sql`, `canonical_result`

- [ ] **Step 1: Write failing tests for safe execution**

```python
def test_executor_rejects_write_candidate(snapshot):
    record = execute_candidate(
        CandidateDraft("direct-0", "direct", "DELETE FROM network_flows", "...", {}),
        snapshot,
        "unordered_rows",
    )
    assert record.safety_rejected is True
    assert record.execution_success is False
    assert record.result_fingerprint is None

def test_executor_accepts_terminal_semicolon(snapshot):
    record = execute_candidate(
        CandidateDraft("direct-0", "direct", "SELECT 1 AS x;", "...", {}),
        snapshot,
        "scalar",
    )
    assert record.syntax_valid is True
    assert record.execution_success is True
    assert record.result_fingerprint is not None
```

- [ ] **Step 2: Write comparator/fingerprint tests**

```python
def test_unordered_fingerprint_ignores_row_order_but_not_duplicates(snapshot):
    a = fingerprint_rows([{"v": 2}, {"v": 1}], "unordered_rows")
    b = fingerprint_rows([{"v": 1}, {"v": 2}], "unordered_rows")
    c = fingerprint_rows([{"v": 1}, {"v": 1}, {"v": 2}], "unordered_rows")
    assert a == b
    assert a != c

def test_ordered_fingerprint_preserves_order(snapshot):
    assert fingerprint_rows([{"v": 1}, {"v": 2}], "ordered_rows") != fingerprint_rows(
        [{"v": 2}, {"v": 1}], "ordered_rows"
    )
```

- [ ] **Step 3: Run tests and verify failure**

```bash
python -m pytest tests/test_text_to_sql_optimization_executor.py -q
```

- [ ] **Step 4: Implement execution with existing safety**

Implementation order:

```python
def execute_candidate(draft, snapshot, comparator):
    syntax_valid = _has_valid_syntax(draft.sql)
    if not syntax_valid:
        return ... error="DuckDB parser rejected SQL"

    try:
        validate_read_only_sql(draft.sql)
    except QuerySafetyError as exc:
        return ... safety_rejected=True, error=str(exc)

    try:
        result = snapshot.query(draft.sql)
    except RuntimeError as exc:
        return ... execution_success=False, error=str(exc)

    fingerprint = sha256(
        repr(canonical_result(result.rows, comparator)).encode("utf-8")
    ).hexdigest()
    return ... execution_success=True, result_fingerprint=fingerprint
```

Copy provider metadata from the draft unchanged into the candidate record.

- [ ] **Step 5: Add a test proving execution never evaluates against gold**

Monkeypatch `evaluation.text_to_sql.evaluate_sql_case` to raise if called and verify `execute_candidate` still succeeds. Candidate execution must know only snapshot + comparator.

- [ ] **Step 6: Run tests**

```bash
python -m pytest tests/test_text_to_sql_optimization_executor.py tests/test_text_to_sql_runner.py -q
```

Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add evaluation/text_to_sql_optimization/executor.py tests/test_text_to_sql_optimization_executor.py
git commit -m "feat(eval): execute and fingerprint SQL candidates"
git push origin master
```

---

### Task 5: Implement E4 Majority and E5 Pairwise Selection

**Files:**
- Create: `evaluation/text_to_sql_optimization/selector.py`
- Create: `tests/test_text_to_sql_optimization_selector.py`

**Interfaces:**
- Produces: `select_e4(candidates) -> SelectionRecord`
- Produces: `select_e5(case, context, candidates, provider) -> SelectionRecord`
- Pairwise provider input contains only question/context/candidate SQL
- No candidate SQL is regenerated by selector

- [ ] **Step 1: Write E4 majority tests**

```python
def test_e4_uses_two_vs_one_execution_majority():
    candidates = [
        ok("direct-0", "direct", "SELECT 'wrong-a'", fp="wrong"),
        ok("query-plan-0", "query_plan", "SELECT 'wrong-b'", fp="wrong"),
        ok("dc-0", "divide_and_conquer", "SELECT 'right'", fp="right"),
    ]
    result = select_e4(candidates)
    assert result.selected_candidate_id == "direct-0"
    assert result.mode == "majority"
    assert result.disagreement is True
    assert result.selector_calls == 0
```

The stable representative for a result group is `direct > query_plan > divide_and_conquer`.

- [ ] **Step 2: Write the critical E5 wrong-majority test**

```python
def test_e5_invokes_llm_even_when_two_candidates_share_wrong_result(case, context):
    candidates = [
        ok("direct-0", "direct", "SELECT 'wrong-a'", fp="wrong"),
        ok("query-plan-0", "query_plan", "SELECT 'wrong-b'", fp="wrong"),
        ok("dc-0", "divide_and_conquer", "SELECT 'right'", fp="right"),
    ]
    provider = SequenceProvider(['{"winner":"B","reason_code":"filter_coverage"}'])

    result = select_e5(case, context, candidates, provider)

    assert result.selected_candidate_id == "dc-0"
    assert result.selector_calls == 1
    assert result.disagreement is True
```

This test prevents E5 from collapsing into self-consistency.

- [ ] **Step 3: Write early-exit tests**

```python
def test_e5_skips_llm_when_all_executable_results_agree(case, context):
    provider = SequenceProvider([])
    candidates = [
        ok("direct-0", "direct", "SELECT 1", fp="same"),
        ok("query-plan-0", "query_plan", "SELECT 1", fp="same"),
        ok("dc-0", "divide_and_conquer", "SELECT 1", fp="same"),
    ]
    result = select_e5(case, context, candidates, provider)
    assert result.selected_candidate_id == "direct-0"
    assert result.selector_calls == 0

def test_e5_skips_failed_candidates_when_one_executable_group_remains(case, context):
    ...
```

Implement the second test with one executable candidate, one syntax error, and one safety rejection.

- [ ] **Step 4: Write malformed-selector fail-closed test**

```python
def test_pairwise_selector_rejects_malformed_json(case, context):
    provider = SequenceProvider(["I think candidate A is better"])
    with pytest.raises(ProviderError, match="selector"):
        select_e5(case, context, disagreeing_candidates(), provider)
```

- [ ] **Step 5: Implement result grouping**

```python
def executable_groups(candidates):
    groups = {}
    for candidate in candidates:
        if candidate.execution_success and candidate.result_fingerprint:
            groups.setdefault(candidate.result_fingerprint, []).append(candidate)
    return groups
```

Sort groups and representatives deterministically. Never use correctness labels.

- [ ] **Step 6: Implement E4**

Rules:

1. zero executable groups => no selected candidate;
2. one group => stable representative;
3. strict largest group => representative of largest group;
4. exact tie => stable representative from the first group by representative strategy order then candidate ID.

Record `mode="majority"` and `disagreement=len(groups)>1`.

- [ ] **Step 7: Implement E5 pairwise tournament**

Collapse each execution-equivalent group to its stable representative.

For two groups: one pairwise call.

For three groups:

```text
representative 1 vs representative 2 -> winner
winner vs representative 3 -> final
```

Prompt must demand exactly:

```json
{"winner":"A","reason_code":"question_semantics"}
```

Allowed reason codes:

```python
{
    "question_semantics",
    "value_linking",
    "filter_coverage",
    "aggregation",
    "boolean_logic",
    "ordering_limit",
    "dialect",
}
```

Reject unknown winner IDs, malformed JSON, extra top-level keys, or unknown reason codes.

- [ ] **Step 8: Add selector gold-leak test**

Use a question/context without the poison string and candidates without the poison string, then assert the fake provider's captured prompt does not contain `POISON_GOLD_LITERAL`.

- [ ] **Step 9: Run tests**

```bash
python -m pytest tests/test_text_to_sql_optimization_selector.py -q
```

Expected: PASS.

- [ ] **Step 10: Commit**

```bash
git add evaluation/text_to_sql_optimization/selector.py tests/test_text_to_sql_optimization_selector.py
git commit -m "feat(eval): add CHASE-Lite SQL selection"
git push origin master
```

---

### Task 6: Add Oracle@3, Selector, Diversity, and Efficiency Metrics

**Files:**
- Create: `evaluation/text_to_sql_optimization/metrics.py`
- Create: `tests/test_text_to_sql_optimization_metrics.py`

**Interfaces:**
- Consumes: completed `OptimizationCaseResult` objects after final selection/evaluation
- Produces: JSON-ready aggregate metrics

- [ ] **Step 1: Write the Oracle@3 test**

```python
def test_oracle_counts_case_when_any_candidate_is_correct():
    case = result(
        candidate_correctness={"a": False, "b": True, "c": False},
        selected="a",
        final_correct=False,
    )
    metrics = aggregate_optimization_metrics([case])
    assert metrics["execution_accuracy"] == 0.0
    assert metrics["oracle_at_3"] == 1.0
```

- [ ] **Step 2: Write selector conditional-accuracy tests**

```python
def test_selector_conditional_population_requires_mixed_correctness():
    mixed_good = result(
        candidate_correctness={"a": False, "b": True},
        selected="b",
        final_correct=True,
    )
    all_good = result(
        candidate_correctness={"a": True, "b": True},
        selected="a",
        final_correct=True,
    )
    metrics = aggregate_optimization_metrics([mixed_good, all_good])
    assert metrics["selector_selectable_cases"] == 1
    assert metrics["selector_conditional_accuracy"] == 1.0
```

- [ ] **Step 3: Write diversity and efficiency tests**

Assert:

- 3 candidates with 2 unique normalized SQL strings => `sql_diversity=2/3`;
- 3 executable candidates with 2 result fingerprints => `result_diversity=2/3`;
- API calls sum generator + selector calls;
- token/cost/latency totals are additive and missing cost marks `cost_complete=False`.

- [ ] **Step 4: Implement metrics**

Required report keys:

```python
{
    "execution_accuracy": ...,
    "oracle_at_3": ...,
    "oracle_case_count": ...,
    "selector_selectable_cases": ...,
    "selector_conditional_accuracy": ...,
    "mean_sql_diversity": ...,
    "mean_result_diversity": ...,
    "total_api_calls": ...,
    "input_tokens": ...,
    "output_tokens": ...,
    "estimated_cost_usd": ...,
    "cost_complete": ...,
    "total_latency_ms": ...,
    "selector_call_rate": ...,
}
```

For E0–E3, call the oracle key `oracle_at_1` in the experiment-level serialization or explicitly include `candidate_count=1`; do not misleadingly label a one-candidate experiment as Oracle@3.

- [ ] **Step 5: Run tests**

```bash
python -m pytest tests/test_text_to_sql_optimization_metrics.py -q
```

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add evaluation/text_to_sql_optimization/metrics.py tests/test_text_to_sql_optimization_metrics.py
git commit -m "feat(eval): add R2 optimization metrics"
git push origin master
```

---

### Task 7: Add Fail-Closed Cost Preflight

**Files:**
- Create: `evaluation/text_to_sql_optimization/budget.py`
- Create: `tests/test_text_to_sql_optimization_budget.py`

**Interfaces:**
- Produces: `preflight_experiment(...) -> BudgetPreflight`
- Public pilot budget ceiling: `1.00 USD`
- Counts worst-case E5 as 3 generator calls + 2 selector calls per case
- E6 adds at most 1 repair call per case

- [ ] **Step 1: Write call-count tests**

```python
@pytest.mark.parametrize(
    ("experiment", "calls_per_case"),
    [("E0", 1), ("E1", 1), ("E2", 1), ("E3", 1), ("E4", 3), ("E5", 5), ("E6", 6)],
)
def test_worst_case_call_count(experiment, calls_per_case):
    assert worst_case_calls(experiment, case_count=8) == calls_per_case * 8
```

- [ ] **Step 2: Write budget rejection test**

```python
def test_preflight_blocks_before_provider_when_ceiling_reaches_budget():
    with pytest.raises(ValueError, match="budget"):
        preflight_experiment(
            experiment="E5",
            generator_requests=[very_large_request()] * 24,
            selector_template=very_large_selector_template(),
            case_count=8,
            input_usd_m=10_000,
            output_usd_m=10_000,
            budget_usd=1.0,
        )
```

- [ ] **Step 3: Implement conservative bounds**

Reuse the public pilot principle:

```python
FRAMING_TOKENS = 4096
COMPLETION_CAP = 1000
MAX_SQL_CHARS = 16_000
PUBLIC_PILOT_BUDGET_USD = 1.00
```

Generator request bounds use their actual serialized UTF-8 bytes.

Selector worst-case request uses the actual selector template plus two SQL placeholders each exactly `MAX_SQL_CHARS` bytes; count two selector calls per case.

E6 adds one repair-template request with one `MAX_SQL_CHARS` SQL placeholder per case.

The preflight output must include:

```python
{
    "experiment": "E5",
    "case_count": 8,
    "worst_case_calls": 40,
    "cost_ceiling_usd": ...,
    "budget_limit_usd": 1.0,
    "method": "...",
}
```

Reject when `cost_ceiling_usd >= budget_limit_usd`.

- [ ] **Step 4: Add actual-run guard API**

Implement:

```python
def ensure_remaining_budget(known_cost_usd, remaining_request_bounds, budget_usd):
    if known_cost_usd + sum(x.max_cost_usd for x in remaining_request_bounds) >= budget_usd:
        raise ValueError("Budget gate blocked before next API request")
```

This mirrors the public pilot's per-request fail-closed behavior.

- [ ] **Step 5: Run tests**

```bash
python -m pytest tests/test_text_to_sql_optimization_budget.py tests/test_public_pilot_runner.py -q
```

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add evaluation/text_to_sql_optimization/budget.py tests/test_text_to_sql_optimization_budget.py
git commit -m "feat(eval): add R2 optimization budget gate"
git push origin master
```

---

### Task 8: Orchestrate E0–E5 Without Gold Leakage

**Files:**
- Create: `evaluation/text_to_sql_optimization/runner.py`
- Create: `tests/test_text_to_sql_optimization_runner.py`

**Interfaces:**
- Produces: `run_experiment(...) -> dict[str, Any]`
- Consumes full `SQLBenchmarkCase` only at outer orchestration boundary
- Inner optimization path consumes `OptimizationCase`
- Final/candidate correctness analysis occurs only after selection returns

- [ ] **Step 1: Write experiment-strategy tests**

```python
@pytest.mark.parametrize(
    ("experiment", "expected"),
    [
        ("E0", [("direct", False)]),
        ("E1", [("direct", True)]),
        ("E2", [("query_plan", True)]),
        ("E3", [("divide_and_conquer", True)]),
        ("E4", [("direct", True), ("query_plan", True), ("divide_and_conquer", True)]),
        ("E5", [("direct", True), ("query_plan", True), ("divide_and_conquer", True)]),
    ],
)
def test_experiment_contract(experiment, expected):
    assert experiment_contract(experiment).generators == expected
```

Represent the boolean as `use_value_hints` at the contract level rather than duplicating it per generator if cleaner.

- [ ] **Step 2: Write a gold-leak integration test**

Create a benchmark case whose gold contains `POISON_GOLD_LITERAL`. Use a fake provider that records every generator and selector request. Run E5 with candidate outputs that force selector disagreement.

After the run:

```python
assert all("POISON_GOLD_LITERAL" not in repr(call) for call in provider.calls)
assert report["cases"][0]["candidate_correctness"]  # analysis happened later
```

This proves gold was used for post-selection analysis but not provider input.

- [ ] **Step 3: Write E4/E5 behavioral integration tests**

Fixture candidate outputs:

```text
direct              -> wrong result X
query_plan          -> wrong result X
divide_and_conquer  -> correct result Y
```

Expected:

- E4 final SQL is the X-majority representative and is incorrect.
- E5 pairwise selector can select Y and final execution becomes correct.
- Oracle@3 is 1.0 for both.
- E5 `selector_conditional_accuracy` is 1.0 in the fixture.

- [ ] **Step 4: Implement experiment contracts**

```python
EXPERIMENTS = {
    "E0": ExperimentContract(("direct",), use_value_hints=False, selector="none"),
    "E1": ExperimentContract(("direct",), use_value_hints=True, selector="none"),
    "E2": ExperimentContract(("query_plan",), use_value_hints=True, selector="none"),
    "E3": ExperimentContract(("divide_and_conquer",), use_value_hints=True, selector="none"),
    "E4": ExperimentContract(
        ("direct", "query_plan", "divide_and_conquer"),
        use_value_hints=True,
        selector="majority",
    ),
    "E5": ExperimentContract(
        ("direct", "query_plan", "divide_and_conquer"),
        use_value_hints=True,
        selector="pairwise",
    ),
}
```

- [ ] **Step 5: Implement the gold-blind inner pipeline**

Structure the code so the inner method signature cannot accept gold:

```python
def optimize_case(
    case: OptimizationCase,
    *,
    snapshot: DuckDBSnapshot,
    provider: LLMProvider,
    experiment: str,
) -> OptimizationCaseResult:
    ...
```

Outer method:

```python
def run_benchmark_case(full_case: SQLBenchmarkCase, ...):
    optimized = optimize_case(OptimizationCase.from_benchmark(full_case), ...)
    # Only now score candidate/final SQL against full_case.
    ...
```

Candidate correctness for Oracle@3 is calculated only after `optimized.selection` and `optimized.final_sql` are fixed.

- [ ] **Step 6: Make provider failures invalidate the run**

A provider error, malformed selector response, missing final candidate in E0–E5, or unverifiable usage metadata must set:

```python
"run_status": "stopped_provider_usage_or_scoring_error",
"eligible": False,
"ineligible_reasons": [...]
```

Write the partial report before re-raising.

Do not silently substitute E4 when E5 selector fails.

- [ ] **Step 7: Add provenance fields**

Run report must include:

```python
{
    "experiment_id": "E5",
    "run_id": ...,
    "git_sha": ...,
    "benchmark_version": ...,
    "benchmark_split_sha256": ...,
    "snapshot_content_sha256": ...,
    "scorer_sha256": ...,
    "model": "gpt-4.1-mini-2025-04-14",
    "temperature": 0,
    "context_sha256": [...],
    "prompt_sha256": {...},
    "preflight": {...},
    "metrics": {...},
    "cases": [...],
}
```

Every case record contains all candidate SQLs, execution statuses/fingerprints, selection path, final SQL, final score, and usage metadata.

- [ ] **Step 8: Run tests**

```bash
python -m pytest   tests/test_text_to_sql_optimization_runner.py   tests/test_text_to_sql_optimization_models.py   tests/test_text_to_sql_optimization_context.py   tests/test_text_to_sql_optimization_generators.py   tests/test_text_to_sql_optimization_executor.py   tests/test_text_to_sql_optimization_selector.py   tests/test_text_to_sql_optimization_metrics.py   tests/test_text_to_sql_optimization_budget.py   -q
```

Expected: PASS.

- [ ] **Step 9: Commit**

```bash
git add evaluation/text_to_sql_optimization/runner.py tests/test_text_to_sql_optimization_runner.py
git commit -m "feat(eval): orchestrate CHASE-Lite R2 experiments"
git push origin master
```

---

### Task 9: Add Manual Public-Dev CLI and Paid Workflow

**Files:**
- Create: `scripts/run_r2_optimization.py`
- Create: `.github/workflows/public-pilot-r2-optimization.yml`
- Modify: `tests/test_text_to_sql_optimization_runner.py`

**Interfaces:**
- CLI runs one experiment at a time: E0–E6
- Paid workflow is `workflow_dispatch` only
- Output path is explicit and must not already exist unless `--force` is deliberately supplied for a local non-evidence test; evidence workflow never uses `--force`

- [ ] **Step 1: Write CLI argument tests**

Test parsing rejects:

- `frozen`;
- unknown experiment;
- output path that already exists;
- model differing from `gpt-4.1-mini-2025-04-14`;
- temperature differing from 0 for evidence mode.

- [ ] **Step 2: Implement the CLI**

Required invocation:

```bash
python -m scripts.run_r2_optimization   --experiment E5   --snapshot data/public_pilot/snapshot.duckdb   --snapshot-report data/public_pilot/snapshot_report.json   --cases evaluation/public_pilot/r2/public_dev   --version-lock evaluation/public_pilot/VERSION.lock   --output results/evaluation_v1/r2_optimization/<run-id>-E5.json
```

The CLI must:

1. verify source/snapshot/case/scorer hashes before any API call;
2. enforce branch/commit identity for evidence runs;
3. instantiate OpenAI with timeout 60 and max retries 0;
4. pin model and completion cap;
5. run budget preflight;
6. write a partial report before first request;
7. execute exactly one experiment;
8. persist final JSON atomically.

- [ ] **Step 3: Add a manual-only workflow**

`.github/workflows/public-pilot-r2-optimization.yml` begins:

```yaml
name: R2 CHASE-Lite public-dev

on:
  workflow_dispatch:
    inputs:
      experiment:
        description: "E0-E6 experiment ID"
        required: true
        type: choice
        options: [E0, E1, E2, E3, E4, E5, E6]
```

It must **not** contain `push:`, `pull_request:`, or `schedule:`.

Workflow sequence:

1. checkout exact `master`;
2. setup Python 3.11;
3. install requirements;
4. fetch/verify public pilot sources using existing scripts;
5. rebuild snapshot and verify logical content hash;
6. run optimization CLI;
7. upload JSON as an Actions artifact;
8. never auto-commit result artifacts.

- [ ] **Step 4: Add workflow-shape test**

Read YAML as text in a test and assert:

```python
assert "workflow_dispatch:" in workflow
assert "\npush:" not in workflow
assert "\npull_request:" not in workflow
assert "\nschedule:" not in workflow
```

- [ ] **Step 5: Run tests**

```bash
python -m pytest tests/test_text_to_sql_optimization_runner.py tests/test_public_pilot_runner.py -q
python -m pytest -q
```

Expected: full suite PASS on Python 3.11 locally; CI must then pass Python 3.11 and 3.12.

- [ ] **Step 6: Commit**

```bash
git add scripts/run_r2_optimization.py .github/workflows/public-pilot-r2-optimization.yml tests/test_text_to_sql_optimization_runner.py
git commit -m "ci(eval): add manual CHASE-Lite public-dev runner"
git push origin master
```

---

### Task 10: Run and Preserve E0–E5 Public-Dev Evidence

**Files:**
- Create after verified runs:
  - `results/evaluation_v1/r2_optimization/<run-id>-E0.json`
  - `results/evaluation_v1/r2_optimization/<run-id>-E1.json`
  - `results/evaluation_v1/r2_optimization/<run-id>-E2.json`
  - `results/evaluation_v1/r2_optimization/<run-id>-E3.json`
  - `results/evaluation_v1/r2_optimization/<run-id>-E4.json`
  - `results/evaluation_v1/r2_optimization/<run-id>-E5.json`
- Create: `docs/r2_chase_lite_public_dev_results_2026-09-25.md`
- Modify: `docs/public_pilot_results_2026-09-25.md`

**Interfaces:**
- Consumes the manual workflow artifacts
- No code/prompt/scorer changes between E0 and E5 once the first evidence run begins

- [ ] **Step 1: Freeze the experiment commit**

Record:

```bash
git rev-parse HEAD
git status --porcelain
```

Expected: one exact SHA, clean tree.

Do not start E0 until CI on that SHA is green.

- [ ] **Step 2: Run local/offline preflight for all six experiments**

Use the CLI's preflight-only option:

```bash
for e in E0 E1 E2 E3 E4 E5; do
  python -m scripts.run_r2_optimization --experiment "$e" ... --preflight-only
done
```

Expected: every experiment reports a ceiling below `$1.00`; record each ceiling in the results document before paid execution.

- [ ] **Step 3: Trigger exactly one evidence run per E0–E5**

Run in order E0, E1, E2, E3, E4, E5 against the same commit and rebuilt logical snapshot.

For each run verify before continuing:

- `run_status == "completed"`;
- 8 distinct case IDs;
- actual model equals pinned model;
- temperature is 0;
- snapshot content SHA equals the version lock;
- scorer SHA is unchanged;
- usage metadata is complete;
- result artifact SHA-256 is recorded.

If any run is invalid, stop the series; do not change code and continue as if comparable.

- [ ] **Step 4: Preserve artifacts**

Download each Actions artifact, verify JSON SHA, and commit the six extracted JSON files to `results/evaluation_v1/r2_optimization/` in one documentation/evidence commit.

Do not alter their contents.

- [ ] **Step 5: Write the comparison document**

`docs/r2_chase_lite_public_dev_results_2026-09-25.md` must report:

```text
Experiment
Execution Accuracy
Oracle@N
Selector Conditional Accuracy
Syntax Validity
Execution Success
Safety Rejection
Mean SQL Diversity
Mean Result Diversity
API Calls
Input / Output Tokens
Cost
Latency
```

Also include:

- per-case final verdict;
- whether any correct candidate existed;
- whether selection lost a correct candidate;
- error taxonomy;
- explicit statement that 8 cases are diagnostic only;
- explicit distinction from the prior 2/8 v1 and 5/8 scorer replay;
- no claim of model improvement from scorer-only changes.

- [ ] **Step 6: Decide whether the public-pilot gate passes**

A **strong pilot signal** requires E_best to improve at least 2/8 cases over the newly run E0.

Regardless of the threshold, report exact values without rounding away case counts.

- [ ] **Step 7: Commit evidence**

```bash
git add results/evaluation_v1/r2_optimization docs/r2_chase_lite_public_dev_results_2026-09-25.md docs/public_pilot_results_2026-09-25.md
git commit -m "docs(eval): preserve CHASE-Lite public-dev experiments"
git push origin master
```

---

### Task 11: Add E6 One-Shot Fixer Only After E0–E5 Review

**Gate:** Do not start this task until Task 10 is complete and the E0–E5 error report shows syntax or execution failures that can plausibly benefit from repair. If there are zero such failures, record `E6 not run: no eligible repair failures` in the results document and skip code changes in this task.

**Files if gate passes:**
- Create: `evaluation/text_to_sql_optimization/fixer.py`
- Create: `tests/test_text_to_sql_optimization_fixer.py`
- Modify: `evaluation/text_to_sql_optimization/runner.py`
- Modify: `evaluation/text_to_sql_optimization/budget.py`

**Interfaces:**
- Produces: `repair_once(case, context, failed_candidate, provider) -> CandidateDraft`
- Eligible only for `SYNTAX_ERROR` or `EXECUTION_ERROR`
- One call maximum per case

- [ ] **Step 1: Write eligibility tests**

```python
@pytest.mark.parametrize("error_category", ["SYNTAX_ERROR", "EXECUTION_ERROR"])
def test_fixer_runs_once_for_eligible_failures(error_category):
    ...

@pytest.mark.parametrize(
    "error_category",
    ["RESULT_MISMATCH", "SAFETY_REJECTION", "OK"],
)
def test_fixer_never_runs_for_ineligible_outcome(error_category):
    ...
```

Use a counting fake provider and assert exact call counts.

- [ ] **Step 2: Write zero-row protection test**

A syntactically valid executable SQL returning zero rows must not trigger repair.

- [ ] **Step 3: Implement fixer prompt**

Input:

- question;
- schema/value hints;
- failed SQL;
- parser/execution error text.

Do not include gold or another candidate's correctness.

Prompt says:

```text
Repair this DuckDB read-only SELECT query only enough to resolve the supplied
syntax/execution error. Preserve the user's intended semantics. Return one SQL
statement only.
```

- [ ] **Step 4: Enforce one attempt**

Runner stores `repair_attempted: true/false`; a repaired candidate is executed once and never recursively repaired.

- [ ] **Step 5: Extend budget preflight**

E6 worst-case adds one repair request per case and must still remain below the evidence budget before any API call.

- [ ] **Step 6: Run tests**

```bash
python -m pytest tests/test_text_to_sql_optimization_fixer.py tests/test_text_to_sql_optimization_runner.py tests/test_text_to_sql_optimization_budget.py -q
python -m pytest -q
```

- [ ] **Step 7: Commit**

```bash
git add evaluation/text_to_sql_optimization/fixer.py evaluation/text_to_sql_optimization/runner.py evaluation/text_to_sql_optimization/budget.py tests/test_text_to_sql_optimization_fixer.py tests/test_text_to_sql_optimization_runner.py tests/test_text_to_sql_optimization_budget.py
git commit -m "feat(eval): add one-shot R2 query repair"
git push origin master
```

- [ ] **Step 8: Run one E6 evidence experiment**

Only after CI is green and the preflight passes. Preserve its artifact separately and update the result document. Never rewrite E0–E5.

---

### Task 12: Stability Check and Official-Dev Handoff

**Files:**
- Create: `docs/r2_chase_lite_stability_2026-09-25.md`
- Modify: `README.md`
- Modify: `docs/r2_chase_lite_public_dev_results_2026-09-25.md`

**Interfaces:**
- Stability check reruns only E0 and E_best three times each
- Same commit/model/prompts/scorer/snapshot for all six runs
- Official-dev handoff freezes the winning config; it does not open frozen

- [ ] **Step 1: Select E_best from public_dev without touching frozen**

Selection order:

1. highest Execution Accuracy;
2. if tied, lower total API cost;
3. if tied, fewer selector calls;
4. if tied, lower total latency.

Record the rule and selected experiment before stability runs.

- [ ] **Step 2: Run E0 three times and E_best three times**

Each run gets a unique run ID. Report:

- case-level agreement across repetitions;
- min/mean/max Execution Accuracy;
- changed SQL outputs by case;
- cost/latency range.

Do not average different benchmark versions.

- [ ] **Step 3: Write the stability document**

The document must state whether temperature-0 outputs were stable and identify any case whose selected SQL changed across runs.

- [ ] **Step 4: Freeze the official-dev configuration**

Write a machine-readable config block into the results document:

```json
{
  "experiment": "E5",
  "model": "gpt-4.1-mini-2025-04-14",
  "temperature": 0,
  "generator_strategies": ["direct", "query_plan", "divide_and_conquer"],
  "value_hints": true,
  "selector": "pairwise_on_disagreement",
  "fixer": false
}
```

Use the actual winning experiment values; do not assume E5 wins.

Record prompt hashes and git SHA.

- [ ] **Step 5: Update README status**

Document:

- CHASE-Lite public-dev experiment exists;
- exact public-dev result is diagnostic;
- official three-source R2 dev remains the next gate;
- frozen has not been used for tuning.

- [ ] **Step 6: Run final verification**

```bash
python -m pytest -q
git status --porcelain
git log -1 --oneline
```

Expected:

- all tests PASS;
- clean working tree after documentation commit;
- final commit is on `master`.

- [ ] **Step 7: Commit**

```bash
git add docs/r2_chase_lite_stability_2026-09-25.md docs/r2_chase_lite_public_dev_results_2026-09-25.md README.md
git commit -m "docs(eval): freeze CHASE-Lite official-dev configuration"
git push origin master
```

---

## End-to-End Verification Checklist

Before claiming CHASE-Lite implementation complete:

- [ ] `python -m pytest -q` passes.
- [ ] GitHub CI passes on Python 3.11 and 3.12.
- [ ] No paid workflow runs on push or pull request.
- [ ] No optimizer provider prompt contains gold SQL or gold result.
- [ ] E4 2-vs-1 majority behavior is covered by test.
- [ ] E5 2-vs-1 disagreement invokes LLM selection and is covered by test.
- [ ] Result fingerprint tests match all existing comparator semantics.
- [ ] Value hints stay under 8192 bytes and are deterministic.
- [ ] Public-dev model/scorer/snapshot/prompt/config hashes are preserved.
- [ ] E0 is newly generated under the same experimental contract as E1–E5.
- [ ] The old 5/8 replay is never used as a new model baseline.
- [ ] Accuracy is always reported with API calls, tokens, cost, and latency.
- [ ] Frozen holdout remains untouched.
- [ ] E6 is skipped unless E0–E5 provide an eligible repair rationale.
- [ ] Official-dev config is frozen before any official-dev comparison.

## Expected Commit Sequence

```text
feat(eval): add gold-blind R2 optimization models
feat(eval): add deterministic R2 value hints
feat(eval): add CHASE-Lite SQL generators
feat(eval): execute and fingerprint SQL candidates
feat(eval): add CHASE-Lite SQL selection
feat(eval): add R2 optimization metrics
feat(eval): add R2 optimization budget gate
feat(eval): orchestrate CHASE-Lite R2 experiments
ci(eval): add manual CHASE-Lite public-dev runner
docs(eval): preserve CHASE-Lite public-dev experiments
feat(eval): add one-shot R2 query repair          # only if E6 gate passes
docs(eval): freeze CHASE-Lite official-dev configuration
```

No squashing is required; each commit is intended to be independently reviewable and pushed directly to `master`.
