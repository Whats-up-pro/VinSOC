"""Tests for public-source normalization and snapshot assembly.

The inline records are minimal source-format fixtures. They are not official
VinSOC benchmark data and must never be copied into a released snapshot.
"""

from __future__ import annotations

import csv
import hashlib
import json
import zipfile
from pathlib import Path

import pytest

from evaluation.text_to_sql_snapshot import load_snapshot_manifest, verify_snapshot
from scripts.build_vinsoc_public_snapshot import (
    build_snapshot,
    normalize_ctu13_binetflow,
    normalize_sysmon_jsonl,
    normalize_sysmon_zip_jsonl,
    normalize_threatfox_csv,
    normalize_threatfox_csv_with_diagnostics,
)
from vinsoc_data.duckdb_store import DuckDBSnapshot, SocSnapshotBuilder


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _write_csv(path: Path, fieldnames: list[str], rows: list[dict[str, str]]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def test_threatfox_adapter_maps_fields_and_skips_invalid_rows(tmp_path):
    source = tmp_path / "threatfox.csv"
    fields = [
        "ioc_id",
        "ioc_value",
        "ioc_type",
        "threat_type",
        "malware_printable",
        "confidence_level",
        "first_seen_utc",
        "last_seen_utc",
        "reference",
    ]
    _write_csv(
        source,
        fields,
        [
            {
                "ioc_id": "42",
                "ioc_value": "203.0.113.10:443",
                "ioc_type": "ip:port",
                "threat_type": "botnet_cc",
                "malware_printable": "ExampleFamily",
                "confidence_level": "90",
                "first_seen_utc": "2024-01-02 03:04:05",
                "last_seen_utc": "2024-01-03 04:05:06",
                "reference": "https://example.invalid/ioc/42",
            },
            {
                "ioc_id": "",
                "ioc_value": "",
                "ioc_type": "domain",
                "threat_type": "payload_delivery",
                "malware_printable": "",
                "confidence_level": "not-an-int",
                "first_seen_utc": "not-a-time",
                "last_seen_utc": "",
                "reference": "",
            },
        ],
    )

    rows = normalize_threatfox_csv(source, "threatfox-test")

    assert rows == [
        {
            "source_dataset": "threatfox-test",
            "source_row_id": "42",
            "indicator": "203.0.113.10:443",
            "indicator_type": "ip:port",
            "threat_type": "botnet_cc",
            "malware_printable": "ExampleFamily",
            "confidence_level": 90,
            "first_seen": "2024-01-02T03:04:05",
            "last_seen": "2024-01-03T04:05:06",
            "reference_url": "https://example.invalid/ioc/42",
        }
    ]


def test_threatfox_adapter_discovers_commented_full_export_header(tmp_path):
    source = tmp_path / "full.csv"
    source.write_text(
        "# ThreatFox full export generated at 2026-09-26 00:00:00 UTC\n"
        "# Terms: https://threatfox.abuse.ch/\n"
        "# first_seen_utc,ioc_id,ioc_value,ioc_type,threat_type,malware_printable,confidence_level,reference,last_seen_utc\n"
        "2026-09-25 01:02:03,9876,evil.example,domain,botnet_cc,ExampleBot,95,https://threatfox.abuse.ch/ioc/9876/,2026-09-25 04:05:06\n",
        encoding="utf-8",
    )

    rows = normalize_threatfox_csv(source, "threatfox_full")

    assert rows == [{
        "source_dataset": "threatfox_full",
        "source_row_id": "9876",
        "indicator": "evil.example",
        "indicator_type": "domain",
        "threat_type": "botnet_cc",
        "malware_printable": "ExampleBot",
        "confidence_level": 95,
        "first_seen": "2026-09-25T01:02:03",
        "last_seen": "2026-09-25T04:05:06",
        "reference_url": "https://threatfox.abuse.ch/ioc/9876/",
    }]


def test_threatfox_adapter_honors_delimiter_space_before_quoted_fields(tmp_path):
    source = tmp_path / "full.csv"
    source.write_text(
        "# first_seen_utc,ioc_id,ioc_value,ioc_type,threat_type,"
        "malware_printable,confidence_level,reference,last_seen_utc\n"
        '"2026-09-25 01:02:03", "9876", "evil.example", "domain", '
        '"botnet_cc", "Example, Bot", "95", '
        '"https://threatfox.abuse.ch/ioc/9876/", ""\n',
        encoding="utf-8",
    )

    rows, diagnostics = normalize_threatfox_csv_with_diagnostics(source, "threatfox_full")

    assert rows == [
        {
            "source_dataset": "threatfox_full",
            "source_row_id": "9876",
            "indicator": "evil.example",
            "indicator_type": "domain",
            "threat_type": "botnet_cc",
            "malware_printable": "Example, Bot",
            "confidence_level": 95,
            "first_seen": "2026-09-25T01:02:03",
            "last_seen": None,
            "reference_url": "https://threatfox.abuse.ch/ioc/9876/",
        }
    ]
    assert diagnostics["rows_accepted"] == 1
    assert diagnostics["rows_rejected"] == 0


def test_threatfox_adapter_fails_loudly_without_export_header(tmp_path):
    source = tmp_path / "full.csv"
    source.write_text("# metadata only\n42,evil.example,domain\n", encoding="utf-8")

    with pytest.raises(ValueError, match="ThreatFox CSV header not found"):
        normalize_threatfox_csv(source, "threatfox_full")


def test_threatfox_adapter_fails_loudly_when_required_columns_are_missing(tmp_path):
    source = tmp_path / "full.csv"
    source.write_text(
        "# first_seen_utc,ioc_value,threat_type\n"
        "2026-09-25 01:02:03,evil.example,botnet_cc\n",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match=r"missing required column\(s\): ioc_id, ioc_type"):
        normalize_threatfox_csv(source, "threatfox_full")


def test_threatfox_diagnostics_count_first_failure_without_values(tmp_path):
    source = tmp_path / "full.csv"
    source.write_text(
        "# first_seen_utc,ioc_id,ioc_value,ioc_type,confidence_level,last_seen_utc\n"
        "2026-09-25 01:02:03,1,accepted.example,domain,95,2026-09-25 04:05:06\n"
        "2026-09-25 01:02:03 UTC,2,utc.example,domain,95,\n"
        "not-a-time,3,bad-first.example,domain,95,\n"
        "2026-09-25 01:02:03,4,bad-last.example,domain,95,2026-09-25 04:05:06 UTC\n"
        "2026-09-25 01:02:03,5,bad-confidence.example,domain,unknown,\n"
        "2026-09-25 01:02:03,6,,domain,95,\n",
        encoding="utf-8",
    )

    rows, diagnostics = normalize_threatfox_csv_with_diagnostics(
        source, "threatfox_full"
    )

    assert len(rows) == 1
    assert diagnostics == {
        "dataset_id": "threatfox_full",
        "data_rows_seen": 6,
        "rows_accepted": 1,
        "rows_rejected": 5,
        "primary_rejection_reasons": {
            "missing_required_value": 1,
            "invalid_first_seen_timestamp": 2,
            "invalid_last_seen_timestamp": 1,
            "invalid_confidence_level": 1,
        },
        "timestamp_shape_counts": {
            "first_seen_ends_with_utc_literal": 1,
            "last_seen_ends_with_utc_literal": 1,
        },
    }
    assert diagnostics["rows_accepted"] + diagnostics["rows_rejected"] == diagnostics[
        "data_rows_seen"
    ]
    serialized = json.dumps(diagnostics, sort_keys=True)
    assert "accepted.example" not in serialized
    assert "not-a-time" not in serialized
    assert "unknown" not in serialized


def test_ctu13_adapter_maps_flow_fields_and_skips_invalid_rows(tmp_path):
    source = tmp_path / "capture.binetflow"
    fields = [
        "StartTime",
        "Dur",
        "Proto",
        "SrcAddr",
        "Sport",
        "Dir",
        "DstAddr",
        "Dport",
        "State",
        "sTos",
        "dTos",
        "TotPkts",
        "TotBytes",
        "SrcBytes",
        "Label",
    ]
    _write_csv(
        source,
        fields,
        [
            {
                "StartTime": "2011/08/12 15:00:37.123456",
                "Dur": "1.5",
                "Proto": "tcp",
                "SrcAddr": "147.32.84.165",
                "Sport": "1025",
                "Dir": "  ->",
                "DstAddr": "198.51.100.8",
                "Dport": "80",
                "State": "CON",
                "sTos": "0",
                "dTos": "0",
                "TotPkts": "4",
                "TotBytes": "1000",
                "SrcBytes": "600",
                "Label": "From-Botnet",
            },
            {
                "StartTime": "bad-time",
                "Dur": "",
                "Proto": "tcp",
                "SrcAddr": "not-an-ip",
                "Sport": "70000",
                "Dir": "",
                "DstAddr": "198.51.100.8",
                "Dport": "80",
                "State": "",
                "sTos": "",
                "dTos": "",
                "TotPkts": "",
                "TotBytes": "",
                "SrcBytes": "",
                "Label": "",
            },
        ],
    )

    rows = normalize_ctu13_binetflow(source, "ctu13-test")

    assert rows == [
        {
            "source_dataset": "ctu13-test",
            "source_row_id": "line:2",
            "event_time": "2011-08-12T15:00:37.123456",
            "src_ip": "147.32.84.165",
            "src_port": 1025,
            "dst_ip": "198.51.100.8",
            "dst_port": 80,
            "protocol": "TCP",
            "action": "CON",
            "bytes_out": 600,
            "bytes_in": 400,
            "label": "From-Botnet",
        }
    ]


def test_sysmon_adapter_maps_parent_child_host_and_skips_invalid_rows(tmp_path):
    source = tmp_path / "sysmon.jsonl"
    records = [
        {
            "@timestamp": "2020-04-29T20:07:43.123Z",
            "winlog": {
                "event_id": 1,
                "computer_name": "WORKSTATION01.example.test",
                "event_data": {
                    "ParentImage": "C:\\Windows\\explorer.exe",
                    "ParentProcessId": "2048",
                    "Image": "C:\\Windows\\System32\\cmd.exe",
                    "ProcessId": "4096",
                    "CommandLine": "cmd.exe /c whoami",
                    "User": "EXAMPLE\\analyst",
                },
            },
        },
        {"@timestamp": "bad", "winlog": {"event_id": 1, "computer_name": ""}},
        {"not": "json event fields"},
    ]
    source.write_text("\n".join(json.dumps(record) for record in records), encoding="utf-8")

    rows = normalize_sysmon_jsonl(source, "otrf-test")

    assert rows == [
        {
            "source_dataset": "otrf-test",
            "source_row_id": "line:1",
            "event_time": "2020-04-29T20:07:43.123000",
            "host": "WORKSTATION01.example.test",
            "event_id": 1,
            "parent_image": "C:\\Windows\\explorer.exe",
            "parent_pid": 2048,
            "image": "C:\\Windows\\System32\\cmd.exe",
            "process_id": 4096,
            "command_line": "cmd.exe /c whoami",
            "user_name": "EXAMPLE\\analyst",
        }
    ]


def test_official_otrf_top_level_layout_maps_sysmon_process_and_stable_member_row_id(tmp_path):
    archive = tmp_path / "apt29.zip"
    member = "apt29_evals_day1_manual_2020-05-01225525.json"
    valid = {
        "Channel": "Microsoft-Windows-Sysmon/Operational",
        "Hostname": "ENDPOINT.example.test",
        "EventID": 1,
        "UtcTime": "2020-05-01 22:55:25.123",
        "Image": "C:\\Windows\\System32\\WindowsPowerShell\\v1.0\\powershell.exe",
        "ParentImage": "C:\\Windows\\System32\\cmd.exe",
        "ProcessId": "0x1000",
        "ParentProcessId": "2048",
        "CommandLine": "powershell.exe -NoProfile",
        "User": "EXAMPLE\\analyst",
    }
    unrelated = {**valid, "Channel": "Security", "Hostname": "WRONG.example.test"}
    malformed = {"Channel": "Microsoft-Windows-Sysmon/Operational", "EventID": 1,
                 "UtcTime": "2020-05-01 22:55:25.123"}
    with zipfile.ZipFile(archive, "w") as handle:
        handle.writestr(member, "\n".join(json.dumps(row) for row in (
            valid, unrelated, malformed
        )))

    rows = normalize_sysmon_zip_jsonl(archive, "otrf_apt29_day1", member)

    assert rows == [{
        "source_dataset": "otrf_apt29_day1",
        "source_row_id": f"{member}:line:1",
        "event_time": "2020-05-01T22:55:25.123000",
        "host": "ENDPOINT.example.test",
        "event_id": 1,
        "parent_image": "C:\\Windows\\System32\\cmd.exe",
        "parent_pid": 2048,
        "image": "C:\\Windows\\System32\\WindowsPowerShell\\v1.0\\powershell.exe",
        "process_id": 4096,
        "command_line": "powershell.exe -NoProfile",
        "user_name": "EXAMPLE\\analyst",
    }]


def test_build_snapshot_verifies_sources_and_writes_exact_manifest(tmp_path, monkeypatch):
    threatfox = tmp_path / "threatfox.csv"
    _write_csv(
        threatfox,
        [
            "ioc_id",
            "ioc_value",
            "ioc_type",
            "threat_type",
            "malware_printable",
            "confidence_level",
            "first_seen_utc",
            "last_seen_utc",
            "reference",
        ],
        [
            {
                "ioc_id": "1",
                "ioc_value": "malware.example",
                "ioc_type": "domain",
                "threat_type": "botnet_cc",
                "malware_printable": "FixtureOnly",
                "confidence_level": "80",
                "first_seen_utc": "2024-01-01 00:00:00",
                "last_seen_utc": "2024-01-02 00:00:00",
                "reference": "https://example.invalid/1",
            }
        ],
    )
    network = tmp_path / "network.binetflow"
    _write_csv(
        network,
        [
            "StartTime",
            "Proto",
            "SrcAddr",
            "Sport",
            "DstAddr",
            "Dport",
            "State",
            "TotBytes",
            "SrcBytes",
            "Label",
        ],
        [
            {
                "StartTime": "2011/08/12 15:00:37",
                "Proto": "udp",
                "SrcAddr": "192.0.2.1",
                "Sport": "53000",
                "DstAddr": "198.51.100.53",
                "Dport": "53",
                "State": "CON",
                "TotBytes": "300",
                "SrcBytes": "100",
                "Label": "Normal",
            }
        ],
    )
    endpoint = tmp_path / "endpoint.zip"
    endpoint_record = json.dumps(
        {
            "@timestamp": "2020-04-29T20:07:43Z",
            "winlog": {
                "event_id": 1,
                "computer_name": "HOST01",
                "event_data": {"Image": "cmd.exe", "ProcessId": "99"},
            },
        }
    )
    with zipfile.ZipFile(endpoint, "w") as archive:
        archive.writestr("export/events.jsonl", endpoint_record)
    sources = [
        ("threatfox", threatfox, "threatfox_csv", None),
        ("ctu13", network, "ctu13_binetflow", None),
        ("otrf", endpoint, "sysmon_zip_jsonl", "export/events.jsonl"),
    ]
    dataset_manifest = tmp_path / "dataset_manifest.json"
    dataset_manifest.write_text(
        json.dumps(
            {
                "schema_version": "1",
                "sources": [
                    {
                        "dataset_id": dataset_id,
                        "source_name": dataset_id,
                        "source_url": f"https://example.invalid/{path.name}",
                        "retrieved_at": "2026-09-23T00:00:00Z",
                        "file_sha256": _sha256(path),
                        "license_note": "Test-only source-format fixture; not benchmark data.",
                        "format": source_format,
                        "path": str(path),
                        "archive_member": archive_member,
                    }
                    for dataset_id, path, source_format, archive_member in sources
                ],
            }
        ),
        encoding="utf-8",
    )
    snapshot_path = tmp_path / "vinsoc_public_v1.duckdb"
    snapshot_manifest = tmp_path / "snapshot_manifest.json"
    monkeypatch.setattr(
        SocSnapshotBuilder,
        "insert_rows",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            AssertionError("official builder must stream rows instead of materializing them")
        ),
    )

    counts = build_snapshot(dataset_manifest, snapshot_path, snapshot_manifest)

    assert counts == {
        "cti_indicators": 1,
        "network_flows": 1,
        "sysmon_process_events": 1,
    }
    manifest = load_snapshot_manifest(snapshot_manifest)
    verify_snapshot(snapshot_path, manifest)
    snapshot = DuckDBSnapshot(snapshot_path)
    assert snapshot.query("SELECT count(*) AS n FROM dataset_provenance").rows == [{"n": 3}]
    assert snapshot.query("SELECT source_dataset, source_row_id FROM network_flows").rows == [
        {"source_dataset": "ctu13", "source_row_id": "line:2"}
    ]
    assert snapshot.query(
        "SELECT source_dataset, source_row_id FROM sysmon_process_events"
    ).rows == [
        {
            "source_dataset": "otrf",
            "source_row_id": "export/events.jsonl:line:1",
        }
    ]
    assert snapshot.query(
        "SELECT file_sha256 FROM dataset_provenance WHERE dataset_id = 'otrf'"
    ).rows == [{"file_sha256": _sha256(endpoint)}]


