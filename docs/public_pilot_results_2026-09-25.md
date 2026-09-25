# VinSOC network and endpoint public pilot, 2026-09-25

This is `public_dev` pilot version `r1_r2_network_endpoint_public_dev_v1`. It is separate from R1 `dev v2` (22/24); the scores cannot be interpreted as improvement on the same benchmark. Neither frozen nor CTI was used. [Dataset manifest](../evaluation/public_pilot/dataset_manifest.json) records original URLs, retrieval timestamps (UTC), file formats, license notes and SHA-256 hashes. The original source bytes and DuckDB binaries are not committed.

## Verified data and version

| Source URL | Downloaded-original SHA-256 | Rights note |
| --- | --- | --- |
| [CTU-13 scenario 5](https://mcfp.felk.cvut.cz/publicDatasets/CTU-Malware-Capture-Botnet-46/detailed-bidirectional-flow-labels/capture20110815-2.binetflow) | `ef5c9ed6895d4ca5aec723449dae30054ccd1f6b091713a52ffcb681ff78a02c` | Attribute Sebastian Garcia and MCFP. |
| [CTU-13 scenario 7](https://mcfp.felk.cvut.cz/publicDatasets/CTU-Malware-Capture-Botnet-48/detailed-bidirectional-flow-labels/capture20110816-2.binetflow) | `df0b5338190b967bd340a0d6c1bb3c34d1bbfb4b7ffa764c2dd26f77f1a26680` | Attribute Sebastian Garcia and MCFP. |
| [OTRF APT29 Day 1 ZIP](https://raw.githubusercontent.com/OTRF/Security-Datasets/master/datasets/compound/apt29/day1/apt29_evals_day1_manual.zip) | `98a073140860560d70080ace9142961be4f64b4862bae892d62d0f254d0fdbe5` | OTRF README says GPL-3.0, repository LICENSE says MIT; clarify before redistributing raw data. |

The OTRF ZIP member `apt29_evals_day1_manual_2020-05-01225525.json` has SHA-256 `dce651806007a20f6f4bac806dd6054e3361e0dd57a74ddd2f7cb5665d98c954`. Snapshot: **243,906** network flows and **143,884** Sysmon process events; no CTI table. Two independent builds matched ordered logical content SHA-256 `8dc07dd60d9222776ff3438bedd8488582e95f53d7b8052bbd510adad73cc42e`; the DuckDB binary hashes differ. The [version lock](../evaluation/public_pilot/VERSION.lock) pins source, snapshot, splits and scorer. All 16 R1 investigation cases reference verified evidence rows; 8/8 gold SQL queries execute.

## Runs, configuration, cost

Both runs used direct OpenAI `gpt-4.1-mini-2025-04-14`, temperature 0, `max_completion_tokens=1000`, zero retries. Preflight estimated a **$0.129056 maximum for all 28 actual serialized request payloads combined**, allowing 4,096 framing tokens and 1,000 completion tokens per request, below the **$1 task cap**. Calculated usage cost uses $0.40/M input and $1.60/M output tokens; this is not a provider invoice. Reports preserve prompt/schema/split/scorer hashes, actual model/provider, usage and errors for each case. Both show `pilot_eligible=true`, `official_eligible=false` and `official_ineligible_reasons=["public_dev_pilot_is_distinct_from_official_benchmarks"]`.

| Track | Evaluator commit / Actions run | Distinct IDs / API calls | Input / output tokens | Cost from usage |
| --- | --- | ---: | ---: | ---: |
| [R1 JSON](../results/evaluation_v1/public_pilot/public-r1.json) | [`8d0df826`](https://github.com/Whats-up-pro/VinSOC/commit/8d0df8262025b100a6e171b166a1df14d0e39304) / [run 36095417137](https://github.com/Whats-up-pro/VinSOC/actions/runs/36095417137) | 20/20 | 15,686 / 1,177 | $0.0081576 |
| [R2 JSON](../results/evaluation_v1/public_pilot/public-r2.json) | [`6c5a6139`](https://github.com/Whats-up-pro/VinSOC/commit/6c5a61391018df6254d93b07e0fe7caf610e20a4) / [run 36095590918](https://github.com/Whats-up-pro/VinSOC/actions/runs/36095590918) | 8/8 | 1,538 / 466 | $0.0013608 |
| **Total** | One run each | **28/28** | **17,224 / 1,643** | **$0.0095184** |

The Actions artifact ZIP SHA-256 hashes are R1 `873bf104c7e0b2d92f063f857f6c6385b482b3cd875b825ecf45b64f50922bf5`, R2 `dae6d924f80284f06b93034263250326d25e8da1b568eb48012c85ed4004f462`. Preserved extracted JSON SHA-256 hashes are R1 `73ce5a28eca4cde59761aeeff44f401e025dd4b73fabea8635a21111537af69b`, R2 `0bac8abd8523eb5fe7faaa90e1708fee779ba217acead125b71fb90d4c72f636`. Both automatic push triggers were disabled in a separate commit after the runs; no marker was touched.

## R1: Tool Calling in one turn

Case success **20/20**, exact-call F1 **1.0**, no-tool accuracy **4/4**. Category: network `public_r1_001`–`008` **8/8**, endpoint `public_r1_009`–`016` **8/8**, no-tool `public_r1_017`–`020` **4/4**. Difficulty: basic **8/8**, intermediate **7/7**, advanced **5/5**. Every individual case succeeded (see JSON for calls, normalized arguments and matches). The tool F1 within the no-tool subgroup is zero by the empty-positive convention; its appropriate metric is no-tool accuracy. This measures single-turn selection/arguments, not tool execution or end-to-end investigation quality.

## R2: Text-to-SQL against the offline snapshot

Execution accuracy **2/8 (25%)**, syntax validity **8/8 (100%)**, execution success **3/8 (37.5%)**, safety rejection **5/8 (62.5%)**. Category: aggregation **1/1**, endpoint **1/2**, network **0/2**, distinct **0/1**, time range **0/1**, ordering limit **0/1**. Difficulty: basic **1/2**, intermediate **1/3**, advanced **0/3**. The scorer compares ordered queries in sequence and unordered results as row multisets; fixtures exercise `DISTINCT`, exclusive time bounds, Boolean grouping and `ORDER BY`.

| Case | Category / difficulty | Result at pinned scorer |
| --- | --- | --- |
| `public_sql_001` | network / basic | `RESULT_MISMATCH`: wrong source identifier and label. |
| `public_sql_002` | distinct / intermediate | `SAFETY_REJECTION`: terminal semicolon. |
| `public_sql_003` | time range / intermediate | `SAFETY_REJECTION`: terminal semicolon. |
| `public_sql_004` | network / advanced | `SAFETY_REJECTION`: terminal semicolon. |
| `public_sql_005` | aggregation / intermediate | Correct. |
| `public_sql_006` | endpoint / basic | Correct. |
| `public_sql_007` | ordering limit / advanced | `SAFETY_REJECTION`: terminal semicolon. |
| `public_sql_008` | endpoint / advanced | `SAFETY_REJECTION`: terminal semicolon. |

**Scorer limitation:** The existing conservative validator rejects *any* semicolon as multi-statement SQL. The five flagged queries end with one ordinary semicolon; they do not demonstrate a write attempt, and their untested SQL cannot be assumed semantically correct. The **2/8 score remains fixed** at the original scorer version; changes to SQL normalization or safety policy require a new version and a separately reviewed evaluation. Execution equality on one finite snapshot can also reward semantically wrong queries by coincidence. `public_dev` is not an independent holdout; this pilot uses only two CTU scenarios and one OTRF dataset. Text-to-SQL executes offline in read-only DuckDB, never as a production LLM-issued SQL command.
