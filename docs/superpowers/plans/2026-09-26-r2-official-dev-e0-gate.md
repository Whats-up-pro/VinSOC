# R2 Official-Dev E0 Gate Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the CTU-13 + OTRF diagnostic public snapshot with a verified official ThreatFox + CTU-13 + OTRF snapshot, validate the existing eight R2 dev cases against it, then execute exactly one locked E0 official-dev model run with reproducible provenance and no further public-dev tuning.

**Architecture:** Keep the existing R2 scorer and existing eight `evaluation/text_to_sql_benchmarks/dev/` cases. Build a new official snapshot from the three approved source families, bind it to source and logical-content hashes, freeze the exact E0 one-shot request contract selected by public-dev v4, and run only E0. This plan ends after the official-dev E0 report and error analysis; frozen remains sealed.

**Tech Stack:** Python 3.11/3.12, DuckDB, OpenAI `gpt-4.1-mini-2025-04-14`, existing `scripts/build_vinsoc_public_snapshot.py`, existing `evaluation/text_to_sql.py`, SHA-256 provenance, GitHub Actions manual workflows.

**Spec:** `docs/superpowers/specs/2026-09-25-dualsql-lite-agent-handoff-spec.md`

## Global Constraints

- Work directly on `master`; do not create a feature branch or PR.
- Do not run R1 frozen or R2 frozen.
- Do not run E1, E2, or E3 again.
- Do not tune prompts or tool behavior on the eight public-dev cases.
- Treat public-dev v4 as closed research history: E0 is the selected architecture.
- Preserve the existing R2 Execution Accuracy scorer semantics.
- Official source families are ThreatFox + CTU-13 + OTRF.
- Do not reuse the CTU-13 scenario 5/7 public-pilot snapshot as the official snapshot.
- Do not use ThreatFox samples or recent-IOC API responses as official CTI input.
- Do not place a ThreatFox Auth-Key in source URLs, manifests, logs, artifacts, or committed files.
- No synthetic row may enter the official snapshot.
- The eight existing `dev` cases are the official-dev benchmark authoring set; validate/freeze them rather than inventing a replacement benchmark.
- Public-dev `SELECTED_CONFIG.lock` selects architecture/configuration, but its public snapshot hashes are not valid official-dev snapshot identities.
- Official E0 model contract: OpenAI, `gpt-4.1-mini-2025-04-14`, temperature 0, `max_completion_tokens=1000`, SDK retries 0, no tools.
- Use the exact E0 one-shot prompt contract already exercised by public-dev v4; do not silently improve prompt wording.
- Before any paid call, verify source/snapshot/benchmark/scorer/prompt/config identities and a conservative cost ceiling.
- A valid paid official-dev E0 run is executed once. Only a documented infrastructure/provider failure permits a replacement run.
- The plan stops after official-dev E0 evidence + error analysis + review. No automatic optimization and no frozen run.

## Current Locked Baseline

- Public-dev v4 evidence commit: `7fd111124777645a8490b4d90de6554f2f567f7d`.
- Public-dev result lock: `evaluation/dualsql_lite/SELECTED_CONFIG.lock`.
- Selected experiment: E0.
- Public-dev E0: 5/8 = 62.5% Execution Accuracy.
- Public-dev v1-v4 total usage-derived research cost: $0.0894992.
- Current manual paid workflow: `.github/workflows/r2-dualsql-lite-public-dev.yml` uses `workflow_dispatch` only.
- R1 remains 22/24 on `dev v2`; R1 frozen remains unopened.

## Review Focus

1. Official OTRF bytes use top-level event fields that the current generic official builder does not fully normalize; no official snapshot may be released until this mapping is verified on the real archive.
2. The current official source gate has not verified the complete selected CTU-13 Scenario 3 source file/hash; the public pilot's scenario 5/7 files are not a substitute.
3. ThreatFox full export provenance must preserve both the downloaded transport artifact and the exact CSV bytes ingested, without exposing the Auth-Key.
4. `SELECTED_CONFIG.lock` records DualSQL prompt/tool hashes, but E0 actually uses the one-shot `build_r2_request` prompt; the official run must record the real E0 prompt identity.
5. The official snapshot needs a logical-content identity in addition to the DuckDB binary hash, so equivalent content is distinguishable from binary-layout changes.

---

### Task 1: Close and Verify the Public-Dev Research Phase

