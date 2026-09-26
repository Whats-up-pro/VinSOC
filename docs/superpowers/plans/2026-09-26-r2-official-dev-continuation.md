# R2 Official-Dev Continuation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Resume the official R2 gate from the current repository state: fix the ThreatFox ingestion blocker, produce one verified three-source snapshot, freeze the existing eight dev cases plus the actual E0 request contract, run one official-dev E0 evaluation, then stop for human review.

**Architecture:** The source-byte gate, OTRF mapping, snapshot identity helpers, and public-dev closure already exist and must not be rebuilt. The continuation starts from the failed official snapshot build at GitHub Actions run `36216646548`, fixes only the ThreatFox CSV ingestion defect and source-set freeze discipline, then proceeds through the already-approved official-dev E0 gate.

**Tech Stack:** Python 3.11/3.12, DuckDB, GitHub Actions, OpenAI `gpt-4.1-mini-2025-04-14`, SHA-256 provenance.

**Spec:** `docs/superpowers/specs/2026-09-25-dualsql-lite-agent-handoff-spec.md`

## Current Checkpoint

Completed and accepted:

- Public-dev research is closed.
- E0 is selected from v4 at 5/8.
- Public-dev v1-v4 usage-derived cost is `$0.0894992`.
- R1 remains 22/24 on dev v2.
- R1 frozen and R2 frozen remain sealed.
- Full official source retrieval succeeded in run `36215516647`.
- Source receipts exist for ThreatFox, CTU-13 Scenario 3, and OTRF APT29 Day 1.
- OTRF top-level `Hostname` / `EventID` / process-field normalization is implemented.
- Official binary/logical snapshot identity helpers and two-build verification code are implemented.
- CI on current `master@dcdc95b` passes.

Current blocker:

- Official snapshot build run `36216646548` failed at `cti_indicators` with zero rows.
- The failure occurs after complete sources are downloaded and staged successfully.
- The current ThreatFox normalizer expects a normal CSV header, while ThreatFox `full.csv` uses a metadata/comment preamble and a commented header row. The generic `_csv_rows()` drops comment lines, so the actual header is discarded and all rows fail field lookup.
- ThreatFox is mutable: the successful probe receipt and the later snapshot-build download already produced different ThreatFox hashes. Therefore the final official source identity must come from the exact successful snapshot-build run, not from an earlier receipt.

## Global Constraints

- Do not reopen public-dev tuning.
- Do not run E1/E2/E3 again.
- Do not run any frozen split.
- Do not change R1.
- Do not alter R2 scorer semantics.
- Do not alter the eight existing official-dev questions/gold SQL unless a versioned benchmark correction is explicitly approved before the paid run.
- Do not use ThreatFox sample data or recent-IOC API data.
- Never serialize `THREATFOX_AUTH_KEY`.
- Official snapshot source bytes must be the same bytes whose receipts are frozen with that snapshot.
- Official E0 must use OpenAI `gpt-4.1-mini-2025-04-14`, temperature 0, `max_completion_tokens=1000`, zero retries, no tools.
- Use the actual E0 one-shot prompt from `evaluation.public_pilot.run_model.build_r2_request`.
- Stop after official-dev E0 evidence and error analysis.

## Review Focus

1. ThreatFox header parsing must support the real commented header without changing CTU-13 CSV parsing.
2. ThreatFox mutable exports must not create a manifest/receipt/snapshot mismatch across separate downloads.
3. Snapshot workflow must be manual-only before the next run to avoid another accidental duplicate 600+ MB download.
4. The eight dev gold queries must all execute on the exact official snapshot before provider construction.
5. E0 provenance must hash the actual one-shot prompt, not the unused DualSQL generator prompt.

---

### Task 1: Fix ThreatFox Full-Export Parsing

**Files:**
- Modify: `scripts/build_vinsoc_public_snapshot.py`
- Modify: `tests/test_public_snapshot_builder.py`

