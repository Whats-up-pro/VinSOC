"""Download and hash the complete official R2 source inputs.

Raw bytes stay in the requested output directory. Receipts deliberately use
credential-free source URLs and never serialize the ThreatFox download URL.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Mapping
from urllib.request import Request, urlopen


THREATFOX_CANONICAL_URL = "https://threatfox.abuse.ch/export/"
THREATFOX_DOWNLOAD_PREFIX = "https://threatfox-api.abuse.ch/v2/files/exports/"
OTRF_MEMBER = "apt29_evals_day1_manual_2020-05-01225525.json"

OFFICIAL_SOURCES = (
    {
        "dataset_id": "threatfox_full",
        "source_name": "ThreatFox full CSV export",
        "canonical_source_url": THREATFOX_CANONICAL_URL,
        "file_name": "threatfox_full.csv.zip",
        "format": "threatfox_csv_zip",
        "license_note": "ThreatFox data export; retain abuse.ch attribution and comply with its terms.",
    },
    {
        "dataset_id": "ctu13_s3",
        "source_name": "CTU-13 Scenario 3",
        "canonical_source_url": (
            "https://mcfp.felk.cvut.cz/publicDatasets/"
            "CTU-Malware-Capture-Botnet-44/detailed-bidirectional-flow-labels/"
            "capture20110812.binetflow"
        ),
        "file_name": "capture20110812.binetflow",
        "format": "ctu13_binetflow",
        "license_note": "MCFP permits use with attribution to Sebastian Garcia and the Malware Capture Facility Project.",
    },
    {
        "dataset_id": "otrf_apt29_day1",
        "source_name": "OTRF APT29 Day 1 Sysmon",
        "canonical_source_url": (
            "https://raw.githubusercontent.com/OTRF/Security-Datasets/master/"
            "datasets/compound/apt29/day1/apt29_evals_day1_manual.zip"
        ),
        "file_name": "apt29_evals_day1_manual.zip",
        "format": "sysmon_zip_jsonl",
        "license_note": "Retain OTRF attribution; resolve the repository README/LICENSE discrepancy before redistributing source bytes.",
    },
)


def _copy_hash(source, target) -> tuple[int, str]:
    digest = hashlib.sha256()
    size = 0
    while chunk := source.read(1024 * 1024):
        target.write(chunk)
        digest.update(chunk)
        size += len(chunk)
    return size, digest.hexdigest()


def download_complete(url: str, target: Path, *, opener: Callable = urlopen) -> dict[str, Any]:
    """Store a response only after EOF and declared Content-Length agree."""
    target = Path(target)
    target.parent.mkdir(parents=True, exist_ok=True)
    partial = target.with_suffix(target.suffix + ".partial")
    partial.unlink(missing_ok=True)
    request = Request(url, headers={"User-Agent": "VinSOC-official-evaluation/1.0"})
    try:
        with opener(request, timeout=180) as response, partial.open("wb") as handle:
            size, digest = _copy_hash(response, handle)
            declared = response.headers.get("Content-Length")
        if declared is not None and int(declared) != size:
            raise ValueError(f"Content-Length mismatch: declared {declared}, received {size}")
        os.replace(partial, target)
        return {"bytes": size, "sha256": digest}
    finally:
        partial.unlink(missing_ok=True)


def inspect_zip_member(path: Path, expected_member: str) -> dict[str, Any]:
    """Hash the exact uncompressed archive member consumed by the builder."""
    with zipfile.ZipFile(path) as archive:
        members = [item for item in archive.infolist() if not item.is_dir()]
        if [item.filename for item in members] != [expected_member]:
            raise ValueError(f"Archive must contain exactly member {expected_member}")
        with archive.open(members[0]) as handle:
            size, digest = _copy_hash(handle, _NullWriter())
    return {"archive_member": expected_member, "bytes": size, "sha256": digest}


class _NullWriter:
    def write(self, data: bytes) -> int:
        return len(data)


def _safe_error(dataset_id: str, exc: Exception) -> dict[str, str]:
    if dataset_id == "threatfox_full":
        return {"type": type(exc).__name__, "message": "ThreatFox download or archive verification failed"}
    return {"type": type(exc).__name__, "message": str(exc)[:300]}


def _write_receipts(output: Path, record: dict[str, Any]) -> None:
    (output / "probe.json").write_text(
        json.dumps(record, sort_keys=True, indent=2) + "\n", encoding="utf-8"
    )
    receipt_dir = output / "receipts"
    receipt_dir.mkdir(exist_ok=True)
    for source in record["sources"]:
        (receipt_dir / f"{source['dataset_id']}.json").write_text(
            json.dumps(source, sort_keys=True, indent=2) + "\n", encoding="utf-8"
        )


def probe(output: Path, *, environ: Mapping[str, str] | None = None,
          opener: Callable = urlopen, retrieved_at: str | None = None) -> dict[str, Any]:
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    raw = output / "raw"
    raw.mkdir(exist_ok=True)
    environment = os.environ if environ is None else environ
    timestamp = retrieved_at or datetime.now(timezone.utc).isoformat()
    record: dict[str, Any] = {
        "schema_version": "r2_official_source_probe_v1", "status": "partial", "sources": []
    }
    for source in OFFICIAL_SOURCES:
        item = {key: source[key] for key in (
            "dataset_id", "source_name", "canonical_source_url", "format", "license_note"
        )}
        item["retrieved_at"] = timestamp
        record["sources"].append(item)
        try:
            if source["dataset_id"] == "threatfox_full":
                secret = environment.get("THREATFOX_AUTH_KEY")
                if not secret:
                    item["status"] = "failed"
                    item["error"] = {"type": "MissingSecret",
                                     "message": "THREATFOX_AUTH_KEY unavailable"}
                    _write_receipts(output, record)
                    continue
                download_url = THREATFOX_DOWNLOAD_PREFIX + secret + "/full.csv.zip"
            else:
                download_url = source["canonical_source_url"]
            path = raw / source["file_name"]
            item["transport"] = download_complete(download_url, path, opener=opener)
            if source["dataset_id"] == "threatfox_full":
                item["ingest"] = inspect_zip_member(path, "full.csv")
            elif source["dataset_id"] == "otrf_apt29_day1":
                item["ingest"] = inspect_zip_member(path, OTRF_MEMBER)
            else:
                item["ingest"] = dict(item["transport"])
            item["status"] = "verified_bytes"
        except Exception as exc:
            item.pop("transport", None)
            item.pop("ingest", None)
            item["status"] = "failed"
            item["error"] = _safe_error(source["dataset_id"], exc)
        finally:
            _write_receipts(output, record)
    if all(source["status"] == "verified_bytes" for source in record["sources"]):
        record["status"] = "verified_bytes"
        _write_receipts(output, record)
    return record


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    result = probe(parser.parse_args().output)
    print(json.dumps({"status": result["status"], "sources": [
        {key: item.get(key) for key in ("dataset_id", "status", "transport", "ingest", "error")
         if key in item} for item in result["sources"]
    ]}, sort_keys=True))
    return 0 if result["status"] == "verified_bytes" else 1


if __name__ == "__main__":
    raise SystemExit(main())
