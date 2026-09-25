> **NOT AUTHORIZED FOR EXECUTION**
>
> The project owner requested a specification-only handoff. Do not execute this implementation plan.
> Authoritative handoff document: docs/superpowers/specs/2026-09-25-dualsql-lite-agent-handoff-spec.md
> This plan is retained only as historical planning material.

# DualSQL-Lite Text-to-SQL Optimization Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox syntax for tracking.

**Goal:** Build and evaluate an inference-only DualSQL-inspired R2 pipeline that separates schema linking from SQL generation, gives bounded read-only database tools to the appropriate agent roles, and measures whether that architecture improves VinSOC Execution Accuracy without training or fine-tuning.

**Architecture:** Keep evaluation/text_to_sql.py as the sole correctness authority. Add an isolated evaluation/text_to_sql_agentic package containing deterministic database tools, gold-blind agent contracts, bounded native tool-call loops, E0-E3 experiment orchestration, provenance, efficiency metrics, and fail-closed budget controls. Both roles use the same pinned LLM configuration; E0-E3 differ only by whether schema linking and generator-side database tools are enabled.

**Tech Stack:** Python 3.11/3.12, DuckDB >=1.1.0,<2.0.0, existing agent.provider.LLMProvider/OpenAIProvider, OpenAI native function calling, Python standard library json/hashlib/difflib, pytest.

**Spec:** docs/superpowers/specs/2026-09-25-dualsql-lite-text-to-sql-optimization-design.md

## Global Constraints

- Work directly on master; do not create a feature branch or PR.
- Do not train, fine-tune, run RL, GRPO, SFT, or reward optimization.
- Preserve evaluation/text_to_sql.py scoring semantics and the existing read-only DuckDB boundary.
- Execution Accuracy remains the primary R2 metric.
- The historical 5/8 scorer-v2 replay is not a model baseline; E0 must be regenerated under the same evidence contract as E1-E3.
- Public-dev is diagnostic tuning only; official dev validates the selected architecture; frozen holdout remains sealed until final configuration freeze.
- Both agent roles use the same evidence-run provider/model/configuration.
- Evidence model is pinned to gpt-4.1-mini-2025-04-14, temperature 0, max SDK retries 0, and a fixed completion cap unless a new experiment version is explicitly frozen before any E0-E3 run.
- Schema Linker: maximum 5 model turns, maximum 5 database-tool calls, exactly one final linked-schema submission, never final SQL.
- SQL Generator: maximum 5 model turns, maximum 5 database-tool calls, exactly one final SQL submission, no post-evaluator retry.
- E0 exposes no database tools.
- E1 uses database tools in the linker and no database tools in the SQL generator.
- E2 skips the linker and exposes database tools to the SQL generator.
- E3 uses the linker and exposes database tools to both stages.
- No agent message, database tool, finalization tool, or tool result may contain gold_sql, gold result rows, or the current-case correctness label.
- Database tools operate only on the verified evaluation snapshot and never mutate it.
- SQL probes are stricter than ordinary final evaluation: they must reject external file/network table functions and internal metadata/provenance relations in addition to the existing write/multi-statement policy.
- Value search returns at most 5 values per column, at most 50 values per call, and a bounded serialized response.
- SQL probe returns at most 20 rows and at most 8192 serialized UTF-8 bytes.
- Paid evidence workflows are workflow_dispatch only; push/pull_request/schedule must never trigger paid model calls.
- Every paid evidence run must pass snapshot, benchmark, scorer, model, prompt, tool, catalog, branch/commit, and cost preflight before the first API call.
- Provider/model/usage mismatch or an incomplete fixed run invalidates the run; model-behavior failures count as case failures.
- Result artifacts are append-only and never overwrite prior run evidence.

## Review Focus

1. External-data escape through SQL probes: read_csv_auto, read_parquet, glob, http URLs, extension scan functions, information_schema, dataset_provenance, and other non-benchmark relations must be rejected before DuckDB execution.
2. Native tool-call protocol correctness: multi-tool turns, tool_call_id correlation, finalization-tool exclusivity, malformed arguments, and turn/tool limits must fail deterministically instead of creating ambiguous trajectories.
3. Gold isolation: a poison literal present only in SQLBenchmarkCase.gold_sql must never appear in linker/generator messages, database-tool calls, finalization arguments, or tool results.
4. Search-catalog scale and determinism: duplicate values, rare values, case differences, long paths, and large distinct columns must produce a stable catalog hash and bounded search output without loading arbitrary raw telemetry into prompts.
5. Evidence-run validity: provider outage, wrong actual model, missing usage, dirty checkout, changed snapshot/scorer/tool hash, or budget exhaustion must preserve a partial artifact and invalidate the run rather than being scored as a comparable E0-E3 result.

---

## File Structure

Create:

~~~
evaluation/text_to_sql_agentic/
  __init__.py
  models.py
  prompts.py
  profiler.py
  value_search.py
  probe.py
  tools.py
  loop.py
  schema_linker.py
  sql_generator.py
  metrics.py
  provenance.py
  budget.py
  runner.py

scripts/run_r2_agentic_optimization.py

tests/test_text_to_sql_agentic_models.py
tests/test_text_to_sql_agentic_profiler.py
tests/test_text_to_sql_agentic_value_search.py
tests/test_text_to_sql_agentic_probe.py
tests/test_text_to_sql_agentic_tools.py
tests/test_text_to_sql_agentic_loop.py
tests/test_text_to_sql_agentic_schema_linker.py
tests/test_text_to_sql_agentic_sql_generator.py
tests/test_text_to_sql_agentic_runner.py
tests/test_text_to_sql_agentic_budget.py
tests/test_text_to_sql_agentic_gold_isolation.py

.github/workflows/r2-dualsql-lite-public-dev.yml
~~~

Modify only when required:

~~~
evaluation/text_to_sql.py
README.md
docs/public_pilot_results_2026-09-25.md
~~~

Responsibility boundaries:

- models.py: immutable gold-blind case/trajectory/result contracts.
- prompts.py: versioned role prompts and canonical prompt hashes.
- profiler.py: deterministic DuckDB schema/statistics profiling.
- value_search.py: deterministic snapshot-derived searchable value catalog.
- probe.py: stricter bounded read-only SQL probe execution.
- tools.py: local OpenAI-compatible tool schemas and deterministic dispatch.
- loop.py: generic bounded native function-calling loop.
- schema_linker.py: linker role plus LinkedSchemaResult validation.
- sql_generator.py: static one-shot and agentic SQL-generation role.
- metrics.py: Execution Accuracy diagnostics plus agent/tool/cost summaries.
- provenance.py: file/config/hash/run identity.
- budget.py: conservative preflight and remaining-budget gates.
- runner.py: E0-E3 orchestration and post-submission scoring.
- CLI/workflow: evidence-run entry point only.

---

### Task 1: Add Gold-Blind Agentic Data Contracts

**Files:**
- Create: evaluation/text_to_sql_agentic/__init__.py
- Create: evaluation/text_to_sql_agentic/models.py
- Create: tests/test_text_to_sql_agentic_models.py

**Interfaces:**
- Consumes: evaluation.text_to_sql.SQLBenchmarkCase and ComparatorName.
- Produces: AgenticCase.from_benchmark(case) -> AgenticCase.
- Produces: ValueEvidence, LinkedSchemaResult, ToolEvent, AgentStageResult, AgenticCaseResult, ExperimentContract.

- [ ] **Step 1: Write the gold-isolation unit test**

~~~python
from dataclasses import asdict
from evaluation.text_to_sql import SQLBenchmarkCase
from evaluation.text_to_sql_agentic.models import AgenticCase

def test_agentic_case_strips_gold_sql():
    source = SQLBenchmarkCase(
        case_id="poison_001",
        question="Count network flows",
        database_snapshot="snapshot.duckdb",
        gold_sql=("SELECT 'POISON_GOLD_LITERAL' AS secret",),
        category="aggregation",
        difficulty="basic",
        result_comparator="scalar",
    )

    case = AgenticCase.from_benchmark(source)

    payload = asdict(case)
    assert "gold_sql" not in payload
    assert "POISON_GOLD_LITERAL" not in repr(payload)
    assert case.case_id == "poison_001"
    assert case.result_comparator == "scalar"
~~~

- [ ] **Step 2: Write validation tests for linked schema records**

~~~python
import pytest
from evaluation.text_to_sql_agentic.models import LinkedSchemaResult, ValueEvidence

def test_linked_schema_canonicalizes_duplicates_and_order():
    result = LinkedSchemaResult.create(
        tables={
            "network_flows": ["protocol", "src_ip", "protocol"],
            "sysmon_process_events": ["host"],
        },
        value_evidence=[
            ValueEvidence(
                table="network_flows",
                column="protocol",
                value="TCP",
                source_tool="search_database_values",
            )
        ],
    )

    assert result.tables == {
        "network_flows": ("protocol", "src_ip"),
        "sysmon_process_events": ("host",),
    }

def test_value_evidence_requires_database_tool_source():
    with pytest.raises(ValueError, match="source_tool"):
        ValueEvidence(
            table="network_flows",
            column="protocol",
            value="TCP",
            source_tool="model_guess",
        )
~~~

