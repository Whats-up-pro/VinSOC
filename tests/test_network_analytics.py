from datetime import datetime, timedelta, timezone

from analytics.network.beaconing import analyze_periodicity
from analytics.network.scanning import analyze_scanning
from analytics.network.transfer import analyze_transfer
from analytics.network.fanout import analyze_service_fanout
from telemetry.network.models import NormalizedNetworkEvent
from telemetry.network.query import NetworkScope


def ev(i, ts, dst="1.2.3.4", port=443, bytes_out=100, bytes_in=20):
    return NormalizedNetworkEvent.create(
        event_id=f"e{i}",
        source="test",
        source_record_id=str(i),
        observed_at=ts,
        src_ip="10.0.0.5",
        src_port=50000 + i,
        dst_ip=dst,
        dst_port=port,
        protocol="tcp",
        bytes_src_to_dst=bytes_out,
        bytes_dst_to_src=bytes_in,
        source_event_type="flow",
    )


def test_periodicity_exposes_metrics_not_c2_label():
    start = datetime(2026, 9, 18, tzinfo=timezone.utc)
    events = [ev(i, (start + timedelta(seconds=60 * i)).isoformat()) for i in range(6)]
    findings = analyze_periodicity(events)
    candidate = next(f for f in findings if f["classification"] == "periodic_connection_candidate")
    assert candidate["coefficient_of_variation"] == 0
    assert candidate["sample_count"] == 6
    assert "c2" not in candidate["classification"].lower()


def test_horizontal_and_vertical_scan_candidates():
    start = datetime(2026, 9, 18, tzinfo=timezone.utc)
    horizontal = [
        ev(i, (start + timedelta(seconds=i)).isoformat(), dst=f"10.0.1.{i+1}", port=445)
        for i in range(8)
    ]
    vertical = [
        ev(100+i, (start + timedelta(seconds=i)).isoformat(), dst="10.0.2.5", port=1000+i)
        for i in range(8)
    ]
    classes = {f["classification"] for f in analyze_scanning(horizontal + vertical)}
    assert "horizontal_scan_candidate" in classes
    assert "vertical_scan_candidate" in classes


def test_transfer_returns_metrics_not_exfiltration_verdict():
    events = [ev(1, "2026-09-18T00:00:00+00:00", bytes_out=20_000_000, bytes_in=100)]
    finding = analyze_transfer(events)[0]
    assert finding["classification"] == "transfer_metrics"
    assert "exfil" not in finding["classification"]


def test_internal_service_fanout_requires_scope():
    scope = NetworkScope(["10.0.0.0/8"])
    events = [
        ev(i, f"2026-09-18T00:00:0{i}+00:00", dst=f"10.0.1.{i+1}", port=445)
        for i in range(4)
    ]
    findings = analyze_service_fanout(events, scope)
    assert findings[0]["classification"] == "internal_service_fanout_candidate"
