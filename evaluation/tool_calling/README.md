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

| Metric | Description |
|--------|-------------|
| Tool Precision | Of predicted tools, % correct |
| Tool Recall | Of required tools, % predicted |
| Tool F1 | Harmonic mean of tool-level precision/recall |
| Exact Call F1 | Tool + required argument values correct |
| Argument Field Accuracy | Required argument values correct |
| Critical Argument Accuracy | Critical argument values correct |
| Tool Set Exact Match | Predicted tool multiset matches allowed required/optional set |
| No-Tool Accuracy | Correctly abstains on no-tool requests |
| Trajectory Success | Required calls exact, no non-exact predictions, no forbidden/order violations |

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
│   ├── dev/         # 20 development cases
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