Allowed source_tool values are exactly search_database_values, profile_database, and execute_sql_probe.

- [ ] **Step 3: Run tests and verify failure**

Run:

~~~bash
python -m pytest tests/test_text_to_sql_agentic_models.py -q
~~~

Expected: import failure because the package does not exist.

- [ ] **Step 4: Implement immutable contracts**

models.py must define these exact public types:

~~~python
from dataclasses import dataclass, field
from typing import Any, Literal
from evaluation.text_to_sql import ComparatorName, SQLBenchmarkCase

ExperimentId = Literal["E0", "E1", "E2", "E3"]
StageName = Literal["schema_linker", "sql_generator"]
DatabaseToolName = Literal[
    "profile_database",
    "search_database_values",
    "execute_sql_probe",
]

@dataclass(frozen=True)
class AgenticCase:
    case_id: str
    question: str
    category: str
    difficulty: str
    result_comparator: ComparatorName

    @classmethod
    def from_benchmark(cls, case: SQLBenchmarkCase) -> "AgenticCase":
        return cls(
            case_id=case.case_id,
            question=case.question,
            category=case.category,
            difficulty=case.difficulty,
            result_comparator=case.result_comparator,
        )

@dataclass(frozen=True)
class ValueEvidence:
    table: str
    column: str
    value: str
    source_tool: DatabaseToolName

    def __post_init__(self) -> None:
        if self.source_tool not in {
            "profile_database",
            "search_database_values",
            "execute_sql_probe",
        }:
            raise ValueError("value evidence source_tool must be a database tool")

@dataclass(frozen=True)
class LinkedSchemaResult:
    tables: dict[str, tuple[str, ...]]
    value_evidence: tuple[ValueEvidence, ...]

    @classmethod
    def create(cls, tables, value_evidence=()):
        canonical = {
            table: tuple(sorted(set(columns)))
            for table, columns in sorted(tables.items())
        }
        return cls(canonical, tuple(value_evidence))

@dataclass(frozen=True)
class ToolEvent:
    turn_index: int
    tool_call_id: str
    tool_name: str
    arguments: dict[str, Any]
    result: dict[str, Any]

@dataclass
class AgentStageResult:
    stage: StageName
    status: str
    turns: int
    database_tool_calls: int
    tool_events: list[ToolEvent] = field(default_factory=list)
    linked_schema: LinkedSchemaResult | None = None
    final_sql: str | None = None
    error_category: str | None = None

@dataclass
class AgenticCaseResult:
    case_id: str
    experiment_id: ExperimentId
    linker: AgentStageResult | None
    generator: AgentStageResult
    final_sql: str | None
    execution_accurate: bool
    syntax_valid: bool
    execution_success: bool
    safety_rejected: bool
    error_category: str
    input_tokens: int = 0
    output_tokens: int = 0
    estimated_cost_usd: float | None = None
    latency_ms: float = 0.0

@dataclass(frozen=True)
class ExperimentContract:
    experiment_id: ExperimentId
    use_linker: bool
    linker_tools: bool
    generator_tools: bool
~~~

- [ ] **Step 5: Add exact E0-E3 contract definitions**

~~~python
EXPERIMENTS = {
    "E0": ExperimentContract("E0", False, False, False),
    "E1": ExperimentContract("E1", True, True, False),
    "E2": ExperimentContract("E2", False, False, True),
    "E3": ExperimentContract("E3", True, True, True),
}
~~~

Add a test asserting those exact tuples.

- [ ] **Step 6: Run focused tests**

~~~bash
python -m pytest tests/test_text_to_sql_agentic_models.py -q
~~~

Expected: PASS.

- [ ] **Step 7: Commit and push**

~~~bash
git add evaluation/text_to_sql_agentic/__init__.py evaluation/text_to_sql_agentic/models.py tests/test_text_to_sql_agentic_models.py
git commit -m "feat(eval): add gold-blind DualSQL-Lite contracts"
git push origin master
~~~

---

### Task 2: Implement Deterministic Database Profiler

**Files:**
- Create: evaluation/text_to_sql_agentic/profiler.py
- Create: tests/test_text_to_sql_agentic_profiler.py

**Interfaces:**
- Consumes: vinsoc_data.duckdb_store.DuckDBSnapshot.
- Produces: allowed_tables(snapshot) -> dict[str, tuple[str, ...]].
- Produces: profile_database(snapshot, table=None, columns=None) -> dict.
- Excludes: dataset_provenance and all non-main/internal relations.

- [ ] **Step 1: Write a fixture and failing schema tests**

~~~python
from vinsoc_data.duckdb_store import DuckDBSnapshot, SocSnapshotBuilder

def build_snapshot(tmp_path):
    path = tmp_path / "agentic.duckdb"
    builder = SocSnapshotBuilder(path)
    builder.create_empty_snapshot()
    builder.register_provenance(
        dataset_id="ctu13_s5",
        source_name="fixture",
        source_url="https://example.invalid/source",
        retrieved_at="2026-09-25T00:00:00",
        file_sha256="a" * 64,
        license_note="unit fixture",
    )
    builder.insert_rows(
        "network_flows",
        [
            {
                "source_dataset": "ctu13_s5",
                "source_row_id": "line:1",
                "event_time": "2011-08-15T16:52:50",
                "src_ip": "147.32.84.165",
                "src_port": 1000,
                "dst_ip": "147.32.80.9",
                "dst_port": 80,
                "protocol": "TCP",
                "action": "CON",
                "bytes_out": 100,
                "bytes_in": 50,
                "label": "flow=From-Botnet-TCP-HTTP",
            }
        ],
        source_dataset="ctu13_s5",
    )
    return DuckDBSnapshot(path)

def test_allowed_tables_excludes_provenance_and_internal_relations(tmp_path):
    snapshot = build_snapshot(tmp_path)
    tables = allowed_tables(snapshot)
    assert "network_flows" in tables
    assert "dataset_provenance" not in tables
    assert "information_schema" not in tables
~~~

- [ ] **Step 2: Write bounded metadata tests**

~~~python
def test_profile_returns_deterministic_column_metadata(tmp_path):
    snapshot = build_snapshot(tmp_path)
    first = profile_database(snapshot, table="network_flows")
    second = profile_database(snapshot, table="network_flows")

    assert first == second
    protocol = next(item for item in first["columns"] if item["name"] == "protocol")
    assert protocol["data_type"] == "VARCHAR"
    assert protocol["distinct_count"] == 1
    assert protocol["top_values"] == [{"value": "TCP", "count": 1}]

def test_profile_rejects_unknown_table(tmp_path):
    snapshot = build_snapshot(tmp_path)
    with pytest.raises(ValueError, match="benchmark table"):
        profile_database(snapshot, table="dataset_provenance")
~~~

- [ ] **Step 3: Run tests and verify failure**

~~~bash
python -m pytest tests/test_text_to_sql_agentic_profiler.py -q
~~~

- [ ] **Step 4: Implement schema discovery**

Query information_schema.columns through DuckDBSnapshot for main-schema tables, explicitly remove dataset_provenance, and return sorted table/column names.

Use parameter-free static SQL only in this module. Do not accept raw SQL from the model.

- [ ] **Step 5: Implement bounded per-column statistics**

For each requested column:
- return name and DuckDB data_type;
- return non_null_count and null_count;
- return distinct_count;
- for numeric/timestamp columns return min and max;
- for VARCHAR columns with distinct_count <= 32, return at most 12 top values ordered by count descending then text ascending;
- for higher-cardinality VARCHAR columns, omit top_values and return top_values_omitted=true.

Reject requested columns not present in the selected table.

- [ ] **Step 6: Cap profiler serialization**

Add constant MAX_PROFILE_BYTES = 8192.

If the full response exceeds the cap, retain table/column/type/count fields first, then drop optional top_values sections from the end until canonical JSON serialization is <= 8192 bytes. Add truncated=true when any optional section is removed.

Test with a table containing 40 low-cardinality VARCHAR columns and assert serialized size <= 8192 bytes.

- [ ] **Step 7: Run tests**

~~~bash
python -m pytest tests/test_text_to_sql_agentic_profiler.py -q
~~~

Expected: PASS.

- [ ] **Step 8: Commit and push**

~~~bash
git add evaluation/text_to_sql_agentic/profiler.py tests/test_text_to_sql_agentic_profiler.py
git commit -m "feat(eval): add deterministic R2 database profiler"
git push origin master
~~~

---

### Task 3: Build and Search a Deterministic Value Catalog

**Files:**
- Create: evaluation/text_to_sql_agentic/value_search.py
- Create: tests/test_text_to_sql_agentic_value_search.py

**Interfaces:**
- Consumes: DuckDBSnapshot and snapshot_content_sha256.
- Produces: ValueCatalog.build(snapshot, snapshot_content_sha256) -> ValueCatalog.
- Produces: ValueCatalog.search(query, table=None, column=None) -> dict.
- Produces: catalog.sha256 and catalog metadata for provenance.

- [ ] **Step 1: Write failing catalog determinism tests**

~~~python
def test_catalog_hash_is_stable_for_same_snapshot(tmp_path):
    snapshot = build_snapshot_with_search_values(tmp_path)
    first = ValueCatalog.build(snapshot, "a" * 64)
    second = ValueCatalog.build(snapshot, "a" * 64)

    assert first.sha256 == second.sha256
    assert first.entries == second.entries

