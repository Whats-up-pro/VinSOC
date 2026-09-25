# R2 public_dev scorer v2: offline replay of the eight saved v1 predictions

The original [R2 model report](../results/evaluation_v1/public_pilot/public-r2.json), benchmark cases and [`VERSION.lock`](../evaluation/public_pilot/VERSION.lock) remain unchanged. Its exact JSON SHA-256 is `0bac8abd8523eb5fe7faaa90e1708fee779ba217acead125b71fb90d4c72f636`. The [diagnostic replay JSON](../results/evaluation_v1/public_pilot/r2-replay-scorer-v2.json) records the original evaluator SHA, original and new scorer SHA, eight generated SQL strings, both verdicts per case, source/split hashes and snapshot content hash. **This is not another model run**: zero API calls and $0 additional model cost.

Scorer version `r2_public_dev_replay_scorer_v2_terminal_semicolon` accepts exactly one terminal SQL semicolon, removes it before the bounded subquery wrapper, and continues to reject multiple statements or write keywords. Tests include semicolons inside quoted literals and comments, as well as multi-statement and write attempts. Original report scorer SHA `e116736b2ccf86a5cf28724e7fad2eace604edbc654e33a3c2bd5818bcbf03ca`; replay scorer SHA `c4430c5ec390b2909b6677b7872296569fd917ae1d230dc451300dd9e064605d`. The original source file SHA-256s, case split SHA-256 `fb09a35be56c20f01add8363d1c42a43a14c105483b89fbb48ae8b680d2afdbf` and ordered snapshot content SHA-256 `8dc07dd60d9222776ff3438bedd8488582e95f53d7b8052bbd510adad73cc42e` were checked before replay; gold SQL results matched the original run.

| Metric | V1 model run / scorer v1 | Same saved predictions / scorer v2 |
| --- | ---: | ---: |
| Execution accuracy | 2/8 (25%) | 5/8 (62.5%) |
| Syntax validity | 8/8 | 8/8 |
| Execution success | 3/8 | 8/8 |
| Safety rejection | 5/8 | 0/8 |

| Saved SQL ID | V1 verdict | Replay v2 verdict | Interpretation |
| --- | --- | --- | --- |
| `public_sql_001` | result mismatch | result mismatch | Wrong source identifier/label. |
| `public_sql_002` | safety rejection | result mismatch | Removing the terminal semicolon exposes a distinct-result error. |
| `public_sql_003` | safety rejection | execution match | Omits `source_dataset = 'ctu13_s5'`; a cross-scenario fixture makes it disagree with gold. |
| `public_sql_004` | safety rejection | result mismatch | Removing the terminal semicolon exposes a result error. |
| `public_sql_005` | execution match | execution match | Unchanged. |
| `public_sql_006` | execution match | execution match | Unchanged. |
| `public_sql_007` | safety rejection | execution match | Equal results on this snapshot only. |
| `public_sql_008` | safety rejection | execution match | Uses case-sensitive `LIKE` instead of gold `ILIKE`; a mixed-case Sysmon fixture makes it disagree. |

In particular, **5/8 is execution agreement on one snapshot, not proof of semantic correctness**. Tests in `tests/test_text_to_sql_runner.py` preserve concrete counterexamples for `003` and `008`. The revised policy does not change the original v1 2/8 result, prompt, benchmark version or frozen data. A semantic catalog and a new R1/R2 benchmark require a separately versioned task before another model run.

Offline reproduction on a machine with the manifest source files and installed dependencies:

```bash
python -m scripts.replay_r2_public_pilot --snapshot data/public_pilot/snapshot.duckdb --out results/evaluation_v1/public_pilot/r2-replay-scorer-v2.json
```
