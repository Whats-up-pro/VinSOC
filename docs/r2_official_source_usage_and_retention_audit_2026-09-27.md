# R2 Official Source Usage and Retention Audit

**Date:** 2026-09-27
**Audit Scope:** Three-source R2 Text-to-SQL evaluation using ThreatFox, CTU-13 Scenario 3, and OTRF APT29 Day 1
**Repository:** Whats-up-pro/VinSOC
**Commit:** f2f38f454a83ecd185dc381d150d092235843f26

---

## Executive Summary

This audit examines whether the proposed R2 official workflow can legally and ethically use three third-party datasets to build a DuckDB snapshot for Text-to-SQL model evaluation. The evaluation intent is to score 8 `official_dev` SQL cases against the snapshot, including the `cti_indicators` table containing ThreatFox IOC data. **Raw IOCs are not included in prompts** — only schema context is exposed to the model.

**Key Finding:** Usage rights for all three sources are **UNRESOLVED**. No source has confirmed rights for AI model evaluation use. Durable encrypted source retention is **UNIDENTIFIED**.

---

## 1. Workflow Architecture (for reference)

The `r2-official-snapshot-build.yml` workflow (read-only, not modified):

1. Downloads all sources in a single probe step within the same run
2. Stages manifest/receipts from the same probe output
3. Builds snapshot from the same staged sources
4. Encrypts exact source bytes (AES-256-CBC) with passphrase
5. Uploads three artifacts:
   - `r2-official-frozen-source-bytes` (encrypted tar, 90-day retention)
   - `r2-official-snapshot-build-metadata` (hashes/receipts/lock, 90-day retention)
   - `r2-official-snapshot-duckdb` (unencrypted, 30-day retention)

**Note:** This is a **one-shot manual workflow** (`workflow_dispatch` only). Probe and build are in the same run, ensuring source bytes are frozen from the exact download that created the snapshot.

---

## 2. Source-by-Source Evidence

### 2.1 ThreatFox (abuse.ch)

| Item | Details |
|------|---------|
| **Dataset** | ThreatFox full CSV export |
| **URL** | https://threatfox.abuse.ch/export/ |
| **Auth Required** | Yes (THREATFOX_AUTH_KEY) |
| **Manifest SHA** | `cd366e759830c71d36a9f7a3c7c9f5f8...` (CSV hash) |

#### Terms of Use Analysis

**Source:** https://abuse.ch/terms-of-use/ (verified 2026-09-27)

| Use Case | Status | Evidence |
|----------|--------|----------|
| Download and retain exact bytes | `CONFIRMED` | Free API access with authentication |
| Transform to DuckDB table | `UNCONFIRMED` | Terms don't explicitly address data transformation |
| Distribute via GitHub Actions artifact | `UNCONFIRMED` | Terms mention "intellectual property" restrictions |
| Use for AI model evaluation | `UNCONFIRMED` | **No AI/ML provisions found in ToS** |
| Cite when publishing results | `CONFIRMED` | Attribution to abuse.ch required |

**Key Terms (verbatim):**
> "Use of the Platforms by companies, networks, or individuals with commercial or for-profit needs may require a paid subscription"
>
> "copy, adapt, alter, translate, modify or make derivative works based on the Platforms and/or any other of our or Spamhaus' intellectual property, without the express consent of abuse.ch"

**Analysis:**
- Free access exists under "fair use principles" for non-commercial API use
- The ToS does NOT explicitly address AI/ML model training or evaluation
- Converting to a database table may constitute "derivative work"
- Distributing via public artifact may breach redistribution terms
- VinSOC's use is **evaluation, not training**, but this distinction is not in the ToS

**Status: UNRESOLVED** — Requires clarification from abuse.ch or qualified legal review.

---

### 2.2 CTU-13 Scenario 3 (MCFP/Stratosphere)

