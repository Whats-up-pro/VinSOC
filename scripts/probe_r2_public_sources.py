"""Fetch and inspect complete public pilot sources without model access.

The JSON probe records digests of actual downloaded bytes. No raw dataset is
uploaded or committed. Failure still writes partial provenance for diagnosis.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import zipfile
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from urllib.request import Request, urlopen


SOURCES = (
    {
        "dataset_id": "ctu13_s5",
        "source_url": "https://mcfp.felk.cvut.cz/publicDatasets/CTU-Malware-Capture-Botnet-46/detailed-bidirectional-flow-labels/capture20110815-2.binetflow",
        "license_note": "MCFP allows use with attribution to Sebastian Garcia and the Malware Capture Facility Project; consult scenario 5 README.",
    },
    {
        "dataset_id": "ctu13_s7",
        "source_url": "https://mcfp.felk.cvut.cz/publicDatasets/CTU-Malware-Capture-Botnet-48/detailed-bidirectional-flow-labels/capture20110816-2.binetflow",
        "license_note": "MCFP allows use with attribution to Sebastian Garcia and the Malware Capture Facility Project; consult scenario 7 README.",
    },
    {
        "dataset_id": "otrf_apt29_day1",
        "source_url": "https://raw.githubusercontent.com/OTRF/Security-Datasets/master/datasets/compound/apt29/day1/apt29_evals_day1_manual.zip",
        "license_note": "OTRF README describes GPL-3.0, while repository LICENSE says MIT; retain source attribution and resolve the discrepancy before redistributing data.",
    },
)


def copy_and_hash(source, target) -> tuple[int, str]:
    digest = hashlib.sha256()
    length = 0
    while chunk := source.read(1024 * 1024):
        target.write(chunk)
        digest.update(chunk)
        length += len(chunk)
    return length, digest.hexdigest()


def label_group(label: str) -> str:
    return label.removeprefix("flow=").split("-", 1)[0]


def _flow_samples(path: Path) -> dict:
    samples: list[dict] = []
    distribution: Counter[str] = Counter()
    sampled_groups: Counter[str] = Counter()
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        fieldnames = reader.fieldnames
        for line, row in enumerate(reader, start=2):
            label = label_group(row.get("Label") or "")
            distribution[label] += 1
            if label in ("From", "To", "Normal", "Background") and sampled_groups[label] < 20:
                sampled_groups[label] += 1
                samples.append({"line": line, **{key: row.get(key) for key in (
                    "StartTime", "SrcAddr", "Sport", "DstAddr", "Dport", "Proto", "Label"
                )}})
    return {"fields": fieldnames, "record_count": sum(distribution.values()),
            "label_prefixes": dict(distribution), "samples": samples}


def _event_samples(path: Path) -> dict:
    samples: list[dict] = []
    event_ids: Counter[str] = Counter()
    with zipfile.ZipFile(path) as archive:
        members = [m for m in archive.infolist() if not m.is_dir()]
        if len(members) != 1:
            raise ValueError("OTRF archive must contain exactly one JSONL member")
        member = members[0]
        digest = hashlib.sha256()
        with archive.open(member) as handle:
            for line_number, line in enumerate(handle, start=1):
                digest.update(line)
                payload = json.loads(line)
                event_id = str(payload.get("EventID", "missing"))
                event_ids[event_id] += 1
                if event_id == "1" and len(samples) < 80:
                    samples.append({"line": line_number, **{key: payload.get(key) for key in (
                        "Hostname", "EventID", "UtcTime", "@timestamp", "Image", "ParentImage",
                        "ProcessId", "CommandLine", "EventData"
                    ) if key in payload}})
        return {"archive_member": member.filename, "member_bytes": member.file_size,
                "member_sha256": digest.hexdigest(), "record_count": sum(event_ids.values()),
                "event_ids": dict(event_ids), "samples": samples}


def probe(output: Path) -> dict:
    output.mkdir(parents=True, exist_ok=True)
    record: dict = {"schema_version": "public_probe_v1", "sources": [], "status": "partial"}
    destination = output / "probe.json"
    for source in SOURCES:
        item = dict(source)
        record["sources"].append(item)
        try:
            path = output / Path(source["source_url"]).name
            request = Request(source["source_url"], headers={"User-Agent": "VinSOC-public-evaluation/1.0"})
            with urlopen(request, timeout=90) as response, path.open("wb") as handle:
                item["bytes"], item["file_sha256"] = copy_and_hash(response, handle)
            item["retrieved_at"] = datetime.now(timezone.utc).isoformat()
            item["format"] = "sysmon_zip_jsonl" if source["dataset_id"].startswith("otrf") else "ctu13_binetflow"
            item["inspection"] = _event_samples(path) if item["format"] == "sysmon_zip_jsonl" else _flow_samples(path)
            item["status"] = "verified_bytes"
        except Exception as exc:
            item["status"] = "failed"
            item["error"] = f"{type(exc).__name__}: {exc}"
        finally:
            destination.write_text(json.dumps(record, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    if all(item["status"] == "verified_bytes" for item in record["sources"]):
        record["status"] = "verified_bytes"
        destination.write_text(json.dumps(record, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    return record


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    result = probe(parser.parse_args().output)
    print(json.dumps({"status": result["status"], "sources": [
        {key: value for key, value in item.items() if key in {"dataset_id", "bytes", "file_sha256", "status", "error"}}
        for item in result["sources"]
    ]}, sort_keys=True))
    return 0 if result["status"] == "verified_bytes" else 1


if __name__ == "__main__":
    raise SystemExit(main())
