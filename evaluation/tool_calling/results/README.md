# R1 Tool Calling Evaluation Results

## Directory Structure

```
results/tool_calling/
└── <run_id>/
    ├── metrics.json      # Aggregate metrics + per-case results
    ├── cases.jsonl       # Raw case results (optional)
    └── report.md        # Markdown summary (optional)
```

## Running Benchmarks

```bash
# A2 Integration (existing scenarios)
python -m evaluation.tool_calling benchmarks dev --mode integration

# A2 Integration (specific cases)
python -m evaluation.tool_calling benchmarks dev --mode integration --cases case_001 case_002

# A1 Decision (benchmark cases)
python -m evaluation.tool_calling benchmarks dev --mode decision
```

## Output Format

### metrics.json

```json
{
  "run_id": "r1_integration_dev_20260922_120000",
  "mode": "integration",
  "split": "dev",
  "aggregate": {
    "case_count": 20,
    "tool_precision": 0.8065,
    "tool_recall": 0.5938,
    "tool_f1": 0.6822,
    "exact_call_f1": 0.4500,
    "tool_set_exact_match_rate": 0.1500,
    "trajectory_success_rate": 0.0000
  },
  "error_summary": {
    "MISSING_TOOL": 14,
    "EXTRA_TOOL": 6
  },
  "case_results": [...]
}
```

## Interpreting Results

### Tool Precision / Recall / F1
- Measures whether the correct tools are selected
- High precision = few extra tools
- High recall = few missing tools

### Exact Call F1
- Measures whether both tool AND arguments are correct
- Stricter than tool-only metrics

### Trajectory Success
- All required calls exact + no forbidden + critical args correct
- The most stringent metric

### Error Categories
| Error | Meaning |
|-------|---------|
| MISSING_TOOL | Required tool not called |
| EXTRA_TOOL | Unnecessary tool called |
| FORBIDDEN_TOOL | Forbidden tool called |
| WRONG_ARGUMENT | Critical argument wrong |
