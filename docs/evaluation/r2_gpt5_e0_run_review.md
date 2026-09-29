# CTU R2 GPT-5 Mini E0 development run review

This is the single GPT-5 Mini one-shot run on the eight locked CTU S5/S7 **development** cases. It is a candidate E0 for the new DualSQL series, subject to the exact request, prompt, schema, snapshot, split, and scorer identity check before E1–E3. Its 0/8 score is evidence and is not a reason to rerun E0.

## Run and provenance

| Check | Observed evidence |
| --- | --- |
| Run / CI | [paid Actions run 36520685612](https://github.com/Whats-up-pro/VinSOC/actions/runs/36520685612) / [CI 36520615263](https://github.com/Whats-up-pro/VinSOC/actions/runs/36520615263), both on evaluator SHA `4fa777ed8a3fd450cef871d427df16270c8fa606` |
| Original evidence | [full JSON](../../results/evaluation_v1/ctu_network_public/gpt5_e0/36520685612/ctu-r2-result.json), [preflight](../../results/evaluation_v1/ctu_network_public/gpt5_e0/36520685612/ctu-r2-preflight.json), [receipt](../../results/evaluation_v1/ctu_network_public/gpt5_e0/36520685612/receipt.json) |
| Artifact integrity | Actions artifact `11013215781`, ZIP digest `sha256:4222b2d94d0df030842f1191bb4743c0f3497300c83d0467827b55e62cc0b0cd`; committed original report SHA-256 `33b35678171309c1a8958c1d9818499915986942e6936a03428df8fa0544bc15` |
| Model/request | OpenAI `gpt-5-mini-2025-08-07` requested and returned on all eight calls; `reasoning_effort=low`, no `temperature` field, cap 1000, SDK retries 0 |
| Dev data | S5 `ef5c9ed6895d4ca5aec723449dae30054ccd1f6b091713a52ffcb681ff78a02c`; S7 `df0b5338190b967bd340a0d6c1bb3c34d1bbfb4b7ffa764c2dd26f77f1a26680`; 243,906 normalized flows; logical snapshot `42c8e0a62441295cc5d95329a65dc22409c37de5b26a1e37dd56fbf0164a758c` |
| Locked evaluation | Split `96362f80e9e6bf01f18f1023c75066c553ddd9c105d2545f98af808d24f736fb`; model config `682254f85e2b6ca181d452643091eded385050edca13653e0d60c041c1814f58`; builder/scorer file hashes match `evaluation/ctu_network_public/VERSION.lock` |
| Cost gate | Conservative ceiling `$0.02540325` < `$0.10`; actual usage 845 input and 1,818 output tokens, calculated `$0.00384725` |
| Completeness | Eight distinct case IDs, eight attempted calls, eight responses, eight valid usage records; `run_status=complete`, `pilot_eligible=true`, no provider or execution errors |

The two preserved build reports have matching logical snapshot hashes and 243,906 rows. The source files in the local verified snapshot match the pinned manifest checksums. `pilot_eligible` states that this run met its runner contract; it does not make this a frozen or final architecture result.

## Score and per-case diagnosis

Execution Accuracy is **0/8**. Syntax Validity and Execution Success are both **8/8**; Safety Rejection is **0/8**. Every deterministic scorer label is `RESULT_MISMATCH`. Offline execution of the saved SQL against the verified snapshot produced the values below. The semantic causes are diagnostic annotations; they do not change the scorer, gold SQL, or cases.

| Case | Primary semantic cause | Gold result → saved SQL result | What the saved SQL did |
| --- | --- | --- | --- |
| `ctu_sql_001` | `VALUE_GROUNDING` | 901 → 0 | Used `source_dataset='scenario 5'` instead of `ctu13_s5` and exact `label='From-Botnet'` instead of the stored `flow=From-Botnet...` values. |
| `ctu_sql_002` | `VALUE_GROUNDING` | 1,677 → 0 | Used `source_dataset='scenario 7'` and exact `label='Normal'`; the snapshot stores `ctu13_s7` and longer flow labels. |
| `ctu_sql_003` | `SCHEMA_SELECTION` | 15,038 → 0 | Preserved `COUNT(DISTINCT dst_ip)` but searched `label` for scenario names instead of filtering `source_dataset`. |
| `ctu_sql_004` | `SCHEMA_SELECTION` | 1 → 0 | Preserved the inclusive/exclusive microsecond bounds but filtered `label='scenario 5'` rather than `source_dataset`. |
| `ctu_sql_005` | `SCHEMA_SELECTION` | 89,247 → 0 | Preserved UDP and positive outbound bytes, but used `label LIKE '%7%'` instead of the scenario 7 source column. |
| `ctu_sql_006` | `SCHEMA_SELECTION` | 5 rows → 0 rows | Filtered `label='scenario 5'`; it also added `dst_port IS NOT NULL` and omitted the gold's deterministic port tie-break. |
| `ctu_sql_007` | `VALUE_GROUNDING` | 2 rows → 0 rows | Used exact `label='Botnet'` although labels contain longer `flow=...Botnet...` strings; also omitted the scenario 7 source filter. |
| `ctu_sql_008` | `AGGREGATION` | 2 rows → 129 rows | Grouped by `source_dataset, label` and projected extra byte totals instead of one flow total per source dataset. |

Primary-cause counts: `VALUE_GROUNDING` 3, `SCHEMA_SELECTION` 4, `AGGREGATION` 1. The snapshot stores `source_dataset` values `ctu13_s5` and `ctu13_s7`; Botnet labels include values such as `flow=From-Botnet-V46-TCP-Attempt`. The preserved SQL, case questions, gold SQL, individual usage/cost/latency, and deterministic scores remain in the linked JSON.

The historical GPT-4.1 Mini CTU run also scored 0/8 on this split, but that separate run is preserved as historical baseline. No controlled E1–E3 result or frozen result is implied by this review.
