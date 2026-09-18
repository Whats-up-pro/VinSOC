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

Execution accuracy means the returned values match an accepted gold result. It is the main correctness metric. The evaluator ignores SQL aliases, supports unordered or multiset rows, and supports scalar and Boolean results.

## Build a snapshot

Create an empty schema first. Do not register or insert rows until the exact public file, its checksum, retrieval time, and licence note are known.

```python
from vinsoc_data.duckdb_store import SocSnapshotBuilder

builder = SocSnapshotBuilder("data/snapshots/vinsoc_public_v1.duckdb")
builder.create_empty_snapshot()
builder.register_provenance(
    dataset_id="ctu13-scenario-name",
    source_name="CTU-13",
    source_url="https://mcfp.felk.cvut.cz/publicDatasets/CTU-13-Dataset/",
    retrieved_at="2026-09-18T00:00:00Z",
    file_sha256="<sha256-of-downloaded-file>",
    license_note="<licence or usage note from the source>",
)
```

The next data-preparation step is to map the chosen public files to these normalized tables. It must preserve `source_row_id` and register provenance first.
