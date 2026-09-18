# R0 Convergence Inventory

**Created**: 2026-09-19
**Status**: Draft

## Baseline Verification

- `origin/master`: `b6a1245` (local HEAD: `9231a76` on `feat/r0-convergence`)
- `origin/feature/evidence-v2-real-cti`: `4e9caeb`
- Local baseline tests: **132 passed** ✅

## Divergence Classification

### A. Branch-Only Files (in `feature/evidence-v2-real-cti`, NOT in `master`)

| File | Category | Priority | Action |
|------|----------|----------|--------|
| `telemetry/network/__init__.py` | Telemetry | HIGH | Restore |
| `telemetry/network/base.py` | Telemetry | HIGH | Restore |
| `telemetry/network/models.py` | Telemetry | HIGH | Restore |
| `telemetry/network/query.py` | Telemetry | HIGH | Restore |
| `telemetry/network/zeek.py` | Telemetry | HIGH | Restore |
| `telemetry/network/suricata.py` | Telemetry | HIGH | Restore |
| `analytics/network/__init__.py` | Analytics | HIGH | Restore |
| `analytics/network/beaconing.py` | Analytics | HIGH | Restore |
| `analytics/network/scanning.py` | Analytics | HIGH | Restore |
| `analytics/network/transfer.py` | Analytics | HIGH | Restore |
| `analytics/network/fanout.py` | Analytics | HIGH | Restore |
| `skills/cti_providers.py` | CTI | HIGH | Restore + merge |
| `tests/test_network_adapters.py` | Tests | HIGH | Restore |
| `tests/test_network_query.py` | Tests | HIGH | Restore |
| `tests/test_network_analytics.py` | Tests | HIGH | Restore |
| `tests/test_network_skill_v2.py` | Tests | HIGH | Restore |
| `tests/test_cti_providers.py` | Tests | HIGH | Restore + merge |
| `tests/test_evidence_v2.py` | Tests | HIGH | Restore |
| `docs/evidence_v2_cti.md` | Docs | MEDIUM | Restore |
| `docs/network_telemetry_v2.md` | Docs | MEDIUM | Restore |

### B. Master-Only Files (in `master`, NOT in branch)

| File | Category | Priority | Action |
|------|----------|----------|--------|
| `docs/provider_routing.md` | Docs | HIGH | PRESERVE |
| `evaluation/__init__.py` | Evaluation | MEDIUM | PRESERVE |
| `evaluation/text_to_sql.py` | Evaluation | HIGH | PRESERVE |
| `vinsoc_data/__init__.py` | DuckDB | HIGH | PRESERVE |
| `vinsoc_data/domain_queries.py` | DuckDB | HIGH | PRESERVE |
| `vinsoc_data/duckdb_store.py` | DuckDB | HIGH | PRESERVE |
| `tests/test_provider_routing.py` | Tests | HIGH | PRESERVE |
| `tests/test_duckdb_data_layer.py` | Tests | HIGH | PRESERVE |
| `scripts/measure_tool_calling.py` | Tools | HIGH | PRESERVE |
| `schemas/text_to_sql_case.json` | Schema | MEDIUM | PRESERVE |
| `.claude/agents/*` | Dev | LOW | DO NOT RESTORE |

### C. Both Changed (Semantic Merge Required)

| File | Master Behavior | Branch Behavior | Merge Strategy |
|------|-----------------|-----------------|----------------|
| `agent/evidence.py` | V1 (no class/confidence) | V2 (full provenance) | Merge V2 + preserve backward compat |
| `agent/orchestrator.py` | HITL + routing | Evidence materialization | Merge both |
| `agent/tools.py` | Current routing | May have routing changes | Compare and merge |
| `agent/provider.py` | Routing logic | May have changes | Compare and merge |
| `skills/cti_skill.py` | V1 + fail-closed | Provider adapters | Merge V2 + preserve fail-closed |
| `skills/network_skill.py` | V1 semantics | V2 normalized | MERGE required |
| `skills/endpoint_skill.py` | V1 | May have changes | Compare and preserve |
| `schemas/cti_result.json` | V1 schema | V2 schema | Merge V2 extensions |
| `schemas/network_result.json` | V1 schema | V2 schema | MERGE required |
| `schemas/investigation_case.json` | V1 schema | V2 schema | Merge V2 extensions |
| `scenarios/case_012.json` | hostname+CTI | hostname only | Keep current (hostname only) |
| `scenarios/case_013.json` | hostname+CTI | hostname only | Keep current (hostname only) |
| `scenarios/case_014.json` | hostname+CTI | hostname only | Keep current (hostname only) |
| `pyproject.toml` | Current deps | May have new deps | Merge carefully |
| `README.md` | Current docs | Updated docs | Merge both |
| `.github/workflows/ci.yml` | Current CI | May have updates | Compare and merge |
| `.gitignore` | Current | May have changes | Compare and merge |
| `docs/evaluation.md` | Current | May have changes | Merge both |
| `tests/test_skills.py` | Current tests | May have new tests | Merge both |
| `tests/test_cti_semantics.py` | Current (fail-closed) | Branch (providers) | PRESERVE fail-closed |

### D. Obsolete (DO NOT Restore)

| File | Reason |
|------|--------|
| `.claude/agents/*` | Stale agent definitions |
| `docs/dev/current_baseline.md` | Outdated baseline doc |
| `docs/duckdb_data_layer.md` | Replaced by provider_routing.md |
| `docs/evaluation_results_preliminary.md` | Outdated results |

## Critical Implementation Notes

### Evidence V2 Requirements
- `evidence_class`: OBSERVED | DERIVED | EXTERNAL_INTEL
- `source_name`: str | None
- `observed_at`: str | None
- `confidence`: str | None
- `provenance`: dict
- `references`: list[str]
- `related_evidence_ids`: list[str]

### CTI Provider Status
- MATCH: Provider found intelligence
- NO_MATCH: Provider executed, no match
- NOT_APPLICABLE: Provider doesn't support this indicator type
- ERROR: Provider execution failed

### Network V2 Semantics
- **ALLOWED**: beaconing, port_scan (as pattern markers)
- **FORBIDDEN**: normal, data_exfiltration, unusual_port, lateral_movement (as conclusions)
- **CANDIDATE**: periodic_connection_candidate, horizontal_scan_candidate, etc.

## Execution Order

1. **R0.1**: Restore telemetry + analytics (additive)
2. **R0.2**: Restore Evidence V2
3. **R0.3**: Merge CTI providers + preserve fail-closed
4. **R0.4**: Merge Network V2 + DuckDB
5. **R0.5**: Converge orchestrator
6. **R0.6**: Align routing semantics
7. **R0.7**: CI convergence
8. **R0.8**: Documentation reconciliation
9. **R0.9**: Final verification
