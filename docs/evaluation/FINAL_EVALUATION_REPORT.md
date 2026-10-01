# VinSOC Phase 3 - Final Evaluation Report

**Date:** 2026-10-01  
**Status:** COMPLETE

---

## Executive Summary

DualSQL Phase 2 với INTEGER column hint đạt **8/8 EX** trên cả Dev và Frozen holdout.

| Benchmark | Score | Status |
|-----------|-------|--------|
| R2 Dev (CTU S5/S7) | **8/8** | ✅ Perfect |
| R2 Frozen (CTU S1/S4) | **8/8** | ✅ Perfect |

---

## R1: Tool Calling (24 cases)

| Model | Score | Status |
|-------|-------|--------|
| GPT-4.1 Mini | 22/24 (91.67%) | ✅ Baseline Winner |
| GPT-5 Mini | 19/24 (79.17%) | ❌ Not selected |

**Note:** Khác request contract → so sánh không hoàn toàn công bằng.

---

## R2: Text-to-SQL (8 cases)

### Progress Timeline

| Version | Dev Score | Delta | Notes |
|---------|-----------|-------|-------|
| v1 E3 | 0/8 | baseline | Model dùng label nhầm |
| v2 Remediation | 1/8 | +1 | Case 004 sửa được |
| Phase 2 (old) | 7/8 | +7 | Còn Case 006 TOOL_LIMIT |
| **Phase 2 (fixed)** | **8/8** | **+8** | INTEGER hint fix |

### Key Fix: INTEGER Column Handling

**Problem:** Case 006 (`dst_port` aggregation) gây TOOL_LIMIT vì model search INTEGER column thay vì dùng SQL aggregation.

**Solution:**
```python
# grounding.py - Phase2Tools.value_search()
{
    'resolution': 'typed_constraint_not_catalog_value',
    'hint': 'INTEGER column "dst_port" has no catalog values. Use SQL aggregation (COUNT, GROUP BY) for analysis - do NOT continue value search.'
}
```

**Result:** Model đọc hint và dùng `GROUP BY dst_port ORDER BY count(*) DESC LIMIT 5`.

---

## Frozen Holdout Evaluation

| Dataset | Cases | Score |
|---------|-------|-------|
| CTU S1/S4 (holdout) | 8 | **8/8** |

**Frozen snapshot:**
- Logical SHA: `0251bbe1a2bdca6acc4f181cf7342ec03b2e04048ab747c8625dbfc0b5d03ea4`
- S1 rows: 2,824,609
- S4 rows: 1,121,063
- Total: 3,945,672

---

## Technical Details

### Architecture
- **Linker:** Schema discovery + value grounding via tools
- **Generator:** SQL generation với linked schema
- **Controller:** Fail-closed, max 5 turns, max 5 tool calls

### Model Parameters
| Parameter | Value |
|-----------|-------|
| Model | `gpt-5-mini-2025-08-07` |
| reasoning_effort | `low` |
| max_completion_tokens | 1000 |
| temperature | `null` |

### Tools
| Tool | Purpose |
|------|---------|
| `database_profiler` | Inspect schema + column types |
| `value_search` | Find VARCHAR catalog values |
| `sql_probe` | Bounded SQL inspection |

---

## Files

### Results
- Dev: `results/evaluation_v1/ctu_network_public/r2_phase2_live/20261001_3f9d72d/suite/`
- Frozen: `results/evaluation_v1/ctu_network_frozen/r2_phase2_frozen_v1/`

### Code
- Phase2 tools: `evaluation/r2_phase2/grounding.py`
- Runner: `evaluation/r2_phase2/runner.py`

---

## Conclusion

1. **INTEGER column handling** là fix quan trọng nhất - giúp model phân biệt aggregation vs value search
2. **8/8 EX** trên cả Dev và Frozen = proof of generalization
3. **DualSQL approach** (Linker + Generator + Tools) cải thiện đáng kể so với one-shot

---

**Commit:** `499e9ae`
