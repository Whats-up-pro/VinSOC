# ThreatFox Null-Sentinel and Retention Remediation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Secure the unencrypted run-4 source artifact, classify the exact `last_seen_utc` representation without exposing IOC content, and create the evidence required to authorize one narrow ThreatFox parser fix.

**Architecture:** Treat run #4 source bytes as the authoritative diagnostic dataset. First create and verify an encrypted equivalent of the existing raw artifact, then classify only the `last_seen_utc` representation using aggregate categories. Do not modify parser semantics until the classification result is reviewed and an exact sentinel is approved.

**Tech Stack:** GitHub Actions manual workflow, Python 3.11, `csv`, SHA-256, OpenSSL AES-256-CBC + PBKDF2 (matching the current repository retention format).

**Spec:** `docs/superpowers/plans/2026-09-26-threatfox-diagnostic-gate.md`

## Current Evidence

- Current master: `431bb2b07f35de8b110ebaad36b2e56083a42754`.
- Diagnostic run: `36230976997`.
- Run-4 code SHA: `0245cba44309e98b47449f015d72682731821d84`.
- Metadata artifact: `10902621571`.
- Metadata artifact digest:
  `sha256:bb8b4e874e51f77d73a8f70495ea6f228ddc43d24ce9df9da416002deb51c4af`.
- Unencrypted source artifact: `10902596707`.
- Unencrypted source artifact digest:
  `sha256:d59793d9c95c8effeeb2da9dff4642ecb00ba2114f99213f9eefb11c6af871f6`.

Run-4 ThreatFox diagnostics:

- rows seen: 107,817;
- accepted: 0;
- rejected: 107,817;
- missing required: 0;
- invalid first_seen: 0;
- invalid last_seen: 107,817;
- invalid confidence: 0.

The parser/header fix is therefore not the blocker. Every row reaches the `last_seen_utc` check and fails there.

Official ThreatFox API documentation represents `last_seen` as nullable. This supports the null-sentinel hypothesis, but does not identify the exact CSV export representation.

## Global Constraints

- No OpenAI/model calls.
- No E0/E1/E2/E3.
- No frozen run.
- No benchmark/scorer changes.
- Do not broaden global `_timestamp()`.
- Do not log IOC ID/value, malware, reference URL, raw CSV rows, or raw timestamps.
- Do not commit source bytes.
- Do not delete artifact `10902596707` until an encrypted equivalent has been uploaded and independently verified against the run-4 source hashes.
- The current retention encryption format remains:
  `openssl enc -aes-256-cbc -salt -pbkdf2 -iter 600000`.
- The encryption secret is `R2_SOURCE_RETENTION_PASSPHRASE`; it must never be printed or persisted.
- Any remediation/diagnostic workflow must be `workflow_dispatch` only.
- Phase A below is authorized now.
- Phase B parser modification is **not authorized until the Phase-A classification result is reviewed and the exact sentinel category is approved by the project owner**.

## Review Focus

1. The encrypted replacement must contain the exact run-4 bytes, not a new ThreatFox download.
2. The classifier must never serialize arbitrary unrecognized `last_seen_utc` values.
3. The encrypted artifact must be round-trip verified before the old raw artifact is deleted.
4. A parser patch must affect ThreatFox optional `last_seen_utc` only, not global timestamp behavior.
5. If more than one representation is materially present, the parser patch must not collapse them into one guessed null policy.

---

## Phase A — Authorized Now

### Task 1: Create a One-Off Run-4 Artifact Remediation Workflow

**Files:**
- Create: `.github/workflows/r2-run4-source-remediation.yml`
- Test: `tests/test_r2_official_snapshot_build.py`

**Interfaces:**
- Input source is fixed to run `36230976997`, artifact `10902596707`.
- Output encrypted artifact must use a distinct name, for example:
  `r2-official-run4-source-bytes-encrypted`.
- Output diagnostic metadata must contain only hashes/counts/categories.

- [ ] **Step 1: Add a workflow-shape test**

Assert:
- trigger set is exactly `workflow_dispatch`;
- permissions include only `contents: read` and the minimum Actions read permission required to fetch an earlier same-repository artifact;
- workflow references run `36230976997` and artifact name `r2-official-frozen-source-bytes`;
- workflow requires `R2_SOURCE_RETENTION_PASSPHRASE`;
- no source-download/probe command is present.

- [ ] **Step 2: Implement same-repository artifact retrieval**

Download the existing run-4 raw artifact. Do not call ThreatFox, CTU, or OTRF network sources.

Fail if the downloaded artifact identity does not correspond to run `36230976997`.

- [ ] **Step 3: Verify exact source identities before encryption**

Recompute and require these values:

```text
ThreatFox ZIP
28927b7eaf4b853b8c1dd57bd3a03bb80c2ac01c6f21d370481f0e07cc63d66b

ThreatFox full.csv
444e2caa3a3226e3778bd1e49732aac527c214f8c521b57707f4215de3a1691d

CTU-13 Scenario 3
0ebcd1df082bb5f85f8254c3857b02fdbb597c9b2ee7c50f908cc24ca92c0054

OTRF archive
98a073140860560d70080ace9142961be4f64b4862bae892d62d0f254d0fdbe5

OTRF member
dce651806007a20f6f4bac806dd6054e3361e0dd57a74ddd2f7cb5665d98c954
```

Any mismatch aborts remediation and preserves the old artifact.

- [ ] **Step 4: Encrypt the exact verified source bundle**

Use the repository's current encryption contract:

```bash
openssl enc -aes-256-cbc -salt -pbkdf2 -iter 600000
```

