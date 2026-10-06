"""Execute new CTU gold only; this is not model inference or benchmark accuracy."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path

import duckdb

from evaluation.ctu_network_public.contract import validate
from evaluation.r2_cross_domain_v1.annotations import annotate_reference
from evaluation.r2_cross_domain_v1.ctu_cases import new_ctu_cases
from evaluation.r2_cross_domain_v1.data import DatabaseContext
from evaluation.r2_cross_domain_v1.tools import DatabaseTools


EXPECTED_BINARY = "0b29765b9a175d00e0a193039a1b058691406e28a434e10030ae78265cfa67b9"
EXPECTED_LOGICAL = "42c8e0a62441295cc5d95329a65dc22409c37de5b26a1e37dd56fbf0164a758c"


def audit(snapshot: Path, output: Path):
    if output.exists():
        raise ValueError("OUTPUT_ALREADY_EXISTS")
    binary = hashlib.sha256(snapshot.read_bytes()).hexdigest()
    if binary != EXPECTED_BINARY:
        raise ValueError("CTU_BINARY_IDENTITY_MISMATCH")
    validated = validate(snapshot)
    if validated["logical_snapshot_sha256"] != EXPECTED_LOGICAL:
        raise ValueError("CTU_LOGICAL_IDENTITY_MISMATCH")
    code_hashes = {name: hashlib.sha256(Path(name).read_bytes()).hexdigest() for name in (
        "scripts/audit_r2_cross_domain_ctu_cases.py", "evaluation/r2_cross_domain_v1/ctu_cases.py",
        "evaluation/r2_cross_domain_v1/annotations.py", "evaluation/r2_cross_domain_v1/safety.py",
        "evaluation/r2_cross_domain_v1/tools.py")}
    with duckdb.connect(str(snapshot), read_only=True) as conn:
        info = conn.execute("PRAGMA table_info(network_flows)").fetchall()
        keys = conn.execute("SELECT constraint_column_names FROM duckdb_constraints() WHERE table_name='network_flows' AND constraint_type='PRIMARY KEY'").fetchone()[0]
    schema = [{"name": "network_flows", "columns": [{"ordinal": row[0], "name": row[1], "duckdb_type": row[2],
                "sqlite_type": "", "not_null": row[3], "default": row[4],
                "primary_key_position": keys.index(row[1])+1 if row[1] in keys else 0} for row in info]}]
    # The legacy identity is verified above, not recomputed with the new generic
    # hashing algorithm or falsely presented as a generic registry identity.
    context = DatabaseContext("ctu_dev", snapshot, {"schema": schema, "relationships": [],
        "logical_sha256": EXPECTED_LOGICAL, "identity_algorithm": "ctu_network_public_dev_v1",
        "primary_keys": {"network_flows": keys}, "duckdb_binary_sha256": binary})
    results = []
    for case in new_ctu_cases():
        row = {**case, "gold_execution_success": False, "base_snapshot_binary_sha256": binary,
               "base_snapshot_logical_sha256": EXPECTED_LOGICAL, "semantic_validation_status": "PENDING"}
        try:
            response = DatabaseTools(context, row_cap=10000, payload_bytes=4_000_000).sql_probe({"sql": case["gold_sql"]})
            if response["truncated"]:
                raise ValueError("GOLD_RESULT_LIMIT")
            row.update({"accepted_links": annotate_reference(case["gold_sql"], context), "gold_execution_success": True,
                        "gold_row_count": len(response["rows"]), "sample_gold_rows": response["rows"][:3],
                        "observed_result_sha256": hashlib.sha256(json.dumps(response["rows"], default=str, sort_keys=True).encode()).hexdigest()})
        except Exception as error:
            row["error_code"] = str(error) if isinstance(error, ValueError) else type(error).__name__
        results.append(row)
    report = {"scope": "New CTU gold execution and direct annotations only; not model accuracy",
              "audited_at_utc": datetime.now(timezone.utc).isoformat(), "source_code_sha256_before_execution": code_hashes,
              "snapshot_binary_sha256": binary, "snapshot_logical_sha256": EXPECTED_LOGICAL,
              "identity_algorithm": "ctu_network_public_dev_v1", "legacy_source_validation": validated,
              "case_count": len(results), "gold_execution_success_count": sum(row["gold_execution_success"] for row in results),
              "benchmark_locked": False, "external_model_calls": 0, "new_inference_cost_usd": 0, "case_results": results}
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2, default=str) + "\n", encoding="utf-8", newline="\n")
    print(json.dumps({key: report[key] for key in ("case_count", "gold_execution_success_count", "benchmark_locked", "external_model_calls")}))
    return 0 if all(row["gold_execution_success"] for row in results) else 2


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--snapshot", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    return audit(args.snapshot, args.output)


if __name__ == "__main__":
    raise SystemExit(main())
