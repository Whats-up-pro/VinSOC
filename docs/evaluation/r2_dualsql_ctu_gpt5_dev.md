# CTU S5/S7 GPT-5 Mini DualSQL-Lite development comparison

## Contract and decision

This comparison reused the locked eight-case CTU S5/S7 development suite and the immutable E0 run [36520685612](https://github.com/Whats-up-pro/VinSOC/actions/runs/36520685612). E1, E2, and E3 each ran once through the manual GitHub Actions workflow on implementation SHA `ff12a3e32781b452ae266251b7997cc28b76c80f`. Python 3.11 and 3.12 CI passed on that exact SHA in [run 36661248341](https://github.com/Whats-up-pro/VinSOC/actions/runs/36661248341). No benchmark question, gold SQL, scorer, or source snapshot was changed for these runs.

The deterministic [selection lock](../../evaluation/dualsql_lite_ctu_gpt5/SELECTED_CONFIG.lock) chooses **E0**. All four conditions scored **0/8 Execution Accuracy**; E0 had the lowest usage-derived cost. There is no improvement signal and no claim of statistical significance. The older GPT-4.1 Mini public-development series used a different model and snapshot and is not a direct comparator.

The development logical snapshot SHA-256 was `42c8e0a62441295cc5d95329a65dc22409c37de5b26a1e37dd56fbf0164a758c`, with 243,906 normalized flows. The split SHA-256 was `96362f80e9e6bf01f18f1023c75066c553ddd9c105d2545f98af808d24f736fb`. Source SHA-256 values were S5 `ef5c9ed6895d4ca5aec723449dae30054ccd1f6b091713a52ffcb681ff78a02c` and S7 `df0b5338190b967bd340a0d6c1bb3c34d1bbfb4b7ffa764c2dd26f77f1a26680`. The scorer and builder hashes are in [SERIES.lock](../../evaluation/dualsql_lite_ctu_gpt5/SERIES.lock) and the selection lock.

## Results

All calls used `gpt-5-mini-2025-08-07`, `reasoning_effort=low`, `max_completion_tokens=1000`, no `temperature` request parameter, and SDK retries `0`. Cost uses the [official standard GPT-5 Mini rates](https://developers.openai.com/api/docs/pricing) of $0.25 per million input tokens and $2.00 per million output tokens. Latency is the sum of provider call latencies, not the workflow wall time.

| Condition | Execution Accuracy | Syntax Valid | Execution Success | Safety Rejections | Linker complete | Model calls | DB tool calls | Input / output tokens | Cost USD | Call latency ms |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| E0 one-shot | 0/8 | 8/8 | 8/8 | 0 | n/a | 8 | 0 | 845 / 1,818 | 0.00384725 | 25,028.858 |
| E1 linker + one-shot generator | 0/8 | 8/8 | 7/8 | 1 | 8/8 | 26 | 12 | 11,155 / 4,330 | 0.01144875 | 57,255.037 |
| E2 agentic generator | 0/8 | 7/8 | 6/8 | 1 | n/a | 19 | 12 | 8,542 / 2,041 | 0.00621750 | 36,996.676 |
| E3 linker + agentic generator | 0/8 | 8/8 | 7/8 | 1 | 8/8 | 34 | 19 | 15,338 / 4,588 | 0.01301050 | 69,453.219 |

Tie-break order was higher Execution Accuracy, lower calculated cost, fewer model calls, lower latency, then simpler E0/E1/E2/E3. The resulting ranking was **E0, E2, E1, E3**. Each case represents 12.5 percentage points, so the predeclared two-case threshold for a strong pilot signal was not met.

## Case-level errors

| Case | E0 | E1 | E2 | E3 | Observed semantic issue |
| --- | --- | --- | --- | --- | --- |
| `ctu_sql_001` | Result mismatch | Result mismatch | Result mismatch | Result mismatch | Scenario 5 was written as an invented `source_dataset` value; the label filter used exact equality instead of the locked From-Botnet pattern. |
| `ctu_sql_002` | Result mismatch | Result mismatch | Turn limit | Result mismatch | Scenario 7 was not mapped to `ctu13_s7`; E1 filtered a single row ID, while E2 exhausted its bounded turns without final SQL. |
| `ctu_sql_003` | Result mismatch | Result mismatch | Result mismatch | Result mismatch | Generated SQL searched `label` for “scenario 5” rather than filtering `source_dataset`. |
| `ctu_sql_004` | Result mismatch | Result mismatch | Result mismatch | Result mismatch | The microsecond bounds were retained, but the scenario filter used `label` instead of `source_dataset`. |
| `ctu_sql_005` | Result mismatch | Result mismatch | Result mismatch | Result mismatch | UDP and positive bytes predicates appeared, but the scenario 7 filter searched `label` instead of `source_dataset`. |
| `ctu_sql_006` | Result mismatch | Result mismatch | Result mismatch | Result mismatch | Top-five aggregation used `label` for scenario 5; some SQL also added a NULL exclusion or omitted the locked secondary ordering. |
| `ctu_sql_007` | Result mismatch | Result mismatch | Result mismatch | Result mismatch | All four omitted the S7 `source_dataset` filter and used exact `label = 'Botnet'` instead of the locked Botnet substring. |
| `ctu_sql_008` | Result mismatch | Safety rejection | Safety rejection | Safety rejection | All four added aggregates or grouping detail beyond the requested per-source flow count; the scorer recorded safety rejection for E1–E3. |

The recurring failure is incorrect grounding of scenario IDs and label values, even when the new conditions made DB tool calls. These are observations from the immutable SQL/tool traces, not a reason to edit questions, gold, scorer, or the completed runs. Full SQL, tool trajectories, per-case scores, response IDs, usage, and latency remain in the reports below.

## Evidence and cost accounting

| Condition | Actions run | Artifact ID | Artifact digest | Report SHA-256 | Preserved report and receipt |
| --- | --- | ---: | --- | --- | --- |
| E0 | [36520685612](https://github.com/Whats-up-pro/VinSOC/actions/runs/36520685612) | Historical | See historical receipt | `33b35678171309c1a8958c1d9818499915986942e6936a03428df8fa0544bc15` | [E0 report](../../results/evaluation_v1/ctu_network_public/gpt5_e0/36520685612/ctu-r2-result.json) |
| E1 | [36662231091](https://github.com/Whats-up-pro/VinSOC/actions/runs/36662231091) | 11074877219 | `sha256:ee79ad543a574136f892de81ca55191cbacd3fcba7c3a39fbd1d45a2b5613ac9` | `ae528538a4291f7a99f3618b6b94876c0fe510e0937b917cb134e4148656f622` | [E1 report](../../results/evaluation_v1/ctu_network_public/dualsql_lite_ctu_gpt5_v1/36662231091/E1.json), [receipt](../../results/evaluation_v1/ctu_network_public/dualsql_lite_ctu_gpt5_v1/36662231091/receipt.json) |
| E2 | [36662683274](https://github.com/Whats-up-pro/VinSOC/actions/runs/36662683274) | 11075027530 | `sha256:b687f31a454d72723eb5349324fd8e5587e700b7b03e63ce9a146e67c4a54bc3` | `6bdd3bb513877b2c9d8035e7c74f7ad4826b2cfd9ce631a3e23ced3e85cd57af` | [E2 report](../../results/evaluation_v1/ctu_network_public/dualsql_lite_ctu_gpt5_v1/36662683274/E2.json), [receipt](../../results/evaluation_v1/ctu_network_public/dualsql_lite_ctu_gpt5_v1/36662683274/receipt.json) |
| E3 | [36662943266](https://github.com/Whats-up-pro/VinSOC/actions/runs/36662943266) | 11075032927 | `sha256:5b32ac00e528262d6f0aa3fd52a4372499ffdbba71ceb79c5747a7703b147609` | `23e18c9d2d7a1899d1506d9ee722a50c26ac2e07a9b7bc7c5b66358f09ec73b4` | [E3 report](../../results/evaluation_v1/ctu_network_public/dualsql_lite_ctu_gpt5_v1/36662943266/E3.json), [receipt](../../results/evaluation_v1/ctu_network_public/dualsql_lite_ctu_gpt5_v1/36662943266/receipt.json) |

E1–E3 cost **$0.03067675** together. Adding immutable E0 (**$0.00384725**) and the completed R1 dev run (**$0.01595**) gives **$0.050474** known VinSOC spend against the user-approved $2 ceiling. The account credit over $3 was reported by the account owner during this run; the conservative $0.71 remaining spend-limit input was inferred from their authorization and was not independently read from the Billing console. No credit was purchased or limit changed. Frozen model calls and E2E demonstrations were not run in this comparison.
