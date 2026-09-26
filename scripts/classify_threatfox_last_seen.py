"""Classify ThreatFox ``last_seen_utc`` representations without retaining values."""

from __future__ import annotations

import argparse
import csv
import hashlib
import itertools
import json
from collections.abc import Iterator
from pathlib import Path
from typing import Any, TextIO

from scripts.build_vinsoc_public_snapshot import _timestamp

CLASSIFIER_VERSION = "threatfox_last_seen_v1"
RUN4_ID = 36230976997
RUN4_FULL_CSV_SHA256 = "444e2caa3a3226e3778bd1e49732aac527c214f8c521b57707f4215de3a1691d"
RUN4_ROWS = 107817
CATEGORIES = (
    "empty",
    "valid_timestamp",
    "literal_none",
    "literal_null",
    "literal_na",
    "literal_n_a",
    "literal_never",
    "literal_dash",
    "zero_datetime",
    "other_unrecognized",
)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _last_seen_values(handle: TextIO) -> Iterator[str]:
    header: str | None = None
    for line in handle:
        if header is None:
            candidate = line.lstrip()
            if candidate.startswith("#"):
                candidate = candidate[1:].lstrip()
            if "first_seen_utc" in candidate and "ioc_value" in candidate:
                header = candidate
                break
    if header is None:
        raise ValueError("ThreatFox CSV header not found")

    lines = itertools.chain(
        [header],
        (line for line in handle if line.strip() and not line.lstrip().startswith("#")),
    )
    reader = csv.reader(lines, skipinitialspace=True)
    fieldnames = next(reader)
    try:
        last_seen_index = fieldnames.index("last_seen_utc")
    except ValueError as exc:
        raise ValueError("ThreatFox CSV missing required column: last_seen_utc") from exc

    for row in reader:
        if len(row) <= last_seen_index:
            raise ValueError("ThreatFox CSV row is shorter than its header")
        yield row[last_seen_index]


def _category(value: str) -> str:
    rendered = value.strip()
    if not rendered:
        return "empty"
    if rendered == "-":
        return "literal_dash"
    if rendered == "0000-00-00 00:00:00":
        return "zero_datetime"

    try:
        token = rendered.encode("ascii").decode("ascii").casefold()
    except UnicodeEncodeError:
        token = ""
    literals = {
        "none": "literal_none",
        "null": "literal_null",
        "na": "literal_na",
        "n/a": "literal_n_a",
        "never": "literal_never",
    }
    if token in literals:
        return literals[token]
    if _timestamp(rendered) is not None:
        return "valid_timestamp"
    return "other_unrecognized"


def classify_last_seen(path: Path) -> dict[str, object]:
    counts = {category: 0 for category in CATEGORIES}
    with Path(path).open("r", encoding="utf-8-sig", newline="") as handle:
        for value in _last_seen_values(handle):
            counts[_category(value)] += 1
    rows_seen = sum(counts.values())
    return {
        "classifier_version": CLASSIFIER_VERSION,
        "data_rows_seen": rows_seen,
        "representation_counts": counts,
    }


def build_run4_report(
    path: Path,
    *,
    expected_sha256: str,
    expected_rows: int,
    run_id: int,
) -> dict[str, Any]:
    path = Path(path)
    source_sha256 = _sha256(path)
    if source_sha256 != expected_sha256:
        raise ValueError("ThreatFox full.csv SHA-256 mismatch")
    result = classify_last_seen(path)
    if result["data_rows_seen"] != expected_rows:
        raise ValueError("ThreatFox full.csv row count mismatch")
    counts = result["representation_counts"]
    if sum(counts.values()) != result["data_rows_seen"]:
        raise AssertionError("ThreatFox representation counts do not balance")
    return {
        "schema_version": "r2_run4_threatfox_last_seen_classification_v1",
        "classifier_version": CLASSIFIER_VERSION,
        "classifier_sha256": _sha256(Path(__file__)),
        "run_id": run_id,
        "full_csv_sha256": source_sha256,
        "data_rows_seen": result["data_rows_seen"],
        "representation_counts": counts,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    report = build_run4_report(
        args.input,
        expected_sha256=RUN4_FULL_CSV_SHA256,
        expected_rows=RUN4_ROWS,
        run_id=RUN4_ID,
    )
    args.output.write_text(json.dumps(report, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
