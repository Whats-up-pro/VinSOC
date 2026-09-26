# DualSQL-Lite public-dev v4 result

## Decision

The locked public-dev winner is **E0 one-shot**, with **5/8 correct (62.5% Execution Accuracy)**.
E2 also reached 5/8, but E0 wins the predeclared tie-break because it used less cost and fewer model calls.
The DualSQL-Lite variants did not produce the required strong pilot signal of at least +2 correct cases over the newly generated E0 baseline.

This is a diagnostic `public_dev` result. It is not official-dev or frozen evidence.

## Fixed experiment contract

- Run: `dualsql-lite-36122033957-1`
- Evidence commit: `7fd111124777645a8490b4d90de6554f2f567f7d`
- GitHub Actions run: <https://github.com/Whats-up-pro/VinSOC/actions/runs/36122033957>
- Model: `gpt-4.1-mini-2025-04-14`
- Provider: OpenAI
- Temperature: `0`
- Completion cap: `1000`
- Automatic retries: `0`
- Cases: 8 distinct `public_dev` cases
- Headline metric: Execution Accuracy
- Conservative series preflight ceiling: `$1.9797192 < $2.00`
- Actual calculated usage cost for E0-E3: `$0.0229036`
- Artifact ZIP SHA-256: `5347878234ad2343c068bb648706904d00bd8adb3a04b172555cca78dde44070`
- All four experiment reports are `completed`, `eligible=true`, and `official_eligible=false`.

The snapshot contains 243,906 CTU-13 network flows and 143,884 OTRF Sysmon events. Its logical-content SHA-256 is `8dc07dd60d9222776ff3438bedd8488582e95f53d7b8052bbd510adad73cc42e` and its run-specific binary SHA-256 is `18a7bfbf21c74714b699c0bad130bf23b1d66f1e50f3fc4f446c8d5e58aef6d5`.

## Architecture matrix

| ID | Schema Linker | Generator database tools | Generator mode |
| --- | --- | --- | --- |
| E0 | No | No | One-shot baseline |
| E1 | Yes | No | One-shot from validated linked schema |
| E2 | No | Yes | Bounded agentic generation |
| E3 | Yes | Yes | Bounded DualSQL-Lite |

Schema Linker and SQL Generator use the same pinned model and provider configuration. Database tools are the bounded, read-only `Database Profiler`, `Value Search`, and `SQL Probe` capabilities. Gold SQL is exposed only to the scorer after final SQL generation.

## Headline and diagnostic metrics

| Experiment | Correct | Execution Accuracy | Syntax Validity | Execution Success | Safety Rejection | Model calls | DB tool calls | Input / output tokens | Cost USD | Latency ms | Avg turns |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| E0 | 5/8 | 62.5% | 100% | 100% | 0% | 8 | 0 | 1,538 / 473 | 0.0013720 | 10,452.685 | 1.000 |
| E1 | 1/8 | 12.5% | 25% | 25% | 0% | 26 | 17 | 20,682 / 946 | 0.0097864 | 23,314.400 | 3.250 |
| E2 | 5/8 | 62.5% | 100% | 100% | 0% | 14 | 6 | 6,815 / 549 | 0.0036044 | 12,966.520 | 1.750 |
| E3 | 1/8 | 12.5% | 12.5% | 12.5% | 0% | 23 | 13 | 15,992 / 1,090 | 0.0081408 | 20,008.098 | 2.875 |

## Per-case result

| Case | E0 | E1 | E2 | E3 |
| --- | --- | --- | --- | --- |
| `public_sql_001` | Result mismatch | Result mismatch | Result mismatch | Syntax error |
| `public_sql_002` | Result mismatch | Linker failure | Result mismatch | Linker failure |
| `public_sql_003` | Correct | Correct | Result mismatch | Correct |
| `public_sql_004` | Result mismatch | Linker failure | Correct | Linker failure |
| `public_sql_005` | Correct | Linker failure | Correct | Linker failure |
| `public_sql_006` | Correct | Linker failure | Correct | Linker failure |
| `public_sql_007` | Correct | Linker failure | Correct | Linker failure |
| `public_sql_008` | Correct | Linker failure | Correct | Linker failure |

## Error analysis

E0 failed cases `001`, `002`, and `004` because it guessed stored literals rather than the snapshot representation. It used variants such as `scenario5`, `CTU-13`, or `From-Botnet`, while the snapshot uses dataset IDs such as `ctu13_s5`/`ctu13_s7` and labels prefixed with `flow=From-Botnet...`.

E2 fixed case `004` by using Value Search, but it lost case `003` by adding an incorrect label predicate. Its net result therefore remained 5/8. E2 cost about 2.63 times E0 and used 14 rather than 8 model calls.

E1 and E3 were dominated by Schema Linker format/limit failures. In v4, only 2/8 linked-schema submissions completed validation in each linker condition. The strict validator correctly rejected invented or untraceable values, but the current linker behavior is not reliable enough to justify official use. E3 additionally duplicated a SELECT in case `001`, producing a syntax error.

No unsafe SQL was accepted. Safety Rejection is 0% because the submitted final SQL was read-only; the failures were accuracy, syntax, or linker failures.

## Selection and lock

The predeclared rule is:

1. highest Execution Accuracy;
2. lower total API cost;
3. fewer model calls;
4. lower latency;
5. simpler architecture in E0, E1, E2, E3 order.

E0 and E2 tie at 5/8. E0 is selected at `$0.0013720` and 8 calls versus E2 at `$0.0036044` and 14 calls. The exact selected configuration, hashes, artifact identities, and tie-break inputs are frozen in `evaluation/dualsql_lite/SELECTED_CONFIG.lock`.

## Historical results are separate

- Original public-pilot model run under scorer v1: 2/8.
- Offline replay of those saved SQL strings under scorer v2: 5/8.
- Newly generated DualSQL-Lite v4 E0 under the current contract: 5/8.

The 2/8 to 5/8 replay is a scorer effect, not a model improvement. The new E0 result is a fresh provider run and is the only baseline used for the v4 architecture comparison.

## Progression gates and limitations

- Public-dev has only 8 cases and was used repeatedly for architecture diagnosis. Its result is not statistical proof and must not be presented as general Text-to-SQL accuracy.
- The winning configuration is E0, so the public pilot does not support claiming that DualSQL-Lite improves accuracy.
- Official-dev remains blocked until a verified three-source ThreatFox + CTU-13 + OTRF snapshot and its official benchmark split are available. The current public snapshot has CTU-13 and OTRF only.
- Frozen remains sealed. It must not be opened before official-dev is complete and the final configuration is reviewed.
- The workflow is manual-only after this evidence run. Re-running it requires an explicit `workflow_dispatch` action and creates a new immutable artifact directory.
