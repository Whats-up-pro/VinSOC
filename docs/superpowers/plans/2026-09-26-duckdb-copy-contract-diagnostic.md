# R2 DuckDB COPY Contract Diagnostic Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Eliminate the run-5 DuckDB CSV conversion failure without exposing source rows, then validate the corrected CTI load offline against the exact encrypted run-5 ThreatFox bytes before any new official snapshot retry.

**Architecture:** The ThreatFox source parser is now correct: all 107,834 rows normalize successfully. The remaining failure is in the temporary normalized-CSV → DuckDB `COPY` boundary. Replace CSV dialect auto-detection with the exact dialect emitted by Python `csv.DictWriter`, sanitize DuckDB exceptions so raw IOC rows cannot reach Actions logs, and validate the fix on the retained encrypted run-5 source artifact without downloading new source data.

**Tech Stack:** Python 3.11/3.12, standard-library `csv`, DuckDB 1.x, GitHub Actions manual workflow, OpenSSL AES-256-CBC/PBKDF2.

**Spec:** `docs/superpowers/plans/2026-09-26-threatfox-csv-dialect-fix.md`

## Current Evidence

Current code/evidence checkpoint:

- master: `bcd5cb6306abd64df792c9cff005d2acb0341841`;
- run #5: `36235433476`;
- encrypted source artifact: `10904266318`;
- encrypted artifact digest:
  `sha256:a3858d1a92f15b70fc0d629a46f7c6eff6763caffde8b43077eabff74186d8f8`;
- ciphertext SHA-256:
  `b39c70b47bdef1c9668d3dde250ad11880516744ebb7edd98748fc8eded61f65`;
- metadata artifact: `10904001875`;
- metadata digest:
  `sha256:bdd298c103d1a1b9b4d1da19e13e7fd69742919f92d08c640f2aa93039b576d4`.

Run-5 source identities:

- ThreatFox ZIP:
  `0aa5b4371970bc4fd16c111cc65b2a7a54c744a810fa15054206640de36260ac`;
- ThreatFox `full.csv`:
  `5df2498e5abc1d5f9c1564d16b6f00618611943cba7cc25dab12b2ed5c5ccd46`;
- CTU-13 Scenario 3:
  `0ebcd1df082bb5f85f8254c3857b02fdbb597c9b2ee7c50f908cc24ca92c0054`;
- OTRF archive:
  `98a073140860560d70080ace9142961be4f64b4862bae892d62d0f254d0fdbe5`;
- OTRF member:
  `dce651806007a20f6f4bac806dd6054e3361e0dd57a74ddd2f7cb5665d98c954`.

ThreatFox normalization itself succeeded:

- rows seen: 107,834;
- rows accepted: 107,834;
- rows rejected: 0.

The Actions traceback identifies the actual load-boundary problem:

- failure occurs inside `_bulk_insert_rows()`;
- DuckDB CSV sniffer selected an empty quote rule for the staged CSV;
- a later normalized VARCHAR field containing commas was therefore split as multiple CSV columns;
- a textual field shifted into target column `confidence_level INTEGER`;
- DuckDB raised `ConversionException`.

Therefore the problem is not a ThreatFox row-normalization error and not a timestamp/null policy issue.

## Security Finding

The sanitized JSON failure artifact did not retain source values, but the uncaught DuckDB exception printed an original CSV row into the GitHub Actions job log.

No credential was exposed, but this violates the project's no-raw-row diagnostic policy.

Before another source/snapshot run, DuckDB load exceptions must be rethrown without their raw message/context.

## Global Constraints

- No OpenAI/model calls.
- No E0/E1/E2/E3.
- No frozen run.
- No benchmark/scorer changes.
- Do not modify ThreatFox normalization semantics.
- Do not modify global timestamp parsing.
- Do not add null-sentinel rules.
- Do not re-download ThreatFox, CTU-13, or OTRF during this diagnostic plan.
- Use only exact encrypted run-5 retained bytes for real-source validation.
- Do not serialize raw IOC values, URLs, malware strings, command lines, CSV rows, or DuckDB exception text.
- Do not commit decrypted/raw source bytes.
- Any workflow added by this plan must use `workflow_dispatch` only.
- Official snapshot retry is not authorized by this plan; success ends at a human review gate.

## Review Focus