**Files:**
- Read: `docs/dualsql_lite_public_dev_v4_results_2026-09-26.md`
- Read: `evaluation/dualsql_lite/SELECTED_CONFIG.lock`
- Read: `.github/workflows/r2-dualsql-lite-public-dev.yml`
- Create: `docs/r2_official_dev_status_2026-09-26.md`

**Interfaces:**
- Consumes the four immutable public-dev series and the v4 selection lock.
- Produces a short status record that states public-dev is closed and official-dev E0 is the next gate.

- [ ] Verify `SELECTED_CONFIG.lock.selected_experiment == "E0"`.
- [ ] Verify public-dev v4 E0 is 5/8 and E1-E3 are not selected.
- [ ] Recompute the usage-derived cost across v1-v4 artifacts and assert total `0.0894992`.
- [ ] Verify `.github/workflows/r2-dualsql-lite-public-dev.yml` has `workflow_dispatch` and no `push`, `pull_request`, or `schedule` trigger.
- [ ] Record that public-dev is closed to further tuning and that no frozen run has occurred.
- [ ] Commit the status document.

**Acceptance:** no paid model call; no benchmark or prompt changes.

---

### Task 2: Acquire and Verify the Three Official Source Inputs

**Files:**
- Modify or create: `scripts/probe_r2_official_sources.py`
- Test: `tests/test_r2_official_source_probe.py`
- Create after real retrieval: credential-free source receipt JSON under `evaluation/text_to_sql_benchmarks/source_receipts/`

**Exact official inputs:**
- ThreatFox full CSV export from the authenticated ThreatFox export service.
- CTU-13 Scenario 3 `capture20110812.binetflow`.
- OTRF APT29 Day 1 `apt29_evals_day1_manual.zip`.

- [ ] Add/verify a source probe that retrieves complete bytes only; partial/HEAD-only evidence is not enough.
- [ ] ThreatFox credentials must come only from an environment secret and must never be serialized.
- [ ] Record UTC retrieval time, canonical credential-free URL, byte count, SHA-256, usage/licence note, and status for each source.
- [ ] For ThreatFox, record SHA-256 for the downloaded archive and separately for the exact extracted CSV that will be ingested.
- [ ] For OTRF, record archive SHA-256, exact JSONL member path, member byte size, and member SHA-256.
- [ ] For CTU-13, record full `.binetflow` byte count and SHA-256.
- [ ] If any source cannot be fully retrieved and hashed, STOP. Update `docs/r2_source_gate_2026-09-24.md` (or add a dated successor) with the exact blocker and do not proceed to snapshot build.
- [ ] Commit only credential-free receipt/probe code and metadata; do not commit raw source bytes.

**Acceptance:** all three complete official sources have verifiable hashes before Task 3 starts.

---

### Task 3: Fix the Official OTRF Adapter Against Real Bytes

**Files:**
- Modify: `scripts/build_vinsoc_public_snapshot.py`
- Modify: `tests/test_public_snapshot_builder.py`

**Interfaces:**
- Existing function: `_normalize_sysmon_lines(lines, dataset_id, source_prefix=None)`.
- Output must remain compatible with `sysmon_process_events`.

- [ ] Inspect real OTRF member fields from the verified archive without copying raw benchmark rows into the repository.
- [ ] Add tests using minimal structural fixtures for the actual top-level layout, including at least `Hostname`, `EventID`, event time, `Image`, `ParentImage`, `ProcessId`, `ParentProcessId` when present, `CommandLine`, and user field when present.
- [ ] Update normalization so the official OTRF layout maps to the existing table contract.
- [ ] Preserve stable row IDs as `<archive_member>:line:<n>`.
- [ ] Verify malformed/unrelated events are skipped deterministically rather than synthesized.
- [ ] Run `python -m pytest tests/test_public_snapshot_builder.py -q`.

**Acceptance:** real OTRF Event ID 1 rows can be normalized with non-empty host/event identity using the official builder.

---

### Task 4: Create the Official Dataset Manifest and Snapshot Identity Contract

**Files:**
- Create: `evaluation/text_to_sql_benchmarks/dataset_manifest.json`
- Create or extend: `evaluation/text_to_sql_benchmarks/official_snapshot.lock`
- Modify only if required: `evaluation/text_to_sql_snapshot.py`
- Test: `tests/test_text_to_sql_snapshot.py`

