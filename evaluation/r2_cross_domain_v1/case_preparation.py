"""Pre-inference case materialization; this does not create a benchmark lock."""
from dataclasses import asdict

from sqlglot import parse_one

from .annotations import annotate_reference
from .benchmark import BenchmarkError, ReferenceCase, validate_gold_parity


def materialize_external_reference(candidate, original, context, source_path):
    if candidate["database_id"] != context.database_id or original["db_id"] != context.database_id or candidate["question"] != original["question"]:
        raise BenchmarkError("SOURCE_CASE_IDENTITY_MISMATCH")
    tree = parse_one(original["query"], read="sqlite")
    comparator = "ordered_rows" if tree.args.get("order") else "unordered_multiset"
    parity = validate_gold_parity(original["query"], source_path, context, comparator)
    if not parity["parity"]:
        raise BenchmarkError("GOLD_RESULT_PARITY_MISMATCH")
    reference = ReferenceCase(candidate["case_id"], context.database_id, candidate["question"], parity["adapted_sql"],
                              comparator, candidate["difficulty"], candidate["features"], candidate["family_id"],
                              annotate_reference(parity["adapted_sql"], context))
    private = {**asdict(reference), "source_gold_sql": original["query"],
               "source_sqlite_sha256": context.identity["source_sha256"],
               "base_snapshot_binary_sha256": context.identity["duckdb_binary_sha256"],
               "base_snapshot_logical_sha256": context.identity["logical_sha256"],
               "benchmark_locked": False, "semantic_validation_status": "PENDING",
               "annotation_validation_status": "DIRECT_SCHEMA_PREDICATES_ONLY_PENDING_FULL_VALIDATION",
               "source_license": "CC BY-SA 4.0", "source_attribution": "Spider 1.0, Yu et al. 2018, Yale-LILY/taoyds"}
    return private, asdict(reference.runtime()), parity