Write:
- ciphertext archive;
- ciphertext SHA-256 file.

Do not include the passphrase in command output.

- [ ] **Step 5: Round-trip verify the encrypted replacement**

Decrypt to a temporary directory inside the same job and recompute all five source hashes above.

Require exact equality before upload is considered valid.

Delete decrypted temporary bytes at the end of the step.

- [ ] **Step 6: Upload encrypted replacement**

Upload:
- encrypted source bundle;
- ciphertext SHA-256;
- credential-free remediation metadata.

Metadata must include:
- original run ID;
- original artifact ID/digest;
- encrypted artifact ID/digest;
- ciphertext SHA-256;
- exact five verified source hashes;
- encryption scheme identifier;
- `round_trip_verified: true`.

No raw source content.

---

### Task 2: Classify `last_seen_utc` on the Exact Run-4 `full.csv`

**Files:**
- Create: `scripts/classify_threatfox_last_seen.py`
- Test: `tests/test_threatfox_last_seen_classifier.py`
- Invoke only from the remediation workflow after source hashes pass.

**Interface:**

```python
classify_last_seen(path: Path) -> dict[str, object]
```

The function returns aggregate counts only.

- [ ] **Step 1: Define a closed representation classifier**

The classifier may emit only these categories:

```text
empty
valid_timestamp
literal_none
literal_null
literal_na
literal_n_a
literal_never
literal_dash
zero_datetime
other_unrecognized
```

Matching rules for named literals are exact after surrounding-whitespace trim and ASCII case-folding where the category name implies a word token.

`zero_datetime` is restricted to an explicitly tested all-zero date/time representation.

Do not emit the unmatched input value for `other_unrecognized`.

- [ ] **Step 2: Add privacy tests**

Fixtures must prove:
- arbitrary unknown text increments `other_unrecognized` but never appears in serialized output;
- IOC columns never appear in the output;
- only category names and counts are returned.

- [ ] **Step 3: Parse the same ThreatFox commented-header format**

Reuse or mirror the already-validated ThreatFox header discovery contract.

Read only the `last_seen_utc` field for classification.

- [ ] **Step 4: Add accounting invariants**

Require:

```text
sum(representation_counts.values()) == data_rows_seen
```

and:

```text
data_rows_seen == 107817
```

for the run-4 retained `full.csv`.

If row count differs, abort; do not classify a different export as run-4 evidence.

- [ ] **Step 5: Persist aggregate classifier report**

The workflow uploads a small diagnostic JSON containing:
- run ID;
- `full.csv` SHA-256;
- rows seen;
- representation counts;
- classifier version/hash.

No raw `last_seen_utc` values.

---

### Task 3: Old Raw Artifact Deletion Gate

The raw artifact is:

`10902596707`

Do **not** delete it automatically from code before verification.

Deletion is permitted only when all are true:

- [ ] encrypted replacement artifact exists;
- [ ] encrypted replacement artifact digest is recorded;
- [ ] ciphertext SHA-256 is recorded;
- [ ] round-trip verification recovered the exact five run-4 source hashes;
- [ ] classifier report is preserved;
- [ ] project owner has retained the decryption secret.

After those conditions are verified, delete the old unencrypted artifact through GitHub Actions UI/API using an authorized human/admin path.

The current ChatGPT GitHub connector does not expose an artifact-delete action, so the implementation agent must not claim this deletion was performed unless it has independent authorized GitHub Actions deletion capability and evidence.

After deletion, record:
- old artifact ID;
- deletion timestamp;
- encrypted replacement artifact ID;
- remediation evidence location.

Do not store the secret.

---

## Mandatory Human Review Gate

After Phase A, STOP and report exactly:

```text
run4 full.csv SHA-256:
rows seen:
empty:
valid_timestamp:
literal_none:
literal_null:
literal_na:
literal_n_a:
literal_never:
literal_dash:
zero_datetime:
other_unrecognized:

encrypted replacement artifact ID:
encrypted artifact digest:
ciphertext SHA-256:
round-trip source hashes verified: yes/no
old raw artifact deleted: yes/no
```

No parser change is authorized before this report is reviewed.

---

## Phase B — Conditional Parser Patch After Human Approval

Phase B becomes executable only if Phase A identifies one exact null representation and the project owner approves that representation.

The patch requirements are fixed in advance:

1. Add one TDD fixture containing the approved sentinel in ThreatFox `last_seen_utc`.
2. Map only that approved sentinel to `None`.
3. Keep ordinary blank `last_seen_utc` semantics unchanged.
4. Keep valid timestamps parsed through the existing timestamp path.
5. Keep any other non-empty unparseable `last_seen_utc` rejected.
6. Do not modify global `_timestamp()`.
7. Do not add a generic list of null-ish strings beyond the one observed/approved representation.
8. Run focused builder tests and the full suite.
9. Commit the narrow parser patch separately from security/remediation work.

### Required regression assertions

After the patch:

- approved sentinel -> accepted row with `last_seen is None`;
- valid timestamp -> parsed timestamp;
- arbitrary invalid string -> row remains rejected as `invalid_last_seen_timestamp`;
- first_seen behavior unchanged;
- confidence behavior unchanged.

---

## Phase C — One Snapshot Retry After Parser Approval

Only after Phase B passes CI:

1. trigger one manual official snapshot build;
2. require encrypted source retention;
3. require CTI rows > 0;
4. require network rows > 0;
5. require Sysmon rows > 0;
6. require two-build logical-content identity match.

Then STOP for snapshot review before `official_dev.lock` or E0.

No model call is authorized by this plan.