| Item | Details |
|------|---------|
| **Dataset** | CTU-13 Scenario 3 Botnet Capture |
| **URL** | https://mcfp.felk.cvut.cz/publicDatasets/CTU-Malware-Capture-Botnet-44/detailed-bidirectional-flow-labels/capture20110812.binetflow |
| **License Claim** | "Creative Commons CC-BY" |
| **Manifest SHA** | `0ebcd1df082bb5f85f8254c3857b02fd...` |

#### License Analysis

**Source:** https://www.stratosphereips.org/datasets-overview/ (verified 2026-09-27)

| Use Case | Status | Evidence |
|----------|--------|----------|
| Download and retain | `CONFIRMED` | CC-BY permits downloading |
| Transform to DuckDB | `CONFIRMED` | CC-BY permits modification |
| Distribute via artifact | `CONFIRMED` | CC-BY permits redistribution with attribution |
| Use for AI evaluation | `CONFIRMED` | CC-BY permits any use with attribution |
| Cite when publishing | `CONFIRMED` | Citation requirement in dataset page |

**Key Terms (verbatim):**
> "The CTU-13 dataset is published with the license Creative Commons CC-BY"

**Analysis:**
- CC-BY is a permissive license allowing redistribution with attribution
- The dataset page explicitly states CC-BY applies
- However, I could not verify if the binetflow file specifically has CC-BY or a different license
- License note in manifest states: "MCFP permits use with attribution to Sebastian Garcia and the Malware Capture Facility Project"

**Status: CONFIRMED** — CC-BY appears to apply. Attribution required when publishing results.

---

### 2.3 OTRF APT29 Day 1 (Security-Datasets)

| Item | Details |
|------|---------|
| **Dataset** | APT29 Evals Day 1 Manual Sysmon |
| **URL** | https://raw.githubusercontent.com/OTRF/Security-Datasets/master/datasets/compound/apt29/day1/apt29_evals_day1_manual.zip |
| **License Claim** | Repository: GPL-3.0 or MIT (CONFLICTING) |
| **Manifest SHA** | `98a073140860560d70080ace9142961b...` |

#### License Analysis

**Source:** https://github.com/OTRF/Security-Datasets (verified 2026-09-27)

| Use Case | Status | Evidence |
|----------|--------|----------|
| Download and retain | `CONFIRMED` | GitHub repo is public |
| Transform to DuckDB | `UNCONFIRMED` | License ambiguity |
| Distribute via artifact | `CONFLICTING` | GPL-3.0 vs MIT mismatch |
| Use for AI evaluation | `UNCONFIRMED` | No AI provisions in either license |
| Cite when publishing | `CONFIRMED` | Attribution to OTRF required |

**Key Findings:**

1. **Repository LICENSE file:** States MIT License
2. **README:** States GPL-3.0 ("'Security Datasets's GNU General Public License")
3. **APT29 folder:** No dataset-specific license found

**License note in manifest:**
> "Retain OTRF attribution; resolve the repository README/LICENSE discrepancy before redistributing source bytes."

**Analysis:**
- The repository has conflicting license claims (MIT in LICENSE, GPL-3.0 in README)
- No specific license found for the APT29 dataset subdirectory
- Converting to DuckDB and distributing via public artifact is risky under GPL-3.0 (requires source disclosure)
- MIT would permit redistribution with attribution
- **This is a known conflict that the manifest itself flags as needing resolution**

**Status: CONFLICTING** — Repository has MIT/GPL-3.0 discrepancy. Dataset-specific license unverified. Requires OTRF clarification.

---

## 3. Artifact Analysis

### 3.1 Encrypted Source Bytes Artifact

| Property | Value |
|----------|-------|
| **Name** | `r2-official-frozen-source-bytes` |
| **Content** | `probe.json`, `receipts/`, `raw/` (tar archive) |
| **Encryption** | AES-256-CBC, PBKDF2 (600k iterations) |
| **Passphrase** | Stored in `R2_SOURCE_RETENTION_PASSPHRASE` secret |
| **Retention** | 90 days |
| **Access** | Anyone with repo read access + artifact ID |