1. Python's staged CSV writer and DuckDB COPY reader must use the same explicit delimiter/quote/escape/header/null contract.
2. A VARCHAR containing embedded commas must stay one CSV field even when earlier sampled rows do not require quoting.
3. Numeric-looking `source_row_id` values must remain VARCHAR without relying on DuckDB type sniffing.
4. DuckDB exceptions containing raw source rows must not appear in raised exception strings or Actions output.
5. The exact run-5 artifact must be verified before offline CTI load validation; no newer ThreatFox export is acceptable.

---

### Task 1: Sanitize the DuckDB Bulk-Load Failure Boundary

**Files:**
- Modify: `scripts/build_vinsoc_public_snapshot.py`
- Modify: `scripts/build_r2_official_snapshot.py` only if needed to expose sanitized diagnostic category
- Test: `tests/test_public_snapshot_builder.py`
- Test: `tests/test_r2_official_snapshot_build.py`

**Interfaces:**
- Existing `_bulk_insert_rows(snapshot_path, table, rows, temporary_directory) -> int` remains the load entry point.
- Add a safe exception type such as:
  `SnapshotBulkLoadError(RuntimeError)`.
- Public exception text may contain table/category only, never DuckDB's original message.

- [ ] **Step 1: Add a failing exception-redaction test**

Mock the DuckDB COPY call to raise an exception whose message contains:

```text
SENSITIVE_RAW_IOC_VALUE
SENSITIVE_ORIGINAL_LINE
```

Assert:
- the caller raises `SnapshotBulkLoadError`;
- `str(exc)` contains neither sensitive token;
- the exception is raised `from None` so the original DuckDB message is not emitted as chained traceback context.

- [ ] **Step 2: Add failure-report redaction coverage**

Run the official builder fixture through the same safe error and assert serialized diagnostic JSON contains only:
- failure stage;
- safe failure category;
- affected table.

It must not contain the underlying DuckDB message.

- [ ] **Step 3: Implement the safe boundary**

Catch DuckDB load errors immediately around the staged CSV `COPY`.

Allowed public error information:

```json
{
  "category": "duckdb_copy_error",
  "table": "cti_indicators"
}
```

Do not inspect or regex-redact the original value; discard the raw exception message entirely.

- [ ] **Step 4: Verify focused tests**

```bash
python -m pytest   tests/test_public_snapshot_builder.py   tests/test_r2_official_snapshot_build.py   -q
```

---

### Task 2: Make the Normalized CSV Contract Deterministic

**Files:**
- Modify: `scripts/build_vinsoc_public_snapshot.py`
- Test: `tests/test_public_snapshot_builder.py`

**Interfaces:**
- Keep the temporary CSV streaming architecture.
- Do not switch back to `SocSnapshotBuilder.insert_rows()` for multi-million-row sources.

- [ ] **Step 1: Pin the writer dialect explicitly**

The temporary normalized CSV writer must explicitly use:

- delimiter: comma;
- quote character: double quote;
- double-quote escaping;
- minimal quoting;
- newline: `\n`.

Do not rely on `csv.DictWriter` defaults for this evidence path.

- [ ] **Step 2: Pin the DuckDB COPY dialect explicitly**

The COPY statement must disable CSV auto-detection and specify the dialect matching the writer:

```text
FORMAT CSV
HEADER TRUE
AUTO_DETECT FALSE
DELIMITER ','
QUOTE '"'
ESCAPE '"'
NULL ''
```

Do not let DuckDB sniff delimiter, quote, escape, header, or target column types for this internally generated file.

- [ ] **Step 3: Add an embedded-comma regression test**

Create normalized CTI rows where:
- `source_row_id` is numeric-looking text;
- one `indicator` or other VARCHAR contains embedded commas;
- `confidence_level` is an integer;
- timestamps are valid/nullable.

Assert all rows load and preserve:
- exact number of rows;
- exact confidence values;
- the embedded-comma field as one VARCHAR.

The test must not depend on source-level ThreatFox parser behavior; it tests only the normalized staging/load boundary.

- [ ] **Step 4: Add a COPY-contract regression test**

Assert generated COPY configuration explicitly disables auto-detection and defines quote/escape/delimiter.

This prevents a future refactor from silently restoring sniffer behavior.

- [ ] **Step 5: Run focused tests**

```bash
python -m pytest   tests/test_public_snapshot_builder.py   tests/test_r2_official_snapshot_build.py   -q
```

- [ ] **Step 6: Run the full suite**

```bash
python -m pytest -q
```

- [ ] **Step 7: Commit separately**

