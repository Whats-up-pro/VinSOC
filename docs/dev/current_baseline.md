# Current Baseline - R0 Closeout

**Repository SHA:** `7bcbf86` (feat/r0-closeout)

**Measured on:** Python 3.13.7

**Status:** local engineering baseline, R0 closeout verified

## Recorded checks

| Command or check | Result |
|---|---|
| `python -m pytest -q` | 172/172 passed, 862 warnings |
| `python scripts/measure_tool_calling.py` | 20 scenarios; 42 actual calls; 36 TP, 6 FP, 5 FN |

### Tool Calling Metrics (MockProvider Integration)

| Metric | Value |
|---|---|
| Precision | 85.71% (36/42) |
| Recall | 87.80% (36/41) |
| F1 | 86.75% |
| Tool Set Exact Match | 45.00% (9/20) |
| Sequence Exact Match | 45.00% (9/20) |
| Execution Success Rate | 92.86% (39/42) |

## R0 Changes Summary

### Plan 01 - CTI Provider Runtime
- Added `CTIProviderStatus` enum (MATCH, NO_MATCH, NOT_APPLICABLE, ERROR)
- Added `providers` parameter to `CTISkill`
- Fail-closed contract: ERROR present → FAIL

### Plan 02 - Evidence V2 Schema
- Schema requires: `evidence_class`, `provenance`, `references`, `related_evidence_ids`
- Valid evidence classes: OBSERVED, DERIVED, EXTERNAL_INTEL

### Plan 03 - Network V2
- Updated `network_result.json` schema to V2 with analytics candidates
- Removed stale patterns: data_exfiltration, lateral_movement, unusual_port

### Plan 04 - Tool Routing
- Removed "Call this FIRST" and "Call this AFTER" from tool descriptions
- Added evidence-based routing guidance

### Plan 05 - Repository Hygiene
- Removed stale `.claude/agents/` files

### Plan 06 - CI Full Suite
- Full pytest on pull_request and master push
- Both Python 3.11 and 3.12

## Contract and Limitations

- CTI fail-closed semantics preserved
- Evidence V2 enforced in schema
- Network V2 analytics (not attack verdicts)
- Cases 012–014: MockProvider still calls CTI for hostname cases (counts as FP in metrics)

## Known Issues

- 862 deprecation warnings (datetime.utcnow())
- Tool Set Exact Match rate is 45% - reflects current MockProvider behavior, not target

## Next: R1

R1 plans pending:
- R1.1 Tool Call Ground Truth Schema
- R1.2 Argument Normalizer
- R1.3 One-to-One Call Matcher
- R1.4 Metrics Engine