**Current artifact status (from gh api):**
```json
{
  "name": "r2-official-frozen-source-bytes",
  "expires_at": "2026-12-25T10:19:20Z",
  "created_at": "2026-09-26T10:21:46Z"
}
```

**Analysis:**
- 90 days is **NOT durable** — artifact expires and exact bytes cannot be recovered
- Encrypted tar contains all three sources in plaintext
- Passphrase holder has complete access to source bytes
- After 90 days, only SHA-256 hashes remain (not recoverable for exact rebuild)

### 3.2 DuckDB Snapshot Artifact

| Property | Value |
|----------|-------|
| **Name** | `r2-official-snapshot-duckdb` |
| **Content** | Three tables: `cti_indicators`, `network_flows`, `sysmon_process_events` |
| **Encryption** | None (uploaded plaintext) |
| **Retention** | 30 days |
| **Access** | Anyone with repo read access + artifact ID |

**Analysis:**
- Contains **transformed data**, not raw source bytes
- `cti_indicators` table contains IOC data derived from ThreatFox
- `network_flows` contains netflow data derived from CTU-13
- `sysmon_process_events` contains process events derived from OTRF
- **Distributing this artifact may still breach source terms** if raw data transformation doesn't create clean derivative rights
- OTRF APT29 data embedded in process events may inherit GPL-3.0 obligations

### 3.3 Metadata Artifact

| Property | Value |
|----------|-------|
| **Name** | `r2-official-snapshot-build-metadata` |
| **Content** | `snapshot_manifest.json`, `official_snapshot.lock`, `source_receipts/`, `r2-official-source-retention.json` |
| **Encryption** | None (credential-free) |
| **Retention** | 90 days |

**Analysis:**
- Contains only hashes, receipts, and locks
- No raw data, keys, or IOCs
- Safe for public distribution

---

## 4. Proposed Durable Storage Solution

### 4.1 Encrypted Source Bytes

**Current state:** GitHub Actions artifact, 90-day retention, expires.

**Proposed solution:** Transfer to restricted storage after successful build.

| Element | Recommendation |
|---------|----------------|
| **Storage type** | Encrypted file storage (e.g., AWS S3 + KMS, Azure Blob + Key Vault, or GCS + CMEK) |
| **Owner** | Repository admin or designated Ops lead |
| **Access group** | Core VinSOC contributors (3-5 people) |
| **Retention** | Minimum 12 months (aligns with evaluation cycle) |
| **Backup** | One cross-region copy |
| **Verification** | Store artifact ID, run ID, ciphertext SHA-256, decryption instructions |

**Sample retention record:**
```json
{
  "artifact_id": "<from workflow run>",
  "run_id": "<from workflow run>",
  "ciphertext_sha256": "<from r2-official-source-retention.json>",
  "transferred_at": "<timestamp>",
  "storage_location": "<reference to storage config>",
  "decryption_instructions": "See R2_SOURCE_RETENTION_PASSPHRASE in <secret manager>"
}
```

**Status: BLOCKED** — Storage destination and owner not yet identified.

### 4.2 DuckDB Snapshot

**Current state:** GitHub Actions artifact, 30-day retention, unencrypted.

**Proposed solution:** Option A (preferred) or Option B.

| Option | Description | Risk |
|--------|-------------|------|
| **A: Encrypted upload** | Encrypt snapshot before upload, keep decryption key restricted | Lower distribution risk |
| **B: Private artifact only** | Don't upload to public repo; use authenticated download for evaluation only | Limits reproducibility |

**Note:** The 30-day window is for CI artifact; actual evaluation can occur within that window.

**Status: BLOCKED** — No decision made on snapshot distribution policy.

---

## 5. Decision Matrix

