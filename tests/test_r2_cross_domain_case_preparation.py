"""Case materialization is offline and cannot authorize an unlocked benchmark."""
import json
import sqlite3
from contextlib import closing

import pytest


@pytest.fixture
def inputs(tmp_path):
    from evaluation.r2_cross_domain_v1.data import DatabaseContext, build_duckdb_snapshot
    source = tmp_path / "items.sqlite"
    with closing(sqlite3.connect(source)) as conn, conn:
        conn.executescript("CREATE TABLE items(id INTEGER PRIMARY KEY); INSERT INTO items VALUES(1),(2)")
    receipt = build_duckdb_snapshot(source, tmp_path / "items.duckdb", "items")
    registry = tmp_path / "registry.json"
    registry.write_text(json.dumps({"databases": [{**receipt, "snapshot_path": "items.duckdb"}]}))
    candidate = {"case_id": "synthetic_candidate", "database_id": "items", "question": "Count all items", "difficulty": "medium", "features": [], "family_id": "fixture_family"}
    original = {"db_id": "items", "question": "Count all items", "query": "SELECT COUNT(*) FROM items -- SECRET_SENTINEL_GOLD"}
    return candidate, original, DatabaseContext.from_manifest(registry, "items"), source


def test_materialized_runtime_has_no_gold_and_reference_retains_provenance(inputs):
    from evaluation.r2_cross_domain_v1.case_preparation import materialize_external_reference
    candidate, original, context, source = inputs
    reference, runtime, parity = materialize_external_reference(candidate, original, context, source)
    assert set(runtime) == {"case_id", "database_id", "question"}
    assert "SECRET_SENTINEL_GOLD" not in json.dumps(runtime)
    assert reference["source_gold_sql"] == original["query"] and parity["parity"]
    assert reference["base_snapshot_binary_sha256"] == context.identity["duckdb_binary_sha256"]
    assert reference["benchmark_locked"] is False and reference["semantic_validation_status"] == "PENDING"


def test_changed_question_or_database_is_not_silently_materialized(inputs):
    from evaluation.r2_cross_domain_v1.case_preparation import materialize_external_reference
    from evaluation.r2_cross_domain_v1.benchmark import BenchmarkError
    candidate, original, context, source = inputs
    with pytest.raises(BenchmarkError, match="SOURCE_CASE_IDENTITY_MISMATCH"):
        materialize_external_reference({**candidate, "question": "Different question"}, original, context, source)
    with pytest.raises(BenchmarkError, match="SOURCE_CASE_IDENTITY_MISMATCH"):
        materialize_external_reference({**candidate, "database_id": "other"}, original, context, source)
