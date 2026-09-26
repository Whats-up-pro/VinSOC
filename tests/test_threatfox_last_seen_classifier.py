from __future__ import annotations

import csv
import hashlib
import json
from pathlib import Path

import pytest

from scripts.classify_threatfox_last_seen import (
    CATEGORIES,
    CLASSIFIER_VERSION,
    build_run4_report,
    classify_last_seen,
)


def _write_fixture(path: Path, last_seen_values: list[str]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        handle.write("# ThreatFox test export\n")
        handle.write("# first_seen_utc,ioc_id,ioc_value,ioc_type,last_seen_utc\n")
        writer = csv.writer(handle)
        for index, value in enumerate(last_seen_values, start=1):
            writer.writerow(
                [
                    "2026-09-25 00:00:00",
                    f"SENSITIVE_IOC_ID_{index}",
                    f"sensitive-{index}.example",
                    "domain",
                    value,
                ]
            )


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_classifier_emits_only_closed_category_counts(tmp_path):
    source = tmp_path / "full.csv"
    _write_fixture(
        source,
        [
            "",
            "2026-09-25 01:02:03",
            " None ",
            "NULL",
            "Na",
            "n/A",
            "Never",
            "-",
            "0000-00-00 00:00:00",
            "SENSITIVE_UNRECOGNIZED_TIMESTAMP",
        ],
    )

    result = classify_last_seen(source)

    assert result == {
        "classifier_version": CLASSIFIER_VERSION,
        "data_rows_seen": 10,
        "representation_counts": {
            "empty": 1,
            "valid_timestamp": 1,
            "literal_none": 1,
            "literal_null": 1,
            "literal_na": 1,
            "literal_n_a": 1,
            "literal_never": 1,
            "literal_dash": 1,
            "zero_datetime": 1,
            "other_unrecognized": 1,
        },
    }
    assert tuple(result["representation_counts"]) == CATEGORIES
    assert sum(result["representation_counts"].values()) == result["data_rows_seen"]


def test_classifier_honors_threatfox_delimiter_space_before_quoted_empty(tmp_path):
    source = tmp_path / "full.csv"
    source.write_text(
        "# first_seen_utc,ioc_id,ioc_value,ioc_type,threat_type,"
        "malware_printable,confidence_level,reference,last_seen_utc\n"
        '"2026-09-25 01:02:03", "9876", "evil.example", "domain", '
        '"botnet_cc", "Example, Bot", "95", '
        '"https://threatfox.abuse.ch/ioc/9876/", ""\n',
        encoding="utf-8",
    )

    result = classify_last_seen(source)

    assert result["data_rows_seen"] == 1
    assert result["representation_counts"]["empty"] == 1
    assert result["representation_counts"]["other_unrecognized"] == 0


def test_classifier_report_never_serializes_unknown_or_ioc_values(tmp_path):
    source = tmp_path / "full.csv"
    _write_fixture(source, ["SENSITIVE_UNRECOGNIZED_TIMESTAMP"])

    serialized = json.dumps(classify_last_seen(source), sort_keys=True)

    assert "SENSITIVE_UNRECOGNIZED_TIMESTAMP" not in serialized
    assert "SENSITIVE_IOC_ID" not in serialized
    assert "sensitive-1.example" not in serialized
    assert set(json.loads(serialized)) == {
        "classifier_version",
        "data_rows_seen",
        "representation_counts",
    }


def test_classifier_requires_last_seen_column(tmp_path):
    source = tmp_path / "full.csv"
    source.write_text(
        "# first_seen_utc,ioc_id,ioc_value,ioc_type\n"
        "2026-09-25 00:00:00,1,example.test,domain\n",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="last_seen_utc"):
        classify_last_seen(source)


def test_run4_report_requires_exact_hash_and_row_count(tmp_path):
    source = tmp_path / "full.csv"
    _write_fixture(source, ["None"])
    digest = _sha256(source)

    report = build_run4_report(
        source,
        expected_sha256=digest,
        expected_rows=1,
        run_id=36230976997,
    )

    assert report["run_id"] == 36230976997
    assert report["full_csv_sha256"] == digest
    assert report["data_rows_seen"] == 1
    assert report["representation_counts"]["literal_none"] == 1
    assert len(report["classifier_sha256"]) == 64

    with pytest.raises(ValueError, match="SHA-256 mismatch"):
        build_run4_report(
            source,
            expected_sha256="0" * 64,
            expected_rows=1,
            run_id=36230976997,
        )
    with pytest.raises(ValueError, match="row count mismatch"):
        build_run4_report(
            source,
            expected_sha256=digest,
            expected_rows=107817,
            run_id=36230976997,
        )