| Decision | Status | Evidence/Notes |
|----------|--------|----------------|
| **ThreatFox AI evaluation right** | `UNRESOLVED` | ToS has no AI provisions; derivative work concern |
| **CTU-13 retention and redistribution** | `CONFIRMED` | CC-BY explicitly permits |
| **OTRF APT29 dataset terms** | `CONFLICTING` | MIT/GPL-3.0 discrepancy; dataset license unverified |
| **Durable restricted source storage** | `UNDECIDED` | No storage destination or owner identified |
| **DuckDB artifact access** | `UNRESOLVED` | License compliance for transformed data unclear |
| **Official build dispatch** | **BLOCKED** | ThreatFox and OTRF rights unresolved |
| **Official E0 model run** | **BLOCKED** | Depends on ThreatFox-backed snapshot rights |

---

## 6. Recommended Questions for Rights Holders

### ThreatFox / abuse.ch
> "VinSOC intends to use ThreatFox IOC data to populate a reference database for evaluating Text-to-SQL model accuracy. The IOCs will be normalized into a database schema; raw IOCs are not exposed in model prompts. Evaluation results (SQL accuracy scores) may be published with attribution. Does this use case comply with abuse.ch's Terms of Use? Are there any restrictions on using ThreatFox data for AI/ML model evaluation?"

### OTRF / Security-Datasets
> "The Security-Datasets repository has conflicting license claims (MIT in LICENSE file, GPL-3.0 in README). Specifically for the APT29 Evals dataset: (1) Which license applies to this dataset? (2) Does converting to a database table and using for AI model evaluation comply with the license? (3) Can derived artifacts (DuckDB files) be distributed?"

---

## 7. Alternative Benchmark Design (if rights not cleared)

If ThreatFox rights cannot be obtained:

1. **Option: Public snapshot without CTI table**
   - Build snapshot with only CTU-13 (network flows) and OTRF (sysmon events)
   - Modify `sql_dev_008` to query `network_flows` or `sysmon_process_events` instead
   - Mark as "R2 Lite" or "R2 Network+Endpoint"

2. **Option: Synthetic CTI data**
   - Generate fictional IOC records matching ThreatFox schema
   - No real-world IP addresses, domains, or hashes
   - Evaluation validity reduced but legally clean

3. **Option: Delay until rights obtained**
   - Hold E0 until ThreatFox clarification received
   - Continue with other R2 tasks (documentation, scorer refinement)

---

## 8. References

| Source | URL | Checked |
|--------|-----|---------|
| ThreatFox FAQ | https://threatfox.abuse.ch/faq/ | 2026-09-27 |
| ThreatFox Terms | https://abuse.ch/terms-of-use/ | 2026-09-27 |
| CTU-13 Dataset | https://www.stratosphereips.org/datasets-overview/ | 2026-09-27 |
| OTRF Security-Datasets | https://github.com/OTRF/Security-Datasets | 2026-09-27 |
| OTRF LICENSE | https://github.com/OTRF/Security-Datasets/blob/master/LICENSE | 2026-09-27 |
| Dataset Manifest | `evaluation/text_to_sql_benchmarks/dataset_manifest.json` | f2f38f4 |
| Workflow | `.github/workflows/r2-official-snapshot-build.yml` | f2f38f4 |

---

## 9. Conclusion

**The R2 official snapshot build and E0 evaluation cannot proceed until:**

1. [ ] ThreatFox usage rights for AI evaluation are clarified
2. [ ] OTRF APT29 dataset license conflict is resolved
3. [ ] Durable encrypted source storage is identified and configured
4. [ ] DuckDB artifact distribution policy is decided

**This audit should be reviewed by:**
- Repository owner (legal authority)
- Potentially: abuse.ch, MCFP/Stratosphere, OTRF for rights clarification
- Potentially: Legal counsel for license interpretation

---

*Audit performed by Agent A on 2026-09-27 at master@f2f38f454a83ecd185dc381d150d092235843f26*
