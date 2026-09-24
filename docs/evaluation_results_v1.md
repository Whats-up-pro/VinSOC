# VinSOC Evaluation V1 — Verification and Result Status

**Status as of 2026-09-24:** R1 A1 has one real-model run on the original `dev` benchmark (15/24 at `1fd3843`) and [one on the adjudicated `dev v2` benchmark](r1_a1_dev_v2_results.md) (22/24 at `852e543`). The benchmark and production tool schema changed between runs; the difference is not a model improvement delta. No frozen or R2 model evaluation has run.

## Verified implementation

| Check | Evidence |
|---|---|
| Fresh clone baseline | Initial `master` SHA `cfbb5318e1d8c8a99f269a50bb7d7352b82af9ae`; upstream `origin/master`; baseline `214 passed` |
| R1 `dev v2` evaluator/run | `852e543b971b6d0c565fbab5f885178c17f8b8eb`; the [versioned run artifact](../results/evaluation_v1/r1/r1_a1_dev_v2_852e543.json) records the prompt, schema, split and scorer hashes |
| R1 contract at `852e543` | 24 dev cases, including **5 dev no-tool cases**; 8 frozen cases remain unopened. A1 uses the production schemas. |
| R2 contract | 8 dev cases, 6 frozen cases; execution accuracy primary; path and SHA check before provider creation |
| Scoring regression fixes | Provider errors cannot count as successful no-tool decisions; unordered SQL results preserve duplicate multiplicity |
| Snapshot builder | Source checksum, HTTPS URL, UTC timestamp, provenance registration, row identities, read-only reopen, dev gold SQL checks; ZIP input uses named member with archive hash |
| Full CI on final `master@7e43bc5` | [CI run 35976112640](https://github.com/Whats-up-pro/VinSOC/actions/runs/35976112640): Python 3.11 **271 passed**; Python 3.12 **271 passed, 1041 warnings**. These are CI results; no local pytest run is claimed for this SHA. |

The first independent review found two critical score defects and two important provenance defects. Fixes were committed as `b3278bb` and `4ecc6f3`; regression tests pass. The requested second independent review did not complete because that agent hit its usage limit. A full fresh independent sign-off is still pending.

## Official benchmark status

| Track | Dev baseline | Error analysis | Controlled improvements | Frozen holdout |
|---|---|---|---|---|
| R1 / A1 | Pinned `gpt-4.1-mini-2025-04-14`: original 15/24 and versioned `dev v2` 22/24, single run each; [v2 artifact and per-case review](r1_a1_dev_v2_results.md) | v2 failures `002`, `015` pending separate analysis | No controlled model improvement | Unopened |
| R2 | Blocked: verified official DuckDB snapshot and source provenance are absent | Pending verified snapshot | Pending error analysis | Unopened |

The historical A2 MockProvider regression artifact is an integration check and is not an official A1 model score. No percentage, improvement, or before/after comparison is inferred from test fixtures.

## External prerequisites and coverage gaps

1. A ThreatFox Auth-Key has been supplied privately, but direct HTTPS access to `threatfox.abuse.ch` times out in this runtime. The key is not stored in the repository or in a manifest. No official `dataset_manifest.json`, `vinsoc_public_v1.duckdb`, or `snapshot_manifest.json` has been created. Existing ThreatFox samples have insufficient source-file provenance.
2. Direct HTTPS access to `mcfp.felk.cvut.cz` and `github.com` also timed out. The chosen OTRF ZIP member must be inspected against downloaded archive bytes before ingestion. The CTU-13 source file likewise needs retrieval, exact SHA-256, and a validated source-format mapping before official use.
3. The current R2 benchmark references one snapshot. Multiple dev/frozen source-session snapshots, as preferred by the master evaluation prompt, are not yet implemented. A one-snapshot execution score can over-credit semantically wrong SQL that coincidentally returns the same rows.
4. Current frozen sets remain unused. Challenge/OOD sets have no cases and are excluded from primary metrics.
5. The local runtime has no evaluation credential or complete test dependencies. R1 A1 runs used the GitHub Actions secret and pinned model; the secret is absent from artifacts and this repository. No R2 model call was attempted.

## Reproducibility identifiers

The exact benchmark directory digests, category counts, and tool-schema SHA-256 are in [`r1_coverage_matrix.json`](../evaluation/r1_coverage_matrix.json) and [`r2_coverage_matrix.json`](../evaluation/r2_coverage_matrix.json). Run configurations and snapshot SHA must be recorded with real outputs when prerequisites become available. The full procedure is in [`evaluation_protocol_v1.md`](evaluation_protocol_v1.md).
