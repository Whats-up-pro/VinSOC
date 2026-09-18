from __future__ import annotations

from collections import defaultdict
from typing import Any, Dict, Iterable, List, Set

from telemetry.network.models import NormalizedNetworkEvent
from telemetry.network.query import NetworkScope


DEFAULT_ADMIN_PORTS: Set[int] = {22, 445, 3389, 5985, 5986}


def analyze_service_fanout(
    events: Iterable[NormalizedNetworkEvent],
    scope: NetworkScope | None,
    min_unique_internal_targets: int = 4,
    admin_ports: Set[int] | None = None,
) -> List[Dict[str, Any]]:
    """Detect internal administrative-service fan-out; does not assert lateral movement."""
    if scope is None:
        return []
    ports = admin_ports or DEFAULT_ADMIN_PORTS
    by_source = defaultdict(list)
    for event in events:
        if (
            event.source_event_type == "flow"
            and event.dst_port in ports
            and scope.classify(event.src_ip) == "INTERNAL"
            and scope.classify(event.dst_ip) == "INTERNAL"
        ):
            by_source[event.src_ip].append(event)

    findings = []
    for src_ip, group in by_source.items():
        targets = {event.dst_ip for event in group}
        if len(targets) < min_unique_internal_targets:
            continue
        findings.append({
            "analytic": "service_fanout",
            "classification": "internal_service_fanout_candidate",
            "src_ip": src_ip,
            "unique_internal_targets": len(targets),
            "ports": sorted({event.dst_port for event in group if event.dst_port is not None}),
            "connection_count": len(group),
            "related_event_ids": [event.event_id for event in group],
        })
    return findings
