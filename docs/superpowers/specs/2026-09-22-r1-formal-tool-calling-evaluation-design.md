# VinSOC R1 — Formal Tool Calling Evaluation Specification

**Document type:** Architectural specification
**Stage:** R1 (Implementation in Progress)
**Status:** Active
**Repository:** `Whats-up-pro/VinSOC`
**Current master:** `b011302`

---

# 1. Purpose

R1 xây dựng một evaluation framework chính thức để trả lời câu hỏi:

> Khi nhận một SOC investigation request và tập tool schemas của VinSOC, model có chọn đúng tool, đúng arguments và đúng chuỗi hành động hay không?

Stage này **không đánh giá chất lượng CTI/network/endpoint skill bên trong**.

---

# 2. Two-Layer Architecture

```
                ┌───────────────┐
Input Case ────→│      A1       │
                │ Model Decision│
                └───────┬───────┘
                        │
                   Tool Calls
                        │
                        ▼
                ┌───────────────┐
                │      A2       │
                │ Integration   │
                └───────────────┘
```

## A1 — Decision-Only Evaluation (Inspired by BFCL)

Đánh giá:
```
question + system prompt + tool schemas
         ↓
         LLM
         ↓
    predicted tool call(s)
```

**Không execute production skill.** Inspired by BFCL's approach of measuring pure function selection accuracy.

## A2 — Integration Evaluation

Đánh giá:
```
model decision → orchestrator → skill → evidence
```

---

# 3. Reference Benchmarks

## BFCL (Berkeley Function Calling Leaderboard)

**Key insights applied to R1:**

1. **Multi-turn evaluation**: Model calls tool, gets response, continues calling
2. **Strict signature matching**: Arguments must match function schema exactly
3. **Categories**: Simple, Multiple, Parallel, Complex
4. **Metrics**: Call-level accuracy, Argument-level accuracy

**Our adaptation:**
- Single-turn (A1) + Multi-turn (future R1.7)
- Strict argument matching with normalization
- Category coverage: CTI-only, Network-only, Endpoint-only, Multi-tool

## Spider2 (Text-to-SQL Benchmark)

**Key insights for R2 (Text-to-SQL):**

1. **Difficulty levels**: Easy, Medium, Hard, Extra Hard
2. **Component metrics**: SELECT, WHERE, JOIN accuracy
3. **Execution-based evaluation**: Run SQL against test database

**R2 will apply:**
- Difficulty classification for SQL generation
- Component-level error analysis
- Execution accuracy for SQL

---

# 4. Implementation Status

| Component | File | Status |
|-----------|------|--------|
| R1.1 Data Model | `evaluation/tool_calling/models.py` | ✅ |
| R1.2 Argument Normalization | `evaluation/tool_calling/arguments.py` | ✅ |
| R1.3 Call Matcher | `evaluation/tool_calling/matching.py` | ✅ |
| R1.4 Metrics Engine | `evaluation/tool_calling/metrics.py` | ✅ |
| R1.5 A2 Integration | `evaluation/tool_calling/integration_runner.py` | ✅ |
| R1.6 A1 Decision | `evaluation/tool_calling/decision_runner.py` | 🔄 LLM not integrated |
| R1.7 Multi-Turn | - | ⏳ Pending |
| R1.8 Benchmark Authoring | `evaluation/tool_calling/benchmarks/` | 🔄 20 cases converted |
| R1.9 Official Baseline | - | ⏳ Pending |

---

# 5. Key Design Decisions

## 5.1 Match Types (BFCL-inspired)

```python
class MatchType(Enum):
    EXACT    = "exact"      # Tool + all critical args match
    PARTIAL  = "partial"    # Tool matches, some args differ  
    NO_MATCH = "no_match"   # No compatibility
```

**Rationale**: BFCL uses strict matching. We add PARTIAL to distinguish between wrong tool vs wrong argument.

## 5.2 Argument Categories

| Category | Behavior |
|----------|----------|
| Critical | Wrong value = call fails |
| Required | Must be present |
| Optional | Can be missing |

## 5.3 Metrics (BFCL-inspired)

| Metric | Definition |
|--------|------------|
| **Call Accuracy** | % of calls with EXACT match |
| **Argument Accuracy** | % of arguments correct (given call matched) |
| **Trajectory Success** | All required calls EXACT + no forbidden |

---

# 6. Current Results

### A2 Integration Benchmark (20 scenarios)

```
Cases: 20
Tool Precision: 80.65%
Tool Recall: 59.38%
Tool F1: 68.22%
Tool Set EM: 15.00%
Trajectory Success: 0.00%
```

### Analysis

**HIGH FP** (20%): Extra tool calls beyond expected
**HIGH FN** (40%): Missing required tool calls

This indicates the orchestrator is calling tools differently than gold standard expects.

---

# 7. Next Steps

1. **R1.6**: Integrate LLM provider for A1 (decision-only) evaluation
2. **R1.8**: Author more benchmark cases with proper gold standards
3. **R1.9**: Run official baseline with pinned model
4. **R2**: Start Text-to-SQL benchmark (Spider2-inspired)

---

# 8. R2 Preview (Text-to-SQL)

Inspired by Spider2, R2 will evaluate:

```
Natural language question
         ↓
         LLM
         ↓
    Generated SQL
         ↓
   Execute against test DB
         ↓
   Compare results
```

**Metrics:**
- Execution Accuracy
- Component Accuracy (SELECT, WHERE, JOIN, etc.)
- Hard/Extra Hard case performance

---

# 9. Appendix: BFCL Categories (Reference)

| Category | Description |
|----------|-------------|
| Simple | Single function call |
| Multiple | Sequential function calls |
| Parallel | Independent parallel calls |
| Complex | Nested/conditional calls |

Our categories mapped to SOC domain:
- Basic: Single tool (CTI-only, Network-only, Endpoint-only)
- Intermediate: Two tools (CTI+Network, CTI+Endpoint, Network+Endpoint)
- Advanced: Three tools (full investigation)