def test_build_snapshot_fails_closed_on_hash_mismatch(tmp_path):
    source = tmp_path / "source.csv"
    source.write_text("ioc_id,ioc_value,ioc_type\n1,example.test,domain\n", encoding="utf-8")
    dataset_manifest = tmp_path / "dataset_manifest.json"
    dataset_manifest.write_text(
        json.dumps(
            {
                "schema_version": "1",
                "sources": [
                    {
                        "dataset_id": "threatfox",
                        "source_name": "ThreatFox",
                        "source_url": "https://example.invalid/source.csv",
                        "retrieved_at": "2026-09-23T00:00:00Z",
                        "file_sha256": "0" * 64,
                        "license_note": "Test-only fixture.",
                        "format": "threatfox_csv",
                        "path": str(source),
                        "archive_member": None,
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="Source SHA-256 mismatch"):
        build_snapshot(
            dataset_manifest,
            tmp_path / "snapshot.duckdb",
            tmp_path / "snapshot_manifest.json",
        )


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("source_url", "not-a-url", "HTTPS URL"),
        ("retrieved_at", "2026-09-23 00:00:00", "UTC date-time"),
        ("retrieved_at", "2026-09-23T01:00:00+01:00", "UTC date-time"),
    ],
)
def test_build_snapshot_rejects_invalid_public_provenance(tmp_path, field, value, message):
    source = tmp_path / "source.csv"
    source.write_text("ioc_id,ioc_value,ioc_type\n1,example.test,domain\n", encoding="utf-8")
    source_entry = {
        "dataset_id": "threatfox",
        "source_name": "ThreatFox",
        "source_url": "https://example.invalid/source.csv",
        "retrieved_at": "2026-09-23T00:00:00Z",
        "file_sha256": _sha256(source),
        "license_note": "Test-only fixture.",
        "format": "threatfox_csv",
        "path": str(source),
        "archive_member": None,
    }
    source_entry[field] = value
    dataset_manifest = tmp_path / "dataset_manifest.json"
    dataset_manifest.write_text(
        json.dumps({"schema_version": "1", "sources": [source_entry]}),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match=message):
        build_snapshot(
            dataset_manifest,
            tmp_path / "snapshot.duckdb",
            tmp_path / "snapshot_manifest.json",
        )