**Interfaces:**
- Keep `normalize_threatfox_csv(path: Path, dataset_id: str) -> list[dict[str, Any]]`.
- Keep generic `_csv_rows()` behavior for CTU-13 unchanged.
- Add a ThreatFox-specific row iterator or header reader.

- [ ] **Step 1: Add a failing regression test for a commented ThreatFox header**

The fixture must contain:
- arbitrary metadata comment lines;
- a header line beginning with `#` and containing at least `first_seen_utc`, `ioc_id`, `ioc_value`, `ioc_type`, `threat_type`, `malware_printable`, `confidence_level`, `reference`, `last_seen_utc`;
- at least one valid IOC data row.

Assertions:
- exactly one normalized row is returned;
- `source_row_id`, `indicator`, `indicator_type`, and timestamps map correctly.

- [ ] **Step 2: Run the focused test and confirm current code fails**

Run:

```bash
python -m pytest tests/test_public_snapshot_builder.py -k threatfox -q
```

Expected: the new commented-header test fails with zero normalized rows or missing expected values.

- [ ] **Step 3: Implement ThreatFox-specific header discovery**

Required behavior:
- scan until the first comment/non-comment line containing both `first_seen_utc` and `ioc_value`;
- strip only the leading comment marker/whitespace from that header;
- feed that header plus following non-empty, non-comment data rows to `csv.DictReader`;
- do not alter `_csv_rows()`, because CTU-13 uses ordinary CSV headers.

If no ThreatFox header is found, raise `ValueError("ThreatFox CSV header not found")` rather than returning zero rows.

- [ ] **Step 4: Add explicit required-column validation**

Before iteration, require at least:
`ioc_id`, `ioc_value`, `ioc_type`, `first_seen_utc`.

A structurally incompatible export must fail early instead of silently producing an empty CTI table.

- [ ] **Step 5: Run builder-focused tests**

```bash
python -m pytest tests/test_public_snapshot_builder.py tests/test_r2_official_snapshot_build.py -q
```

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add scripts/build_vinsoc_public_snapshot.py tests/test_public_snapshot_builder.py
git commit -m "fix(data): parse official ThreatFox commented header"
git push origin master
```

---

### Task 2: Make the Official Snapshot Build Manual-Only and Freeze One Source Set

**Files:**
- Modify: `.github/workflows/r2-official-snapshot-build.yml`
- Modify: `scripts/stage_r2_official_sources.py` only if needed for stronger consistency checks
- Test: add workflow/static validation to the nearest existing official-R2 test file

**Interfaces:**
- The snapshot workflow must have only `workflow_dispatch`.
- The staged manifest and receipts must be derived from the same probe directory used to build the snapshot.

- [ ] **Step 1: Remove the temporary `push` trigger**

The workflow must contain:

```yaml
on:
  workflow_dispatch:
```

and no `push:`, `pull_request:`, or `schedule:` trigger.

- [ ] **Step 2: Add a regression test for workflow shape**

Assert the workflow is manual-only.

- [ ] **Step 3: Add/verify same-run source consistency**

Before snapshot build:
- each staged file SHA must equal the receipt identity generated in the same workflow run;
- `dataset_manifest.json` must be generated from those same receipts;
- CTU-13 and OTRF stable hashes must match their previously verified identities;
- ThreatFox is allowed to differ from earlier probes because the feed is mutable, but the final receipt/manifest/snapshot must all use the same current hash.

- [ ] **Step 4: Define the final source-set rule**

The first successful official snapshot build becomes the frozen official source set.

Do not run another source probe afterward and silently replace ThreatFox bytes for the same official benchmark version.

If a rebuild is needed after the successful build, it must consume the exact frozen source bytes from a durable restricted location; do not re-download a newer ThreatFox export and call it the same snapshot version.

- [ ] **Step 5: Commit**

```bash
git add .github/workflows/r2-official-snapshot-build.yml tests/
git commit -m "ci(eval): make official snapshot build manual only"
git push origin master
```

---

### Task 3: Re-run and Freeze the Official Three-Source Snapshot

**Files/artifacts:**
- GitHub Actions output from `r2-official-snapshot-build.yml`
- Commit after success:
  - `evaluation/text_to_sql_benchmarks/dataset_manifest.json`
  - `evaluation/text_to_sql_benchmarks/source_receipts/*.json`
  - `evaluation/text_to_sql_benchmarks/snapshot_manifest.json`
  - `evaluation/text_to_sql_benchmarks/official_snapshot.lock`
- Do not commit raw dataset bytes or the DuckDB database.

- [ ] **Step 1: Trigger the workflow manually once on the clean post-fix master SHA**

Do not use push-trigger execution.

- [ ] **Step 2: Verify the source stage**

Require:
- ThreatFox CTI normalizer produces >0 rows;
- CTU-13 network table produces >0 rows;
- OTRF endpoint table produces >0 rows.

- [ ] **Step 3: Verify the independent two-build contract**

Both builds must have:
- identical row counts;
- identical logical-content SHA-256;
- identical provenance source IDs.

Binary DuckDB hashes may differ if physical layout differs; logical identity must not.

- [ ] **Step 4: Verify the final snapshot metadata**

Record:
- three final source hashes;
- ThreatFox transport and ingest hashes;
- CTU-13 hash;
- OTRF archive/member hashes;
- row counts;
- snapshot binary hash;
- snapshot logical hash;
- builder version/hash;
- artifact SHA.

- [ ] **Step 5: Preserve the exact source-set reproducibility route**

Because ThreatFox is mutable, document where the exact frozen source bytes are retained for future rebuilds.

If policy prevents redistributing raw sources, record a restricted/private retention location and access owner. A hash without retained bytes is not sufficient for later exact reconstruction.

- [ ] **Step 6: Commit only the successful build metadata**

Do not commit metadata from the failed run `36216646548` as the official snapshot lock.

- [ ] **Step 7: Stop immediately if the build fails again**

Do not proceed to benchmark lock or model calls. Write the exact new blocker first.

---

### Task 4: Validate and Freeze Existing Official-Dev Cases

**Files:**
- Create: `evaluation/text_to_sql_benchmarks/official_dev.lock`
- Read only: `evaluation/text_to_sql_benchmarks/dev/sql_dev_001.json` through `sql_dev_008.json`
- Do not modify `frozen/`.

**Interfaces:**
- Existing 8 dev cases remain the benchmark.
- `official_dev.lock` binds case-directory identity to the successful official snapshot identity.

- [ ] **Step 1: Verify exactly 8 distinct dev cases**

Expected IDs: `sql_dev_001` through `sql_dev_008`.

- [ ] **Step 2: Execute every accepted gold SQL against the official snapshot**

All must:
- parse;
- pass read-only safety;
- execute successfully.

- [ ] **Step 3: Verify coverage**

Require:
- network cases execute against `network_flows`;
- endpoint cases execute against `sysmon_process_events`;
- `sql_dev_008` executes against non-empty ThreatFox-backed `cti_indicators`.

- [ ] **Step 4: Freeze benchmark identity**

Record:
- dev directory SHA-256;
- exact case IDs;
- category/difficulty counts;
- official snapshot binary/logical hashes;
- scorer hash.

- [ ] **Step 5: Do not change dev content after lock**

Any later benchmark correction requires a new official-dev version before a paid run.

- [ ] **Step 6: Commit**

```bash
git add evaluation/text_to_sql_benchmarks/official_dev.lock
git commit -m "docs(eval): freeze official R2 dev benchmark"
git push origin master
```

---

### Task 5: Freeze and Run the Actual E0 Official-Dev Contract

**Files:**
- Create: `evaluation/text_to_sql_benchmarks/OFFICIAL_E0.lock`
- Create or modify a dedicated manual official-E0 workflow/runner.
- Create result artifact under `results/evaluation_v1/r2/`.

**Required request contract:**
- provider: OpenAI;
- model: `gpt-4.1-mini-2025-04-14`;
- temperature: 0;
- `max_completion_tokens=1000`;
- SDK retries: 0;
- tools: none;
- exact prompt from `evaluation.public_pilot.run_model.build_r2_request`.

- [ ] **Step 1: Hash the actual E0 request template**

Do not reuse `dualsql_generator_v4` as the E0 prompt identity.

- [ ] **Step 2: Bind E0 to the official identities**

`OFFICIAL_E0.lock` must include:
- selected architecture E0;
- model/provider/config;
- prompt hash;
- dev benchmark hash;
- snapshot binary/logical hashes;
- scorer hash;
- git SHA;
- pricing snapshot.

- [ ] **Step 3: Pre-serialize all 8 requests and run cost preflight**

Provider construction/calls are forbidden until every lock matches and the cost ceiling passes.

- [ ] **Step 4: Use manual-only workflow execution**

No push-trigger paid run.

- [ ] **Step 5: Run exactly one valid official-dev E0 series**

For each case preserve:
- generated SQL;
- actual model;
- input/output tokens;
- usage-derived cost;
- latency;
- syntax/execution/safety/result status.

No retry for a wrong SQL.

- [ ] **Step 6: Preserve partial evidence on infrastructure failure**

Only a run-invalidating infrastructure/provider failure permits a replacement run.

- [ ] **Step 7: Commit immutable valid evidence after verification**

Do not run E1/E2/E3.

---

### Task 6: Publish Official R2 Dev Result and Stop

**Files:**
- Create: `docs/r2_official_dev_e0_results_2026-09-26.md`
- Update: `docs/evaluation_results_v1.md`
- Update: `README.md` only for verified state changes.

- [ ] Report correct count and Execution Accuracy.
- [ ] Report Syntax Validity, Execution Success, Safety Rejection, category/difficulty breakdown.
- [ ] Report tokens, usage-derived cost, latency, provider/model identity.
- [ ] Include per-case generated SQL and primary error category.
- [ ] State public-dev v1-v4 prior research cost separately as `$0.0894992`.
- [ ] Do not compare official-dev percentage directly to public-dev 5/8 as an improvement delta because the snapshot/domain composition changed.
- [ ] State this is the first official R2 dev accuracy result if all official gates passed.
- [ ] Leave R1 status unchanged at 22/24 dev v2.
- [ ] State R1 frozen and R2 frozen remain sealed.
- [ ] STOP for human review. No automatic optimization and no frozen execution.

## Completion Gate

Do not claim the continuation complete unless:

- [ ] ThreatFox parser accepts the actual commented header format.
- [ ] Official snapshot workflow is manual-only.
- [ ] One successful snapshot build has non-empty CTI/network/endpoint tables.
- [ ] Final manifest/receipts come from the same successful source set.
- [ ] Exact ThreatFox frozen bytes are retained somewhere durable/restricted for reproducibility.
- [ ] Two independent builds match logically.
- [ ] All 8 dev gold queries execute on that exact snapshot.
- [ ] Official dev benchmark lock exists.
- [ ] Actual E0 prompt/config lock exists.
- [ ] Exactly one valid official-dev E0 evidence run exists.
- [ ] No E1/E2/E3 official-dev run exists.
- [ ] Frozen remains unopened.

## Expected Commit Sequence

```text
fix(data): parse official ThreatFox commented header
ci(eval): make official snapshot build manual only
docs(data): freeze successful official R2 snapshot provenance
docs(eval): freeze official R2 dev benchmark
feat(eval): lock official E0 run contract
ci(eval): add manual official R2 E0 workflow
docs(eval): preserve official R2 E0 result
```