**Interfaces:**
- Builder input remains `scripts/build_vinsoc_public_snapshot.py --dataset-manifest ...`.
- Existing `snapshot_manifest.json` continues to bind canonical path and DuckDB binary SHA.
- `official_snapshot.lock` additionally binds logical content and source-receipt identities.

- [ ] Populate the dataset manifest with exactly the verified official source inputs and exact ingest-file SHA-256 values.
- [ ] Ensure no secret appears in `source_url` or any committed metadata.
- [ ] Record source receipt hashes, source-file hashes, expected source IDs, and builder version in `official_snapshot.lock`.
- [ ] Add a deterministic logical-content SHA-256 over canonical table content for `cti_indicators`, `network_flows`, and `sysmon_process_events`.
- [ ] Record row counts per benchmark table.
- [ ] Keep DuckDB binary SHA-256 in `snapshot_manifest.json`.
- [ ] Test that any source, binary, or logical-content hash mismatch fails before provider construction.

**Acceptance:** official snapshot identity has both binary and logical-content hashes and a credential-free provenance chain to all three source families.

---

### Task 5: Build the Official Three-Source Snapshot

**Files generated locally / in CI, not committed as raw database:**
- `data/snapshots/vinsoc_public_v1.duckdb`
- `evaluation/text_to_sql_benchmarks/snapshot_manifest.json`
- verification/build report artifact

- [ ] Build from a clean checkout using the verified dataset manifest.
- [ ] Rebuild independently a second time from the same source bytes.
- [ ] Verify both builds have identical logical-content SHA-256 and identical row counts.
- [ ] Verify all three tables are non-empty:
  - `cti_indicators`
  - `network_flows`
  - `sysmon_process_events`
- [ ] Verify every benchmark row has non-empty `source_dataset` and `source_row_id`.
- [ ] Verify `dataset_provenance` contains one entry per declared official source.
- [ ] Reopen the snapshot read-only and verify the snapshot manifest.
- [ ] Do not continue if either build differs logically.

**Acceptance:** one verified official ThreatFox + CTU-13 + OTRF snapshot exists and can be rebuilt to the same logical content.

---

### Task 6: Validate and Freeze the Existing Eight Official-Dev Cases

**Files:**
- Read/validate: `evaluation/text_to_sql_benchmarks/dev/sql_dev_001.json` ... `sql_dev_008.json`
- Do not inspect/modify frozen semantics.
- Create/update: `evaluation/text_to_sql_benchmarks/official_dev.lock`

- [ ] Assert exactly eight distinct dev case IDs exist.
- [ ] Compute and record a deterministic dev-directory SHA-256.
- [ ] Verify every case points to `data/snapshots/vinsoc_public_v1.duckdb`.
- [ ] Execute every accepted gold SQL against the verified official snapshot.
- [ ] Require every gold query to parse, pass the read-only policy, execute successfully, and return a result.
- [ ] Record category/difficulty counts.
- [ ] Confirm `sql_dev_008` exercises the ThreatFox-backed `cti_indicators` table.
- [ ] Hash the frozen directory without executing or using frozen cases for tuning; record only its closed-set identity if needed for later final gating.
- [ ] Do not rewrite dev questions/gold after this lock unless the official-dev version is explicitly bumped and the run has not happened.

**Acceptance:** official-dev is an existing 8-case benchmark validated on the new official snapshot; no replacement benchmark is invented.

---

### Task 7: Freeze the Actual E0 Official-Dev Request Contract

**Files:**
- Create: `evaluation/text_to_sql_benchmarks/OFFICIAL_E0.lock`
- Modify or add a dedicated runner/wrapper only as needed to enforce the lock.
- Test the preflight before any paid call.

**Required configuration:**
- provider: OpenAI
- model: `gpt-4.1-mini-2025-04-14`
- temperature: 0
- `max_completion_tokens`: 1000
- SDK retries: 0
- tools: none
- architecture: E0 one-shot

- [ ] Reuse the exact one-shot prompt wording from `evaluation.public_pilot.run_model.build_r2_request`.
- [ ] Record the actual E0 prompt/template identity; do not use `dualsql_generator_v4` hash as a substitute because E0 bypasses that prompt.
- [ ] Record scorer file hashes, benchmark hash, official snapshot binary/logical hashes, provider/model/config, and git SHA.
- [ ] Construct all eight exact serialized requests before creating/sending provider calls.
- [ ] Compute a conservative worst-case cost ceiling using the same pinned pricing snapshot as the public-dev evidence unless pricing is explicitly re-versioned.
- [ ] Fail before provider creation if any lock/hash/config check fails or the cost ceiling exceeds the task budget.
- [ ] Reject `OPENAI_BASE_URL` overrides and provider fallback routing.
- [ ] Verify actual response model and usage telemetry for every successful call.

