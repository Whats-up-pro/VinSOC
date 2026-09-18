# VinSOC

VinSOC is a read-only, evidence-grounded SOC investigation project. It uses an LLM to select investigation tools, then returns structured evidence for a human analyst to review. It does not block traffic, change systems, or make autonomous incident decisions.

## Current scope

VinSOC works with three evidence types:

| Evidence type | Current source |
|---|---|
| External CTI | [ThreatFox](https://threatfox.abuse.ch/) |
| Network telemetry | [CTU-13](https://www.stratosphereips.org/datasets-ctu13/) and [CICIDS2017](https://www.unb.ca/cic/datasets/ids-2017.html) |
| Endpoint telemetry | Public Sysmon event logs, using [Microsoft Sysmon](https://learn.microsoft.com/en-us/sysinternals/downloads/sysmon) event definitions |

The project focuses on observed telemetry, derived analytics, CTI enrichment, evidence correlation, and assessment reports. It does not train ML/DL models, perform anomaly detection with ML, or run automated response.

For CTI, a valid lookup with an available source but no match returns `UNKNOWN`. A missing source, source execution error, or input validation error fails closed.

## Architecture

```text
Analyst input
  -> LLM orchestrator
  -> CTI / network / endpoint tool
  -> evidence store
  -> assessment report
  -> human review
```

Text-to-SQL uses the approved Option A design:

```text
LLM orchestrator
  -> domain tool
  -> internal query layer
  -> read-only DuckDB snapshot
  -> normalized evidence
```

The LLM does not receive raw database access. The database layer is hidden behind `network_investigation` and `endpoint_investigation`.

## DuckDB and data integrity

DuckDB is used for a local frozen snapshot because the current project is an offline public-data benchmark with one evaluator. The runtime opens the snapshot in read-only mode and permits only one `SELECT` or `WITH ... SELECT` statement. It hard-rejects writes, schema changes, multi-statement SQL, and database attachment commands.

The repository does not ship a benchmark snapshot or download sources automatically. Before loading rows, the snapshot builder requires source provenance: URL, retrieval time, file SHA-256, licence note, and schema version. Do not add synthetic, modified, or training rows to the frozen benchmark.

See [the DuckDB data-layer guide](docs/duckdb_data_layer.md) for the schema and build rules.

## Evaluation

VinSOC has three separate evaluation tracks:

| Track | Question answered | Main metric |
|---|---|---|
| Tool calling | Did the model select the right tool with the right arguments? | Tool Precision, Recall, F1; exact call match |
| Text-to-SQL | Did the query return the correct result from the same frozen snapshot? | Execution accuracy |
| End-to-end | Did the whole investigation produce grounded evidence and a correct assessment? | Evidence and assessment metrics |

Text-to-SQL metrics are separated on purpose:

- **Syntax validity**: DuckDB can parse the query without executing it.
- **Execution success**: the query runs on the snapshot.
- **Execution accuracy**: its result matches an accepted gold SQL result. This is the headline metric.
- **Safety rejection rate**: unsafe SQL stopped before execution.

The evaluator is in `evaluation/text_to_sql.py`. Each future benchmark case must follow [`schemas/text_to_sql_case.json`](schemas/text_to_sql_case.json). Gold SQL and predicted SQL always run against the same frozen database snapshot.

See [preliminary evaluation results](docs/evaluation_results_preliminary.md) for the current mock integration baseline and test status.

## Setup

Python 3.11 or newer is required.

```bash
pip install -r requirements.txt
python -m pytest -q
```

## Run the current skill and scenario checks

```bash
python -m cli.main test
python -m cli.main list
python -m cli.main scenario case_001
python -m cli.main benchmark --limit 5
```

## Use a frozen DuckDB snapshot

After a provenance-checked public snapshot is built, pass its path to a direct investigation:

```bash
python -m cli.main investigate 185.220.101.45 \
  --type ipv4 \
  --duckdb-snapshot data/snapshots/vinsoc_public_v1.duckdb
```

This connects only the network and endpoint skills to the snapshot. CTI remains fail-closed unless an approved ThreatFox source is configured.

## Provider policy

OpenAI is the primary provider. OpenRouter is a fallback only when the OpenAI provider has an approved operational failure, and it must use a model with the `:free` suffix. Fallback is disabled in official evaluation mode. The provider layer keeps model, cost, and fallback metadata for reproducibility.

See [provider routing](docs/provider_routing.md) for configuration details.

## Project layout

```text
agent/          LLM orchestration, tools, evidence, HITL
skills/         CTI, network, and endpoint investigation skills
vinsoc_data/    DuckDB snapshot boundary and domain query layer
evaluation/     Text-to-SQL execution evaluator
schemas/        Output and benchmark schemas
scenarios/      Existing tool-calling scenarios
docs/           Architecture, evaluation, safety, and data-layer notes
tests/          Unit and integration tests
```

## Security boundary

- All investigation tools are read-only.
- Telemetry and CTI text are treated as untrusted data, never as instructions.
- Every report must link claims to evidence IDs.
- An analyst approves, rejects, requests more evidence, or escalates the final assessment.

## Licence

This is an academic and research project for SOC investigation evaluation.
