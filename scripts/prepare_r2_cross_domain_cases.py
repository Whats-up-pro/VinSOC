"""Materialize qualified external candidates offline; full benchmark remains closed."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path

from evaluation.r2_cross_domain_v1.case_preparation import materialize_external_reference
from evaluation.r2_cross_domain_v1.data import DatabaseContext, verify_archive_member, verify_archive_sha256
from evaluation.r2_cross_domain_v1.selection import select_external_candidates


def _sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def prepare(metadata: Path, sources: Path, qualification: Path, output: Path):
    if output.exists():
        raise ValueError("OUTPUT_ALREADY_EXISTS")
    manifest_path, registry_path = metadata / "source_manifest.json", metadata / "database_registry.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    registry = json.loads(registry_path.read_text(encoding="utf-8"))
    pool = json.loads(qualification.read_text(encoding="utf-8"))
    if pool["manifest_sha256"] != _sha(manifest_path) or pool["registry_sha256"] != _sha(registry_path) or not pool["all_registered_database_quotas_met"]:
        raise ValueError("QUALIFICATION_IDENTITY_OR_QUOTA_MISMATCH")
    archive = sources / manifest["archive_filename"]
    verify_archive_sha256(archive, manifest["archive_sha256"])
    dev_path = sources / manifest["split_member"]
    verify_archive_member(archive, manifest["split_member"], dev_path)
    raw = json.loads(dev_path.read_text(encoding="utf-8"))
    good = {case["case_id"] for case in pool["case_results"] if case["status"] == "BASE_PARITY_VERIFIED"}
    qualified, lookup = [], {}
    for case in raw:
        identity = json.dumps({"db_id": case["db_id"], "question": " ".join(case["question"].split()), "sql": case["sql"]}, sort_keys=True)
        case_id = "external_" + case["db_id"] + "_" + hashlib.sha256(identity.encode()).hexdigest()[:16]
        lookup[case_id] = case
        if case_id in good:
            qualified.append(case)
    selected = select_external_candidates(qualified, registry["databases"], seed=20261005)
    contexts = {}
    for entry in registry["databases"]:
        source = sources / entry["source_sqlite_member"]
        verify_archive_member(archive, entry["source_sqlite_member"], source)
        contexts[entry["database_id"]] = (DatabaseContext.from_manifest(registry_path, entry["database_id"]), source)
    output.mkdir(parents=True, exist_ok=False)
    produced, errors = [], []
    for split in ("calibration", "evaluation"):
        (output / split).mkdir()
        runtime_rows = []
        for candidate in selected[split]:
            context, source = contexts[candidate["database_id"]]
            try:
                reference, runtime, parity = materialize_external_reference(candidate, lookup[candidate["case_id"]], context, source)
                reference["split"] = split
                path = output / split / (candidate["case_id"] + ".json")
                path.write_text(json.dumps({"reference": reference, "base_gold_parity": parity}, ensure_ascii=False, indent=2, default=str) + "\n", encoding="utf-8", newline="\n")
                runtime_rows.append(runtime)
                produced.append({"case_id": candidate["case_id"], "path": path.relative_to(output).as_posix(), "sha256": _sha(path)})
            except Exception as error:
                errors.append({"case_id": candidate["case_id"], "error_code": str(error) if isinstance(error, ValueError) else type(error).__name__})
        (output / (split + "_runtime.json")).write_text(json.dumps(runtime_rows, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
    excluded = [{"case_id": case["case_id"], "database_id": case["database_id"], "reason": case.get("error_code", case["status"])} for case in pool["case_results"] if case["status"] != "BASE_PARITY_VERIFIED"]
    receipt = {"scope": "External candidate materialization only; CTU and semantic gates pending",
               "prepared_at_utc": datetime.now(timezone.utc).isoformat(), "source_archive_sha256": manifest["archive_sha256"],
               "dev_member_sha256": _sha(dev_path), "registry_sha256": _sha(registry_path), "qualification_sha256": _sha(qualification),
               "selection_seed": 20261005, "selection": selected, "produced": produced, "errors": errors,
               "pre_inference_exclusions": excluded, "external_cases_produced": len(produced),
               "benchmark_locked": False, "release_eligible": False, "external_model_calls": 0, "new_inference_cost_usd": 0,
               "license": "CC BY-SA 4.0", "attribution": "Spider 1.0, Yu et al. 2018, Yale-LILY/taoyds"}
    (output / "materialization_receipt.json").write_text(json.dumps(receipt, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
    print(json.dumps({"produced": len(produced), "errors": errors, "benchmark_locked": False, "external_model_calls": 0}))
    return 0 if len(produced) == 80 and not errors else 2


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--metadata", type=Path, default=Path("evaluation/r2_cross_domain_v1"))
    parser.add_argument("--sources", type=Path, default=Path("data/r2_cross_domain_v1/sources"))
    parser.add_argument("--qualification", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    return prepare(args.metadata, args.sources, args.qualification, args.output)


if __name__ == "__main__":
    raise SystemExit(main())
