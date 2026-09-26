"""Stage one verified source probe as exact official R2 builder inputs."""

from __future__ import annotations

import argparse
import json
import shutil
import zipfile
from pathlib import Path
from typing import Any

from evaluation.text_to_sql_snapshot import sha256_file
from scripts.probe_r2_official_sources import OFFICIAL_SOURCES


_BUILDER_FORMATS = {
    "threatfox_full": "threatfox_csv",
    "ctu13_s3": "ctu13_binetflow",
    "otrf_apt29_day1": "sysmon_zip_jsonl",
}
_STAGED_NAMES = {
    "threatfox_full": "full.csv",
    "ctu13_s3": "capture20110812.binetflow",
    "otrf_apt29_day1": "apt29_evals_day1_manual.zip",
}


def _verify_file(path: Path, identity: dict[str, Any], label: str) -> None:
    if not path.is_file():
        raise ValueError(f"{label} does not exist: {path}")
    if path.stat().st_size != identity.get("bytes"):
        raise ValueError(f"{label} byte count mismatch")
    if sha256_file(path) != identity.get("sha256"):
        raise ValueError(f"{label} SHA-256 mismatch")


def stage_probe_output(
    *,
    probe_dir: Path,
    source_root: Path,
    dataset_manifest_path: Path,
    receipt_dir: Path,
) -> dict[str, Any]:
    """Verify probe bytes, stage inputs, and write credential-free provenance."""
    probe_dir = Path(probe_dir)
    source_root = Path(source_root)
    dataset_manifest_path = Path(dataset_manifest_path)
    receipt_dir = Path(receipt_dir)
    record = json.loads((probe_dir / "probe.json").read_text(encoding="utf-8"))
    if record.get("schema_version") != "r2_official_source_probe_v1" or record.get("status") != "verified_bytes":
        raise ValueError("Official source probe is not fully verified")
    by_id = {
        source.get("dataset_id"): source
        for source in record.get("sources", [])
        if isinstance(source, dict)
    }
    expected_ids = [source["dataset_id"] for source in OFFICIAL_SOURCES]
    if sorted(by_id) != sorted(expected_ids) or len(record.get("sources", [])) != 3:
        raise ValueError("Official source probe does not contain exactly three sources")

    source_root.mkdir(parents=True, exist_ok=True)
    receipt_dir.mkdir(parents=True, exist_ok=True)
    manifest_sources: list[dict[str, Any]] = []
    for specification in OFFICIAL_SOURCES:
        dataset_id = specification["dataset_id"]
        receipt = by_id[dataset_id]
        if (
            receipt.get("status") != "verified_bytes"
            or receipt.get("canonical_source_url") != specification["canonical_source_url"]
            or receipt.get("source_name") != specification["source_name"]
        ):
            raise ValueError(f"Official source receipt mismatch for {dataset_id}")
        raw_path = probe_dir / "raw" / specification["file_name"]
        _verify_file(raw_path, receipt["transport"], f"{dataset_id} transport")
        staged_path = source_root / _STAGED_NAMES[dataset_id]
        archive_member = None
        if dataset_id == "threatfox_full":
            member = receipt["ingest"].get("archive_member")
            with zipfile.ZipFile(raw_path) as archive:
                members = [item.filename for item in archive.infolist() if not item.is_dir()]
                if members != [member]:
                    raise ValueError("ThreatFox archive member changed after probe")
                with archive.open(member) as source, staged_path.open("wb") as target:
                    shutil.copyfileobj(source, target)
            file_identity = receipt["ingest"]
        else:
            shutil.copyfile(raw_path, staged_path)
            file_identity = receipt["transport"]
            if dataset_id == "otrf_apt29_day1":
                archive_member = receipt["ingest"].get("archive_member")
        _verify_file(staged_path, file_identity, f"{dataset_id} staged input")
        manifest_sources.append({
            "archive_member": archive_member,
            "dataset_id": dataset_id,
            "file_sha256": file_identity["sha256"],
            "format": _BUILDER_FORMATS[dataset_id],
            "license_note": receipt["license_note"],
            "path": staged_path.as_posix(),
            "retrieved_at": receipt["retrieved_at"],
            "source_name": receipt["source_name"],
            "source_url": receipt["canonical_source_url"],
        })
        (receipt_dir / f"{dataset_id}.json").write_text(
            json.dumps(receipt, sort_keys=True, indent=2) + "\n", encoding="utf-8"
        )

    manifest = {"schema_version": "1", "sources": manifest_sources}
    dataset_manifest_path.parent.mkdir(parents=True, exist_ok=True)
    dataset_manifest_path.write_text(
        json.dumps(manifest, sort_keys=True, indent=2) + "\n", encoding="utf-8"
    )
    return manifest


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--probe-dir", type=Path, required=True)
    parser.add_argument(
        "--source-root", type=Path, default=Path("data/official_r2/sources")
    )
    parser.add_argument(
        "--dataset-manifest",
        type=Path,
        default=Path("evaluation/text_to_sql_benchmarks/dataset_manifest.json"),
    )
    parser.add_argument(
        "--receipt-dir",
        type=Path,
        default=Path("evaluation/text_to_sql_benchmarks/source_receipts"),
    )
    args = parser.parse_args()
    manifest = stage_probe_output(
        probe_dir=args.probe_dir,
        source_root=args.source_root,
        dataset_manifest_path=args.dataset_manifest,
        receipt_dir=args.receipt_dir,
    )
    print(json.dumps({
        "source_ids": [source["dataset_id"] for source in manifest["sources"]],
        "source_file_sha256": {
            source["dataset_id"]: source["file_sha256"] for source in manifest["sources"]
        },
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
