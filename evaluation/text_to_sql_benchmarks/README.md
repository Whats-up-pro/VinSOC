# Text-to-SQL Benchmarks

R2 evaluates model-generated DuckDB SQL against the same frozen, read-only VinSOC snapshot used by the gold SQL.

- `dev/`: visible development cases used for debugging and controlled improvements.
- `frozen/`: holdout cases reserved for final evaluation.
- Headline metric: execution accuracy.
- Diagnostics: syntax validity, execution success, safety rejection, and error category.
- Ordered top-k/timeline tasks use `ordered_rows`; set-like queries use `unordered_rows`.
- The canonical snapshot path in cases is `data/snapshots/vinsoc_public_v1.duckdb`.

The repository intentionally does not fabricate a frozen benchmark database. Build the snapshot from approved public datasets with provenance as documented in `docs/duckdb_data_layer.md` before running an official score.