def test_catalog_hash_binds_snapshot_identity(tmp_path):
    snapshot = build_snapshot_with_search_values(tmp_path)
    a = ValueCatalog.build(snapshot, "a" * 64)
    b = ValueCatalog.build(snapshot, "b" * 64)
    assert a.sha256 != b.sha256
~~~

- [ ] **Step 2: Define the approved searchable columns**

Use this exact initial allowlist:

~~~python
SEARCHABLE_TEXT_COLUMNS = {
    "cti_indicators": (
        "source_dataset",
        "indicator",
        "indicator_type",
        "threat_type",
        "malware_printable",
    ),
    "network_flows": (
        "source_dataset",
        "src_ip",
        "dst_ip",
        "protocol",
        "action",
        "label",
    ),
    "sysmon_process_events": (
        "source_dataset",
        "host",
        "parent_image",
        "image",
        "user_name",
    ),
}
~~~

Skip tables absent from the current snapshot.

Do not catalog source_row_id or command_line in v1.

- [ ] **Step 3: Write search-behavior tests**

Fixture values must include:
- ctu13_s5;
- ctu13_s7;
- flow=From-Botnet-TCP-HTTP;
- flow=Background-TCP-Established;
- SCRANTON.dmevals.local;
- C:\Windows\System32\cmd.exe;
- C:\Windows\System32\WindowsPowerShell\v1.0\powershell.exe.

Tests:

~~~python
def test_search_finds_encoded_scenario_value(tmp_path):
    catalog = ValueCatalog.build(build_snapshot_with_search_values(tmp_path), "c" * 64)
    result = catalog.search("scenario 5")
    values = [m["value"] for m in result["matches"]]
    assert "ctu13_s5" in values

def test_search_finds_botnet_label_by_partial_tokens(tmp_path):
    catalog = ValueCatalog.build(build_snapshot_with_search_values(tmp_path), "c" * 64)
    result = catalog.search("From Botnet")
    assert any("From-Botnet" in m["value"] for m in result["matches"])

def test_search_respects_table_column_filters(tmp_path):
    catalog = ValueCatalog.build(build_snapshot_with_search_values(tmp_path), "c" * 64)
    result = catalog.search("cmd.exe", table="sysmon_process_events", column="parent_image")
    assert result["matches"]
    assert {m["column"] for m in result["matches"]} == {"parent_image"}
~~~

- [ ] **Step 4: Implement catalog entries**

Each entry is canonical data:

~~~python
@dataclass(frozen=True)
class CatalogEntry:
    table: str
    column: str
    value: str
    frequency: int
    normalized: str
~~~

For each approved existing VARCHAR column, query all distinct non-null values with count, sort by exact value text, and construct entries.

Canonical catalog hash is SHA-256 of JSON containing:
- builder_version="value_catalog_v1";
- snapshot_content_sha256;
- searchable-column allowlist;
- sorted entries as table/column/value/frequency.

This is a derived evaluation artifact, not model-generated data.

- [ ] **Step 5: Implement deterministic ranking**

Normalization:
- lowercase;
- convert backslashes, slashes, underscores, hyphens, dots, and colons to token separators;
- keep alphanumeric token content.

Score each entry with this tuple, descending:
1. exact normalized query substring in normalized value: 1 or 0;
2. count of query tokens present in value tokens;
3. difflib.SequenceMatcher(query_normalized, value_normalized).ratio();
4. log-frequency tie-break represented by integer frequency;
5. lexical table, column, value ascending for final determinism.

Add special token normalization for a token shaped as scenario N: also compare token N against trailing numeric token in dataset values such as ctu13_s5. This is generic token normalization, not a benchmark-case-specific alias map.

- [ ] **Step 6: Enforce search bounds**

Constants:

~~~python
MAX_VALUES_PER_COLUMN = 5
MAX_VALUES_PER_CALL = 50
MAX_SEARCH_BYTES = 8192
~~~

After ranking, retain at most 5 per table/column and at most 50 overall. If canonical JSON still exceeds 8192 bytes, remove lowest-ranked matches until within limit and set truncated=true.

- [ ] **Step 7: Test scale bounds**

Generate 500 distinct host/path values and assert:
- catalog builds deterministically;
- search returns <= 50 matches;
- no table/column group has > 5;
- serialized result <= 8192 bytes.

- [ ] **Step 8: Run tests**

~~~bash
python -m pytest tests/test_text_to_sql_agentic_value_search.py -q
~~~

Expected: PASS.

- [ ] **Step 9: Commit and push**

~~~bash
git add evaluation/text_to_sql_agentic/value_search.py tests/test_text_to_sql_agentic_value_search.py
git commit -m "feat(eval): add deterministic R2 value search"
git push origin master
~~~

---

### Task 4: Add Strict Read-Only SQL Probe Execution

**Files:**
- Create: evaluation/text_to_sql_agentic/probe.py
- Create: tests/test_text_to_sql_agentic_probe.py

**Interfaces:**
- Consumes: DuckDBSnapshot and SQL string.
- Produces: execute_sql_probe(snapshot, sql) -> dict.
- Reuses: vinsoc_data.duckdb_store.validate_read_only_sql.
- Adds: stricter relation/function guard specific to agent probes.

- [ ] **Step 1: Write safe-query tests**

~~~python
def test_probe_executes_benchmark_select(tmp_path):
    snapshot = build_snapshot(tmp_path)
    result = execute_sql_probe(
        snapshot,
        "SELECT protocol, count(*) AS n FROM network_flows GROUP BY protocol",
    )
    assert result["status"] == "ok"
    assert result["rows"] == [{"protocol": "TCP", "n": 1}]
~~~

- [ ] **Step 2: Write write/multi-statement rejection tests**

~~~python
@pytest.mark.parametrize(
    "sql",
    [
        "DELETE FROM network_flows",
        "UPDATE network_flows SET protocol='UDP'",
        "SELECT 1; SELECT 2",
        "PRAGMA version",
        "ATTACH 'other.duckdb' AS other",
    ],
)
def test_probe_rejects_non_read_only_sql(tmp_path, sql):
    with pytest.raises(QuerySafetyError):
        execute_sql_probe(build_snapshot(tmp_path), sql)
~~~

- [ ] **Step 3: Add external-data escape tests from Review Focus**

~~~python
@pytest.mark.parametrize(
    "sql",
    [
        "SELECT * FROM read_csv_auto('/etc/passwd')",
        "SELECT * FROM read_parquet('https://example.com/x.parquet')",
        "SELECT * FROM glob('/tmp/*')",
        "SELECT * FROM parquet_scan('/tmp/x.parquet')",
        "SELECT * FROM read_json_auto('https://example.com/x.json')",
    ],
)
def test_probe_rejects_external_reader_functions(tmp_path, sql):
    with pytest.raises(QuerySafetyError, match="external"):
        execute_sql_probe(build_snapshot(tmp_path), sql)

@pytest.mark.parametrize(
    "sql",
    [
        "SELECT * FROM dataset_provenance",
        "SELECT * FROM information_schema.tables",
        "SELECT * FROM duckdb_tables()",
        "SELECT * FROM sqlite_master",
    ],
)
def test_probe_rejects_internal_relations(tmp_path, sql):
    with pytest.raises(QuerySafetyError, match="benchmark"):
        execute_sql_probe(build_snapshot(tmp_path), sql)
~~~

- [ ] **Step 4: Implement probe-specific validator**

Define forbidden external-access function tokens:

~~~python
FORBIDDEN_PROBE_FUNCTIONS = {
    "read_csv",
    "read_csv_auto",
    "read_json",
    "read_json_auto",
    "read_ndjson",
    "read_parquet",
    "parquet_scan",
    "glob",
    "read_blob",
    "sqlite_scan",
    "postgres_scan",
    "mysql_scan",
    "delta_scan",
    "iceberg_scan",
}
~~~

Define forbidden relation/name prefixes:
- dataset_provenance;
- information_schema;
- duckdb_;
- sqlite_;
- pg_.

The validator first calls validate_read_only_sql(sql), then strips quoted literals/comments using a local scanner based on the same quote/comment rules as duckdb_store._sql_tokens, then rejects forbidden identifiers and function calls before snapshot.query.

Do not import private _sql_tokens from duckdb_store.

- [ ] **Step 5: Enforce row and byte bounds**

Constants:

~~~python
MAX_PROBE_ROWS = 20
MAX_PROBE_BYTES = 8192
~~~

Use a dedicated DuckDBSnapshot with row_limit=20 pointing to the same database path.

Serialize result as:
- status;
- columns;
- rows;
- row_count_returned;
- truncated.

If JSON exceeds 8192 bytes, remove rows from the end until it fits. Keep columns and status. Set truncated=true.

- [ ] **Step 6: Test zero rows and terminal semicolon**

~~~python
def test_probe_zero_rows_is_success(tmp_path):
    result = execute_sql_probe(
        build_snapshot(tmp_path),
        "SELECT * FROM network_flows WHERE protocol='DOES_NOT_EXIST';",
    )
    assert result["status"] == "ok"
    assert result["rows"] == []

