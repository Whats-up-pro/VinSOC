"""Offline release preflight, or a separately authorized matched E0/E3 run.

Defaults grant no paid permission. Preflight validates actual locked data and
never creates an OpenAI client. Private gates come from the operator, never
from historic credit balances or the network-demo authorization.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from evaluation.r2_cross_domain_v1.benchmark_lock import file_hash, validate_benchmark
from evaluation.r2_cross_domain_v1.release import CONDITIONS, preflight_release


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--preflight-only", action="store_true")
    parser.add_argument("--registry", type=Path, default=Path("evaluation/r2_cross_domain_v1/runtime_registry.json"))
    parser.add_argument("--benchmarks", type=Path, default=Path("evaluation/r2_cross_domain_v1/benchmarks"))
    parser.add_argument("--lock", type=Path, default=Path("evaluation/r2_cross_domain_v1/benchmark.lock.json"))
    parser.add_argument("--private-inputs", type=Path, help="Private account/pricing/budget/CI inputs; never an API key")
    parser.add_argument("--release", type=Path, help="Previously generated private release record, required for live")
    parser.add_argument("--ledger", type=Path, help="Canonical cross-domain ledger, required for live")
    parser.add_argument("--env-file", type=Path, default=Path(".env"))
    parser.add_argument("--output", type=Path, required=True, help="New JSON file for preflight, new directory for live")
    args = parser.parse_args(argv)
    if args.preflight_only:
        if args.output.exists():
            parser.error("Refusing to overwrite preflight output")
        private = json.loads(args.private_inputs.read_text(encoding="utf-8")) if args.private_inputs else {}
        try:
            validation = validate_benchmark(args.registry, args.benchmarks, args.lock)
            validated = True
            validation_error = None
        except Exception as error:
            validation, validated = None, False
            validation_error = type(error).__name__  # no raw source/private path
        runtime = json.loads((args.benchmarks/"evaluation_runtime.json").read_text(encoding="utf-8"))
        inventory = {"case_ids": [row["case_id"] for row in runtime], "case_count": len(runtime),
                     "conditions": list(CONDITIONS), "validated": validated,
                     "registry_path": str(args.registry), "benchmark_dir": str(args.benchmarks),
                     "benchmark_lock_path": str(args.lock)}
        identities = dict(private.get("identities", {}))
        identities.update(registry_sha256=file_hash(args.registry), benchmark_lock_sha256=file_hash(args.lock))
        source_paths = ("evaluation/r2_cross_domain_v1/live.py", "evaluation/r2_cross_domain_v1/release.py",
                        "evaluation/r2_cross_domain_v1/reporting.py", "evaluation/r2_cross_domain_v1/statistics.py",
                        "scripts/run_r2_cross_domain.py")
        identities["runtime_source_sha256"] = {p: file_hash(p, portable=True) for p in source_paths}
        result = preflight_release(inventory, identities, private.get("account", {}),
                                   private.get("pricing", {}), private.get("budget", {}))
        # Detailed private gate inputs stay in the operator output, never stdout.
        result["validation_diagnostic"] = {"passed": validated, "error_class": validation_error,
                                           "evidence": validation}
        # Additional diagnostics are outside the authorization digest; bind them
        # explicitly by retaining the exact immutable core release as generated.
        core = dict(result); core.pop("validation_diagnostic")
        args.output.parent.mkdir(parents=True, exist_ok=True)
        with args.output.open("x", encoding="utf-8") as handle:
            json.dump({"release": core, "validation": result["validation_diagnostic"]}, handle, indent=2, sort_keys=True)
        print(json.dumps({"status": result["status"], "reasons": result["reasons"], "max_requests": result["max_requests"],
                          "full_ceiling_usd": result["full_ceiling_usd"], "model_calls": 0, "client_created": False}))
        return 0 if result["authorized"] else 1
    if args.release is None or args.ledger is None:
        parser.error("Live requires --release and --ledger; demo permission does not authorize cross-domain inference")
    from evaluation.r2_cross_domain_v1.live import run_authorized_release
    raw = json.loads(args.release.read_text(encoding="utf-8"))
    release = raw.get("release", raw)
    result = run_authorized_release(release, case_ids=release.get("case_ids", []), conditions=CONDITIONS,
                                    output_dir=args.output, ledger_path=args.ledger, env_file=args.env_file)
    print(json.dumps({"status": result["status"], "attempted_calls": result["attempted_calls"],
                      "responses_received": result["responses_received"], "client_created": result["client_created"]}))
    return 0 if result["status"] == "completed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
