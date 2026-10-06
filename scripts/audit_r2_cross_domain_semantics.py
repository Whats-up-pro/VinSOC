"""Candidate-only semantic audit, no provider or benchmark lock creation."""
import argparse
from contextlib import closing
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import sqlite3
from types import SimpleNamespace

from evaluation.r2_cross_domain_v1.annotations import annotate_reference
from evaluation.r2_cross_domain_v1.benchmark import BenchmarkError, _verify_limit_determinism
from evaluation.r2_cross_domain_v1.data import DatabaseContext, _quote
from evaluation.r2_cross_domain_v1.fixture_generation import generate_fixture_spec
from evaluation.r2_cross_domain_v1.semantic_instances import audit_semantics, build_fixture, equivalent_controls, generate_mutants
from evaluation.r2_cross_domain_v1.semantic_scoring import compare_results
from evaluation.r2_cross_domain_v1.tools import DatabaseTools, _json_value


def write_record(path, record):
    encoded = json.dumps(record, ensure_ascii=False, indent=2, default=_json_value) + "\n"
    with Path(path).open("x", encoding="utf-8", newline="\n") as handle:
        handle.write(encoded)


def sqlite_fixture_parity(reference, spec, instance, destination):
    if destination.exists():
        raise ValueError("SQLITE_FIXTURE_ALREADY_EXISTS")
    with closing(sqlite3.connect(destination)) as connection, connection:
        connection.execute("PRAGMA foreign_keys=ON")
        for table in spec["schema"]:
            definitions = []
            for column in table["columns"]:
                kind = column.get("sqlite_type") or column["duckdb_type"]
                if not re.fullmatch(r"[A-Za-z0-9_ (),]+", kind):
                    raise ValueError("UNSAFE_FIXTURE_SQLITE_TYPE")
                definitions.append(_quote(column["name"]) + " " + kind + (" NOT NULL" if column.get("not_null") else ""))
            keys = sorted([column for column in table["columns"] if column.get("primary_key_position")], key=lambda column: column["primary_key_position"])
            if keys:
                definitions.append("PRIMARY KEY (" + ",".join(_quote(column["name"]) for column in keys) + ")")
            connection.execute(f"CREATE TABLE {_quote(table['name'])} ({','.join(definitions)})")
            rows = spec["rows"][table["name"]]
            if rows:
                connection.executemany(f"INSERT INTO {_quote(table['name'])} VALUES ({','.join('?' for _ in table['columns'])})", rows)
        sqlite_rows = connection.execute(reference["source_gold_sql"]).fetchall()
    import duckdb
    tie_status = "PASS"
    with duckdb.connect(str(instance["context"].snapshot_path), read_only=True) as connection:
        try:
            _verify_limit_determinism(reference["gold_sql"], connection)
        except BenchmarkError as error:
            tie_status = str(error)
    _, duck_rows, truncated = DatabaseTools(instance["context"], row_cap=10000)._execute(reference["gold_sql"])
    if truncated:
        raise ValueError("FIXTURE_GOLD_RESULT_LIMIT")
    return {"parity": compare_results(duck_rows, sqlite_rows, reference["comparator"]), "ordering_validation": tie_status,
            "sample_sqlite_rows": sqlite_rows[:3], "sample_duckdb_rows": duck_rows[:3]}


def read_references(candidates, ctu, *, external_only=False):
    references = [json.loads(path.read_text(encoding="utf-8"))["reference"] for path in sorted(candidates.glob("*/*.json"))]
    if not external_only:
        if ctu is None or ctu.get("gold_execution_success_count") != 40:
            raise ValueError("CTU_GOLD_AUDIT_INCOMPLETE")
        references.extend(ctu["case_results"])
    if (not references or len({item["case_id"] for item in references}) != len(references)
        or not external_only and len(references) != 120):
        raise ValueError("CANDIDATE_INVENTORY_INCOMPLETE")
    return references


