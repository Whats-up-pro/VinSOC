from __future__ import annotations

import csv
import hashlib
import json
import zipfile
from pathlib import Path
from types import SimpleNamespace

import pytest

from scripts import validate_run5_cti_load


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _fixture_zip(tmp_path: Path) -> tuple[Path, str]:
    full_csv = tmp_path / "full.csv"
    fields = [
        "first_seen_utc",
        "ioc_id",
        "ioc_value",
        "ioc_type",
        "threat_type",
        "malware_printable",
        "confidence_level",
        "reference",
        "last_seen_utc",
    ]
    with full_csv.open("w", encoding="utf-8", newline="") as handle:
        handle.write("# " + ",".join(fields) + "\n")
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writerow(
            {
                "first_seen_utc": "2026-09-25 01:02:03",
                "ioc_id": "000123",
                "ioc_value": "SENSITIVE_FIXTURE_IOC",
                "ioc_type": "domain",
                "threat_type": "botnet_cc",
                "malware_printable": "Example, Family",
                "confidence_level": "95",
                "reference": "",
                "last_seen_utc": "",
            }
        )
        writer.writerow(
            {
                "first_seen_utc": "2026-09-25 02:03:04",
                "ioc_id": "000124",
                "ioc_value": "second.invalid",
                "ioc_type": "domain",
                "threat_type": "",
                "malware_printable": "",
                "confidence_level": "",
                "reference": "https://example.invalid/124",
                "last_seen_utc": "2026-09-25 03:04:05",
            }
        )
    archive_path = tmp_path / "threatfox.zip"
    with zipfile.ZipFile(archive_path, "w") as archive:
        archive.write(full_csv, "full.csv")
    return archive_path, _sha256(full_csv)


def test_validate_exact_cti_archive_reports_only_safe_aggregates(monkeypatch, tmp_path):
    archive_path, member_sha = _fixture_zip(tmp_path)
    monkeypatch.setattr(validate_run5_cti_load, "EXPECTED_THREATFOX_ZIP_SHA256", _sha256(archive_path))
    monkeypatch.setattr(validate_run5_cti_load, "EXPECTED_THREATFOX_FULL_CSV_SHA256", member_sha)
    monkeypatch.setattr(validate_run5_cti_load, "EXPECTED_NORMALIZED_ROWS", 2)
    output = tmp_path / "evidence.json"

    result = validate_run5_cti_load.validate_run5_cti_load(
        threatfox_zip_path=archive_path,
        output_path=output,
        working_directory=tmp_path / "work",
        git_sha="a" * 40,
    )

    assert result["status"] == "passed"
    assert result["normalized_rows"] == 2
    assert result["loaded_cti_rows"] == 2
    assert result["distinct_source_row_id"] == 2
    assert result["nullable_field_null_counts"] == {
        "threat_type": 1,
        "malware_printable": 1,
        "confidence_level": 1,
        "first_seen": 0,
        "last_seen": 1,
        "reference_url": 1,
    }
    assert json.loads(output.read_text(encoding="utf-8")) == result
    serialized = json.dumps(result, sort_keys=True)
    assert "SENSITIVE_FIXTURE_IOC" not in serialized
    assert "second.invalid" not in serialized
    assert "Example, Family" not in serialized


def test_validate_cti_archive_rejects_wrong_identity_without_source_values(
    monkeypatch, tmp_path
):
    archive_path, _member_sha = _fixture_zip(tmp_path)
    monkeypatch.setattr(validate_run5_cti_load, "EXPECTED_THREATFOX_ZIP_SHA256", "0" * 64)

    with pytest.raises(
        validate_run5_cti_load.Run5CtiValidationError,
        match="ThreatFox ZIP identity mismatch",
    ) as raised:
        validate_run5_cti_load.validate_run5_cti_load(
            threatfox_zip_path=archive_path,
            output_path=tmp_path / "evidence.json",
            working_directory=tmp_path / "work",
            git_sha="b" * 40,
        )

    assert "SENSITIVE_FIXTURE_IOC" not in str(raised.value)
    assert raised.value.__cause__ is None


def test_cli_discards_unexpected_source_bearing_exception(monkeypatch, tmp_path, capsys):
    output = tmp_path / "failed-evidence.json"
    monkeypatch.setattr(
        validate_run5_cti_load,
        "_parse_args",
        lambda: SimpleNamespace(
            threatfox_zip=tmp_path / "source.zip",
            output=output,
            work_dir=tmp_path / "work",
            git_sha="c" * 40,
        ),
    )

    def fail_validation(**_kwargs):
        raise RuntimeError("SENSITIVE_RAW_IOC_VALUE SENSITIVE_ORIGINAL_LINE")

    monkeypatch.setattr(
        validate_run5_cti_load, "validate_run5_cti_load", fail_validation
    )

    assert validate_run5_cti_load.main() == 1
    serialized = output.read_text(encoding="utf-8")
    captured = capsys.readouterr()
    assert "SENSITIVE_RAW_IOC_VALUE" not in serialized
    assert "SENSITIVE_ORIGINAL_LINE" not in serialized
    assert "SENSITIVE_RAW_IOC_VALUE" not in captured.err
    assert json.loads(serialized)["failure"] == {
        "category": "run5_cti_validation_error"
    }
