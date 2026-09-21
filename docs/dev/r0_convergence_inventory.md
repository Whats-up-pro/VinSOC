# R0 Convergence Inventory

**Created**: 2026-09-19
**Updated**: 2026-09-21
**Status**: Completed

## Verification

| Item | SHA | Status |
|------|-----|--------|
| Base master | `4a8261f` | Verified |
| Closeout branch | `feat/r0-closeout` | All 7 plans completed |
| Test suite | 172 passed | ✅ |
| CI | Updated | ✅ |

## Plans Completed

| Plan | Commit | Status |
|------|--------|--------|
| 01 CTI Provider Runtime | `886d260` | ✅ |
| 02 Evidence V2 Schema | `c639bf2` | ✅ |
| 03 Network V2 | `6d29c61` | ✅ |
| 04 Tool Routing | `d9e7418` | ✅ |
| 05 Repository Hygiene | `1432abc` | ✅ |
| 06 CI Full Suite | `7bcbf86` | ✅ |
| 07 Finalization | - | ✅ |

## R0 Changes Summary

### Evidence V2
- `agent/evidence.py` - OBSERVED/DERIVED/EXTERNAL_INTEL classes
- `schemas/investigation_case.json` - Schema updated to require V2 fields
- `tests/test_evidence_v2.py` - 3 tests
- `tests/test_schema_contracts.py` - 5 tests (new)

### CTI Provider Runtime
- `skills/cti_providers.py` - CTIProviderStatus enum
- `skills/cti_skill.py` - providers parameter, fail-closed aggregation
- `tests/test_cti_providers.py` - 15 tests (new)

### Network V2
- `schemas/network_result.json` - Analytics candidates schema
- `skills/network_skill.py` - Already V2 (periodicity, scan, transfer, fanout)

### Tool Routing
- `agent/tools.py` - Removed CTI-first bias

### CI
- `.github/workflows/ci.yml` - Full pytest on 3.11/3.12

## Remaining Work

R1 Tool Calling Evaluation - pending
R2 Text-to-SQL Benchmark - pending
