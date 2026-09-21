# VinSOC R1 — Formal Tool Calling Evaluation Specification

**Document type:** Architectural specification
**Stage:** R1
**Status:** Proposed for review
**Repository:** `Whats-up-pro/VinSOC`
**Current inspected master:** `115f07aa67ee6d1765b8c819f8d94098da1e0058`

---

# 1. Purpose

R1 xây dựng một evaluation framework chính thức để trả lời câu hỏi:

> Khi nhận một SOC investigation request và tập tool schemas của VinSOC, model có chọn đúng tool, đúng arguments và đúng chuỗi hành động hay không?

Stage này **không đánh giá chất lượng CTI/network/endpoint skill bên trong**.

Nó đánh giá:

```
LLM
 ↓
Tool decision
 ↓
Tool selection
 ↓
Arguments
 ↓
Trajectory
```

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

## A1 — Decision-Only Evaluation

Đánh giá:

```
question
+
system prompt
+
tool schemas
 ↓
LLM
 ↓
predicted tool call(s)
```

**Không execute production skill.** Chỉ đo capability của model trong việc quyết định gọi tool.

## A2 — Integration Evaluation

Đánh giá:

```
model/mock tool decision
 ↓
orchestrator
 ↓
skill
 ↓
evidence
```

Kiểm tra VinSOC có thực thi quyết định đó đúng không.

---

# 3. Benchmark Case Model

```python
ToolCallCase:
  case_id: str
  category: str
  difficulty: "basic" | "intermediate" | "advanced"
  request: str
  reference_time: str  # ISO 8601
  expected_calls: List[ExpectedCall]
  forbidden_tools: List[str]
  ordering_constraints: List[OrderingConstraint]
  acceptable_trajectories: List[List[str]]  # optional
  notes: str
```

## ExpectedCall Schema

```python
ExpectedCall:
  call_id: str
  tool: str  # cti_enrichment | network_investigation | endpoint_investigation
  required_arguments: Dict[str, Any]
  critical_arguments: List[str]
  optional: bool
```

## Example

```json
{
  "case_id": "r1_001",
  "category": "endpoint_only",
  "difficulty": "basic",
  "request": "Investigate suspicious process on workstation WS001",
  "reference_time": "2026-09-22T00:00:00Z",
  "expected_calls": [
    {
      "call_id": "endpoint_1",
      "tool": "endpoint_investigation",
      "required_arguments": {"host": "WS001"},
      "critical_arguments": ["host"],
      "optional": false
    }
  ],
  "forbidden_tools": ["cti_enrichment"],
  "ordering_constraints": [],
  "notes": "No CTI pivot until endpoint evidence provides compatible IOC"
}
```

---

# 4. Argument Categories

## Critical Arguments

Wrong value invalidates the call.

| Tool | Critical |
|------|----------|
| cti_enrichment | indicator, indicator_type |
| network_investigation | indicator |
| endpoint_investigation | host |

## Required Non-Critical

Must be present, but may permit normalization.

| Argument | Normalization |
|----------|---------------|
| time_range | UTC conversion |
| indicator_type | enum validation |

## Optional

Missing optional arguments do not reduce correctness.

---

# 5. Argument Normalization

| Type | Rule |
|------|------|
| IP | Canonical IPv4/IPv6 parsing |
| Domain | lowercase, strip trailing dot |
| Hash | lowercase hex |
| URL | scheme/host case normalization only |
| Timestamp | UTC conversion |
| List | set comparison when order irrelevant |

---

# 6. Call Matching Algorithm

**Do NOT match by sequence index alone.**

Use one-to-one compatibility matching:

```
1. tool name compatibility
2. critical arguments
3. required arguments
4. optional constraints
```

Example - Gold vs Prediction:

| Gold | Prediction | Result |
|------|-----------|--------|
| CTI(A) | CTI(A) | TP |
| Network(A) | CTI(A) | FP + FN |

Example - Duplicate penalty:

| Gold | Prediction | Result |
|------|-----------|--------|
| CTI(A) | CTI(A) | TP |
| Network(A) | CTI(A) + CTI(A) + Network(A) | TP + 2×FP |

---

# 7. Metrics

## M1 — Tool-Level P/R/F1

```
TP: predicted required tool matched
FP: unnecessary/duplicate/forbidden call
FN: missing required call
```

## M2 — Tool Set Exact Match

```
predicted required tool multiset == gold required tool multiset
```

## M3 — Exact Call F1 (Headline)

```
tool correct + required args correct
```

## M4 — Argument Field Accuracy

```
correct required argument fields / all required argument fields
```

## M5 — Critical Argument Accuracy (Headline)

```
correct critical fields / all critical fields
```

## M6 — Forbidden Tool Rate

```
forbidden tool calls / cases
```
Lower is better.

## M7 — No-Tool Accuracy

```
correct no-tool decisions / all no-tool cases
```

## M8 — Ordering Constraint Accuracy

```
satisfied ordering constraints / total constraints
```

## M9 — Trajectory Success (Strictest)

Requires:
- all required calls satisfied
- no forbidden calls
- critical arguments correct
- ordering constraints satisfied

---

# 8. Error Taxonomy

