# VinSOC Evaluation V1 — Verification and Result Status

**Status as of 2026-09-24:** implementation and local tests pass; official development and frozen model benchmarks have not run. No model accuracy score or improvement delta is available.

## Verified implementation

| Check | Evidence |
|---|---|
| Fresh clone baseline | Initial `master` SHA `cfbb5318e1d8c8a99f269a50bb7d7352b82af9ae`; upstream `origin/master`; baseline `214 passed` |
| Current evaluator code | `4ecc6f3f2da601a22d9a9cf76b8fd8ec61ed902c` on `master` |
| R1 contract | 24 dev cases, 8 frozen cases; 4 dev no-tool cases; strict production schemas shared by A1 and runtime |
| R2 contract | 8 dev cases, 6 frozen cases; execution accuracy primary; path and SHA check before provider creation |
| Scoring regression fixes | Provider errors cannot count as successful no-tool decisions; unordered SQL results preserve duplicate multiplicity |
| Snapshot builder | Source checksum, HTTPS URL, UTC timestamp, provenance registration, row identities, read-only reopen, dev gold SQL checks; ZIP input uses named member with archive hash |
| Latest local suite | `241 passed`, `958 warnings` on Python 3.12; warnings are existing deprecations |

The first independent review found two critical score defects and two important provenance defects. Fixes were committed as `b3278bb` and `4ecc6f3`; regression tests pass. The requested second independent review did not complete because that agent hit its usage limit. A full fresh independent sign-off is still pending.

## Official benchmark status

| Track | Dev baseline | Error analysis | Controlled improvements | Frozen holdout |
|---|---|---|---|---|
| R1 / A1 | Blocked: `VINSOC_EVAL_MODEL` and provider credential unset | Pending real dev output | Pending error analysis | Unopened |
| R2 | Blocked: verified official DuckDB snapshot/manifest and provider configuration absent | Pending real dev output | Pending error analysis | Unopened |

The historical A2 MockProvider regression artifact is an integration check and is not an official A1 model score. No percentage, improvement, or before/after comparison is inferred from test fixtures.

## External prerequisites and coverage gaps

1. ThreatFox full CSV export currently requires an Auth-Key. This runtime has no `THREATFOX_AUTH_KEY`; no official `dataset_manifest.json`, `vinsoc_public_v1.duckdb`, or `snapshot_manifest.json` has been created. Existing ThreatFox samples have insufficient source-file provenance.
2. Network access/runtime also prevented inspection of the chosen OTRF ZIP member. The builder requires an exact JSONL member; its identity must be checked against actual archive bytes. The CTU-13 source file also needs retrieval, exact SHA-256, and a validated source-format mapping before official use.
3. The current R2 benchmark references one snapshot. Multiple dev/frozen source-session snapshots, as preferred by the master evaluation prompt, are not yet implemented. A one-snapshot execution score can over-credit semantically wrong SQL that coincidentally returns the same rows.
4. Current frozen sets remain unused. Challenge/OOD sets have no cases and are excluded from primary metrics.

## Reproducibility identifiers

The exact benchmark directory digests, category counts, and tool-schema SHA-256 are in [`r1_coverage_matrix.json`](../evaluation/r1_coverage_matrix.json) and [`r2_coverage_matrix.json`](../evaluation/r2_coverage_matrix.json). Run configurations and snapshot SHA must be recorded with real outputs when prerequisites become available. The full procedure is in [`evaluation_protocol_v1.md`](evaluation_protocol_v1.md).
