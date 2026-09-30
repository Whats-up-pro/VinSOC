"""Read historical JSON flags; never execute SQL or reconstruct run-time identity."""
from __future__ import annotations

import hashlib
import json
import subprocess
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def audit_historical_reports(root: Path) -> dict[str, Any]:
    artifacts, conditions = {}, {}
    for name in ("baseline_e0", "v2_e3"):
        folder = root / name
        records = []
        for path in sorted(folder.glob("*.json")):
            try:
                raw = path.read_bytes()
                data = json.loads(raw)
            except (OSError, ValueError):
                raise ValueError(f"HISTORICAL_JSON_INVALID: {path.name}") from None
            artifacts[f"{name}/{path.name}"] = hashlib.sha256(raw).hexdigest()
            if path.name == "report.json":
                report = data
            else:
                records.append(data)
        if not records or not (folder / "report.json").is_file():
            raise ValueError(f"HISTORICAL_REPORT_MISSING: {name}")
        ids = [r.get("case_id") for r in records]
        accurate = sum(r.get("execution_accurate") is True for r in records)
        executed = sum(r.get("syntax_valid") is True for r in records)
        n = len(records)
        if (not all(isinstance(i, str) for i in ids) or len(set(ids)) != n
                or sorted(ids) != sorted(report.get("case_ids", []))
                or report.get("case_count") != n
                or report.get("metrics", {}).get("execution_accuracy") != f"{accurate}/{n}"
                or report.get("metrics", {}).get("syntax_valid") != f"{executed}/{n}"):
            raise ValueError(f"HISTORICAL_REPORT_MISMATCH: {name}")
        conditions[name] = {
            "case_count": n, "execution_accurate": accurate,
            "historical_execution_success_flags": executed,
            "syntax_validity_verified": False,
            "errors": dict(Counter(r.get("error_category", "UNKNOWN") for r in records)),
            "per_case_flags": [{k: r.get(k) for k in ("case_id", "execution_accurate", "syntax_valid", "error_category")} for r in records],
            "reported_cost_usd": report.get("total_cost_usd"),
        }
    return {
        "receipt_version": "r2_historical_audit_v1",
        "verification_time_utc": datetime.now(timezone.utc).isoformat(),
        "audited_repository_sha": subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip(),
        "artifact_sha256": artifacts, "conditions": conditions,
        "official_eligible": False, "cost_complete": False, "cost_unknown": True,
        "missing_run_time_provenance": ["implementation_sha", "exact_request_bytes", "response_ids", "complete_intermediate_usage", "retry_policy", "pre_run_ci", "preflight", "locked_winner", "snapshot_and_scorer_identity"],
        "hash_scope": "current artifact bytes at verification; not original code/request provenance",
        "reconstructed_fields": [], "inferred_fields": [],
    }


def write_receipt(path: Path, receipt: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8") as stream:
        json.dump(receipt, stream, indent=2, sort_keys=True)
        stream.write("\n")


def main() -> int:
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise FileExistsError("AUDIT_OUTPUT_EXISTS")
    receipt = audit_historical_reports(args.root)
    write_receipt(args.output, receipt)
    print(json.dumps(receipt["conditions"]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
