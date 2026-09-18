# Current Sprint A Baseline

**Repository SHA:** `45ac4f1`

**Measured on:** Python 3.12.14

**Status:** local engineering baseline

## Recorded checks

| Command or check | Result |
|---|---|
| `python -m pytest -q tests/test_cti_semantics.py tests/test_skills.py tests/test_integration.py` | 49/49 passed, 96 warnings |
| `python -m pytest -q tests/test_benchmark.py tests/test_duckdb_data_layer.py` | 4/4 passed |
| `python -m pytest -q` | 138/138 passed, 828 warnings |
| `python scripts/measure_tool_calling.py` | 20 scenarios; 42 actual calls; 36 TP, 6 FP, 5 FN |

The tool-calling measurement gives precision of 36/42 = 85.71%, recall of
36/41 = 87.80%, F1 of 86.75%, tool-set exact match of 9/20 = 45.00%, sequence
exact match of 9/20 = 45.00%, and integration execution success of 39/42 =
92.86%.

## Contract and limitations

- A missing or unusable CTI source, or input validation failure, fails closed.
- With an executable CTI source and no match, the result is successful with
  `UNKNOWN`.
- A hostname alone is not a CTI-compatible pivot. CTI needs an IP address,
  domain, URL, or file hash.
- Cases 012–014 correctly expect endpoint investigation only. The current
  orchestrator still attempts an unnecessary CTI call for each; those calls fail
  validation and count as false positives.
- Python 3.11 was not run locally because no Python 3.11 executable is
  available. Do not treat this baseline as a local Python 3.11 CI result.
- The 828 pytest warnings remain. Ruff on the changed and related legacy files
  reports 36 pre-existing style and modernization issues; lint is not clean.

This is a deterministic mock-integration baseline, not an OpenAI or OpenRouter
model benchmark. It does not replace the future decision-only evaluation against
a frozen public-data snapshot.
