"""Offline CTU source preparation and gated one-condition workflow entrypoint."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import subprocess
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from evaluation.ctu_network_public.contract import validate as validate_dev_contract
from evaluation.dualsql_lite_ctu_gpt5.contract import SERIES_LOCK
from evaluation.dualsql_lite_ctu_gpt5.runner import run_condition
from scripts.build_ctu_network_public_snapshot import build_ctu_network_snapshot

MANIFEST = Path("evaluation/ctu_network_public/dataset_manifest.json")
EXPECTED_SOURCES = {"ctu13_s5", "ctu13_s7"}
EXPECTED_ROWS = 243906
MODEL = "gpt-5-mini-2025-08-07"


def _sources(manifest_path: Path = MANIFEST) -> list[dict[str, Any]]:
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    sources = manifest.get("sources", [])
    if ({source.get("dataset_id") for source in sources} != EXPECTED_SOURCES
            or len(sources) != 2):
        raise ValueError("Pinned manifest must contain exactly S5 and S7")
    source_root = (Path.cwd() / "data/ctu_network_public/sources").resolve()
    for source in sources:
        target = (Path.cwd() / source["path"]).resolve()
        if (not target.is_relative_to(source_root)
                or not source["source_url"].startswith(
                    "https://mcfp.felk.cvut.cz/publicDatasets/")
                or len(source["file_sha256"]) != 64):
            raise ValueError("CTU source path, URL, or digest is outside the pinned boundary")
    return sources


def _download_pinned(source: dict[str, Any]) -> None:
    target = Path(source["path"])
    target.parent.mkdir(parents=True, exist_ok=True)
    digest = hashlib.sha256()
    with urllib.request.urlopen(source["source_url"], timeout=120) as response:
        with target.open("xb") as destination:
            while chunk := response.read(1024 * 1024):
                digest.update(chunk)
                destination.write(chunk)
    if digest.hexdigest() != source["file_sha256"]:
        raise ValueError(f"Pinned source checksum mismatch: {source['dataset_id']}")


def prepare(snapshot_dir: Path, evidence_dir: Path) -> dict[str, Any]:
    """Download only pinned S5/S7 bytes and independently validate two builds."""
    sources = _sources(MANIFEST)
    snapshot_dir = Path(snapshot_dir)
    evidence_dir = Path(evidence_dir)
    snapshot_dir.mkdir(parents=True, exist_ok=False)
    evidence_dir.mkdir(parents=True, exist_ok=True)
    for source in sources:
        _download_pinned(source)
    facts = []
    for name in ("a", "b"):
        snapshot = snapshot_dir / f"ctu-dev-{name}.duckdb"
        build = build_ctu_network_snapshot(MANIFEST, snapshot)
        contract = validate_dev_contract(snapshot)
        if (contract["row_counts"]["network_flows"] != EXPECTED_ROWS
                or contract["logical_snapshot_sha256"] != build["content_sha256"]):
            raise ValueError("CTU dev build count or logical hash mismatch")
        with (evidence_dir / f"build-{name}.json").open("x", encoding="utf-8") as handle:
            json.dump({"builder": build, "contract": contract}, handle, sort_keys=True, indent=2)
        facts.append(contract)
    if (facts[0]["logical_snapshot_sha256"] != facts[1]["logical_snapshot_sha256"]
            or facts[0]["source_row_counts"] != facts[1]["source_row_counts"]):
        raise ValueError("Independent CTU builds differ")
    return {"logical_snapshot_sha256": facts[0]["logical_snapshot_sha256"],
            "row_count": EXPECTED_ROWS,
            "source_file_sha256": {item["dataset_id"]: item["file_sha256"]
                                   for item in sources}}


def _recent_utc(value: str) -> bool:
    try:
        checked = datetime.fromisoformat(value.replace("Z", "+00:00"))
        age = datetime.now(timezone.utc) - checked.astimezone(timezone.utc)
        return -300 <= age.total_seconds() <= 24 * 3600
    except (ValueError, AttributeError):
        return False


def _runtime_gates() -> dict[str, Any]:
    """Consume fresh billing/pricing attestations supplied outside the repository."""
    def number(name: str) -> float:
        value = float(os.environ[name])
        if not math.isfinite(value) or value < 0:
            raise ValueError(f"Invalid {name}")
        return value

    price_time = os.environ.get("OPENAI_PRICE_CHECKED_UTC", "")
    credit_time = os.environ.get("OPENAI_CREDIT_CHECKED_UTC", "")
    if not _recent_utc(price_time) or not _recent_utc(credit_time):
        raise ValueError("Official price or account credit check is stale")
    if not os.environ.get("OPENAI_ORGANIZATION_ID") or not os.environ.get("OPENAI_PROJECT_ID"):
        raise ValueError("OpenAI organization/project identity is unavailable")
    return {"current_input_usd_per_million": number("OPENAI_CURRENT_INPUT_USD_M"),
            "current_output_usd_per_million": number("OPENAI_CURRENT_OUTPUT_USD_M"),
            "pricing_checked_utc": price_time,
            "credit_checked_utc": credit_time,
            "organization_project_verified": True,
            "usable_credit_usd": number("OPENAI_USABLE_CREDIT_USD"),
            "spend_limit_remaining_usd": number("OPENAI_SPEND_LIMIT_REMAINING_USD"),
            "cumulative_known_usd": number("VINSOC_CUMULATIVE_KNOWN_USD"),
            "total_authorized_usd": 2.0}


def run(condition: str, snapshot_dir: Path, evidence_dir: Path) -> dict[str, Any]:
    """Create the SDK client only after the runner's offline cost gates pass."""
    if condition not in {"E1", "E2", "E3"}:
        raise ValueError("Invalid paid condition")
    if (os.environ.get("GITHUB_REF") != "refs/heads/master"
            or os.environ.get("GITHUB_RUN_ATTEMPT") != "1"
            or os.environ.get("OPENAI_EVAL_MODEL") != MODEL):
        raise ValueError("Checkout, attempt, or model identity gate failed")
    actual_sha = subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip()
    if actual_sha != os.environ.get("GITHUB_SHA"):
        raise ValueError("GITHUB_SHA differs from checkout HEAD")
    if not os.environ.get("OPENAI_API_KEY"):
        raise ValueError("OpenAI project credential is unavailable")
    series_lock = json.loads(SERIES_LOCK.read_text(encoding="utf-8"))
    series_lock["runtime_gates"] = _runtime_gates()

    def client_factory():
        from openai import OpenAI

        return OpenAI(api_key=os.environ["OPENAI_API_KEY"],
                      organization=os.environ["OPENAI_ORGANIZATION_ID"],
                      project=os.environ["OPENAI_PROJECT_ID"], max_retries=0)

    evidence_dir = Path(evidence_dir)
    output = evidence_dir / f"{condition.lower()}-{os.environ['GITHUB_RUN_ID']}.json"
    result = run_condition(condition, Path(snapshot_dir) / "ctu-dev-a.duckdb",
                           output, client_factory, series_lock)
    payload = result.payload
    receipt = {"run_id": os.environ["GITHUB_RUN_ID"], "condition": condition,
               "implementation_sha": actual_sha, "report_sha256": hashlib.sha256(
                   output.read_bytes()).hexdigest(),
               "execution_accurate": payload["metrics"]["execution_accurate"],
               "known_cost_usd": payload["known_cost_usd"],
               "model_calls": len(payload["provider_calls"])}
    with (evidence_dir / "receipt.json").open("x", encoding="utf-8") as handle:
        json.dump(receipt, handle, sort_keys=True, indent=2)
    return receipt


def cleanup(snapshot_dir: Path) -> None:
    """Remove only the exact ephemeral source and snapshot files."""
    for source in _sources(MANIFEST):
        Path(source["path"]).unlink(missing_ok=True)
    for name in ("a", "b"):
        (Path(snapshot_dir) / f"ctu-dev-{name}.duckdb").unlink(missing_ok=True)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("prepare", "run", "cleanup"))
    parser.add_argument("--snapshot-dir", type=Path, required=True)
    parser.add_argument("--evidence-dir", type=Path)
    parser.add_argument("--condition", choices=("E1", "E2", "E3"))
    args = parser.parse_args()
    if args.action == "prepare":
        if args.evidence_dir is None:
            parser.error("--evidence-dir is required")
        print(json.dumps(prepare(args.snapshot_dir, args.evidence_dir), sort_keys=True))
    elif args.action == "run":
        if args.evidence_dir is None or args.condition is None:
            parser.error("--evidence-dir and --condition are required")
        print(json.dumps(run(args.condition, args.snapshot_dir, args.evidence_dir), sort_keys=True))
    else:
        cleanup(args.snapshot_dir)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
