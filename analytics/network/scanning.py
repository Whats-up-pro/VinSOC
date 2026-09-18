from __future__ import annotations

from collections import defaultdict
from datetime import datetime
from typing import Any, Dict, Iterable, List

from telemetry.network.models import NormalizedNetworkEvent


def _dt(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def _within_window(group: List[NormalizedNetworkEvent], window_seconds: int):
    ordered = sorted(group, key=lambda event: _dt(event.observed_at))
    for start_index, start_event in enumerate(ordered):
        start_ts = _dt(start_event.observed_at)
        window = []
        for event in ordered[start_index:]:
            if (_dt(event.observed_at) - start_ts).total_seconds() > window_seconds:
                break
            window.append(event)
        yield window


def analyze_scanning(
    events: Iterable[NormalizedNetworkEvent],
    window_seconds: int = 60,
    min_unique_targets: int = 8,
    min_unique_ports: int = 8,
) -> List[Dict[str, Any]]:
    """Detect horizontal/vertical scan candidates using separate grouping axes.

    Horizontal: a source probes the same destination port across many hosts.
    Vertical: a source probes many destination ports on the same host.
    """
    flows = [event for event in events if event.source_event_type == "flow"]
    findings: List[Dict[str, Any]] = []

    horizontal_groups = defaultdict(list)
    vertical_groups = defaultdict(list)
    for event in flows:
        horizontal_groups[(event.src_ip, event.dst_port)].append(event)
        vertical_groups[(event.src_ip, event.dst_ip)].append(event)

    for (src_ip, dst_port), group in horizontal_groups.items():
        for window in _within_window(group, window_seconds):
            targets = {event.dst_ip for event in window}
            if len(targets) < min_unique_targets:
                continue
            findings.append({
                "analytic": "scan",
                "classification": "horizontal_scan_candidate",
                "src_ip": src_ip,
                "dst_port": dst_port,
                "window_seconds": window_seconds,
                "unique_targets": len(targets),
                "unique_ports": 1 if dst_port is not None else 0,
                "connection_attempts": len(window),
                "related_event_ids": [event.event_id for event in window],
            })
            break

    for (src_ip, dst_ip), group in vertical_groups.items():
        for window in _within_window(group, window_seconds):
            ports = {event.dst_port for event in window if event.dst_port is not None}
            if len(ports) < min_unique_ports:
                continue
            findings.append({
                "analytic": "scan",
                "classification": "vertical_scan_candidate",
                "src_ip": src_ip,
                "dst_ip": dst_ip,
                "window_seconds": window_seconds,
                "unique_targets": 1,
                "unique_ports": len(ports),
                "connection_attempts": len(window),
                "related_event_ids": [event.event_id for event in window],
            })
            break

    return findings