def test_probe_accepts_one_terminal_semicolon(tmp_path):
    result = execute_sql_probe(build_snapshot(tmp_path), "SELECT 1 AS value;")
    assert result["status"] == "ok"
~~~

- [ ] **Step 7: Run tests**

~~~bash
python -m pytest tests/test_text_to_sql_agentic_probe.py tests/test_text_to_sql_runner.py -q
~~~

Expected: PASS.

- [ ] **Step 8: Commit and push**

~~~bash
git add evaluation/text_to_sql_agentic/probe.py tests/test_text_to_sql_agentic_probe.py
git commit -m "feat(eval): add bounded read-only SQL probe"
git push origin master
~~~

---

### Task 5: Define Agentic Tool Schemas and Deterministic Dispatch

**Files:**
- Create: evaluation/text_to_sql_agentic/tools.py
- Create: tests/test_text_to_sql_agentic_tools.py

**Interfaces:**
- Produces: get_linker_tool_schemas() -> list[dict].
- Produces: get_generator_tool_schemas(enable_database_tools: bool) -> list[dict].
- Produces: dispatch_database_tool(name, arguments, runtime) -> dict.
- Finalization tools: submit_linked_schema and submit_final_sql.
- Database tools: profile_database, search_database_values, execute_sql_probe.

- [ ] **Step 1: Write tool-schema-name tests**

~~~python
def names(schemas):
    return {item["function"]["name"] for item in schemas}

def test_linker_tool_schema_contains_database_tools_and_link_submit():
    assert names(get_linker_tool_schemas()) == {
        "profile_database",
        "search_database_values",
        "execute_sql_probe",
        "submit_linked_schema",
    }

def test_static_generator_only_exposes_final_submission():
    assert names(get_generator_tool_schemas(False)) == {"submit_final_sql"}

def test_agentic_generator_exposes_database_tools_and_final_submission():
    assert names(get_generator_tool_schemas(True)) == {
        "profile_database",
        "search_database_values",
        "execute_sql_probe",
        "submit_final_sql",
    }
~~~

- [ ] **Step 2: Implement exact database tool arguments**

profile_database:
- table: optional string;
- columns: optional array of strings, maxItems 32;
- additionalProperties false.

search_database_values:
- query: required non-empty string, maxLength 512;
- table: optional string;
- column: optional string;
- additionalProperties false.

execute_sql_probe:
- sql: required non-empty string, maxLength 16000;
- additionalProperties false.

All schemas use type=function and explicit JSON Schema required/additionalProperties fields.

- [ ] **Step 3: Implement finalization tool arguments**

submit_linked_schema arguments:

~~~json
{
  "type": "object",
  "properties": {
    "tables": {
      "type": "object",
      "additionalProperties": {
        "type": "array",
        "items": {"type": "string"},
        "maxItems": 64
      }
    },
    "value_evidence": {
      "type": "array",
      "maxItems": 50,
      "items": {
        "type": "object",
        "properties": {
          "table": {"type": "string"},
          "column": {"type": "string"},
          "value": {"type": "string"},
          "source_tool": {
            "type": "string",
            "enum": [
              "profile_database",
              "search_database_values",
              "execute_sql_probe"
            ]
          }
        },
        "required": ["table", "column", "value", "source_tool"],
        "additionalProperties": false
      }
    }
  },
  "required": ["tables", "value_evidence"],
  "additionalProperties": false
}
~~~

submit_final_sql arguments:
- sql required string, minLength 1, maxLength 16000;
- no other properties.

- [ ] **Step 4: Implement ToolRuntime and dispatch**

ToolRuntime contains:
- snapshot;
- ValueCatalog;
- list of prior ToolEvent records for evidence validation.

dispatch_database_tool validates tool name and JSON argument types, then calls profiler, search, or probe. Unknown names raise ValueError.

- [ ] **Step 5: Validate linked-schema evidence against real tool output**

Add validate_linked_schema_submission(arguments, allowed_schema, tool_events).

For each value_evidence item, require an earlier database ToolEvent whose result contains the exact same table, column, and literal value. This prevents the model from labeling an invented value as tool-grounded.

Table/column selections themselves must exist in allowed_schema.

Test an invented value "ctu13_s999" and assert rejection.

- [ ] **Step 6: Run tests**

~~~bash
python -m pytest tests/test_text_to_sql_agentic_tools.py -q
~~~

Expected: PASS.

- [ ] **Step 7: Commit and push**

~~~bash
git add evaluation/text_to_sql_agentic/tools.py tests/test_text_to_sql_agentic_tools.py
git commit -m "feat(eval): add DualSQL-Lite database tools"
git push origin master
~~~

---

### Task 6: Implement the Bounded Native Tool-Calling Loop

**Files:**
- Create: evaluation/text_to_sql_agentic/loop.py
- Create: tests/test_text_to_sql_agentic_loop.py

**Interfaces:**
- Consumes: LLMProvider, system prompt, initial user content, tool schemas, ToolRuntime, stage name.
- Produces: AgentStageResult.
- Supports finalization callbacks for linked schema and final SQL.
- Max 5 model turns and 5 database-tool calls.

- [ ] **Step 1: Add a scripted fake provider**

~~~python
from agent.provider import LLMResponse

class ScriptedProvider:
    def __init__(self, responses):
        self.responses = iter(responses)
        self.calls = []

    def generate(self, messages, tools=None, system_prompt=None, temperature=0.0):
        self.calls.append({
            "messages": list(messages),
            "tools": tools,
            "system_prompt": system_prompt,
            "temperature": temperature,
        })
        return next(self.responses)

    def get_name(self):
        return "scripted"

    def get_run_metadata(self):
        return {"calls": [], "total_calls": len(self.calls), "estimated_cost_usd": 0.0}

    def reset_tracking(self):
        self.calls.clear()
~~~

- [ ] **Step 2: Write a one-tool-round protocol test**

First response contains:

~~~python
LLMResponse(
    content="",
    tool_calls=[{
        "id": "call_1",
        "name": "profile_database",
        "arguments": {"table": "network_flows"},
    }],
    raw={},
    metadata={"input_tokens": 10, "output_tokens": 5, "latency_ms": 1.0},
)
~~~

Second response contains submit_final_sql.

Assert second provider call messages contain:
- one assistant message with tool_calls and id call_1;
- one role=tool message with tool_call_id call_1;
- serialized profiler result;
- no loss of original user message.

- [ ] **Step 3: Write multi-tool and correlation tests**

One model turn may request multiple database tools. Execute them in response order and append one tool message per call ID.

Reject:
- duplicate tool_call_id in the same trajectory;
- missing tool-call id;
- non-dict arguments;
- unknown tool name.

- [ ] **Step 4: Write finalization exclusivity tests**

A turn containing submit_final_sql plus any other tool call is invalid.

A turn containing two submit_final_sql calls is invalid.

A linker turn containing submit_final_sql is invalid; a generator turn containing submit_linked_schema is invalid.

- [ ] **Step 5: Write turn/tool limit tests**

Construct:
- 5 turns each with one database call and no finalizer, then a sixth response available: loop must stop after turn 5 with status model_limit_failure and must not call provider a sixth time.
- one response with 6 database calls: stop without executing the sixth database tool and mark model_limit_failure.

- [ ] **Step 6: Implement assistant/tool message conversion**

Assistant tool-call message must be constructed as:

~~~python
{
    "role": "assistant",
    "content": response.content or "",
    "tool_calls": [
        {
            "id": call["id"],
            "type": "function",
            "function": {
                "name": call["name"],
                "arguments": json.dumps(
                    call["arguments"],
                    ensure_ascii=False,
                    sort_keys=True,
                    separators=(",", ":"),
                ),
            },
        }
        for call in response.tool_calls
    ],
}
~~~

Tool response message:

~~~python
{
    "role": "tool",
    "tool_call_id": call["id"],
    "content": json.dumps(
        result,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ),
}
~~~

- [ ] **Step 7: Implement completion rules**

The loop accepts final output only through the role-appropriate finalization tool.

If the model returns prose with no tool call before finalization, append one bounded user correction message:

"Use one of the provided tools. When finished, call the required submission tool."

That correction consumes a model turn. Do not infer a final answer from prose.

- [ ] **Step 8: Aggregate stage usage**

Sum response metadata:
- input_tokens;
- output_tokens;
- latency_ms;
- estimated_cost_usd when every response provides it.

If any successful provider response has missing input/output token metadata in evidence mode, the outer evidence runner will invalidate the run; unit loop may retain zero/missing markers for offline test providers.

- [ ] **Step 9: Run tests**

~~~bash
python -m pytest tests/test_text_to_sql_agentic_loop.py tests/test_text_to_sql_agentic_tools.py -q
~~~

Expected: PASS.

- [ ] **Step 10: Commit and push**

~~~bash
git add evaluation/text_to_sql_agentic/loop.py tests/test_text_to_sql_agentic_loop.py
git commit -m "feat(eval): add bounded agentic tool loop"
git push origin master
~~~

---

### Task 7: Implement Schema Linking Agent

**Files:**
- Create: evaluation/text_to_sql_agentic/prompts.py
- Create: evaluation/text_to_sql_agentic/schema_linker.py
- Create: tests/test_text_to_sql_agentic_schema_linker.py