Suggested commit:

```text
fix(data): pin normalized DuckDB CSV load contract
```

---

### Task 3: Exact Run-5 Offline CTI Load Validation

**Files:**
- Create: `.github/workflows/r2-run5-cti-load-validation.yml`
- Create: `scripts/validate_run5_cti_load.py`
- Test: `tests/test_run5_cti_load_validation.py`
- Extend workflow-shape tests in `tests/test_r2_official_snapshot_build.py`.

**Purpose:**

Validate the corrected load boundary on the exact source that failed in run #5 without downloading a new ThreatFox export and without publishing an official snapshot.

**Fixed input:**

- run ID: `36235433476`;
- artifact ID: `10904266318`;
- artifact digest:
  `sha256:a3858d1a92f15b70fc0d629a46f7c6eff6763caffde8b43077eabff74186d8f8`;
- ciphertext SHA-256:
  `b39c70b47bdef1c9668d3dde250ad11880516744ebb7edd98748fc8eded61f65`;
- ThreatFox ZIP SHA-256:
  `0aa5b4371970bc4fd16c111cc65b2a7a54c744a810fa15054206640de36260ac`;
- ThreatFox `full.csv` SHA-256:
  `5df2498e5abc1d5f9c1564d16b6f00618611943cba7cc25dab12b2ed5c5ccd46`;
- expected normalized ThreatFox rows: `107834`.

- [ ] **Step 1: Add workflow-shape tests**

Require:
- `workflow_dispatch` only;
- `contents: read` + minimum `actions: read`;
- `R2_SOURCE_RETENTION_PASSPHRASE`;
- fixed run/artifact identity;
- no call to `probe_r2_official_sources`;
- no ThreatFox/CTU/OTRF source URL download.

- [ ] **Step 2: Download and verify the encrypted artifact**

Verify artifact identity and ciphertext SHA before decryption.

- [ ] **Step 3: Decrypt to runner-temp only**

Use the current repository encryption contract.

Never upload decrypted bytes.

- [ ] **Step 4: Verify exact ThreatFox source identity**

Verify both:
- ZIP hash;
- extracted `full.csv` hash.

Any mismatch aborts.

- [ ] **Step 5: Run CTI-only normalization + load**

The validator must:
1. normalize the exact `full.csv`;
2. require `rows_seen = rows_accepted = 107834`;
3. create an ephemeral DuckDB schema;
4. load only `cti_indicators` using the corrected `_bulk_insert_rows()`;
5. require database row count `107834`.

Do not process CTU-13 or OTRF in this validation workflow.

- [ ] **Step 6: Run aggregate integrity checks**

Report counts only:
- normalized rows;
- loaded rows;
- distinct source-row-id count;
- NULL counts for nullable typed fields such as `last_seen` and `confidence_level`;
- load status.

Do not report min/max or example string values.

Require source-row-id uniqueness to match the table's primary-key contract.

- [ ] **Step 7: Persist credential-free validation evidence**

Artifact schema should contain only:
- git SHA;
- fixed run/artifact/source hashes;
- builder version/hash;
- normalized row count;
- loaded row count;
- safe aggregate/null counts;
- status.

No DuckDB raw errors and no row values.

- [ ] **Step 8: Delete decrypted/plaintext temp data**

Use an `if: always()` cleanup step.

---

### Task 4: CI and One Offline Validation Run

- [ ] Push the sanitization + deterministic COPY patch to `master`.
- [ ] Require Python 3.11 and 3.12 CI green on the exact SHA.
- [ ] Trigger `r2-run5-cti-load-validation.yml` exactly once.
- [ ] Do not trigger `r2-official-snapshot-build.yml`.

## Human Review Output

After the offline validation, STOP and report:

```text
git SHA:
CI:
run5 source artifact verified: yes/no
ThreatFox ZIP SHA:
ThreatFox full.csv SHA:
normalized rows:
loaded CTI rows:
distinct source_row_id:
nullable-field aggregate counts:
sanitized load status:
validation artifact ID/digest:
raw source values present in evidence/logs: yes/no
```

## Resume Gate

Only if:

- exact run-5 source hashes match;
- normalized rows = 107,834;
- loaded CTI rows = 107,834;
- source-row-id uniqueness passes;
- no raw source values are emitted by the new load path;
- CI is green;

may the project request approval for **one** new official three-source snapshot retry.

That future retry is not authorized by this plan.

No model run is authorized by this plan.
