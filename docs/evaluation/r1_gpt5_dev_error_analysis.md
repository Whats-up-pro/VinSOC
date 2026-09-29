# R1 GPT-5 Mini dev v2 error analysis

## Evidence and comparison contract

The single model-only [Actions run 36531679435](https://github.com/Whats-up-pro/VinSOC/actions/runs/36531679435) evaluated all 24 locked `r1_a1_dev_v2` cases on evaluator SHA `eec657fe29e8c06844f72952eb0cb14f519a7530`, after [CI 36531561628](https://github.com/Whats-up-pro/VinSOC/actions/runs/36531561628) passed on Python 3.11 and 3.12. The [unaltered Actions report](../../results/evaluation_v1/r1/gpt5_model_only/36531679435/r1-gpt5-result.json) has SHA-256 `aa653f3950a0c886faa5b4945c048fe8aad45fb96a90879b9584f9ef4e7f6178`; [preflight and artifact receipt](../../results/evaluation_v1/r1/gpt5_model_only/36531679435/receipt.json) give artifact ID `11016344827` and verified ZIP SHA-256 `897bbb1bfdd5e1e5e344c52790cdcc53f5218fcd5af674b0fc5ff44ae2891541`.

Split SHA-256 is `d8e68968a390a09d502a3da01319611f546a6d0189a30e0fe0c316550d0aa259`; scorer SHA-256 is `271aa8ba8b65548f1d17648945ac62cc18b2370fa85c4aa210c155c9154b9149`; prompt SHA-256 is `21f87b197c1bf1206d4a36e111853bddf6ea623bab58a5da311ccbcb61d7780b`; production schema SHA-256 is `aa214e730b1e3eb3ba03fdb08488dcfda4bc33b3c6d4c84700951f87e9c11ff0`. All 24 actual response models were `gpt-5-mini-2025-08-07`; all had usage, with no provider failure or retry. Requests used `reasoning_effort=low`, no temperature field, cap 1000, SDK retries 0. This suite scored native tool decisions only and executed no production tool.

Single-Turn Case Success was **19/24 (79.17%)**; Tool-Set Exact Match was **19/24**; Exact-Call Precision/Recall/F1 were **29/31 = 0.9355** each. Required Argument and Critical Argument Accuracy were both **1.0** on matched calls; No-Tool Accuracy was **4/5 (0.8)**; Forbidden-Tool Rate was **0**. Usage was **20,104 input / 5,462 output tokens** and usage-derived cost **USD 0.01595**. Mean latency was **2,693.66 ms**, p95 **6,933.33 ms**. There were 24 model calls and zero tool executions.

The historical GPT-4.1 Mini [dev v2 report](../../results/evaluation_v1/r1/r1_a1_dev_v2_852e543.json) scored **22/24**, Exact-Call F1 **0.9508**, No-Tool Accuracy **5/5**, and cost **USD 0.0101312**. It used `gpt-4.1-mini-2025-04-14`, temperature 0, cap 1000, retries 0. GPT-5 Mini required `reasoning_effort=low` and an absent temperature field. Prompt, production schema, split, and scorer hashes match; the model and request contract differ. The older 15/24 result used a different benchmark/schema and is not part of this comparison.

## Per-case matrix

`TP/FP/FN` counts exact calls. Predictions list model-selected tools in order; full native arguments, scorer matches, and per-case response metadata are in the linked report. Cost is USD; latency is rounded milliseconds. A blank primary cause means the case succeeded.

| Case | Category | Pass | Predicted tools | TP/FP/FN | Primary cause | Input/output | Cost | Latency |
| --- | --- | --- | --- | --- | --- | ---: | ---: | ---: |
| 001 | network_only | yes | network | 1/0/0 | — | 850/42 | .0002965 | 2678 |
| 002 | cti_only | no | network, CTI | 1/1/0 | `EXTRA_TOOL` | 834/150 | .0005085 | 2506 |
| 003 | endpoint_only | yes | endpoint | 1/0/0 | — | 846/95 | .0004015 | 2751 |
| 004 | cti_only | yes | CTI | 1/0/0 | — | 839/32 | .00027375 | 1955 |
| 005 | cti_network_endpoint | no | network, endpoint | 2/0/1 | `MISSING_TOOL` | 844/205 | .000621 | 2645 |
| 006 | cti_only | yes | CTI | 1/0/0 | — | 839/36 | .00028175 | 1349 |
| 007 | cti_endpoint | yes | CTI, endpoint | 2/0/0 | — | 843/141 | .00049275 | 2223 |
| 008 | cti_network_endpoint | yes | network, endpoint, CTI | 3/0/0 | — | 847/363 | .00093775 | 4253 |
| 009 | network_only | no | network, endpoint | 1/1/0 | `EXTRA_TOOL` | 833/213 | .00063425 | 1997 |
| 010 | network_endpoint | yes | network, endpoint | 2/0/0 | — | 838/144 | .0004975 | 1752 |
| 011 | network_only | yes | network | 1/0/0 | — | 833/106 | .00042025 | 1489 |
| 012 | hostname_led | yes | endpoint | 1/0/0 | — | 833/31 | .00027025 | 841 |
| 013 | hostname_led | yes | endpoint | 1/0/0 | — | 832/31 | .00027 | 1161 |
| 014 | hostname_led | yes | endpoint | 1/0/0 | — | 837/31 | .00027125 | 1098 |
| 015 | cti_network_endpoint | yes | CTI, network, endpoint | 3/0/0 | — | 847/239 | .00068975 | 2142 |
| 016 | hash_led | yes | CTI, endpoint | 2/0/0 | — | 873/174 | .00056625 | 2118 |
| 017 | cti_endpoint | yes | CTI, endpoint | 2/0/0 | — | 845/143 | .00049725 | 1621 |
| 018 | network_endpoint | yes | network, endpoint | 2/0/0 | — | 840/333 | .000876 | 2682 |
| 019 | no_tool | no | none; response truncated | 0/0/0 | `EXECUTION_ERROR` | 871/1000 | .00221775 | 9322 |
| 020 | cti_network | no | network | 1/0/1 | `MISSING_TOOL` | 833/42 | .00029225 | 1224 |
| 021 | no_tool | yes | none | 0/0/0 | — | 811/863 | .00192875 | 6933 |
| 022 | no_tool | yes | none | 0/0/0 | — | 822/469 | .0011435 | 4522 |
| 023 | no_tool | yes | none | 0/0/0 | — | 815/547 | .00129775 | 4508 |
| 024 | no_tool | yes | none | 0/0/0 | — | 799/32 | .00026375 | 875 |

The table reconciles to **29 TP, 2 FP, 2 FN**, five failed cases, 20,104 input and 5,462 output tokens, and USD 0.01595. Category success is: network_only 2/3; cti_only 2/3; endpoint_only 1/1; cti_network_endpoint 2/3; cti_endpoint 2/2; network_endpoint 2/2; hostname_led 3/3; hash_led 1/1; no_tool 4/5; cti_network 0/1.

## Failure diagnosis

| Case | Gold versus model evidence | Deterministic error flag | Primary cause |
| --- | --- | --- | --- |
| 002 | Gold calls only `cti_enrichment(203.0.113.50)`; model also called `network_investigation` on that indicator. This is the same case the GPT-4.1 Mini baseline missed. | none; FP 1 | `EXTRA_TOOL` |
| 005 | Gold requires CTI, network, and endpoint pivots; model correctly called network and endpoint but omitted `cti_enrichment(185.220.101.45)`. | none; FN 1 | `MISSING_TOOL` |
| 009 | Gold requires network only for private scanning source `10.0.0.25`; model also called `endpoint_investigation(host=10.0.0.25)` without a hostname or endpoint objective. | none; FP 1 | `EXTRA_TOOL` |
| 019 | Gold requires no call. The model emitted no native tool call, but the response stopped at `finish_reason=length` and consumed the full 1000 output-token cap. The runner correctly rejected the incomplete response as successful abstention. It was charged; usage and raw response metadata were retained. | `INVALID_TOOL_CALL` | `EXECUTION_ERROR` (response truncation) |
| 020 | Gold requires CTI and network for conflicting reputation/traffic evidence; model called only network and omitted `cti_enrichment(203.0.113.25)`. | none; FN 1 | `MISSING_TOOL` |

`case_015`, the other historical GPT-4.1 Mini failure, succeeded here with all three required tools and exact arguments. Primary causes are `EXTRA_TOOL` 2, `MISSING_TOOL` 2, and `EXECUTION_ERROR` 1. The extra and missing-tool groups pull in different directions. A generic over-investigation change is a candidate only for the two extra-call cases; its value must be judged against the two missing-CTI cases and the already stronger 22/24 baseline at Task 9. No case-specific rule, gold edit, scorer edit, or rerun is justified by this result.
