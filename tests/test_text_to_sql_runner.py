"""R2 Text-to-SQL generation runner tests."""

import json

import pytest

from agent.provider import LLMResponse
from evaluation.text_to_sql import (
    SQLBenchmarkCase,
    TextToSQLRunner,
    evaluate_sql_case,
    run_text_to_sql_benchmark,
)
from vinsoc_data.duckdb_store import DuckDBSnapshot, SocSnapshotBuilder


class FakeSQLProvider:
    def __init__(self, sql):
        self.sql = sql
        self.last_call = None

    def generate(self, messages, tools=None, system_prompt=None, temperature=0.0):
        self.last_call = {
            "messages": messages,
            "tools": tools,
            "system_prompt": system_prompt,
            "temperature": temperature,
        }
        return LLMResponse(
            content=self.sql,
            tool_calls=[],
            raw={},
            metadata={"latency_ms": 4.5, "input_tokens": 20, "output_tokens": 8},
        )

    def get_name(self):
        return "fake-sql"

    def reset_tracking(self):
        pass

    def get_run_metadata(self):
        return {"total_calls": 1}


def _snapshot(tmp_path):
    path = tmp_path / "r2.duckdb"
    builder = SocSnapshotBuilder(path)
    builder.create_empty_snapshot()
    builder.register_provenance(
        dataset_id="test-r2",
        source_name="test-only",
        source_url="https://example.invalid/r2",
        retrieved_at="2026-09-23T00:00:00",
        file_sha256="1" * 64,
        license_note="test fixture",
    )
    builder.insert_rows(
        "network_flows",
        [
            {
                "source_dataset": "test-r2",
                "source_row_id": "flow-1",
                "event_time": "2026-09-23T00:00:00",
                "src_ip": "10.0.0.1",
                "src_port": 12345,
                "dst_ip": "198.51.100.7",
                "dst_port": 443,
                "protocol": "TCP",
                "action": "ALLOW",
                "bytes_out": 100,
                "bytes_in": 50,
                "label": "test",
            },
            {
                "source_dataset": "test-r2",
                "source_row_id": "flow-2",
                "event_time": "2026-09-23T00:01:00",
                "src_ip": "10.0.0.2",
                "src_port": 12346,
                "dst_ip": "198.51.100.7",
                "dst_port": 443,
                "protocol": "TCP",
                "action": "ALLOW",
                "bytes_out": 120,
                "bytes_in": 60,
                "label": "test",
            },
            {
                "source_dataset": "test-r2",
                "source_row_id": "flow-3",
                "event_time": "2026-09-23T00:02:00",
                "src_ip": "10.0.0.3",
                "src_port": 12347,
                "dst_ip": "203.0.113.8",
                "dst_port": 80,
                "protocol": "TCP",
                "action": "ALLOW",
                "bytes_out": 90,
                "bytes_in": 40,
                "label": "test",
            },
        ],
        source_dataset="test-r2",
    )
    return DuckDBSnapshot(path)


def test_r2_runner_uses_schema_context_and_execution_accuracy(tmp_path):
    snapshot = _snapshot(tmp_path)
    case = SQLBenchmarkCase(
        case_id="sql_runner_001",
        question="How many network flows are present?",
        database_snapshot="r2.duckdb",
        gold_sql=("SELECT count(*) AS total FROM network_flows",),
        category="aggregation",
        difficulty="basic",
        result_comparator="scalar",
    )
    provider = FakeSQLProvider("SELECT count(*) AS n FROM network_flows")
    runner = TextToSQLRunner(snapshot=snapshot, provider=provider)

    run = runner.run_case(case)

    assert run.generated_sql == "SELECT count(*) AS n FROM network_flows"
    assert run.evaluation.execution_accurate is True
    assert run.error_category == "OK"
    assert "network_flows" in provider.last_call["system_prompt"]
    assert "src_ip" in provider.last_call["system_prompt"]
    assert provider.last_call["tools"] is None
    assert provider.last_call["messages"] == [{"role": "user", "content": case.question}]


def test_r2_runner_cannot_bypass_read_only_safety(tmp_path):
    snapshot = _snapshot(tmp_path)
    case = SQLBenchmarkCase(
        case_id="sql_runner_002",
        question="Remove all network flows.",
        database_snapshot="r2.duckdb",
        gold_sql=("SELECT count(*) AS total FROM network_flows",),
        category="filter",
        difficulty="basic",
        result_comparator="scalar",
    )
    runner = TextToSQLRunner(
        snapshot=snapshot,
        provider=FakeSQLProvider("DELETE FROM network_flows"),
    )

    run = runner.run_case(case)

    assert run.evaluation.safety_rejected is True
    assert run.error_category == "SAFETY_REJECTION"


