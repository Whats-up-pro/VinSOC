"""Real DuckDB fixtures for the inference-time database boundary."""

import json

import pytest

from vinsoc_data.duckdb_store import SocSnapshotBuilder


@pytest.fixture
def snapshot(tmp_path):
    path = tmp_path / "test.duckdb"
    builder = SocSnapshotBuilder(path)
    builder.create_empty_snapshot()
    for dataset in ("ctu13_s5", "ctu13_s7"):
        builder.register_provenance(dataset_id=dataset, source_name=dataset,
                                    source_url="https://example.invalid/test",
                                    retrieved_at="2026-09-25T00:00:00Z",
                                    file_sha256="0" * 64, license_note="test fixture")
    builder.insert_rows("network_flows", [
        {"source_dataset": "ctu13_s5", "source_row_id": "1",
         "event_time": "2011-08-15T12:00:00", "src_ip": "10.0.0.1",
         "dst_ip": "8.8.8.8", "label": "flow=From-Botnet-TCP"},
    ], source_dataset="ctu13_s5")
    builder.insert_rows("network_flows", [
        {"source_dataset": "ctu13_s7", "source_row_id": "2",
         "event_time": "2011-08-16T12:00:00", "src_ip": "10.0.0.2",
         "dst_ip": "8.8.4.4", "label": "flow=Background-TCP"},
    ], source_dataset="ctu13_s7")
    return path


def test_profiler_and_value_catalog_are_deterministic_and_grounded(snapshot):
    from evaluation.dualsql_lite.tools import DatabaseTools

    first = DatabaseTools(snapshot)
    second = DatabaseTools(snapshot)
    profile = first.profiler({})
    assert profile == second.profiler({})
    assert "dataset_provenance" not in json.dumps(profile)
    assert first.catalog_sha256 == second.catalog_sha256
    result = first.value_search({"query": "scenario 5", "table": "network_flows",
                                 "column": "source_dataset"})
    assert result["matches"][0] == {
        "table": "network_flows", "column": "source_dataset", "value": "ctu13_s5"
    }
    assert len(result["matches"]) <= 50
    assert len(json.dumps(result).encode()) <= 8192


@pytest.mark.parametrize("sql", [
    "DELETE FROM network_flows",
    "SELECT 1; SELECT 2",
    "SELECT * FROM dataset_provenance",
    'SELECT * FROM "dataset_provenance"',
    "SELECT * FROM information_schema.columns",
    "SELECT * FROM read_csv('/etc/passwd')",
    "SELECT * FROM read_parquet('https://example.invalid/a.parquet')",
    "SELECT * FROM sqlite_scan('file', 'table')",
    "SELECT * FROM network_flows WHERE label = 'https://example.invalid/a'",
])
def test_probe_rejects_unsafe_or_internal_sql(snapshot, sql):
    from evaluation.dualsql_lite.tools import DatabaseTools

    result = DatabaseTools(snapshot).sql_probe({"sql": sql})
    assert result["ok"] is False
    assert result["error_type"] == "SAFETY_REJECTION"


def test_probe_bounded_zero_rows_and_bad_sql(snapshot):
    from evaluation.dualsql_lite.tools import DatabaseTools

    tools = DatabaseTools(snapshot)
    assert tools.sql_probe({"sql": "SELECT dst_ip FROM network_flows WHERE dst_ip='0.0.0.0'"}) == {
        "ok": True, "columns": ["dst_ip"], "rows": [], "truncated": False
    }
    assert tools.sql_probe({"sql": "SELECT FROM network_flows"})["error_type"] == "EXECUTION_ERROR"
    result = tools.sql_probe({"sql": "SELECT dst_ip FROM network_flows"})
    assert result["ok"] and len(result["rows"]) <= 20
    assert len(json.dumps(result).encode()) <= 8192


def test_tool_dispatch_rejects_malformed_arguments(snapshot):
    from evaluation.dualsql_lite.tools import DatabaseTools

    tools = DatabaseTools(snapshot)
    assert tools.invoke("value_search", {"query": 12})["error_type"] == "INVALID_ARGUMENTS"
    assert tools.invoke("unknown_tool", {})["error_type"] == "UNKNOWN_TOOL"


def test_final_evaluator_uses_snapshot_only_connection(snapshot):
    from evaluation.dualsql_lite.tools import SnapshotOnlyDuckDBSnapshot
    from vinsoc_data.duckdb_store import QuerySafetyError

    reader = SnapshotOnlyDuckDBSnapshot(snapshot)
    assert list(reader.query("SELECT count(*) FROM network_flows;").rows[0].values()) == [2]
    with pytest.raises(QuerySafetyError):
        reader.query("SELECT * FROM dataset_provenance")
    with reader._connect() as connection:
        assert connection.execute("SELECT current_setting('enable_external_access')").fetchone()[0] is False