**Acceptance:** the paid run cannot start unless the exact selected E0 architecture and official-dev identities are frozen.

---

### Task 8: Execute One Official-Dev E0 Run

**Files/artifacts:**
- Create immutable JSON evidence under `results/evaluation_v1/r2/`
- Create a GitHub Actions artifact containing the same report plus snapshot/build verification metadata.

- [ ] Use a manual `workflow_dispatch` workflow only.
- [ ] Start from a clean `master` commit and record its SHA.
- [ ] Write a partial evidence artifact before the first provider call.
- [ ] Execute exactly the eight official-dev cases once with the locked E0 configuration.
- [ ] After every call, persist actual model, input/output tokens, latency, usage-derived cost, generated SQL, and case status.
- [ ] Score through the unchanged existing R2 evaluator.
- [ ] If a model-generated SQL is wrong, count it as a case failure; do not retry.
- [ ] If infrastructure/provider failure invalidates the fixed run, mark it invalid and preserve the partial artifact before deciding on a replacement run.
- [ ] Do not execute E1/E2/E3.

**Acceptance:** one completed, eligible official-dev E0 artifact with 8 distinct cases and complete usage/provenance.

---

### Task 9: Publish Official-Dev Result and Stop at Review Gate

**Files:**
- Create: `docs/r2_official_dev_e0_results_2026-09-26.md`
- Update: `docs/evaluation_results_v1.md`
- Update: `README.md` only for verified status changes.

- [ ] Report correct case count and Execution Accuracy.
- [ ] Report Syntax Validity, Execution Success, Safety Rejection, category/difficulty breakdown, tokens, cost, and latency.
- [ ] Provide per-case generated SQL and primary error category.
- [ ] Distinguish this result from public-dev 5/8; do not call any delta an improvement unless the benchmark/snapshot are identical (they are not).
- [ ] State that public-dev v1-v4 total research cost before official-dev was $0.0894992.
- [ ] State that official-dev uses the real three-source snapshot and is the first official R2 dev accuracy result.
- [ ] Perform error analysis only; do not change prompt/model/scorer/benchmark automatically.
- [ ] Leave R1 unchanged at 22/24 dev v2.
- [ ] Explicitly state frozen remains sealed.
- [ ] Commit result docs and immutable evidence to `master`.
- [ ] STOP and request human review before any new optimization or frozen evaluation.

**Acceptance:** the project has an official R2 dev baseline and a clear human decision gate; no frozen result exists yet.

---

## Final Gate Checklist

The agent must not claim official-dev completion unless every item is true:

- [ ] ThreatFox full export verified with credential-free provenance.
- [ ] CTU-13 Scenario 3 complete file verified and hashed.
- [ ] OTRF archive/member verified and official adapter validated on its real layout.
- [ ] Official snapshot contains non-empty CTI, network, and endpoint tables.
- [ ] Snapshot binary SHA and logical-content SHA are frozen.
- [ ] Existing eight dev cases all execute their gold SQL on the official snapshot.
- [ ] Public-dev E0 remains the selected architecture; no more public-dev tuning occurred.
- [ ] Actual E0 prompt contract is hashed and frozen.
- [ ] Official model/config is exactly OpenAI `gpt-4.1-mini-2025-04-14`, temperature 0, cap 1000, retries 0, no tools.
- [ ] Cost preflight passes before provider creation.
- [ ] Exactly one valid official-dev E0 run exists.
- [ ] E1/E2/E3 were not rerun on official-dev.
- [ ] R1 frozen and R2 frozen remain unopened.
- [ ] Result report clearly separates public pilot evidence from official-dev evidence.

## Expected Commit Sequence

```text
docs(eval): close DualSQL-Lite public-dev phase
feat(data): verify official R2 source provenance
fix(data): normalize official OTRF event layout
feat(data): lock official R2 snapshot identity
docs(eval): freeze official R2 dev benchmark
feat(eval): lock official E0 run contract
ci(eval): add manual official R2 E0 workflow
docs(eval): preserve official R2 E0 result
```
