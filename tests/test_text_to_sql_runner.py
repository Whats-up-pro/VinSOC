"""R2 Text-to-SQL generation runner tests."""

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


def test_r2_benchmark_splits_are_nonempty_and_disjoint():
    runner = TextToSQLRunner.__new__(TextToSQLRunner)
    runner.benchmarks_dir = __import__("pathlib").Path("evaluation/text_to_sql_benchmarks")

    dev_ids = {case.case_id for case in runner.load_cases("dev")}
    frozen_ids = {case.case_id for case in runner.load_cases("frozen")}

    assert dev_ids
    assert frozen_ids
    assert dev_ids.isdisjoint(frozen_ids)


def test_r2_benchmark_report_aggregates_execution_accuracy(tmp_path):
    snapshot = _snapshot(tmp_path)
    benchmarks = tmp_path / "benchmarks"
    dev = benchmarks / "dev"
    dev.mkdir(parents=True)
    (dev / "sql_001.json").write_text(
        """{
          "case_id": "sql_001",
          "question": "How many network flows are present?",
          "database_snapshot": "r2.duckdb",
          "gold_sql": ["SELECT count(*) AS total FROM network_flows"],
          "result_comparator": "scalar"
        }""",
        encoding="utf-8",
    )

    report = run_text_to_sql_benchmark(
        snapshot_path=snapshot.database_path,
        split="dev",
        provider=FakeSQLProvider("SELECT count(*) AS n FROM network_flows"),
        benchmarks_dir=benchmarks,
    )

    assert report["case_count"] == 1
    assert report["metrics"]["execution_accuracy"] == 1.0
    assert report["error_summary"] == {"OK": 1}
    assert report["cases"][0]["case_id"] == "sql_001"
