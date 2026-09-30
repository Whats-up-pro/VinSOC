# v2 Metrics Definition (Locked BEFORE Paid Run)

## Execution Accuracy

A generated SQL is marked "accurate" if it produces the same result as the gold SQL.

### Exact Match Rules

1. **Scalar results**: Single row with single value. Match if value equals gold value ± tolerance for FLOAT/DOUBLE.

2. **Unordered rows**: Multiple rows, order doesn't matter. Match if:
   - Same row count
   - Each row's values match (column order doesn't matter)

3. **Ordered rows**: Multiple rows with specific ordering. Match if:
   - Same row count
   - Same row order
   - Same values per row

### LIKE Pattern Handling

**IMPORTANT**: `LIKE` patterns in gold SQL have semantic meaning:

| Gold Pattern | Semantic Intent | Match |
|-------------|----------------|-------|
| `'flow=From-Botnet%'` | Label starts with "flow=From-Botnet" | Labels matching prefix |
| `'%Normal%'` | Label contains "Normal" | Labels with substring "Normal" |
| `'%Botnet%'` | Label contains "Botnet" | Labels with substring "Botnet" |

Catalog lookup is NOT authoritative for LIKE patterns.
- "Not in catalog" ≠ "Not in snapshot"
- Catalog is limited to 5000 distinct values per column
- Gold SQL LIKE patterns are evaluated against full snapshot

### SQL Comparison

1. Parse both SQLs
2. Execute both against snapshot
3. Compare results using rules above

## Semantic Tags (Diagnostic Only)

These tags describe query characteristics. They do NOT affect accuracy scoring.

| Tag | Description |
|-----|-------------|
| `scalar_filter` | WHERE clause filters rows |
| `stored_value_grounding` | WHERE uses exact stored values |
| `like_prefix` | LIKE used with % suffix |
| `boolean_precedence` | AND/OR grouping matters |
| `bounded_time_interval` | Time range filter |
| `distinct` | COUNT(DISTINCT ...) used |
| `aggregation_group_by` | GROUP BY clause |
| `order_by_limit` | ORDER BY + LIMIT |

## Prohibited Patterns

These patterns, if detected in gold SQL, indicate a malformed case:

1. `INSERT`, `UPDATE`, `DELETE` (non-read-only)
2. `DROP`, `CREATE`, `ALTER` (DDL)
3. References to `information_schema`, `pg_catalog`, system tables
4. External file access (`read_csv`, `parquet_scan`, etc.)

## Metric Lock

This document is locked at commit:
```
<v2_suite_commit_sha>
```

Any changes to metric definitions require a new suite version.