**Interfaces:**
- Consumes: AgenticCase, ToolRuntime, LLMProvider.
- Produces: run_schema_linker(case, runtime, provider) -> AgentStageResult with LinkedSchemaResult.
- Uses: get_linker_tool_schemas and bounded loop.

- [ ] **Step 1: Write the versioned linker prompt**

prompts.py constants:

~~~python
SCHEMA_LINKER_PROMPT_VERSION = "schema_linker_prompt_v1"

SCHEMA_LINKER_SYSTEM_PROMPT = """You are the schema-linking stage of a DuckDB Text-to-SQL evaluator.
Your job is to identify only the benchmark tables, columns, and database literals needed to answer the user question.
Use the database tools when they provide evidence. Do not write or submit final SQL.
Never invent a table, column, or grounded literal.
When ready, call submit_linked_schema exactly once.
Do not expose hidden reasoning; communicate only through tool calls and the final structured submission."""
~~~

Add canonical_prompt_sha256(name, system_prompt, user_payload) using sorted compact JSON.

- [ ] **Step 2: Write a successful linker test**

Script:
1. profile_database(network_flows);
2. search_database_values("scenario 5 From Botnet", network_flows);
3. submit_linked_schema with network_flows source_dataset and label plus exact values returned by search.

Assert:
- stage.status == completed;
- linked schema contains source_dataset and label;
- database_tool_calls == 2;
- final submission is not counted as a database-tool call.

- [ ] **Step 3: Write invalid-link tests**

Reject submissions containing:
- nonexistent table;
- nonexistent column;
- invented value evidence;
- final SQL text embedded in an unsupported extra property;
- no tables.

These are LINKER_FORMAT_OR_LIMIT_FAILURE case outcomes, not run-invalidating infrastructure errors.

- [ ] **Step 4: Implement run_schema_linker**

User content includes:
- original question;
- complete schema rendering derived from allowed_tables.

Do not include SQLBenchmarkCase or any gold data.

Invoke the generic loop with:
- stage=schema_linker;
- linker schemas;
- max_turns=5;
- max_database_tool_calls=5;
- submit callback validate_linked_schema_submission.

- [ ] **Step 5: Add linker prompt-hash test**

Run the same case twice against the same schema and assert identical prompt hash.

Change one schema column and assert hash changes.

- [ ] **Step 6: Run tests**

~~~bash
python -m pytest tests/test_text_to_sql_agentic_schema_linker.py -q
~~~

Expected: PASS.

- [ ] **Step 7: Commit and push**

~~~bash
git add evaluation/text_to_sql_agentic/prompts.py evaluation/text_to_sql_agentic/schema_linker.py tests/test_text_to_sql_agentic_schema_linker.py
git commit -m "feat(eval): add DualSQL-Lite schema linker"
git push origin master
~~~

---

### Task 8: Implement Static and Agentic SQL Generation

**Files:**
- Create: evaluation/text_to_sql_agentic/sql_generator.py
- Create: tests/test_text_to_sql_agentic_sql_generator.py

**Interfaces:**
- Consumes: AgenticCase, optional LinkedSchemaResult, ToolRuntime, provider, enable_database_tools.
- Produces: run_sql_generator(case: AgenticCase, *, snapshot: DuckDBSnapshot, catalog: ValueCatalog, provider: LLMProvider, linked_schema: LinkedSchemaResult | None, mode: Literal["baseline_one_shot", "linked_static", "agentic"]) -> AgentStageResult with final_sql.
- E0 has one provider call with no tool schema.
- E1 uses submit_final_sql only and one provider turn.
- E2/E3 use database tools plus submit_final_sql through bounded loop.

- [ ] **Step 1: Add the generator prompt**

prompts.py adds:

~~~python
SQL_GENERATOR_PROMPT_VERSION = "sql_generator_prompt_v1"

SQL_GENERATOR_SYSTEM_PROMPT = """You generate one read-only DuckDB SQL query for the VinSOC SOC benchmark.
Use the supplied schema and grounded values as evidence.
When database tools are available, use them only to inspect or test the evaluation snapshot.
Never modify data and never access external files, URLs, extensions, or internal metadata.
Return the answer through submit_final_sql when that tool is available.
Do not expose hidden reasoning."""
~~~

For E0, preserve the existing one-shot baseline system prompt text used by TextToSQLRunner so the baseline is not silently improved by an unrelated prompt rewrite.

- [ ] **Step 2: Write E0 one-shot test**

Use a fake provider returning textual content:

"SELECT count(*) AS flow_count FROM network_flows"

Assert:
- exactly one provider call;
- tools is None;
- system prompt contains the existing VinSOC one-shot wording;
- result.final_sql equals the content after existing _extract_sql normalization.

- [ ] **Step 3: Write E1 static-generator test**

Give a LinkedSchemaResult with network_flows/source_dataset/label and ctu13_s5 evidence.

Expose only submit_final_sql.

Script one response calling submit_final_sql.

Assert no database tools are present in provider request.

- [ ] **Step 4: Write E2/E3 agentic-generator test**

Script:
1. execute_sql_probe with a safe COUNT query;
2. submit_final_sql.

Assert:
- database tool event is recorded;
- final SQL is exactly submission argument;
- no evaluator correctness is visible to the loop.

- [ ] **Step 5: Add recovery test required by spec**

Construct a linked schema intentionally missing protocol while question requires TCP.

E1:
- generator has only submit_final_sql;
- scripted output lacking protocol is accepted as its final SQL and later can score wrong.

E3:
- generator can call profile_database(network_flows);
- tool result exposes protocol;
- generator submits SQL including protocol='TCP'.

Assert E3 trajectory records the profiler call and final SQL includes the recovered column. This is a controlled fixture proving capability, not a model-accuracy claim.

- [ ] **Step 6: Implement linked-schema rendering**

For E1/E3, render only:
- linked tables/columns;
- exact value_evidence.

For E2, render full allowed schema.

For E0, use the existing full schema formatting from TextToSQLRunner.

Never add hand-written semantic aliases.

- [ ] **Step 7: Run tests**

~~~bash
python -m pytest tests/test_text_to_sql_agentic_sql_generator.py tests/test_text_to_sql_runner.py -q
~~~

Expected: PASS.

- [ ] **Step 8: Commit and push**

~~~bash
git add evaluation/text_to_sql_agentic/prompts.py evaluation/text_to_sql_agentic/sql_generator.py tests/test_text_to_sql_agentic_sql_generator.py
git commit -m "feat(eval): add agentic R2 SQL generator"
git push origin master
~~~

---

### Task 9: Add Agentic Metrics and Error Categories

**Files:**
- Create: evaluation/text_to_sql_agentic/metrics.py
- Create: tests/test_text_to_sql_agentic_runner.py

**Interfaces:**
- Consumes: list[AgenticCaseResult].
- Produces: aggregate_agentic_metrics(results) -> dict.
- Primary metric still comes from final execution_accurate booleans.

- [ ] **Step 1: Write aggregate metric tests**

~~~python
def test_metrics_keep_execution_accuracy_primary():
    results = [
        case_result("a", accurate=True, linker_tools=2, generator_tools=1),
        case_result("b", accurate=False, linker_tools=1, generator_tools=3),
    ]

    metrics = aggregate_agentic_metrics(results)

    assert metrics["execution_accuracy"] == 0.5
    assert metrics["case_count"] == 2
    assert metrics["average_linker_tool_calls"] == 1.5
    assert metrics["average_generator_tool_calls"] == 2.0
~~~

- [ ] **Step 2: Require these aggregate keys**

~~~text
case_count
execution_accuracy
syntax_validity_rate
execution_success_rate
safety_rejection_rate
linker_completion_rate
average_linker_turns
average_linker_tool_calls
average_generator_turns
average_generator_tool_calls
profile_database_usage_rate
search_database_values_usage_rate
execute_sql_probe_usage_rate
average_linked_table_count
average_linked_column_count
generator_schema_recovery_count
malformed_agent_output_count
input_tokens
output_tokens
estimated_cost_usd
cost_complete
total_latency_ms
~~~

For E0/E2 where no linker exists, linker-specific averages are null, not zero.

- [ ] **Step 3: Implement deterministic error precedence**

Case error category precedence:
1. LINKER_FORMAT_OR_LIMIT_FAILURE if required linker failed;
2. GENERATOR_FORMAT_OR_LIMIT_FAILURE if no final SQL;
3. SAFETY_REJECTION;
4. SYNTAX_ERROR;
5. EXECUTION_ERROR;
6. RESULT_MISMATCH;
7. OK.

Post-hoc manual semantic categories such as PREDICATE_ERROR are not automatically inferred in code.

- [ ] **Step 4: Add category/difficulty breakdown**

Aggregate Execution Accuracy, syntax validity, and execution success per:
- category;
- difficulty.

Store absolute case IDs in each breakdown group.

- [ ] **Step 5: Run tests**

~~~bash
python -m pytest tests/test_text_to_sql_agentic_runner.py -q
~~~

Expected: PASS for the metrics fixtures added in this task.

- [ ] **Step 6: Commit and push**

~~~bash
git add evaluation/text_to_sql_agentic/metrics.py tests/test_text_to_sql_agentic_runner.py
git commit -m "feat(eval): add DualSQL-Lite diagnostics"
git push origin master
~~~

