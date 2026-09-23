"""Tests for the frozen DuckDB boundary and Text-to-SQL evaluator.

Rows here are isolated test fixtures. They are never part of a VinSOC
benchmark snapshot or public-data provenance record.
"""

import pytest

from evaluation.text_to_sql import SQLBenchmarkCase, aggregate_sql_metrics, evaluate_sql_case
from skills.endpoint_skill import EndpointSkill
from skills.network_skill import NetworkSkill
from vinsoc_data.domain_queries import DuckDBEndpointRepository, DuckDBNetworkRepository
from vinsoc_data.duckdb_store import DuckDBSnapshot, QuerySafetyError, SocSnapshotBuilder


@pytest.fixture
def snapshot_path(tmp_path):
    path = tmp_path / "test_soc.duckdb"
    builder = SocSnapshotBuilder(path)
    builder.create_empty_snapshot()
    builder.register_provenance(
        dataset_id="test-public-fixture",
        source_name="test fixture only",
        source_url="https://example.invalid/test-fixture",
        retrieved_at="2026-09-18T00:00:00",
        file_sha256="0" * 64,
        license_note="Test-only fixture; not benchmark data.",
    )
    builder.insert_rows(
        "network_flows",
        [
            {
                "source_dataset": "test-public-fixture",
                "source_row_id": "flow-1",
                "event_time": "2024-01-15T08:00:00",
                "src_ip": "10.0.0.25",
                "src_port": 51000,
                "dst_ip": "185.220.101.45",
                "dst_port": 443,
                "protocol": "TCP",
                "action": "ALLOW",
                "bytes_out": 256,
                "bytes_in": 128,
                "label": "Botnet",
            }
        ],
        source_dataset="test-public-fixture",
    )
    builder.insert_rows(
        "sysmon_process_events",
        [
            {
                "source_dataset": "test-public-fixture",
                "source_row_id": "sysmon-1",
                "event_time": "2024-01-15T08:00:00",
                "host": "WS001",
                "event_id": 1,
                "parent_image": "winword.exe",
                "parent_pid": 2048,
                "image": "powershell.exe",
                "process_id": 4096,
                "command_line": "powershell.exe -enc AAA",
                "user_name": "user",
            }
        ],
        source_dataset="test-public-fixture",
    )
    return path


def test_snapshot_accepts_select_and_blocks_writes(snapshot_path):
    snapshot = DuckDBSnapshot(snapshot_path)
    result = snapshot.query("SELECT count(*) AS total FROM network_flows")
    assert result.rows == [{"total": 1}]

    with pytest.raises(QuerySafetyError):
        snapshot.query("DELETE FROM network_flows")
    with pytest.raises(QuerySafetyError):
        snapshot.query("WITH x AS (UPDATE network_flows SET action = 'DROP') SELECT * FROM x")
    with pytest.raises(QuerySafetyError):
        snapshot.query("SELECT * FROM network_flows; SELECT 1")


def test_domain_skills_read_the_frozen_snapshot(snapshot_path):
    from vinsoc_data.network_source import DuckDBNetworkDataSource
    snapshot = DuckDBSnapshot(snapshot_path)
    network_repo = DuckDBNetworkRepository(snapshot)
    network_ds = DuckDBNetworkDataSource(network_repo)
    network = NetworkSkill(data_sources=[network_ds])
    endpoint = EndpointSkill(repository=DuckDBEndpointRepository(snapshot))

    # Test network data
    network_result = network.execute(indicator="185.220.101.45", indicator_type="ipv4")
    assert network_result.success
    # Note: Connection count depends on snapshot data

    # Test endpoint data
    endpoint_result = endpoint.execute(host="ws001")
    assert endpoint_result.success
    assert len(endpoint_result.data["process_tree"]) > 0
    assert endpoint_result.data["process_tree"][0]["parent"] == "winword.exe"
    assert endpoint_result.data["suspicious_relationships"][0]["mitre_technique"] == "T1059.001"


def test_text_to_sql_uses_execution_equivalence_and_hard_safety_gate(snapshot_path):
    snapshot = DuckDBSnapshot(snapshot_path)
    case = SQLBenchmarkCase(
        case_id="SQL-TEST-001",
        question="Count flows to the indicator.",
        database_snapshot="test_soc.duckdb",
        gold_sql=("SELECT count(*) AS total FROM network_flows WHERE dst_ip = '185.220.101.45'",),
        category="filter",
        difficulty="basic",
        result_comparator="scalar",
    )

    correct = evaluate_sql_case(
        case,
        "SELECT count(*) AS n FROM network_flows WHERE dst_ip = '185.220.101.45'",
        snapshot,
    )
    rejected = evaluate_sql_case(case, "DROP TABLE network_flows", snapshot)
    invalid_syntax = evaluate_sql_case(case, "SELECT FROM network_flows", snapshot)

    assert correct.syntax_valid and correct.execution_success and correct.execution_accurate
    assert rejected.syntax_valid and rejected.safety_rejected and not rejected.execution_success
    assert not invalid_syntax.syntax_valid and not invalid_syntax.execution_success
    metrics = aggregate_sql_metrics([correct, rejected])
    assert metrics["execution_accuracy"] == 0.5
    assert metrics["safety_rejection_rate"] == 0.5
