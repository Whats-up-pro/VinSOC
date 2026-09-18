from telemetry.network.models import NormalizedNetworkEvent
from telemetry.network.query import NetworkQuery, NetworkScope


def event(src, dst, ts="2026-09-18T08:00:00+00:00"):
    return NormalizedNetworkEvent.create(
        event_id=f"{src}->{dst}",
        source="test",
        source_record_id=None,
        observed_at=ts,
        src_ip=src,
        src_port=1000,
        dst_ip=dst,
        dst_port=443,
        source_event_type="flow",
    )


def test_time_range_filtering():
    events = [
        event("10.0.0.5", "1.2.3.4", "2026-09-18T08:00:00+00:00"),
        event("10.0.0.5", "1.2.3.4", "2026-09-18T12:00:00+00:00"),
    ]
    q = NetworkQuery(
        indicator="1.2.3.4",
        start="2026-09-18T07:00:00+00:00",
        end="2026-09-18T09:00:00+00:00",
    )
    assert len(list(q.filter(events))) == 1


def test_outbound_requires_local_scope():
    scope = NetworkScope(["10.0.0.0/8"])
    q = NetworkQuery(
        indicator="10.0.0.5",
        direction="outbound",
        scope=scope,
    )
    assert q.matches(event("10.0.0.5", "1.2.3.4"))
    assert not q.matches(event("1.2.3.4", "10.0.0.5"))


def test_domain_is_deferred_for_flow_only_query():
    q = NetworkQuery(indicator="example.com", indicator_type="domain")
    assert not q.matches(event("10.0.0.5", "1.2.3.4"))