def test_execution_accuracy_rejects_semantically_wrong_query_on_counterexample(tmp_path):
    snapshot = _snapshot(tmp_path)
    case = SQLBenchmarkCase(
        case_id="semantic_trap_001",
        question="How many distinct destination IPs are present?",
        database_snapshot="r2.duckdb",
        gold_sql=("SELECT count(DISTINCT dst_ip) AS total FROM network_flows",),
        category="distinct",
        difficulty="basic",
        result_comparator="scalar",
    )

    result = evaluate_sql_case(
        case,
        "SELECT count(*) AS total FROM network_flows",
        snapshot,
    )

    assert result.syntax_valid is True
    assert result.execution_success is True
    assert result.execution_accurate is False


def test_unordered_rows_preserves_duplicate_multiplicity(tmp_path):
    snapshot = _snapshot(tmp_path)
    case = SQLBenchmarkCase(
        case_id="unordered_multiplicity_001",
        question="Return each protocol once.",
        database_snapshot="r2.duckdb",
        gold_sql=("SELECT DISTINCT protocol FROM network_flows",),
        category="distinct",
        difficulty="basic",
        result_comparator="unordered_rows",
    )

    result = evaluate_sql_case(case, "SELECT protocol FROM network_flows", snapshot)

    assert result.execution_accurate is False


def test_r2_benchmark_splits_are_nonempty_and_disjoint():
    runner = TextToSQLRunner.__new__(TextToSQLRunner)
    runner.benchmarks_dir = __import__("pathlib").Path("evaluation/text_to_sql_benchmarks")

    dev_ids = {case.case_id for case in runner.load_cases("dev")}
    frozen_ids = {case.case_id for case in runner.load_cases("frozen")}

    assert dev_ids
    assert frozen_ids
    assert dev_ids.isdisjoint(frozen_ids)


def test_r2_benchmark_cases_have_valid_category_and_difficulty():
    runner = TextToSQLRunner.__new__(TextToSQLRunner)
    runner.benchmarks_dir = __import__("pathlib").Path("evaluation/text_to_sql_benchmarks")
    allowed_categories = {
        "filter",
        "time_range",
        "aggregation",
        "distinct",
        "ordering_limit",
        "cti",
        "network",
        "endpoint",
    }
    allowed_difficulties = {"basic", "intermediate", "advanced"}

    cases = runner.load_cases("dev") + runner.load_cases("frozen")

    assert cases
    for case in cases:
        assert case.category in allowed_categories
        assert case.difficulty in allowed_difficulties


def test_sql_case_loader_rejects_missing_coverage_metadata():
    with pytest.raises(ValueError, match="category and difficulty"):
        SQLBenchmarkCase.from_dict(
            {
                "case_id": "missing_metadata",
                "question": "How many rows?",
                "database_snapshot": "snapshot.duckdb",
                "gold_sql": ["SELECT count(*) FROM network_flows"],
                "result_comparator": "scalar",
            }
        )


def test_r2_benchmark_report_aggregates_execution_accuracy(tmp_path):
    snapshot = _snapshot(tmp_path)
    benchmarks = tmp_path / "benchmarks"
    dev = benchmarks / "dev"
    dev.mkdir(parents=True)
    (dev / "sql_001.json").write_text(
        """{
          "case_id": "sql_001",
          "question": "How many network flows are present?",
              "database_snapshot": "SNAPSHOT_PATH",
              "gold_sql": ["SELECT count(*) AS total FROM network_flows"],
              "category": "aggregation",
              "difficulty": "basic",
              "result_comparator": "scalar"
        }""".replace("SNAPSHOT_PATH", str(snapshot.database_path)),
        encoding="utf-8",
    )
    from evaluation.text_to_sql_snapshot import sha256_file

    manifest = tmp_path / "snapshot_manifest.json"
    manifest.write_text(
        json.dumps(
            {
                "snapshot_id": snapshot.database_path.stem,
                "path": str(snapshot.database_path),
                "sha256": sha256_file(snapshot.database_path),
                "schema_version": "1",
            }
        ),
        encoding="utf-8",
    )

    report = run_text_to_sql_benchmark(
        snapshot_path=snapshot.database_path,
        manifest_path=manifest,
        split="dev",
        provider=FakeSQLProvider("SELECT count(*) AS n FROM network_flows"),
        benchmarks_dir=benchmarks,
    )

    assert report["case_count"] == 1
    assert report["snapshot_id"] == snapshot.database_path.stem
    assert report["snapshot_sha256"] == sha256_file(snapshot.database_path)
    assert report["metrics"]["execution_accuracy"] == 1.0
    assert report["category_metrics"] == {
        "aggregation": {
            "case_count": 1,
            "syntax_validity_rate": 1.0,
            "execution_success_rate": 1.0,
            "execution_accuracy": 1.0,
        }
    }
    assert report["error_summary"] == {"OK": 1}
    assert report["cases"][0]["case_id"] == "sql_001"