---

### Task 10: Add Provenance and Fail-Closed Budgeting

**Files:**
- Create: evaluation/text_to_sql_agentic/provenance.py
- Create: evaluation/text_to_sql_agentic/budget.py
- Create: tests/test_text_to_sql_agentic_budget.py

**Interfaces:**
- Produces: canonical_sha256(value) -> str.
- Produces: build_agentic_provenance(*, git_sha: str, benchmark_version: str, benchmark_split_sha256: str, snapshot_binary_sha256: str, snapshot_content_sha256: str, scorer_file_sha256: dict[str, str], model: str, experiment: ExperimentContract, prompt_hashes: dict[str, str], tool_schema_sha256: str, tool_implementation_sha256: dict[str, str], catalog_metadata: dict[str, Any], pricing: dict[str, Any], preflight: dict[str, Any]) -> dict[str, Any].
- Produces: preflight_experiment(*, experiment_id: ExperimentId, initial_request_payloads: list[dict[str, Any]], case_count: int, input_usd_per_million: float, output_usd_per_million: float, budget_usd: float) -> dict[str, Any].
- Produces: ensure_remaining_budget(known_cost_usd: float, remaining_max_cost_usd: float, budget_limit_usd: float) -> None.

- [ ] **Step 1: Implement canonical hashing tests**

Test stable hashes for:
- role prompts;
- tool schemas;
- searchable-column configuration;
- catalog canonical data;
- scorer file-hash mapping;
- benchmark case mapping.

Use sorted compact JSON and UTF-8.

- [ ] **Step 2: Define evidence constants**

~~~python
MODEL = "gpt-4.1-mini-2025-04-14"
TEMPERATURE = 0.0
MAX_COMPLETION_TOKENS = 1000
MAX_RETRIES = 0
PUBLIC_DEV_BUDGET_USD = 1.00
INPUT_USD_PER_MILLION = 0.40
OUTPUT_USD_PER_MILLION = 1.60
FRAMING_TOKEN_ALLOWANCE = 4096
MAX_TURNS_PER_STAGE = 5
MAX_DATABASE_TOOL_CALLS_PER_STAGE = 5
MAX_TOOL_RESULT_BYTES = 8192
~~~

Pricing values must be documented as the pinned experiment pricing snapshot already used by the public pilot. If provider pricing has changed before the evidence run, stop and create a new pricing snapshot rather than silently editing historical cost assumptions.

- [ ] **Step 3: Write worst-case call-count tests**

Expected maximum model calls per case:
- E0: 1;
- E1: linker 5 + static generator 1 = 6;
- E2: generator 5 = 5;
- E3: linker 5 + generator 5 = 10.

~~~python
@pytest.mark.parametrize(
    ("experiment", "expected"),
    [("E0", 1), ("E1", 6), ("E2", 5), ("E3", 10)],
)
def test_max_model_calls_per_case(experiment, expected):
    assert max_model_calls_per_case(experiment) == expected
~~~

- [ ] **Step 4: Implement conservative per-turn bounds**

For each stage, the first request bound is:
- serialized exact model/messages/tools request UTF-8 byte count;
- plus FRAMING_TOKEN_ALLOWANCE;
- plus completion cap charged at output rate.

Each later-turn input bound additionally accumulates, for every prior turn:
- one maximum assistant tool-call envelope of 2048 bytes;
- maximum tool-result bytes for each allowed database tool call;
- one bounded correction message of 256 bytes if applicable;
- prior completion cap as a conservative text/tool-call allowance.

Do not assume tool calls are free.

Compute each case's worst-case input/output/cost and the full split ceiling.

- [ ] **Step 5: Write budget rejection test**

Use artificially high rates and assert preflight_experiment raises before a provider is instantiated when cost_ceiling_usd >= budget_limit_usd.

- [ ] **Step 6: Add remaining-budget gate**

Before each provider call, compare:
known_cost_usd + conservative cost of all remaining permitted calls
against budget_limit_usd.

At equality or above, stop before the provider call.

- [ ] **Step 7: Build provenance record**

Required fields:
- git_sha;
- benchmark_version;
- benchmark_split_sha256;
- snapshot_binary_sha256;
- snapshot_content_sha256;
- scorer_file_sha256;
- scorer_sha256;
- model/config;
- linker prompt version/hash;
- generator prompt version/hash;
- tool schema hash;
- tool implementation file hashes;
- catalog builder version/hash;
- catalog row/value count;
- experiment contract;
- pricing snapshot;
- preflight.

- [ ] **Step 8: Run tests**

~~~bash
python -m pytest tests/test_text_to_sql_agentic_budget.py -q
~~~

Expected: PASS.

- [ ] **Step 9: Commit and push**

~~~bash
git add evaluation/text_to_sql_agentic/provenance.py evaluation/text_to_sql_agentic/budget.py tests/test_text_to_sql_agentic_budget.py
git commit -m "feat(eval): add agentic R2 provenance and budget gates"
git push origin master
~~~

---

### Task 11: Orchestrate E0-E3 and Enforce Gold Isolation

**Files:**
- Create: evaluation/text_to_sql_agentic/runner.py
- Create: tests/test_text_to_sql_agentic_gold_isolation.py
- Modify: tests/test_text_to_sql_agentic_runner.py

**Interfaces:**
- Produces: run_experiment(*, experiment_id: ExperimentId, cases: list[SQLBenchmarkCase], snapshot: DuckDBSnapshot, catalog: ValueCatalog, provider: LLMProvider, provenance: dict[str, Any], preflight: dict[str, Any], progress_callback: Callable[[dict[str, Any]], None] | None = None) -> dict[str, Any].
- Inner inference consumes AgenticCase only.
- Full SQLBenchmarkCase enters only after final_sql has been fixed for post-hoc evaluation.

- [ ] **Step 1: Write exact experiment-isolation tests**

For one case and scripted provider, assert:
- E0: no linker, no tool schemas, one generator call.
- E1: linker uses database tools; generator request has only submit_final_sql.
- E2: no linker; generator has database tools.
- E3: linker and generator both have database tools.

- [ ] **Step 2: Write end-to-end poison-gold test**

Create SQLBenchmarkCase with gold:

~~~sql
SELECT 'POISON_GOLD_LITERAL' AS secret
~~~

The user question does not contain that literal.

Script an E3 trajectory with profiler/search/probe calls and a final SQL.

Capture every provider message and every ToolEvent.

After run:

~~~python
serialized_inference = repr({
    "provider_calls": provider.calls,
    "linker_events": report["cases"][0]["linker"]["tool_events"],
    "generator_events": report["cases"][0]["generator"]["tool_events"],
})
assert "POISON_GOLD_LITERAL" not in serialized_inference
assert report["cases"][0]["execution_accurate"] in {True, False}
~~~

This proves gold is available only after submission for scoring.

- [ ] **Step 3: Implement gold-blind inference boundary**

Public inner function:

~~~python
def infer_case(
    case: AgenticCase,
    *,
    experiment_id: str,
    snapshot: DuckDBSnapshot,
    catalog: ValueCatalog,
    provider: LLMProvider,
) -> tuple[AgentStageResult | None, AgentStageResult]:
    contract = EXPERIMENTS[experiment_id]
    linker_result = None

    if contract.use_linker:
        runtime = ToolRuntime(snapshot=snapshot, catalog=catalog)
        linker_result = run_schema_linker(case, runtime, provider)
        if linker_result.status != "completed" or linker_result.linked_schema is None:
            failed_generator = AgentStageResult(
                stage="sql_generator",
                status="skipped_after_linker_failure",
                turns=0,
                database_tool_calls=0,
                error_category="LINKER_FORMAT_OR_LIMIT_FAILURE",
            )
            return linker_result, failed_generator

    if experiment_id == "E0":
        mode = "baseline_one_shot"
    elif experiment_id == "E1":
        mode = "linked_static"
    else:
        mode = "agentic"

    runtime = ToolRuntime(snapshot=snapshot, catalog=catalog)
    generator_result = run_sql_generator(
        case,
        snapshot=snapshot,
        catalog=catalog,
        provider=provider,
        linked_schema=linker_result.linked_schema if linker_result else None,
        mode=mode,
    )
    return linker_result, generator_result
~~~

Outer scoring function:

~~~python
def score_inferred_case(
    full_case: SQLBenchmarkCase,
    linker_result,
    generator_result,
    snapshot,
    experiment_id,
) -> AgenticCaseResult:
    final_sql = generator_result.final_sql
    if final_sql is None:
        return a model-failure AgenticCaseResult without calling evaluate_sql_case
    evaluation = evaluate_sql_case(full_case, final_sql, snapshot)
    return the completed case record
~~~

Do not pass full_case into infer_case.

- [ ] **Step 4: Implement E0-E3 orchestration**

E0:
- use static one-shot generator against full schema.

E1:
- run linker with tools;
- if linker fails, count case failure and do not call generator;
- otherwise static generator receives linked schema and no database tools.

E2:
- no linker;
- agentic generator gets full schema and database tools.

E3:
- run linker;
- if linker succeeds, agentic generator receives linked context and database tools;
- generator may profile/search/probe beyond linked subset.

- [ ] **Step 5: Implement model-vs-infrastructure failure semantics**