def audit(registry, candidates, ctu_audit, output, builds, *, external_only=False):
    if output.exists() or builds.exists():
        raise ValueError("OUTPUT_OR_BUILD_ALREADY_EXISTS")
    registry_bytes = registry.read_bytes()
    ctu = None if external_only else json.loads(ctu_audit.read_text(encoding="utf-8"))
    context_cache = {}
    references = read_references(candidates, ctu, external_only=external_only)
    # The legacy CTU audit already validated source+binary/logical identities;
    # this stage rechecks the binary before using its publicly observed schema.
    if ctu is not None:
        ctu_snapshot = Path("data/ctu_network_public/snapshots/ctu_dev.duckdb")
        if hashlib.sha256(ctu_snapshot.read_bytes()).hexdigest() != ctu["snapshot_binary_sha256"]:
            raise ValueError("CTU_BINARY_IDENTITY_MISMATCH")
        import duckdb
        with duckdb.connect(str(ctu_snapshot), read_only=True) as connection:
            columns = connection.execute("PRAGMA table_info(network_flows)").fetchall()
            keys = connection.execute("SELECT constraint_column_names FROM duckdb_constraints() WHERE table_name='network_flows' AND constraint_type='PRIMARY KEY'").fetchone()[0]
        ctu_schema = [{"name": "network_flows", "columns": [{"name": row[1], "duckdb_type": row[2], "not_null": row[3], "primary_key_position": keys.index(row[1])+1 if row[1] in keys else 0} for row in columns]}]
        context_cache["ctu_dev"] = DatabaseContext("ctu_dev", ctu_snapshot, {"schema": ctu_schema, "relationships": [], "logical_sha256": ctu["snapshot_logical_sha256"]})
    ctu_hash = None if ctu is None else hashlib.sha256(ctu_audit.read_bytes()).hexdigest()
    producer_hashes = {path: hashlib.sha256(Path(path).read_bytes()).hexdigest() for path in (
        "scripts/audit_r2_cross_domain_semantics.py", "evaluation/r2_cross_domain_v1/annotations.py",
        "evaluation/r2_cross_domain_v1/fixture_generation.py", "evaluation/r2_cross_domain_v1/semantic_instances.py",
        "evaluation/r2_cross_domain_v1/semantic_scoring.py", "evaluation/r2_cross_domain_v1/safety.py")}
    output.mkdir(parents=True)
    builds.mkdir(parents=True)
    write_record(output / "started_receipt.json", {"started_at_utc": datetime.now(timezone.utc).isoformat(),
        "source_code_sha256_before_execution": producer_hashes, "registry_sha256": hashlib.sha256(registry_bytes).hexdigest(),
        "ctu_audit_sha256": ctu_hash, "case_ids": [item["case_id"] for item in references],
        "external_model_calls": 0, "benchmark_locked": False})
    results = []
    for reference in references:
        database = reference["database_id"]
        if database not in context_cache:
            context_cache[database] = DatabaseContext.from_manifest(registry, database)
        context = context_cache[database]
        record = {"case_id": reference["case_id"], "database_id": database, "split": reference["split"], "status": "UNFINISHED"}
        try:
            instances, parity = [], []
            for variant in range(2):
                spec = generate_fixture_spec(context, reference["gold_sql"], variant=variant)
                name = reference["case_id"] + "_" + str(variant)
                write_record(output / (name + ".fixture.json"), spec)
                instance = build_fixture(spec, builds / (name + ".duckdb"))
                instances.append(instance)
                if reference.get("source_gold_sql"):
                    parity.append(sqlite_fixture_parity(reference, spec, instance, builds / (name + ".sqlite")))
            semantic = audit_semantics(SimpleNamespace(**reference), instances, generate_mutants(reference["gold_sql"]), equivalent_controls(reference["gold_sql"]))
            record.update({"semantic": semantic, "fixture_sqlite_duckdb_parity": parity,
                           "updated_annotations": annotate_reference(reference["gold_sql"], context),
                           "fixture_identities": [{key: value for key, value in item.items() if key != "context"} | {"logical_sha256": item["context"].identity["logical_sha256"]} for item in instances]})
            record["status"] = "PASS" if all(item["parity"] and item["ordering_validation"] == "PASS" for item in parity) and semantic["semantic_mutants_killed"] > 0 and semantic["equivalent_controls_accepted"] > 0 else "SEMANTIC_COVERAGE_OR_PARITY_BLOCKED"
        except Exception as error:
            record.update({"status": "FIXTURE_AUDIT_ERROR", "error_type": type(error).__name__, "safe_error_code": str(error) if isinstance(error, ValueError) else None})
        results.append(record)
        write_record(output / (reference["case_id"] + ".audit.json"), record)
    receipt = {"scope": "candidate_semantic_validation_not_benchmark_or_model_score", "created_at_utc": datetime.now(timezone.utc).isoformat(),
               "source_code_sha256_before_execution": producer_hashes, "registry_sha256": hashlib.sha256(registry_bytes).hexdigest(),
               "ctu_audit_sha256": ctu_hash, "inventory_scope": "source_qualification_subset" if external_only else "complete_candidates", "case_count": len(results),
               "passed": sum(item["status"] == "PASS" for item in results), "blocked": [item for item in results if item["status"] != "PASS"],
               "external_model_calls": 0, "new_inference_cost_usd": 0, "benchmark_locked": False}
    write_record(output / "receipt.json", receipt)
    print(json.dumps({key: receipt[key] for key in ("case_count", "passed", "external_model_calls", "benchmark_locked")}))
    return 0 if receipt["passed"] == len(results) else 2


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--registry", type=Path, default=Path("evaluation/r2_cross_domain_v1/database_registry.json"))
    parser.add_argument("--candidates", type=Path, default=Path("evaluation/r2_cross_domain_v1/offline_task3/external_case_candidates"))
    parser.add_argument("--ctu-audit", type=Path, default=Path("evaluation/r2_cross_domain_v1/offline_task3/ctu_new_case_audit_v2.json"))
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--builds", type=Path, required=True)
    parser.add_argument("--external-only", action="store_true", help="Offline source qualification subset; never an accepted complete benchmark")
    args = parser.parse_args()
    return audit(args.registry, args.candidates, args.ctu_audit, args.output, args.builds, external_only=args.external_only)


if __name__ == "__main__":
    raise SystemExit(main())
