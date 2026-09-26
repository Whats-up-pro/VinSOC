# ThreatFox CSV Dialect Fix Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix ThreatFox full-export parsing so quoted fields preceded by delimiter whitespace are parsed correctly, then run exactly one official snapshot retry.

**Architecture:** Keep the fix ThreatFox-specific. The parser must use the actual ThreatFox CSV dialect where rows may contain comma + space + quoted values. Do not modify global timestamp parsing or benchmark logic.

**Tech Stack:** Python 3.11, standard-library `csv`, pytest, existing official snapshot workflow.

**Spec:** `docs/superpowers/plans/2026-09-26-threatfox-null-sentinel-retention-remediation.md`

## Evidence Supporting the Fix

Run #4 showed:
- 107,817 ThreatFox rows seen;
- 0 accepted;
- 107,817 rejected only at `last_seen_utc`;
- all 107,817 classified as `other_unrecognized`.

Public ThreatFox CSV examples show rows formatted like:

```text
"first field", "second field", "...", "", "100", ...
```

That is: a space may appear after the comma and before the next opening quote.

Python's `csv.reader` / `csv.DictReader` defaults to `skipinitialspace=False`. Under that mode, a field such as:

```text
, ""
```

is parsed as a non-empty quoted-looking literal rather than an empty CSV field. Fields containing embedded commas can also lose normal quote semantics.

This explains all observed diagnostics without requiring a new null-sentinel rule.

## Global Constraints

- No OpenAI/model calls.
- No E0/E1/E2/E3.
- No frozen run.
- No benchmark/scorer changes.
- Do not modify global `_timestamp()`.
- Do not introduce a general null-sentinel list.
- Do not alter CTU-13 CSV parsing.
- Apply dialect behavior only to ThreatFox full CSV parsing/classification.
- Workflow remains `workflow_dispatch` only.
- Source retention remains encrypted.
- After the one snapshot retry, STOP for review even if successful.

## Review Focus

1. ThreatFox rows with `, "value"` must preserve quote semantics.
2. Empty quoted `last_seen_utc` must become an empty field, not `'""'`.
3. Quoted ThreatFox fields containing embedded commas must remain one field.
4. Valid non-empty `last_seen_utc` timestamps must continue parsing.
5. Arbitrary malformed non-empty `last_seen_utc` must still be rejected.

---

### Task 1: Add ThreatFox Dialect Regression Tests

**Files:**
- Modify: `tests/test_public_snapshot_builder.py`
- Modify: `tests/test_threatfox_last_seen_classifier.py`

- [ ] Add a fixture whose ThreatFox row contains spaces after delimiters and quoted fields.

The fixture must include:
- an empty quoted `last_seen_utc`;
- at least one quoted field containing an embedded comma;
- valid `first_seen_utc`;
- valid confidence.

- [ ] Assert the current implementation fails before the fix.

Expected pre-fix behavior:
- row is rejected as `invalid_last_seen_timestamp`, or
- parsed fields demonstrate incorrect quote handling.

- [ ] Add a classifier regression asserting the same row is classified as:

```text
empty
```

after dialect parsing is corrected.

---

### Task 2: Fix ThreatFox-Specific CSV Dialect

**Files:**
- Modify: `scripts/build_vinsoc_public_snapshot.py`
- Modify: `scripts/classify_threatfox_last_seen.py`

**Interfaces:**
- Keep `_csv_rows()` unchanged.
- Keep `_threatfox_csv_rows()` public behavior unchanged except correct field parsing.
- Keep `classify_last_seen(path)` return schema unchanged.

- [ ] Update ThreatFox `csv.DictReader` construction to use the appropriate dialect behavior for delimiter whitespace:

```python
skipinitialspace=True
```

- [ ] Update the ThreatFox diagnostic classifier's `csv.reader` in the same way so builder and classifier interpret the source identically.

- [ ] Do not strip quotes manually.

- [ ] Do not preprocess rows with string replacement.

- [ ] Do not change timestamp semantics.

- [ ] Do not add a null-sentinel branch.

---

### Task 3: Verify Correct Semantics Offline

**Files:**
- Tests only plus current parser files.

- [ ] Verify empty quoted `last_seen_utc` produces:

```text
last_seen = None
```

and the row is accepted.

- [ ] Verify a normal timestamp still parses.

- [ ] Verify a deliberately malformed non-empty `last_seen_utc` still increments:

```text
invalid_last_seen_timestamp
```

- [ ] Verify a quoted embedded-comma field does not shift subsequent columns.

- [ ] Run:

```bash
python -m pytest   tests/test_public_snapshot_builder.py   tests/test_threatfox_last_seen_classifier.py   tests/test_r2_official_snapshot_build.py   -q
```

- [ ] Run the full suite:

```bash
python -m pytest -q
```

- [ ] Commit the parser fix separately:

```text
fix(data): honor ThreatFox CSV delimiter whitespace
```

---

### Task 4: CI Gate

- [ ] Push directly to `master`.
- [ ] Wait for Python 3.11 and 3.12 CI to pass on the exact parser-fix SHA.
- [ ] Do not trigger the snapshot workflow before exact-SHA CI is green.

---

### Task 5: Run Exactly One Official Snapshot Retry

**Workflow:**
- `.github/workflows/r2-official-snapshot-build.yml`

- [ ] Trigger manually once.

- [ ] Require encrypted source retention to succeed.

- [ ] Verify:
  - `cti_indicators > 0`;
  - `network_flows > 0`;
  - `sysmon_process_events > 0`;
  - two independent builds have identical logical-content SHA-256;
  - all source hashes and receipts belong to the same run.

- [ ] Preserve snapshot/build metadata and encrypted exact source bytes.

### Failure behavior

If the snapshot build fails for any new reason:

- STOP;
- report exact aggregate failure evidence;
- do not retry automatically;
- do not prepare official-dev E0.

### Success behavior

If the snapshot succeeds:

- STOP;
- report source hashes, row counts, binary SHA, logical SHA, two-build reproducibility result, artifact IDs/digests;
- do not create `official_dev.lock` yet;
- do not run E0 yet.

## Completion Gate

This plan is complete only when either:

1. one retry fails and the new blocker is documented; or
2. one retry succeeds with non-empty CTI/network/endpoint tables and matching two-build logical identity.

No model run is authorized by this plan.