Model failures remain in a completed comparable run:
- linker malformed/limit failure;
- generator malformed/limit failure;
- unsafe SQL;
- syntax failure;
- query execution failure;
- result mismatch.

Infrastructure/provider failures invalidate the entire fixed run:
- ProviderError caused by outage/rate limit/timeout;
- wrong actual model/provider;
- missing required token usage;
- snapshot/benchmark/scorer/provenance mismatch;
- budget stop;
- duplicate/missing case IDs;
- dirty/unpinned evidence checkout.

- [ ] **Step 6: Persist only safe trajectory data**

Per case include:
- linked_schema;
- value_evidence;
- turn counts;
- database-tool events with bounded results;
- final SQL;
- evaluator fields;
- usage/cost/latency.

Do not store free-form hidden reasoning. Assistant prose content from intermediate turns is omitted from evidence artifacts unless it is needed to diagnose a format error; in that case store only a bounded error code and length, not content.

- [ ] **Step 7: Compute aggregate metrics**

Call aggregate_agentic_metrics and category/difficulty breakdown.

- [ ] **Step 8: Run all agentic offline tests**

~~~bash
python -m pytest   tests/test_text_to_sql_agentic_models.py   tests/test_text_to_sql_agentic_profiler.py   tests/test_text_to_sql_agentic_value_search.py   tests/test_text_to_sql_agentic_probe.py   tests/test_text_to_sql_agentic_tools.py   tests/test_text_to_sql_agentic_loop.py   tests/test_text_to_sql_agentic_schema_linker.py   tests/test_text_to_sql_agentic_sql_generator.py   tests/test_text_to_sql_agentic_runner.py   tests/test_text_to_sql_agentic_budget.py   tests/test_text_to_sql_agentic_gold_isolation.py   -q
~~~

Expected: PASS.

- [ ] **Step 9: Commit and push**

~~~bash
git add evaluation/text_to_sql_agentic/runner.py tests/test_text_to_sql_agentic_runner.py tests/test_text_to_sql_agentic_gold_isolation.py
git commit -m "feat(eval): orchestrate DualSQL-Lite R2 experiments"
git push origin master
~~~

---

### Task 12: Add Manual Evidence CLI and Workflow

**Files:**
- Create: scripts/run_r2_agentic_optimization.py
- Create: .github/workflows/r2-dualsql-lite-public-dev.yml
- Modify: tests/test_text_to_sql_agentic_runner.py

**Interfaces:**
- CLI supports experiment E0, E1, E2, E3 and public_dev only in evidence mode.
- workflow_dispatch is the only trigger.
- Evidence output is atomic and partial output survives failure.

- [ ] **Step 1: Define CLI arguments**

Required:
- --experiment with E0/E1/E2/E3;
- --snapshot;
- --snapshot-report;
- --cases;
- --version-lock;
- --output.

Optional:
- --preflight-only.

Evidence mode is always:
- provider openai;
- model gpt-4.1-mini-2025-04-14;
- temperature 0;
- completion cap 1000;
- retries 0.

Do not offer a --split frozen option in this public-dev CLI.

- [ ] **Step 2: Write CLI validation tests**

Reject before provider construction:
- unknown experiment;
- output file already exists;
- missing version lock;
- snapshot hash mismatch;
- logical snapshot content hash mismatch;
- case IDs/count/hash mismatch;
- scorer hash mismatch.

- [ ] **Step 3: Implement provider construction**

Use OpenAIProvider with:
- model pinned above;
- timeout_seconds=60;
- max_retries=0;
- request_overrides={"max_completion_tokens": 1000};
- pricing pinned to the same experiment snapshot rates used by budget.py.

Reject OPENAI_BASE_URL override for evidence runs.

- [ ] **Step 4: Implement atomic partial report**

Before first API call, write report with:
- run_status=preflight_complete;
- eligible=false;
- reason=model_run_incomplete;
- full provenance and preflight.

After every provider turn/case, rewrite via temporary file plus os.replace.

On successful completion:
- run_status=completed;
- eligible=true;
- ineligible_reasons=[].

On infrastructure failure:
- preserve partial report;
- eligible=false;
- record stable error category;
- exit non-zero.

- [ ] **Step 5: Add workflow_dispatch-only workflow**

Workflow requirements:
- permissions contents: read;
- checkout master exact triggering SHA;
- Python 3.11;
- install requirements;
- fetch/verify public-pilot sources with existing scripts;
- rebuild public snapshot;
- verify logical content hash against evaluation/public_pilot/VERSION.lock;
- run the requested E0-E3 experiment;
- always upload full or partial JSON artifact;
- never auto-commit evidence.

- [ ] **Step 6: Add workflow-shape regression test**

Read .github/workflows/r2-dualsql-lite-public-dev.yml as text and assert:
- contains workflow_dispatch;
- does not contain push trigger;
- does not contain pull_request trigger;
- does not contain schedule trigger;
- references only master evidence branch behavior.

- [ ] **Step 7: Run full test suite**

~~~bash
python -m pytest -q
~~~

Expected: all tests pass locally.

Push and wait for CI on Python 3.11 and 3.12 before any paid run.

- [ ] **Step 8: Commit and push**

~~~bash
git add scripts/run_r2_agentic_optimization.py .github/workflows/r2-dualsql-lite-public-dev.yml tests/test_text_to_sql_agentic_runner.py
git commit -m "ci(eval): add manual DualSQL-Lite public-dev runner"
git push origin master
~~~

---

### Task 13: Freeze the Evidence Commit and Run E0-E3 Once

**Files created after valid runs:**
- results/evaluation_v1/r2_optimization/<run-id>-E0.json
- results/evaluation_v1/r2_optimization/<run-id>-E1.json
- results/evaluation_v1/r2_optimization/<run-id>-E2.json
- results/evaluation_v1/r2_optimization/<run-id>-E3.json
- docs/r2_dualsql_lite_public_dev_results_2026-09-25.md

**Files modified:**
- docs/public_pilot_results_2026-09-25.md

**Interfaces:**
- All four runs use the exact same code commit, case split, snapshot content, scorer, model, temperature, pricing snapshot, and tool implementation.
- No code/prompt/tool change is allowed after E0 starts until E3 completes.

- [ ] **Step 1: Verify the freeze candidate**

Run:

~~~bash
git status --porcelain
git rev-parse HEAD
python -m pytest -q
~~~

Expected:
- empty git status;
- one master SHA recorded;
- all tests pass.

Verify GitHub CI for that SHA passes both Python 3.11 and 3.12.

- [ ] **Step 2: Run preflight-only for E0-E3**

For each experiment run the CLI with --preflight-only and the real public snapshot/cases.

Record:
- max model calls;
- input/output upper bound;
- cost ceiling.

Every ceiling must be below the configured $1.00 public-dev experiment budget before any paid run.

- [ ] **Step 3: Trigger one E0 evidence run**

After completion verify:
- run_status=completed;
- eligible=true;
- exactly 8 distinct case IDs;
- actual provider=openai;
- actual model=gpt-4.1-mini-2025-04-14 for every successful call;
- temperature 0;
- snapshot content SHA matches VERSION.lock;
- scorer hash matches frozen experiment scorer hash;
- usage complete;
- output artifact SHA recorded externally before commit.

If invalid, stop the series. Do not silently rerun after code/config changes and compare it with later experiments.

- [ ] **Step 4: Trigger E1, E2, E3 in order**

Repeat the exact validation checklist after each run.

All four runs must reference the same frozen implementation SHA.

- [ ] **Step 5: Preserve immutable JSON evidence**

Download the four workflow artifacts.

Verify each artifact's SHA-256 locally.

Commit unchanged JSON files to results/evaluation_v1/r2_optimization/.

- [ ] **Step 6: Write the public-dev comparison document**

The document must include this table with actual measured values:

~~~text
Experiment
Architecture
Correct / 8
Execution Accuracy
Syntax Validity
Execution Success
Safety Rejection
Avg Linker Turns
Avg Generator Turns
Avg DB Tool Calls
Input Tokens
Output Tokens
Cost USD
Latency
~~~

It must also include:
- per-case final SQL verdict;
- linker completion/failure for E1/E3;
- tool-use summary for E1/E2/E3;
- exact error category for each failure;
- exact E0 -> E_best case-count and percentage-point change;
- explicit statement that 8 public cases are diagnostic only;
- explicit statement that historical 2/8 scorer-v1 and 5/8 replay are not the E0 optimization baseline;
- provenance identities for the comparison.

- [ ] **Step 7: Apply the unchanged pilot-success rule**

E_best must improve by at least 2 cases out of 8 over newly run E0 to be described as a strong pilot signal.

If it improves by 0 or 1 case, report the exact gain and do not use strong-improvement language.

- [ ] **Step 8: Commit evidence and push**

~~~bash
git add results/evaluation_v1/r2_optimization docs/r2_dualsql_lite_public_dev_results_2026-09-25.md docs/public_pilot_results_2026-09-25.md
git commit -m "docs(eval): preserve DualSQL-Lite public-dev experiments"
git push origin master
~~~

---

### Task 14: Select and Freeze the Official-Dev Configuration

**Files:**
- Create: docs/r2_dualsql_lite_official_dev_config.md
- Modify: README.md
- Modify: docs/r2_dualsql_lite_public_dev_results_2026-09-25.md

