# Preliminary Evaluation Results

**Run date:** 2026-09-18 UTC  
**Status:** engineering baseline, not an official model benchmark

This document records the results that are available now. It separates mock integration checks from a future evaluation on a frozen public-data snapshot. The two must not be compared as model capability scores.

## 1. Tool-calling integration baseline

### Protocol

- 20 existing files in `scenarios/case_*.json`.
- `MockProvider(model="benchmark-mock")` and each scenario's existing mock skill data.
- Expected tools come from `ground_truth.expected_tools`.
- Tool names are matched as multisets. A repeated call would count as a separate call.
- This is an **integration** result: it includes the current orchestrator and tool implementations. It is not the planned decision-only evaluation of an OpenAI model.

Reproduce it with:

```bash
python scripts/measure_tool_calling.py
```

### Result

| Metric | Result |
|---|---:|
| Scenarios | 20 |
| Actual tool calls | 42 |
| True positive / false positive / false negative calls | 39 / 3 / 5 |
| Tool Precision | 92.86% |
| Tool Recall | 88.64% |
| Tool F1 | 90.70% |
| Tool-set exact match | 60.00% (12/20) |
| Exact call-sequence match | 60.00% (12/20) |
| Integration execution success | 92.86% (39/42) |

The eight tool-set mismatches are `case_001`, `case_004`, `case_005`, `case_010`, `case_016`, `case_018`, `case_019`, and `case_020`.

The three execution failures are in `case_012` to `case_014`. The mock orchestration sends `WS001`, `WS023`, and `WS045` to `cti_enrichment`. They are host identifiers, not valid IOCs, so CTI validation fails closed as required. This is a useful integration defect to fix, but it is not a ThreatFox availability failure.

### What this result does not prove

- It does not measure an OpenAI or OpenRouter model.
- It does not yet score tool arguments, ordering constraints, optional tools, or no-tool decisions with the full benchmark contract.
- It does not use a frozen public DuckDB snapshot.

The final Track A report must separate A1 decision-only metrics from A2 integration metrics and use the approved formal call schema.

## 2. Text-to-SQL engineering checks

There is no official Text-to-SQL score yet because the public VinSOC snapshot has not been frozen and no model has been run against it. Reporting an execution-accuracy benchmark before that point would be misleading.

The new DuckDB unit test contains three controlled checks:

| Check | Expected behaviour | Result |
|---|---|---|
| Valid `SELECT` with equivalent result | Executes and matches gold SQL | Pass |
| Valid but destructive `DROP TABLE` | Hard-rejected before execution | Pass |
| Invalid `SELECT FROM ...` | Rejected by the DuckDB parser | Pass |

Run it with:

```bash
python -m pytest -q tests/test_duckdb_data_layer.py
```

All 3 checks passed. The corresponding rates on these three test inputs are 66.67% syntax validity, 33.33% execution success, 33.33% execution accuracy, and 33.33% safety rejection. These percentages only prove evaluator behaviour; they are **not** a model result and must not be used in a report or comparison.

## 3. Test suite status

| Check | Result |
|---|---:|
| New DuckDB and Text-to-SQL tests | 3 passed |
| Full repository suite | 114 passed, 2 failed |
| Lint: new `vinsoc_data`, `evaluation`, and DuckDB test files | passed |

The two full-suite failures are older CTI tests that expect `CTISkill()` without a configured source to return a successful `UNKNOWN` result. They conflict with the approved rule: no source or source execution failure must fail closed. They are not caused by the DuckDB change.

## 4. Conditions before official results

Official Track B results can start only after all of the following are frozen:

1. Exact public files, checksums, retrieval dates, and licence notes in `dataset_provenance`.
2. One DuckDB snapshot hash and the `vinsoc_soc_schema_v1` schema.
3. Validated gold SQL and comparator for each case.
4. Pinned provider/model and evaluation mode with OpenRouter fallback disabled.

At that point, the official report should publish syntax validity, execution success, execution accuracy, safety rejection rate, cost, latency, and per-case errors.