def test_snapshot_verification_fails_before_provider_call(tmp_path):
    snapshot = _snapshot(tmp_path)
    benchmarks = tmp_path / "benchmarks"
    (benchmarks / "dev").mkdir(parents=True)
    provider = FakeSQLProvider("SELECT count(*) FROM network_flows")
    manifest = tmp_path / "snapshot_manifest.json"
    manifest.write_text(
        json.dumps(
            {
                "snapshot_id": snapshot.database_path.stem,
                "path": str(snapshot.database_path),
                "sha256": "0" * 64,
                "schema_version": "1",
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="SHA-256"):
        run_text_to_sql_benchmark(
            snapshot_path=snapshot.database_path,
            manifest_path=manifest,
            split="dev",
            provider=provider,
            benchmarks_dir=benchmarks,
        )

    assert provider.last_call is None


def test_ordered_rows_comparator_detects_wrong_top_k_order(tmp_path):
    snapshot = _snapshot(tmp_path)
    case = SQLBenchmarkCase(
        case_id="ordered_001",
        question="Return source IPs ordered by bytes_out descending.",
        database_snapshot="r2.duckdb",
        gold_sql=("SELECT src_ip FROM network_flows ORDER BY bytes_out DESC",),
        category="ordering_limit",
        difficulty="intermediate",
        result_comparator="ordered_rows",
    )

    result = evaluate_sql_case(
        case,
        "SELECT src_ip FROM network_flows ORDER BY bytes_out ASC",
        snapshot,
    )

    assert result.execution_success is True
    assert result.execution_accurate is False


def test_boundary_operator_semantic_trap(tmp_path):
    snapshot = _snapshot(tmp_path)
    case = SQLBenchmarkCase(
        case_id="boundary_001",
        question="How many flows sent more than 100 bytes?",
        database_snapshot="r2.duckdb",
        gold_sql=("SELECT count(*) FROM network_flows WHERE bytes_out > 100",),
        category="filter",
        difficulty="basic",
        result_comparator="scalar",
    )

    result = evaluate_sql_case(
        case,
        "SELECT count(*) FROM network_flows WHERE bytes_out >= 100",
        snapshot,
    )

    assert result.execution_accurate is False


def test_boolean_predicate_semantic_trap(tmp_path):
    snapshot = _snapshot(tmp_path)
    case = SQLBenchmarkCase(
        case_id="boolean_001",
        question="How many TCP flows used destination port 443?",
        database_snapshot="r2.duckdb",
        gold_sql=(
            "SELECT count(*) FROM network_flows "
            "WHERE protocol = 'TCP' AND dst_port = 443",
        ),
        category="filter",
        difficulty="intermediate",
        result_comparator="scalar",
    )

    result = evaluate_sql_case(
        case,
        "SELECT count(*) FROM network_flows WHERE protocol = 'TCP' OR dst_port = 443",
        snapshot,
    )

    assert result.execution_accurate is False


def test_top_k_correct_rows_in_wrong_order_is_inaccurate(tmp_path):
    snapshot = _snapshot(tmp_path)
    case = SQLBenchmarkCase(
        case_id="top_k_order_001",
        question="Return the two highest-byte source IPs in descending order.",
        database_snapshot="r2.duckdb",
        gold_sql=(
            "SELECT src_ip FROM network_flows ORDER BY bytes_out DESC LIMIT 2",
        ),
        category="ordering_limit",
        difficulty="intermediate",
        result_comparator="ordered_rows",
    )

    result = evaluate_sql_case(
        case,
        "SELECT src_ip FROM network_flows "
        "WHERE src_ip IN ('10.0.0.1', '10.0.0.2') ORDER BY bytes_out ASC",
        snapshot,
    )

    assert result.execution_accurate is False
