# Historical Frozen Attempts: Baseline vs DualSQL v2

> Eligibility audit: these are exploratory historical attempts, not accepted
> frozen benchmark results under the approved protocol. See the
> [protocol audit](ctu_frozen_protocol_audit_2026-09-30.md) and consumption lock.
> Preserve the artifacts and do not rerun this holdout.

**Date:** 2026-09-30  
**Snapshot:** CTU-13 S1/S4 Frozen (3,945,672 rows)  
**Model:** GPT-5 Mini  
**Comparison:** Baseline E0 (no tools) vs DualSQL v2 E3 (linker + generator + tools)

---

## Results

| Condition | Accuracy | Syntax Valid | Cost |
|-----------|----------|--------------|------|
| **Baseline E0** | 0/8 (0%) | 8/8 | $0.004 |
| **DualSQL v2 E3** | 2/8 (25%) | 3/8 per JSON | $0.010 reported, incomplete |

### Recorded score difference: +2 cases; no accepted improvement claim

---

## Case-by-Case Analysis

| Case | Category | Baseline | v2 E3 | Notes |
|------|---------|----------|--------|-------|
| frozen_sql_001 | scalar_filter | FAIL | **PASS** | Scenario 1 → ctu13_s1 grounding |
| frozen_sql_002 | distinct | FAIL | **PASS** | Scenario 4 → ctu13_s4 grounding |
| frozen_sql_003 | boolean_precedence | FAIL | FAIL | Wrong table name (flows vs network_flows) |
| frozen_sql_004 | bounded_time_interval | FAIL | FAIL | Time boundary issue |
| frozen_sql_005 | aggregation_group_by | FAIL | FAIL | Label LIKE pattern issue |
| frozen_sql_006 | order_by_limit | FAIL | FAIL | Aggregation + ordering issue |
| frozen_sql_007 | multi_row_comparison | FAIL | FAIL | Aggregation + label issue |
| frozen_sql_008 | scalar_filter | FAIL | FAIL | Label exact match issue |

---

## Historical observations, excluded from further tuning

### 1. Value Grounding Works (Cases 001, 002)
The linker successfully discovers `ctu13_s1` and `ctu13_s4` from `scenario 1` and `scenario 4` via value_search, enabling correct SQL generation.

### 2. Complex Cases Still Fail (Cases 003-008)
- Case 003: Wrong table name (plural vs singular)
- Cases 004-008: Multi-clause SQL with aggregations, boolean logic, time ranges

### 3. Validation claim withdrawn
The recorded 2/8 versus 0/8 difference does not establish that schema linking
improves accuracy under the approved protocol. The required pre-run lock, CI,
identity and cost evidence is missing. These attempts remain descriptive
historical observations.

---

## Methodological Notes

### v2 vs v1
- v2 removes question literal hints from prompts
- v2 validates tool provenance for grounded values
- v2 uses source metadata for scenario→ctu mapping

### Snapshot
- Logical SHA: `0251bbe1a2bdca6acc4f181cf7342ec03b2e04048ab747c8625dbfc0b5d03ea4`
- S1 rows: 2,824,609
- S4 rows: 1,121,063

---

## Conclusion

The scripts recorded v2 2/8 and baseline 0/8. These are not protocol-eligible
frozen accuracy or generalization results. Preserve the artifacts and the
original report at commit `cf46fb4`; eligibility and cost limitations are
documented in the linked audit.

The earlier recommendation to adjust generator prompts from these holdout
outcomes is withdrawn. Do not tune from these outputs or rerun this holdout.

---

## Files

- Baseline E0: `results/evaluation_v1/ctu_network_frozen/baseline_e0/`
- v2 E3: `results/evaluation_v1/ctu_network_frozen/v2_e3/`
- Snapshot: `data/ctu_network_frozen/snapshots/frozen_v1.duckdb`
