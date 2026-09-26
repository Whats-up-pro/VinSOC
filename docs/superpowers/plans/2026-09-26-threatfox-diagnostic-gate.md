# ThreatFox Official-Source Diagnostic Gate

**Status:** Approved diagnostic-only continuation after official snapshot run #3 failed  
**Base commit:** `bc798798a9e9881935a93deddb27d7175a5b1f0e`  
**Failed run:** GitHub Actions `36228785013`  
**Failed artifact:** `10902231125`, SHA-256 `84ed70b1155f640e6195a1a35d97003c75825d7912411da8df8d5888faa45419`

## Goal

Identify exactly why all ThreatFox rows are rejected without exposing IOC content, preserve the exact same-run source bytes needed for reproducible diagnosis, and run one manual diagnostic build. Do not prepare official-dev E0 until the three-source snapshot succeeds.

## Current Evidence

Verified in run #3:

- ThreatFox ZIP SHA-256:
  `28927b7eaf4b853b8c1dd57bd3a03bb80c2ac01c6f21d370481f0e07cc63d66b`
- ThreatFox `full.csv` SHA-256:
  `444e2caa3a3226e3778bd1e49732aac527c214f8c521b57707f4215de3a1691d`
- CTU-13 Scenario 3 SHA-256:
  `0ebcd1df082bb5f85f8254c3857b02fdbb597c9b2ee7c50f908cc24ca92c0054`
- OTRF archive SHA-256:
  `98a073140860560d70080ace9142961be4f64b4862bae892d62d0f254d0fdbe5`
- OTRF member SHA-256:
  `dce651806007a20f6f4bac806dd6054e3361e0dd57a74ddd2f7cb5665d98c954`

Header discovery and required-column validation passed.

The final failure was:

```text
ValueError: Snapshot table has no rows: cti_indicators
```

The current row-level ThreatFox rejection points are:

1. missing `ioc_id`, `ioc_value`, or `ioc_type`;
2. non-empty `first_seen_utc` that fails timestamp parsing;
3. non-empty `last_seen_utc` that fails timestamp parsing;
4. non-empty `confidence_level` that fails integer/range parsing.

## Important Hypothesis

ThreatFox public API examples use timestamps such as:

```text
2020-12-08 13:36:27 UTC
```

The current `_timestamp()` parser accepts ISO forms and `YYYY-MM-DD HH:MM:SS`, but does not currently accept a trailing literal ` UTC`.

This is the highest-probability explanation for rejecting every row, but it is still a hypothesis until measured on the exact export bytes used by a diagnostic run.

Do not change timestamp semantics before the diagnostic counters confirm the cause.

## Constraints

- No OpenAI/model calls.
- No E0/E1/E2/E3 run.
- No frozen run.
- No benchmark mutation.
- No scorer mutation.
- Do not print or upload IOC values, references, malware strings, or full CSV rows in diagnostic metadata.
- Do not commit raw source bytes to Git.
- Exact source bytes must be retained in restricted storage/artifact suitable for the source terms; do not expose auth-gated ThreatFox bytes through an unrestricted public artifact.
- Workflow remains `workflow_dispatch` only.
- One diagnostic build only after instrumentation tests pass.

---

## Task 1 — Add Privacy-Preserving ThreatFox Rejection Diagnostics

**Files:**
- Modify: `scripts/build_vinsoc_public_snapshot.py`
- Modify: `tests/test_public_snapshot_builder.py`
- Add a diagnostic JSON output contract to the official snapshot build path.

### Required diagnostic counters

For ThreatFox only, collect:

```json
{
  "dataset_id": "threatfox_full",
  "data_rows_seen": 0,
  "rows_accepted": 0,
  "rows_rejected": 0,
  "primary_rejection_reasons": {
    "missing_required_value": 0,
    "invalid_first_seen_timestamp": 0,
    "invalid_last_seen_timestamp": 0,
    "invalid_confidence_level": 0
  },
  "timestamp_shape_counts": {
    "first_seen_ends_with_utc_literal": 0,
    "last_seen_ends_with_utc_literal": 0
  }
}
```

Rules:

- Every data row increments exactly one of `rows_accepted` or `rows_rejected`.
- Rejection reason follows the same first-failure order as current normalization code.
- `rows_accepted + rows_rejected == data_rows_seen`.
- No field value is stored.
- No IOC ID/value is stored.
- No raw timestamp is stored.
- Shape counts record only booleans/counts such as whether the trimmed timestamp ends with the literal ` UTC`.

### Required tests

Add fixtures that cover:

- valid current accepted timestamp;
- timestamp with trailing ` UTC`;
- invalid first_seen;
- invalid last_seen;
- invalid confidence;
- missing required IOC field.

Before any parser fix, the fixture with trailing ` UTC` should demonstrate the current parser behavior and increment `invalid_first_seen_timestamp`.

### Acceptance

Focused tests pass and diagnostic output contains counts only.

---

## Task 2 — Preserve Exact Same-Run Source Bytes on Failure

**Files:**
- Modify: `.github/workflows/r2-official-snapshot-build.yml`
- Modify tests for workflow retention behavior.

### Required behavior

The exact source set used by the diagnostic run must survive even if snapshot build fails.

Change the source-retention step from success-only behavior to failure-safe behavior, but respect redistribution restrictions.

Preferred order:

1. restricted/private durable storage already controlled by the project; or
2. a GitHub Actions artifact only if its access characteristics are acceptable for ThreatFox/OTRF terms.

Never commit raw files to the public repository.

The retained source bundle must bind:

- probe.json;
- source receipts;
- exact ThreatFox ZIP;
- exact ThreatFox `full.csv`;
- exact CTU file;
- exact OTRF archive.

Record artifact/storage identity and hashes in the diagnostic metadata.

### Critical rule

The source bytes preserved must be the same bytes used by staging/build in that run.

Do not perform a second ThreatFox download for diagnostics.

### Acceptance

A deliberately failing fixture/workflow path still reaches the source-retention step.

---

## Task 3 — Emit Diagnostic Metadata Even When Snapshot Validation Fails

**Files:**
- Modify: `scripts/build_r2_official_snapshot.py` and/or the builder interface as needed.
- Extend `r2-official-snapshot-build-metadata` artifact.

### Required behavior

Before raising the final empty-table error, persist a JSON report containing:

- source hashes;
- ThreatFox row diagnostic counts;
- table row counts reached so far;
- builder version;
- git SHA;
- failure stage;
- exception category/message.

Do not include raw row values.

The metadata artifact must be uploaded with `if: always()`.

### Acceptance

A test with all-invalid ThreatFox rows produces:
- zero `cti_indicators`;
- non-zero `data_rows_seen`;
- rejection counts summing to `data_rows_seen`;
- persisted diagnostic JSON;
- the expected build failure.

---

## Task 4 — Run Exactly One Manual Diagnostic Build

Prerequisites:

- focused tests pass;
- full test suite passes;
- CI on the exact diagnostic commit passes;
- workflow remains manual-only.

Run the official snapshot workflow once.

### Required review output

After the run, report only aggregate diagnostics:

```text
ThreatFox data rows seen:
accepted:
rejected:
missing required:
invalid first_seen:
invalid last_seen:
invalid confidence:
first_seen ending " UTC":
last_seen ending " UTC":
exact source hashes:
diagnostic artifact identity:
restricted source-byte retention identity:
```

No IOC content.

### Stop conditions

After this diagnostic run:

- if the build still fails, STOP;
- if diagnostics identify one dominant parser defect, STOP and request approval for the specific parser fix;
- if the snapshot unexpectedly succeeds, STOP before benchmark lock/E0 and review the evidence first.

Do not automatically implement a parser fix in the same diagnostic task.

---

## Decision Gate After Diagnostic Run

### Case A — first_seen timestamp rejection dominates

If nearly/all rejected rows have:

- `invalid_first_seen_timestamp`; and
- `first_seen_ends_with_utc_literal`;

then propose a narrow parser patch adding support for ThreatFox's explicit UTC suffix, with tests such as:

```text
YYYY-MM-DD HH:MM:SS UTC
YYYY-MM-DD HH:MM:SS.sss UTC
```

Do not broaden timestamp parsing beyond observed official formats.

### Case B — last_seen rejection dominates

Inspect shape counts and add only the observed official representation.

### Case C — confidence rejection dominates

Report the observed *shape category* only, not values, then propose a narrow confidence parser rule.

### Case D — missing required values dominate

Do not weaken required IOC identity constraints automatically. First determine whether this reflects CSV column misalignment/quoting rather than genuinely missing IOC fields.

### Case E — multiple substantial reasons

Fix one evidenced parser-contract problem at a time, with regression tests, and rerun offline tests before another source build.

---

## Resume Gate

Only after a three-source snapshot build succeeds and two-build logical identity matches may the project resume:

1. freeze successful official snapshot metadata;
2. validate the existing 8 official-dev gold cases;
3. create `official_dev.lock`;
4. freeze actual E0 one-shot request contract;
5. run one official-dev E0;
6. report and stop for human review.

Frozen remains sealed throughout.
