# CTU R2 GPT-5 Mini E0 dev error analysis

The sole GPT-5 Mini one-shot E0 is [Actions run 36520685612](https://github.com/Whats-up-pro/VinSOC/actions/runs/36520685612), evaluated on SHA `4fa777ed8a3fd450cef871d427df16270c8fa606` after [CI 36520615263](https://github.com/Whats-up-pro/VinSOC/actions/runs/36520615263). Its [unaltered full report](../../results/evaluation_v1/ctu_network_public/gpt5_e0/36520685612/ctu-r2-result.json) has SHA-256 `33b35678171309c1a8958c1d9818499915986942e6936a03428df8fa0544bc15`; [receipt](../../results/evaluation_v1/ctu_network_public/gpt5_e0/36520685612/receipt.json) records Actions artifact `11013215781` and ZIP SHA-256 `4222b2d94d0df030842f1191bb4743c0f3497300c83d0467827b55e62cc0b0cd`. The earlier [run review](r2_gpt5_e0_run_review.md) records independent receipt/source checks.

This is the locked CTU S5/S7 **dev** snapshot: 243,906 normalized flows, logical snapshot SHA-256 `42c8e0a62441295cc5d95329a65dc22409c37de5b26a1e37dd56fbf0164a758c`, split SHA-256 `96362f80e9e6bf01f18f1023c75066c553ddd9c105d2545f98af808d24f736fb`. Source SHA-256 values are S5 `ef5c9ed6895d4ca5aec723449dae30054ccd1f6b091713a52ffcb681ff78a02c` and S7 `df0b5338190b967bd340a0d6c1bb3c34d1bbfb4b7ffa764c2dd26f77f1a26680`. Prompt SHA-256 `ceefaab0bb4cbf69d4cb4cd3fad91297f7f5b823f13d2f22d11c976a5bb50115`, schema context SHA-256 `3dfc6d713fcedff0523f1bfd6707a5a6332260380057433f8916387f1687dc71`, model-config SHA-256 `682254f85e2b6ca181d452643091eded385050edca13653e0d60c041c1814f58`. Builder/scorer hashes are in the original report and match the locked dev contract.

All eight actual models were `gpt-5-mini-2025-08-07`. There were eight model calls, zero DB-tool calls, eight usage records, zero provider errors, zero safety rejections, and no retries. Syntax Validity and Execution Success were each **8/8**; **Execution Accuracy was 0/8**. Every deterministic scorer label was `RESULT_MISMATCH`. Usage was **845 input / 1,818 output tokens**, costing **USD 0.00384725** from usage, below the **USD 0.02540325** preflight ceiling. Mean model latency was **3,128.61 ms**.

## Per-case matrix

The result comparison was replayed offline against the verified snapshot. `Gold → SQL` shows scalar values or row counts. SQL column shows the decisive clauses of the saved prediction; the full exact generated SQL, gold, validator outcome, response ID, and model identity are in the linked report and locked case files. Cost is USD; latency is rounded milliseconds. Every case had one model call, zero DB-tool calls, valid syntax, execution success, and no provider error.

| Case | Dev category | Saved SQL decision | Gold → SQL | Primary cause | Input/output | Cost | Latency |
| --- | --- | --- | --- | --- | ---: | ---: | ---: |
| 001 | network | `source_dataset='scenario 5' AND label='From-Botnet'` | 901 → 0 | `VALUE_GROUNDING` | 103/168 | .00036175 | 3379 |
| 002 | network | `source_dataset='scenario 7' AND label='Normal'` | 1,677 → 0 | `VALUE_GROUNDING` | 100/165 | .000355 | 2606 |
| 003 | network | `COUNT(DISTINCT dst_ip)` but scenario variants filtered through `label` | 15,038 → 0 | `SCHEMA_SELECTION` | 101/264 | .00055325 | 3542 |
| 004 | time_range | Correct microsecond bounds, but `label='scenario 5'` | 1 → 0 | `SCHEMA_SELECTION` | 129/268 | .00056825 | 2963 |
| 005 | network | Correct UDP/positive bytes; `lower(label) LIKE '%7%'` | 89,247 → 0 | `SCHEMA_SELECTION` | 100/303 | .000631 | 3142 |
| 006 | ordering_limit | `label='scenario 5'`; extra non-null filter; missing port tie-break | 5 → 0 rows | `SCHEMA_SELECTION` | 101/182 | .00038925 | 2204 |
| 007 | aggregation | `label='Botnet'`; no S7 `source_dataset` filter | 2 → 0 rows | `VALUE_GROUNDING` | 113/162 | .00035225 | 2678 |
| 008 | aggregation | Grouped by `source_dataset, label` and selected extra byte sums | 2 → 129 rows | `AGGREGATION` | 98/306 | .0006365 | 4514 |

The table reconciles to 845 input tokens, 1,818 output tokens, USD 0.00384725, and eight `RESULT_MISMATCH` labels. Primary causes: `VALUE_GROUNDING` 3, `SCHEMA_SELECTION` 4, `AGGREGATION` 1. By locked dev category: network 0/4, time_range 0/1, ordering_limit 0/1, aggregation 0/2.

Stored `source_dataset` values are `ctu13_s5` and `ctu13_s7`, rather than the natural-language strings `scenario 5` and `scenario 7`. Botnet and Normal occur within longer flow labels, e.g. `flow=From-Botnet-V46-TCP-Attempt`; equality to `Botnet`, `Normal`, or `From-Botnet` is not supported by the stored values. Cases 003–006 choose `label` where the question requires source selection; case 008 changes the grouping grain. The correct DISTINCT and time boundaries in cases 003–004 do not compensate for the wrong source predicate. None of these diagnoses changes a question, gold SQL, comparator, scorer, or saved model SQL.

The historical GPT-4.1 Mini CTU baseline also scored 0/8 on this CTU dev split, under a different model contract. Historical DualSQL public-dev v4 reported 5/8 on a **different split and snapshot** and is not a direct control. E0 reuse for the final DualSQL series still requires exact prompt/schema/model/snapshot/split/scorer identity verification before E1–E3; E0 will not be rerun because of this score.
