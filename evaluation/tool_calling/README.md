# Tool Calling Evaluation (R1)

Formal evaluation framework for measuring LLM tool selection accuracy in SOC investigations.

## Quick Start

```bash
# List available cases
python -m evaluation.tool_calling list dev

# Run real-model decision benchmark (A1)
python -m evaluation.tool_calling benchmarks dev --mode decision \
  --provider openai --model <PINNED_MODEL> --temperature 0

# Run integration/regression benchmark (A2)
python -m evaluation.tool_calling benchmarks dev --mode integration
```

## What is Evaluated?

| Component | Evaluated |
|-----------|-----------|
| Tool selection | ✅ |
| Tool arguments | ✅ |
| Critical arguments | ✅ |
| Ordering constraints | ✅ |
| Forbidden tools | ✅ |
| CTI/Network/Endpoint quality | ❌ |

## Architecture

```
┌──────────────────────────────────────────────┐
│              Evaluation Modes                  │
├────────────────────┬─────────────────────────┤
│  A1: Decision-Only │  A2: Integration       │
│  (LLM only)        │  (Mock + Orchestrator) │
├────────────────────┼─────────────────────────┤
│  Input → LLM → Call │ Input → Skills → Metrics│
└────────────────────┴─────────────────────────┘
```

## Metrics

### Headline metrics

| Question | Metric field | Meaning |
|----------|--------------|---------|
| Tool Selection Accuracy | `tool_set_exact_match_rate` | Predicted tool multiset exactly matches the allowed required/optional set |
| Exact Call Correctness | `exact_call_precision`, `exact_call_recall`, `exact_call_f1` | Tool name and required argument values are correct |
| Required Argument Accuracy | `argument_field_accuracy` | Required argument values are correct |
| Critical Argument Accuracy | `critical_argument_accuracy` | Critical argument values are correct |
| No-Tool Accuracy | `no_tool_accuracy` | Model correctly abstains on requests that need no investigation tool |
| Case Success | `trajectory_success_rate` | Single-turn case success: all required calls are exact, with no non-exact prediction, forbidden tool, or ordering violation |

`trajectory_success_rate` is retained for backward compatibility. In R1 A1 it means
single-turn case success; it is **not** BFCL V4 multi-turn trajectory evaluation.
Tool Precision, Tool Recall, and Tool F1 remain diagnostic tool-name metrics and
must not be reported as overall system accuracy.

## Baseline Status

The historical A2/MockProvider regression results are not treated as the official LLM accuracy baseline after metric hardening. Run A1 with a pinned provider/model/config on `dev`, perform controlled improvements, then run the frozen split once for the final holdout result.

## Directory Structure

```
evaluation/tool_calling/
├── models.py           # Data models
├── arguments.py       # Argument normalization
├── matching.py        # One-to-one call matching
├── metrics.py         # Metrics aggregation
├── decision_runner.py  # A1: LLM decision
├── integration_runner.py # A2: Mock integration
├── __main__.py       # CLI
├── benchmarks/
│   ├── dev/         # 24 development cases, including four no-tool cases
│   └── frozen/      # Holdout cases
└── results/         # Benchmark outputs
```

## Case Format

```json
{
  "case_id": "case_001",
  "category": "cti_only",
  "difficulty": "basic",
  "request": "Investigate IP 1.2.3.4",
  "expected_calls": [
    {
      "call_id": "cti_1",
      "tool": "cti_enrichment",
      "required_arguments": {"indicator": "1.2.3.4"},
      "critical_arguments": ["indicator"]
    }
  ],
  "forbidden_tools": []
}
```

## Categories

| Category | Description |
|----------|-------------|
| `cti_only` | CTI enrichment only |
| `network_only` | Network investigation only |
| `endpoint_only` | Endpoint investigation only |
| `cti_network` | CTI + Network |
| `cti_network_endpoint` | All three tools |
| `hostname_led` | No CTI until IOC pivot |

## Difficulty Levels

| Level | Description |
|-------|-------------|
| `basic` | Single tool, obvious |
| `intermediate` | Two tools |
| `advanced` | Three tools or pivot |

## CLI Reference

```bash
python -m evaluation.tool_calling list dev
python -m evaluation.tool_calling benchmarks dev --mode integration
python -m evaluation.tool_calling benchmarks dev --mode decision --provider openai --model <PINNED_MODEL> --temperature 0
python -m evaluation.tool_calling benchmarks frozen --mode decision --provider openai --model <PINNED_MODEL> --temperature 0
python -m evaluation.tool_calling benchmarks dev --cases case_001
```

## Reference

- [BFCL](https://gorilla.cs.berkeley.edu/blogs/15_bfcl_v4_web_search.html) - Berkeley Function Calling Leaderboard
- [Spider2](https://github.com/xlang-ai/Spider2) - Text-to-SQL benchmark