**Interfaces:**
- Uses only public-dev evidence to select architecture.
- Does not inspect or run frozen.
- Official dev still waits for the verified ThreatFox + CTU-13 + OTRF snapshot gate.

- [ ] **Step 1: Select E_best with a predeclared tie rule**

Selection order:
1. highest Execution Accuracy;
2. if tied, lower total model cost;
3. if tied, fewer total model calls;
4. if tied, lower total latency;
5. if still tied, simpler architecture in order E0, E1, E2, E3.

Record the chosen experiment and rule in the config document.

- [ ] **Step 2: Freeze the machine-readable configuration**

Generate the exact JSON from the selected report and the already-defined EXPERIMENTS contract:

~~~python
rank = {"E0": 0, "E1": 1, "E2": 2, "E3": 3}
selected = min(
    reports,
    key=lambda report: (
        -report["aggregate_metrics"]["execution_accuracy"],
        report["total_cost_usd"],
        report["aggregate_metrics"]["total_model_calls"],
        report["aggregate_metrics"]["total_latency_ms"],
        rank[report["experiment_id"]],
    ),
)
contract = EXPERIMENTS[selected["experiment_id"]]
frozen_config = {
    "experiment_id": selected["experiment_id"],
    "provider": "openai",
    "model": "gpt-4.1-mini-2025-04-14",
    "temperature": 0,
    "max_completion_tokens": 1000,
    "max_retries": 0,
    "linker_enabled": contract.use_linker,
    "linker_tools_enabled": contract.linker_tools,
    "generator_tools_enabled": contract.generator_tools,
    "max_turns_per_stage": 5,
    "max_database_tool_calls_per_stage": 5,
}
~~~

Serialize frozen_config with sorted keys into the config document. This guarantees the booleans correspond to the measured winning experiment rather than being edited manually.

Also record:
- implementation git SHA;
- prompt hashes;
- tool schema hash;
- tool implementation hash;
- catalog hash/config;
- public snapshot hash;
- scorer hash.

- [ ] **Step 3: Add official-dev gate checklist**

The config document must state that official dev is blocked until:
- ThreatFox source is verified;
- CTU-13 source is verified;
- OTRF source is verified;
- three-source snapshot manifest exists;
- snapshot binary and logical content hashes exist;
- official dev case split is frozen;
- all gold SQL executes;
- scorer identity is frozen.

- [ ] **Step 4: Update README status**

Document:
- DualSQL-Lite is the active R2 optimization direction;
- CHASE-Lite design/plan is superseded;
- exact public-dev result;
- public-dev is diagnostic;
- official three-source dev is the next gate;
- frozen has not been used for architecture selection.

- [ ] **Step 5: Run final verification**

~~~bash
python -m pytest -q
git status --porcelain
~~~

Commit the docs, push master, and verify CI.

- [ ] **Step 6: Commit and push**

~~~bash
git add docs/r2_dualsql_lite_official_dev_config.md docs/r2_dualsql_lite_public_dev_results_2026-09-25.md README.md
git commit -m "docs(eval): freeze DualSQL-Lite official-dev config"
git push origin master
~~~

---

### Task 15: Official Dev, Error Analysis, and Final Frozen Gate

**Gate:** This task starts only after the existing official three-source R2 data gate passes. Do not create substitute/mock official data.

**Files created after real official-dev evidence:**
- results/evaluation_v1/r2_optimization/<run-id>-official-dev-E0.json
- results/evaluation_v1/r2_optimization/<run-id>-official-dev-Ebest.json
- docs/r2_dualsql_lite_official_dev_results.md
- docs/r2_dualsql_lite_error_analysis.md
- docs/r2_dualsql_lite_frozen_lock.md

**Interfaces:**
- Run only E0 and the already frozen E_best on official dev.
- No architecture selection from frozen.
- Frozen opens only after final lock is committed.

- [ ] **Step 1: Verify official snapshot/data gate**

Before a model call verify:
- exact source file hashes for ThreatFox, CTU-13, OTRF;
- manifest and provenance;
- snapshot content hash;
- dev/frozen split hashes;
- gold SQL validation;
- scorer hash;
- all config/tool/prompt hashes from the frozen official-dev config.

Any mismatch blocks the run.

- [ ] **Step 2: Run official-dev E0 and E_best once**

Use the same evidence workflow semantics:
- zero retries;
- budget preflight;
- partial artifact preservation;
- exact provider/model verification.

Do not re-tune prompts/tools between E0 and E_best.

- [ ] **Step 3: Write official-dev comparison**

Report:
- Execution Accuracy;
- absolute correct case counts;
- percentage-point delta;
- syntax/execution/safety;
- per-category/difficulty metrics;
- model/tool calls;
- tokens/cost/latency;
- public-dev vs official-dev consistency.

- [ ] **Step 4: Perform manual per-case error analysis**

For every failed E_best case, assign one diagnostic category from the approved taxonomy:
- LINKER_TABLE_OMISSION;
- LINKER_COLUMN_OMISSION;
- VALUE_GROUNDING_MISS;
- LINKER_FORMAT_OR_LIMIT_FAILURE;
- SQL_SCHEMA_RECOVERY_FAILURE;
- PREDICATE_ERROR;
- BOUNDARY_ERROR;
- AGGREGATION_ERROR;
- DISTINCT_ERROR;
- BOOLEAN_LOGIC;
- ORDERING_LIMIT;
- DIALECT_ERROR;
- SAFETY_REJECTION;
- EXECUTION_ERROR;
- GENERATOR_FORMAT_OR_LIMIT_FAILURE;
- PROVIDER_OR_INFRASTRUCTURE_FAILURE.

Support each label with the case question, linked schema/tool evidence, final SQL, and evaluator behavior. Do not feed these labels back into the same experiment.

- [ ] **Step 5: Freeze final configuration before frozen**

Write docs/r2_dualsql_lite_frozen_lock.md containing:
- git SHA;
- exact E_best contract;
- model/config;
- prompt hashes;
- tool schema/implementation hashes;
- search catalog hash/config;
- official snapshot hash;
- scorer hash;
- frozen split hash;
- official-dev result artifact hashes;
- statement "No further R2 optimization changes are permitted before frozen evaluation."

Commit and push this lock before opening frozen.

- [ ] **Step 6: Run frozen once**

Run E_best on frozen exactly once unless a documented infrastructure/provider failure makes the run invalid.

Do not use the frozen result to modify the architecture, prompt, tool policy, catalog, or scorer.

- [ ] **Step 7: Produce final before/after report**

Final report distinguishes:
- public-dev tuning evidence;
- official-dev confirmation;
- frozen final estimate;
- model-generation improvement vs scorer changes;
- error categories;
- compute/cost trade-off;
- limitations.

- [ ] **Step 8: Commit final evidence**

Commit immutable run artifacts and final docs directly to master only after verifying their hashes and CI.

---

## End-to-End Verification Checklist

Before claiming DualSQL-Lite implementation or experimentation complete:

- [ ] python -m pytest -q passes locally.
- [ ] GitHub CI passes Python 3.11 and 3.12.
- [ ] CHASE-Lite spec and plan remain visibly superseded.
- [ ] No RL/training/fine-tuning code was introduced.
- [ ] Existing R2 Execution Accuracy semantics remain unchanged.
- [ ] E0 is a new model run under the same comparison contract as E1-E3.
- [ ] Historical 5/8 replay is never presented as E0 model performance.
- [ ] Gold poison tests prove no leakage into agent inference or database tools.
- [ ] SQL probes reject write SQL, multi-statements, external readers, internal metadata, and provenance tables.
- [ ] Linker and generator turn/tool limits are tested.
- [ ] E0/E1/E2/E3 tool-access isolation is tested.
- [ ] Search output is bounded and catalog hash is deterministic.
- [ ] Paid workflow is manual-only.
- [ ] Preflight and per-call budget gates are fail-closed.
- [ ] Actual provider/model/usage are verified for every evidence run.
- [ ] Public-dev result is labeled diagnostic.
- [ ] E_best selection uses only public-dev.
- [ ] Official dev waits for real three-source data.
- [ ] Frozen remains sealed until final lock.
- [ ] Accuracy is always reported with absolute case counts, tokens, cost, latency, and error analysis.

## Expected Commit Sequence

~~~text
feat(eval): add gold-blind DualSQL-Lite contracts
feat(eval): add deterministic R2 database profiler
feat(eval): add deterministic R2 value search
feat(eval): add bounded read-only SQL probe
feat(eval): add DualSQL-Lite database tools
feat(eval): add bounded agentic tool loop
feat(eval): add DualSQL-Lite schema linker
feat(eval): add agentic R2 SQL generator
feat(eval): add DualSQL-Lite diagnostics
feat(eval): add agentic R2 provenance and budget gates
feat(eval): orchestrate DualSQL-Lite R2 experiments
ci(eval): add manual DualSQL-Lite public-dev runner
docs(eval): preserve DualSQL-Lite public-dev experiments
docs(eval): freeze DualSQL-Lite official-dev config
docs(eval): preserve DualSQL-Lite official and frozen evidence
~~~

Each commit is pushed directly to master and is independently reviewable.