```
WRONG_TOOL              - wrong tool selected
MISSING_TOOL            - required tool not called
EXTRA_TOOL              - unnecessary call
WRONG_ARGUMENT          - argument value wrong
MISSING_ARGUMENT        - required argument absent
WRONG_CRITICAL_ARGUMENT - critical arg wrong
FORBIDDEN_TOOL          - forbidden tool called
WRONG_ORDER             - ordering constraint violated
DUPLICATE_CALL          - same call repeated unnecessarily
NO_TOOL_FALSE_POSITIVE - no-tool case got a tool
NO_TOOL_FALSE_NEGATIVE  - tool case got no-tool
MALFORMED_TOOL_CALL     - invalid call format
```

---

# 9. Case Categories

Minimum R1 coverage:

```
CTI-only
Network-only
Endpoint-only
CTI + Network
CTI + Endpoint
Network + Endpoint
CTI + Network + Endpoint
hostname-led investigation
hash-led investigation
URL-led investigation
network-alert investigation
process/EDR investigation
invalid IOC
unsupported type
missing information
no-tool case
multi-step pivot
duplicate-call trap
wrong-argument trap
```

---

# 10. Dataset Structure

```
benchmarks/tool_calling/
├── dev/
│   └── cases.jsonl
└── frozen/
    └── cases.jsonl
```

- **dev/**: 30-50 cases for development, prompt tuning, evaluator debugging
- **frozen/**: 30-50 cases for official evaluation (never used for tuning)

---

# 11. A1 Evaluation Flow

```
ToolCallCase
    ↓
Prompt Builder (system prompt + request)
    ↓
Production Tool Schemas
    ↓
Pinned LLM Provider (temperature=0, fallback=DISABLED)
    ↓
Raw tool_calls
    ↓
Normalizer
    ↓
Matcher
    ↓
Metrics
    ↓
Result
```

**Production skill execution is explicitly disabled.**

---

# 12. A2 Evaluation Flow

```
Case
    ↓
MockProvider / Real Provider
    ↓
Production orchestrator
    ↓
Production skills
    ↓
Evidence
    ↓
ToolTrace
    ↓
same Matcher + Metrics
```

Reuse the same matching/metric engine. No separate implementation.

---

# 13. Reproducibility Metadata

Every A1 run records:

```
run_id
timestamp
git_sha
benchmark_version
benchmark_hash
provider
model
temperature
system_prompt_hash
tool_schema_hash
fallback_enabled
per_case_raw_calls
per_case_normalized_calls
latency_ms
input_tokens
output_tokens
estimated_cost_usd
```

---

# 14. CLI Entrypoint

```bash
# A1 Decision-only evaluation
python scripts/run_tool_calling_benchmark.py \
  --mode decision \
  --split dev

# A2 Integration evaluation  
python scripts/run_tool_calling_benchmark.py \
  --mode integration \
  --split frozen
```

---

# 15. Artifact Layout

```
results/tool_calling/<run_id>/
├── metadata.json
├── cases.jsonl
├── metrics.json
└── report.md
```

Each result folder is **immutable** after completion.

---

# 16. Security Constraints

Benchmark runner SHALL NOT:
- execute shell commands from model output
- allow arbitrary tools
- write to production systems
- perform remediation

A1 performs **no production skill execution**.

A2 remains **read-only**.

---

# 17. R1 Implementation Sequence

```
R1.1 Benchmark Data Model
R1.2 Argument Normalization
R1.3 Call Matcher
R1.4 Metrics Engine
R1.5 A2 Integration Runner Migration
R1.6 A1 Decision-Only Runner
R1.7 Multi-Turn Harness
R1.8 Benchmark Authoring
R1.9 Official Baseline
```

---

# 18. Stage Gates

| Gate | Requirement |
|------|-------------|
| G1 | Benchmark schema finalized, matcher tests green |
| G2 | All 9 metrics verified |
| G3 | A1/A2 separation enforced |
| G4 | dev + frozen benchmark reviewed |
| G5 | Reproducibility metadata complete |
| G6 | Official baseline from frozen |

---

# 19. Definition of Done

R1 complete when:

```
[ ] A1 decision-only evaluator exists
[ ] A2 uses same matcher
[ ] argument-aware matching works
[ ] duplicate calls penalized
[ ] optional calls represented
[ ] forbidden tools represented
[ ] no-tool cases represented
[ ] semantic ordering constraints supported
[ ] multiple valid trajectories supported
[ ] M1-M9 metrics implemented
[ ] dev benchmark reviewed
[ ] frozen benchmark reviewed independently
[ ] reproducibility metadata persisted
[ ] model/provider pinned
[ ] fallback disabled for official
[ ] official result from frozen
[ ] error analysis report generated
```

---

# 20. Explicit Non-Goals

R1 SHALL NOT:
- Text-to-SQL generation
- SQL benchmark
- network detector optimization
- CTI provider quality benchmark
- endpoint detection benchmark
- incident-response automation
- model fine-tuning

---

# 21. R1 Design Principle

> **Evaluate the decision the model should make, not the behavior the current code happens to exhibit.**

Gold data is independent of:
- MockProvider behavior
- current prompt weaknesses
- current orchestrator ordering

The benchmark is the fixed measurement instrument.
The implementation is improved against the benchmark — never the reverse.
