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
| True positive / false positive / false negative calls | 36 / 6 / 5 |
| Tool Precision | 36/42 = 85.71% |
| Tool Recall | 36/41 = 87.80% |
| Tool F1 | 86.75% |
| Tool-set exact match | 9/20 = 45.00% |
| Exact call-sequence match | 9/20 = 45.00% |
| Integration execution success | 92.86% (39/42) |

The 11 tool-set mismatches are `case_001`, `case_004`, `case_005`, `case_010`,
`case_012`, `case_013`, `case_014`, `case_016`, `case_018`, `case_019`, and
`case_020`.

Cases `case_012` to `case_014` now correctly expect endpoint investigation only.
Their hostname inputs (`WS001`, `WS023`, and `WS045`) have no compatible CTI
pivot. The unchanged orchestrator still makes an unnecessary `cti_enrichment`
call for each case. Those calls are false positives and fail validation, which
explains the three unsuccessful executions. This is an integration limitation,
not a ThreatFox availability failure. CTI must fail closed when the input is
invalid, the source is missing or cannot run, or validation fails; with an
executable source and no match, it succeeds with `UNKNOWN`.

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
| Targeted CTI and integration checks | 49/49 passed, 96 warnings |
| Benchmark and DuckDB checks | 4/4 passed |
| Full repository suite | 138/138 passed, 828 warnings |

The earlier two stale no-source CTI test failures are resolved. The 828 warnings
remain part of the current baseline. Ruff on the changed and related legacy
files reports 36 pre-existing style and modernization issues; lint is not clean.

## 4. Conditions before official results

Official Track B results can start only after all of the following are frozen:

1. Exact public files, checksums, retrieval dates, and licence notes in `dataset_provenance`.
2. One DuckDB snapshot hash and the `vinsoc_soc_schema_v1` schema.
3. Validated gold SQL and comparator for each case.
4. Pinned provider/model and evaluation mode with OpenRouter fallback disabled.

At that point, the official report should publish syntax validity, execution success, execution accuracy, safety rejection rate, cost, latency, and per-case errors.
