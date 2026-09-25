"""Public pilot mappings are grounded in CTU-13 and OTRF source formats."""

from __future__ import annotations

import json
import zipfile

from scripts.build_r2_public_pilot import iter_ctu_rows, iter_sysmon_rows, build_pilot_snapshot


def test_ctu_rows_keep_original_line_identity_and_label(tmp_path):
    source = tmp_path / "capture.binetflow"
    source.write_text(
        "StartTime,SrcAddr,Sport,DstAddr,Dport,Proto,State,TotBytes,SrcBytes,Label\n"
        "2011/08/15 16:52:50.947767,147.32.84.165,1234,147.32.80.9,53,udp,CON,100,40,flow=From-Botnet-V46-UDP-DNS\n",
        encoding="utf-8",
    )
    assert list(iter_ctu_rows(source, "ctu13_s5")) == [{
        "source_dataset": "ctu13_s5", "source_row_id": "line:2",
        "event_time": "2011-08-15T16:52:50.947767", "src_ip": "147.32.84.165",
        "src_port": 1234, "dst_ip": "147.32.80.9", "dst_port": 53,
        "protocol": "UDP", "action": "CON", "bytes_out": 40, "bytes_in": 60,
        "label": "flow=From-Botnet-V46-UDP-DNS",
    }]


def test_otrf_mapper_uses_endpoint_hostname_and_sysmon_channel(tmp_path):
    path = tmp_path / "events.zip"
    event = {"Channel": "Microsoft-Windows-Sysmon/Operational", "Hostname": "SCRANTON.dmevals.local",
             "host": "wec.internal.cloudapp.net", "EventID": 1, "UtcTime": "2020-05-02 02:55:56.157",
             "Image": "C:\\Windows\\cmd.exe", "ParentImage": "C:\\Windows\\explorer.exe",
             "ProcessId": "8524", "ParentProcessId": "4440", "CommandLine": "cmd.exe /c whoami",
             "User": "DMEVALS\\pbeesly"}
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("events.json", "\n".join([json.dumps({**event, "Channel": "Security"}), json.dumps(event)]))
    assert list(iter_sysmon_rows(path, "otrf_apt29_day1", "events.json")) == [{
        "source_dataset": "otrf_apt29_day1", "source_row_id": "events.json:line:2",
        "event_time": "2020-05-02T02:55:56.157000", "host": "SCRANTON.dmevals.local",
        "event_id": 1, "parent_image": "C:\\Windows\\explorer.exe", "parent_pid": 4440,
        "image": "C:\\Windows\\cmd.exe", "process_id": 8524,
        "command_line": "cmd.exe /c whoami", "user_name": "DMEVALS\\pbeesly",
    }]


def test_two_independent_builds_have_equal_content_hash_not_binary_hash(tmp_path):
    from evaluation.text_to_sql_snapshot import sha256_file

    flow = tmp_path / "flow.csv"
    flow.write_text(
        "StartTime,SrcAddr,Sport,DstAddr,Dport,Proto,State,TotBytes,SrcBytes,Label\n"
        "2011/08/15 16:52:50.947767,147.32.84.165,1234,147.32.80.9,53,udp,CON,100,40,flow=From-Botnet\n")
    event = tmp_path / "events.zip"
    with zipfile.ZipFile(event, "w") as archive:
        archive.writestr("events.json", json.dumps({
            "Channel": "Microsoft-Windows-Sysmon/Operational", "Hostname": "SCRANTON",
            "EventID": 1, "UtcTime": "2020-05-02 02:55:56.157", "Image": "cmd.exe"}))
    sources = []
    for dataset_id, path, fmt, member in (
        ("ctu13_s5", flow, "ctu13_binetflow", None),
        ("otrf_apt29_day1", event, "sysmon_zip_jsonl", "events.json"),
    ):
        sources.append(dict(dataset_id=dataset_id, source_name=dataset_id,
            source_url=f"https://example.org/{path.name}", retrieved_at="2026-09-25T04:00:00Z",
            file_sha256=sha256_file(path), license_note="Fixture only", format=fmt,
            path=str(path), archive_member=member))
    manifest = tmp_path / "manifest.json"
    manifest.write_text(json.dumps({"schema_version": "1", "sources": sources}))
    first = build_pilot_snapshot(manifest, tmp_path / "run1.duckdb")
    second = build_pilot_snapshot(manifest, tmp_path / "run2.duckdb")
    assert first["row_counts"] == second["row_counts"] == {"network_flows": 1, "sysmon_process_events": 1}
    assert first["content_sha256"] == second["content_sha256"]
    assert first["source_hashes"] == second["source_hashes"]
    import duckdb
    with duckdb.connect(str(tmp_path / "run1.duckdb"), read_only=True) as conn:
        assert "cti_indicators" not in {name for (name,) in conn.execute("SHOW TABLES").fetchall()}
