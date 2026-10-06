"""Pre-inference case materialization; this does not create a benchmark lock."""
from dataclasses import asdict
import hashlib
import json
from pathlib import Path

from sqlglot import parse_one

from .annotations import annotate_reference
from .benchmark import BenchmarkError, ReferenceCase, validate_gold_parity


def read_semantic_exclusions(paths):
    excluded = []
    for path in paths:
        path = Path(path)
        raw = path.read_bytes()
        receipt = json.loads(raw)
        if (receipt.get("scope") != "candidate_semantic_validation_not_benchmark_or_model_score"
            or receipt.get("external_model_calls") != 0 or receipt.get("benchmark_locked") is not False):
            raise BenchmarkError("PRE_INFERENCE_EXCLUSION_EVIDENCE_REQUIRED")
        for record in receipt["blocked"]:
            parity = record.get("fixture_sqlite_duckdb_parity", [])
            proved = [item for item in parity if isinstance(item, dict) and
                      (item.get("parity") is False or item.get("ordering_validation", "").startswith("AMBIGUOUS_"))]
            if proved:
                excluded.append({"case_id": record["case_id"], "reason": "SOURCE_DIALECT_OR_ORDER_SEMANTICS_UNVERIFIED",
                                 "evidence": path.as_posix(), "evidence_sha256": hashlib.sha256(raw).hexdigest(),
                                 "observed_failures": proved})
    return excluded


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
               "annotation_validation_status": "EXHAUSTIVE_PARSED_STRUCTURE_PENDING_SEMANTIC_REVIEW",
               "source_license": "CC BY-SA 4.0", "source_attribution": "Spider 1.0, Yu et al. 2018, Yale-LILY/taoyds"}
    return private, asdict(reference.runtime()), parity
