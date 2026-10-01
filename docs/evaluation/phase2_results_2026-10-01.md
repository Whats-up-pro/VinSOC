# Phase 2 Results: 7/8 EX

**Date:** 2026-10-01  
**Run:** `r2_phase2_live/20261001_3f9d72d`  
**Condition:** E3 (DualSQL v2 with Linker + Generator + Tools)

---

## Results

| Case | Result | Error |
|------|--------|-------|
| ctu_sql_001 | PASS | OK |
| ctu_sql_002 | PASS | OK |
| ctu_sql_003 | PASS | OK |
| ctu_sql_004 | PASS | OK |
| ctu_sql_005 | PASS | OK |
| ctu_sql_006 | **FAIL** | TOOL_LIMIT |
| ctu_sql_007 | PASS | OK |
| ctu_sql_008 | PASS | OK |

**Score: 7/8 EX (87.5%)**

---

## Case 006 Analysis: TOOL_LIMIT

**Question:** "Return the five scenario 5 destination ports with most flows"

**Root Cause:**

| Turn | Call | Result |
|------|------|--------|
| 1 | `database_profiler` | Schema OK, found domains |
| 2 | `value_search(dst_port, "ctu13_s5")` | No match (dst_port is INTEGER) |
| 3 | `value_search(dst_port, "80")` | No match |
| 3 | `value_search(dst_port, "443")` | No match |
| 3 | `value_search(dst_port, "53")` | No match |

**Problem:** Model tried to search specific port values in `dst_port` (INTEGER column), but:
1. INTEGER columns don't have catalog values to search
2. This case needs SQL aggregation (`GROUP BY dst_port ORDER BY count(*) DESC LIMIT 5`)
3. Model spent all 5 tool calls searching non-existent port values

**Fix needed:** Prompts should distinguish INTEGER columns (use aggregation) vs VARCHAR columns (use value search).

---

## Progress Summary

| Version | Score | Delta |
|---------|-------|-------|
| v1 E3 (old) | 0/8 | baseline |
| v2 Remediation | 1/8 | +1 |
| **Phase 2** | **7/8** | +7 |

---

## Files

- Results: `results/evaluation_v1/ctu_network_public/r2_phase2_live/20261001_3f9d72d/suite/`
- Commit: `6534584`
