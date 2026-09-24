# R1 A1 `dev v2` — one real-model run and case review

This report is a **single dev run** of `gpt-4.1-mini-2025-04-14` on benchmark `r1_a1_dev_v2`; it is not a frozen holdout result or an end-to-end VinSOC assessment. The [original 15/24 baseline](https://github.com/Whats-up-pro/VinSOC/actions/runs/35972408012) at `1fd3843` remains unmodified on its original benchmark and schema. Gold and the network tool contract changed between versions, so the scores do not measure a model improvement on a fixed task.

## Run verification

| Field | Value |
|---|---|
| Git commit of evaluator/run | `852e543b971b6d0c565fbab5f885178c17f8b8eb` |
| Workflow / CI | [dev v2 run](https://github.com/Whats-up-pro/VinSOC/actions/runs/35975551401); [CI on same SHA](https://github.com/Whats-up-pro/VinSOC/actions/runs/35975551218) |
| Benchmark version / split SHA-256 | `r1_a1_dev_v2` / `d8e68968a390a09d502a3da01319611f546a6d0189a30e0fe0c316550d0aa259` |
| Scorer SHA-256 | `271aa8ba8b65548f1d17648945ac62cc18b2370fa85c4aa210c155c9154b9149` |
| Provider / actual model | `openai` / `gpt-4.1-mini-2025-04-14` on every call |
| Temperature / completion cap / retries | `0` / `1000` / `0` |
| Requests / distinct case IDs | `24` / `24` (all dev files) |
| Preflight worst-case cost / task budget | `$0.1208448` / `$1.00` |
| Input / output tokens, usage-derived cost | `18,088` / `1,810`, `$0.0101312` |
| Run status / official eligibility | `completed` / `true`, `ineligible_reasons=[]` |
| Provider / execution error rate | `0.0` / `0.0` |

The [JSON artifact](../results/evaluation_v1/r1/r1_a1_dev_v2_852e543.json) preserves the exact prompt, production schema, split hashes, per-case match traces, provider telemetry and cost. The GitHub Actions [ZIP artifact](https://github.com/Whats-up-pro/VinSOC/actions/runs/35975551401) has SHA-256 `a7c9e6a0c84ba5d7f2e82199c0c2c034f01ec5cf20204c8173cfb96661612e75`; the earlier ZIP has SHA-256 `af837f1aa20b56385846ca5ddddf8ddfcc453c4d65fbcec08471d6921a864d2b`. The report used the separately calculated usage cost; provider estimated cost is incomplete.

## Scores on the new benchmark

- Exact successful cases: **22/24** (trajectory success rate `0.9167`).
- Exact-call precision `0.9667`, recall `0.9355`, F1 `0.9508`; no-tool accuracy `1.0` (5 cases).
- Failures: `case_002` chose `network_investigation` instead of the required CTI lookup; `case_015` used network and endpoint but omitted required CTI. No provider errors.

By difficulty: basic 14/15; intermediate 6/6; advanced 2/3. No-tool: 5/5; cases with a required tool: 17/19. Category successes: `cti_only` 2/3 and `cti_network_endpoint` 2/3; every other category passed all its cases.

## Review of all 24 cases

A gold change is benchmark adjudication, not a corrected score for the original run. Predictions are listed in request order. `N` means `network_investigation`, `C` means `cti_enrichment`, `E` means `endpoint_investigation`, and `∅` means no call. `pass` means exact trajectory success; `fail` includes a missing or extra call.

| Case | Gold v1 → v2 | Prediction v1 → v2 | Score v1 → v2 | Review |
|---|---|---|---|---|
| `001` | C → N | N → N | fail → pass | Reworded DNS-query volume as flow volume; N is now the supported required tool. |
| `002` | C → C | C → N | pass → fail | Gold unchanged; new N substitutes for required C. Vendor-reputation question needs CTI; no model fix inferred. |
| `003` | C+E → E | N+E → E | fail → pass | Local DLP needs E; no private-IP CTI and N would remain extra. New prediction E only. |
| `004` | C+N → C | C → C | fail → pass | Domain reputation C only; flow-only N cannot resolve a domain. |
| `005` | C+N+E → C+N+E | C+N+E → C+N+E | pass → pass | Unchanged; CTI, IPv4 flow and endpoint remain justified. |
| `006` | C+N → C | C → C | fail → pass | Email-domain reputation C only; no resolved IP or observed IP flow. |
| `007` | C+N+E → C+E | C+N+E → C+E | pass → pass | Domain CTI and host endpoint; domain N removed from gold and prediction. |
| `008` | C+N+E → C+N+E | C+N+E → C+N+E | pass → pass | Unchanged; explicit CTI, IPv4 traffic and host. |
| `009` | C+N → N | N → N | fail → pass | Internal scan calls for IP flow N; private-IP CTI not requested. |
| `010` | C+N+E → N+E | N+E → N+E | fail → pass | Internal lateral movement calls for N+E; no private-IP CTI objective. |
| `011` | C+N → N | N → N | fail → pass | Internal-source transfer calls for N; no private-IP CTI objective. |
| `012` | E → E | E → E | pass → pass | Unchanged; endpoint process investigation. |
| `013` | E → E | E → E | pass → pass | Unchanged; endpoint process investigation. |
| `014` | E → E | E → E | pass → pass | Unchanged; endpoint host pivot. |
| `015` | C+N+E → C+N+E | N+E+C → N+E | pass → fail | Gold unchanged; new prediction omits required C, so a genuine failure on v2. Same pinned model; schema/run changed. |
| `016` | C+E → C+E | C+E → C+E | pass → pass | Unchanged; hash CTI and host endpoint. |
| `017` | C+N+E → C+E | C+N+E → C+E | pass → pass | Domain CTI and host endpoint; no IPv4 network pivot. |
| `018` | C+N+E → N+E | N+E → N+E | fail → pass | Internal flow and host endpoint; no private-IP CTI objective. |
| `019` | C → ∅ | N → ∅ | fail → pass | Evidence gap explicitly asks for abstention; no-tool with C/N/E forbidden. |
| `020` | C+N → C+N | C+N → C+N | pass → pass | Unchanged; explicit CTI comparison with IPv4 flow. |
| `021` | ∅ → ∅ | ∅ → ∅ | pass → pass | Unchanged; conceptual no-tool. |
| `022` | ∅ → ∅ | ∅ → ∅ | pass → pass | Unchanged; capability no-tool, current IPv4 flow contract. |
| `023` | ∅ → ∅ | ∅ → ∅ | pass → pass | Unchanged; explicit abstention. |
| `024` | ∅ → ∅ | ∅ → ∅ | pass → pass | Unchanged; general-knowledge no-tool. |

## Limitations and next gate

This is one paid dev run. Temperature zero does not establish repeatability across server/runtime changes. The 15/24 and 22/24 values use different gold, requests and production schema, so their difference is not an improvement delta. `case_002` and `case_015` warrant error analysis on v2 without editing the holdout. The current public frozen set remains unopened and must only be run after independently checking contract compatibility and freezing the next evaluation configuration. R2 remains blocked pending validated source files and snapshot provenance.
