from __future__ import annotations

from collections import defaultdict
from typing import Any, Dict, Iterable, List, Tuple

from telemetry.network.models import NormalizedNetworkEvent
from telemetry.network.query import NetworkScope


def analyze_transfer(
    events: Iterable[NormalizedNetworkEvent],
    scope: NetworkScope | None = None,
) -> List[Dict[str, Any]]:
    """Compute transfer asymmetry metrics without declaring exfiltration."""
    groups: Dict[Tuple[str, str], List[NormalizedNetworkEvent]] = defaultdict(list)
    for event in events:
        if event.source_event_type == "flow":
            groups[(event.src_ip, event.dst_ip)].append(event)

    findings = []
    for (src_ip, dst_ip), group in groups.items():
        outbound = sum(max(event.bytes_src_to_dst or 0, 0) for event in group)
        inbound = sum(max(event.bytes_dst_to_src or 0, 0) for event in group)
        ratio = outbound / inbound if inbound > 0 else (float("inf") if outbound > 0 else 0.0)
        findings.append({
            "analytic": "transfer",
            "classification": "transfer_metrics",
            "src_ip": src_ip,
            "dst_ip": dst_ip,
            "bytes_out": outbound,
            "bytes_in": inbound,
            "out_in_ratio": ratio,
            "connection_count": len(group),
            "src_scope": scope.classify(src_ip) if scope else "UNKNOWN",
            "dst_scope": scope.classify(dst_ip) if scope else "UNKNOWN",
            "related_event_ids": [event.event_id for event in group],
        })
    return findings
