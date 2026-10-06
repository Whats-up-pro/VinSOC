"""Offline metric contracts; deliberately wrong outputs are not model runs."""
from types import SimpleNamespace


def reference(alternatives):
    return SimpleNamespace(accepted_links=alternatives)


def alternative(columns, values=()):
    return {"tables": ["items"], "columns": [{"table": "items", "column": value} for value in columns],
            "relationships": [], "stored_values": list(values), "constraints": []}


def link(columns, values=()):
    return {"tables": ["items"], "columns": [{"table": "items", "column": value} for value in columns],
            "relationships": [], "grounded_values": list(values), "constraints": []}


def test_extra_and_missing_schema_items_have_exact_denominators():
    from evaluation.r2_cross_domain_v1.module_metrics import score_modules
    result = score_modules(reference([alternative(["id", "name"])]), {"linked_schema": link(["id", "wrong"])})
    metric = result["schema_linker"]["columns"]
    assert metric == {"correct": 1, "predicted": 2, "required": 2, "precision": .5, "recall": .5, "f1": .5}
    assert not result["schema_linker"]["case_success"]


def test_alternatives_use_one_consistent_reference_for_all_metrics():
    from evaluation.r2_cross_domain_v1.module_metrics import score_modules
    first = alternative(["id"], [{"table": "items", "column": "name", "operator": "=", "value": "Ada"}])
    second = alternative(["name"], [{"table": "items", "column": "name", "operator": "=", "value": "Bo"}])
    result = score_modules(reference([first, second]), {"linked_schema": link(["id"], [{"table": "items", "column": "name", "value": "Bo"}])})
    assert result["selected_alternative"] == 0
    assert result["schema_linker"]["columns"]["f1"] == 1
    assert result["value_grounding"]["predicates"]["f1"] == 0


def test_stage_absence_is_na_and_empty_reference_is_not_an_invented_denominator():
    from evaluation.r2_cross_domain_v1.module_metrics import score_modules, aggregate_module_metrics
    missing = score_modules(reference([alternative([])]), {"error_category": "TURN_LIMIT"})
    present = score_modules(reference([alternative([])]), {"linked_schema": link([])})
    assert missing["schema_linker"] is None
    assert present["schema_linker"]["columns"]["f1"] is None
    assert present["schema_linker"]["case_success"]
    summary = aggregate_module_metrics([missing, present])
    assert summary["schema_linker"]["coverage"] == {"available": 1, "total": 2}
    assert summary["schema_linker"]["case_success"] == {"correct": 1, "total": 1}


def test_unverified_witnesses_do_not_become_provenance_passes():
    from evaluation.r2_cross_domain_v1.module_metrics import score_modules
    result = score_modules(reference([alternative(["name"])]), {"linked_schema": link(["name"], [{"evidence_id": "invented", "table": "items", "column": "name", "value": "Ada"}])})
    assert result["value_grounding"]["witness_precision"] is None
    assert result["value_grounding"]["provenance_status"] == "CONTEXT_UNAVAILABLE"


def test_wrong_relationship_is_not_a_valid_join_path():
    from evaluation.r2_cross_domain_v1.module_metrics import score_modules
    wrong = link(["id"])
    wrong["relationships"] = [{"from_table": "items", "from_column": "id", "to_table": "other", "to_column": "id"}]
    result = score_modules(reference([alternative(["id"])]), {"linked_schema": wrong})
    assert not result["schema_linker"]["valid_relationship_path"]


def test_witness_hash_and_trajectory_do_not_prove_a_fabricated_value(tmp_path):
    import duckdb
    from evaluation.r2_cross_domain_v1.module_metrics import score_modules
    from evaluation.r2_cross_domain_v1.tools import witness_id
    snapshot = tmp_path / "fixture.duckdb"
    with duckdb.connect(str(snapshot)) as connection:
        connection.execute("CREATE TABLE items (name VARCHAR); INSERT INTO items VALUES ('Ada')")
    context = SimpleNamespace(database_id="fixture", snapshot_path=snapshot, identity={"logical_sha256": "fixture_identity",
        "schema": [{"name": "items", "columns": [{"name": "name", "duckdb_type": "VARCHAR"}]}], "relationships": []})
    witnesses = []
    for value in ("Ada", "fabricated"):
        witness = {"database_id": "fixture", "snapshot_identity": "fixture_identity", "table": "items", "column": "name", "type": "VARCHAR", "value": value}
        witness["evidence_id"] = witness_id(witness)
        witnesses.append(witness)
    record = {"linked_schema": link(["name"], witnesses), "trajectory": [{"tool": "value_search", "result": {"matches": witnesses}}]}
    metric = score_modules(reference([alternative(["name"])]), record, context)["value_grounding"]
    assert metric["witness_precision"] == {"correct": 1, "total": 2, "precision": .5}
    assert metric["unsupported_literal_rate"] == {"unsupported": 1, "total": 2, "rate": .5}
