# DuckDB Data Layer

## Purpose

VinSOC uses DuckDB as a local, read-only database for the public-data benchmark. The agent calls a domain tool. It does not receive database access or raw SQL access.

```text
LLM orchestrator
  -> network_investigation / endpoint_investigation
  -> domain query layer
  -> read-only DuckDB snapshot
  -> normalized evidence
```

This is Option A from the approved evaluation plan.

## Frozen snapshot rules

- The repository does not include a benchmark database or download data automatically.
- A snapshot is built from public sources, then its file hash and source details are recorded in `dataset_provenance`.
- The benchmark uses that same snapshot for gold SQL and model SQL.
- No synthetic, mutated, or training rows may enter the frozen benchmark.
- A test fixture is allowed only inside automated tests and is not benchmark data.

Approved source families are ThreatFox for CTI, CTU-13 and CICIDS2017 for network telemetry, and public Sysmon event logs for endpoint telemetry. Sysmon itself defines the collector and event format; a public event-log corpus must be recorded in provenance before endpoint rows are loaded.

## Normalized tables

| Table | Use |
|---|---|
| `dataset_provenance` | Source URL, retrieval time, hash, licence note, schema version |
| `cti_indicators` | Frozen ThreatFox indicator records |
| `network_flows` | Normalized CTU-13 and CICIDS2017 flow records |
| `sysmon_process_events` | Normalized public Sysmon process events; Event ID 1 supports process-tree queries |

Each evidence row has `source_dataset` and `source_row_id`. This keeps output traceable to the input snapshot.

## Safety boundary

`DuckDBSnapshot` uses two controls:

1. It opens the database with DuckDB `read_only=True`.
2. It rejects every query except one `SELECT` or `WITH ... SELECT` statement before execution.

It rejects multiple statements and keywords such as `INSERT`, `UPDATE`, `DELETE`, `DROP`, `ALTER`, `ATTACH`, `COPY`, and `INSTALL`. Results have a fixed row limit.

## Text-to-SQL evaluation

`evaluation/text_to_sql.py` evaluates a model SQL string against a case that follows [`schemas/text_to_sql_case.json`](../schemas/text_to_sql_case.json).

For each case, it runs the predicted query and every accepted gold query against the same frozen snapshot. It reports syntax validity rate, execution success rate, execution accuracy, and safety rejection rate.

Execution accuracy means the returned values match an accepted gold result. It is the main correctness metric. The evaluator ignores SQL aliases where appropriate and supports unordered rows, ordered rows (for top-k/timeline tasks), multisets, scalar values, and Boolean results.

The model-generation runner exposes only schema context, never telemetry rows, and every generated query passes through the same `DuckDBSnapshot` parser/read-only boundary before execution.

```bash
# Development benchmark
python -m evaluation.text_to_sql evaluate \
  --snapshot data/snapshots/vinsoc_public_v1.duckdb \
  --manifest evaluation/text_to_sql_benchmarks/snapshot_manifest.json \
  --split dev \
  --provider openai --model <PINNED_MODEL> --temperature 0

# Final holdout; run only after the development configuration is frozen
python -m evaluation.text_to_sql evaluate \
  --snapshot data/snapshots/vinsoc_public_v1.duckdb \
  --manifest evaluation/text_to_sql_benchmarks/snapshot_manifest.json \
  --split frozen \
  --provider openai --model <PINNED_MODEL> --temperature 0
```

Benchmark case definitions live in `evaluation/text_to_sql_benchmarks/{dev,frozen}/`.

## Reproducible snapshot build

`scripts/build_vinsoc_public_snapshot.py` consumes local files only. It never downloads data, and it verifies every source checksum before creating a database. The accepted source formats are `threatfox_csv`, `ctu13_binetflow`, `sysmon_jsonl`, and `sysmon_zip_jsonl`.

Before ingestion, create `dataset_manifest.json` conforming to [`dataset_manifest.schema.json`](../evaluation/text_to_sql_benchmarks/dataset_manifest.schema.json). Every source entry must contain the exact source URL, UTC retrieval time, downloaded-file SHA-256, source-specific licence/usage note, stable dataset ID, local path, and format. Do not create an entry until every value is known; a placeholder hash is invalid.

The currently selected public inputs are:

| Domain | Exact public input | Usage basis | Build format |
|---|---|---|---|
| CTI | ThreatFox full CSV export from `https://threatfox.abuse.ch/export/` | ThreatFox terms shown on the export service; current downloads require an Auth-Key | `threatfox_csv` |
| Network | CTU-13 Scenario 3 `capture20110812.binetflow` from `https://mcfp.felk.cvut.cz/publicDatasets/CTU-Malware-Capture-Botnet-44/detailed-bidirectional-flow-labels/capture20110812.binetflow` | Malware Capture Facility permits use with project/author attribution | `ctu13_binetflow` |
| Endpoint | OTRF Security-Datasets APT29 Day 1 host archive `https://github.com/OTRF/Security-Datasets/blob/master/datasets/compound/apt29/day1/apt29_evals_day1_manual.zip` | Repository MIT License; record that licence and the exact archive hash | `sysmon_zip_jsonl` with the exact JSONL `archive_member` |

The endpoint adapters accept the OTRF/Elastic `winlog.event_id`, `winlog.computer_name`, and `winlog.event_data` layout. For the selected OTRF ZIP, record the downloaded ZIP as `path`, its exact SHA-256 as `file_sha256`, and the exact internal JSONL path as `archive_member`; the builder streams that member without extracting it. Its stable row IDs use `<archive_member>:line:<n>`. Direct JSONL sources use `archive_member: null`. Do not auto-discover an archive member, filter rows, or synthesize rows to make gold queries pass.

Build only after all three verified files and their provenance are available:

```bash
python scripts/build_vinsoc_public_snapshot.py \
  --dataset-manifest dataset_manifest.json \
  --snapshot data/snapshots/vinsoc_public_v1.duckdb \
  --snapshot-manifest evaluation/text_to_sql_benchmarks/snapshot_manifest.json

python -c 'from pathlib import Path; from evaluation.text_to_sql_snapshot import load_snapshot_manifest, verify_snapshot; p=Path("data/snapshots/vinsoc_public_v1.duckdb"); verify_snapshot(p, load_snapshot_manifest(Path("evaluation/text_to_sql_benchmarks/snapshot_manifest.json")))'
```

The builder registers provenance before rows, requires every benchmark table to be non-empty, checks source identity columns, executes every development gold query, reopens through the read-only boundary, and writes the exact snapshot SHA-256. It refuses to overwrite an existing snapshot or manifest. Raw downloads and the DuckDB file are ignored by Git; only reproducibility code and manifests with real hashes belong in version control.

## Current official-snapshot blocker

As of 2026-09-24, an Auth-Key has been supplied privately, but direct HTTPS requests to ThreatFox time out in this runtime; CTU-13 and GitHub downloads also time out. Never write the Auth-Key into a committed manifest, a public URL, or command history. No official `dataset_manifest.json`, DuckDB snapshot, or `snapshot_manifest.json` has been generated or committed. Existing `data/threatfox_samples.json` is not an acceptable substitute because it does not establish the required source-file provenance. R2 official model runs remain blocked until the exact public sources can be downloaded and all three source hashes recorded.
