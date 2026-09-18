import json

from telemetry.network.query import NetworkQuery
from telemetry.network.zeek import ZeekJSONDataSource
from telemetry.network.suricata import SuricataEVEDataSource


def test_zeek_conn_json_normalizes_and_filters(tmp_path):
    path = tmp_path / "conn.jsonl"
    rows = [
        {
            "ts": 1760000000.0,
            "uid": "C1",
            "id.orig_h": "10.0.0.5",
            "id.orig_p": 50100,
            "id.resp_h": "1.2.3.4",
            "id.resp_p": 443,
            "proto": "tcp",
            "service": "ssl",
            "duration": 3.5,
            "orig_bytes": 100,
            "resp_bytes": 200,
            "orig_pkts": 3,
            "resp_pkts": 4,
            "conn_state": "SF",
        },
        "{bad-json",
    ]
    with path.open("w", encoding="utf-8") as fh:
        fh.write(json.dumps(rows[0]) + "\n")
        fh.write(rows[1] + "\n")

    source = ZeekJSONDataSource(str(path), sensor_version="8.0")
    events = list(source.query(NetworkQuery(indicator="1.2.3.4", direction="any")))

    assert len(events) == 1
    event = events[0]
    assert event.source == "zeek"
    assert event.source_record_id == "C1"
    assert event.src_ip == "10.0.0.5"
    assert event.dst_port == 443
    assert event.bytes_src_to_dst == 100
    assert event.provenance["sensor_version"] == "8.0"


def test_suricata_flow_and_alert_are_distinct_observations(tmp_path):
    path = tmp_path / "eve.jsonl"
    flow = {
        "timestamp": "2026-09-18T09:00:00.000000+0000",
        "flow_id": 99,
        "event_type": "flow",
        "src_ip": "10.0.0.5",
        "src_port": 50000,
        "dest_ip": "1.2.3.4",
        "dest_port": 443,
        "proto": "TCP",
        "app_proto": "tls",
        "flow": {
            "pkts_toserver": 4,
            "pkts_toclient": 3,
            "bytes_toserver": 500,
            "bytes_toclient": 200,
            "state": "established",
        },
    }
    alert = {
        "timestamp": "2026-09-18T09:00:01.000000+0000",
        "flow_id": 99,
        "event_type": "alert",
        "src_ip": "10.0.0.5",
        "src_port": 50000,
        "dest_ip": "1.2.3.4",
        "dest_port": 443,
        "proto": "TCP",
        "alert": {
            "signature_id": 1001,
            "signature": "Test signature",
            "category": "Potentially Bad Traffic",
            "severity": 2,
            "action": "allowed",
        },
    }
    with path.open("w", encoding="utf-8") as fh:
        fh.write(json.dumps(flow) + "\n")
        fh.write(json.dumps(alert) + "\n")

    source = SuricataEVEDataSource(str(path), sensor_version="8.0")
    events = list(source.query(NetworkQuery(indicator="1.2.3.4")))

    assert {event.source_event_type for event in events} == {"flow", "alert"}
    alert_event = next(event for event in events if event.source_event_type == "alert")
    assert alert_event.provenance["alert"]["signature_id"] == 1001
