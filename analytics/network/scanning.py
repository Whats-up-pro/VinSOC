from __future__ import annotations

from collections import defaultdict
from datetime import datetime
from typing import Any, Dict, Iterable, List

from telemetry.network.models import NormalizedNetworkEvent


def _dt(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def analyze_scanning(
    events: Iterable[NormalizedNetworkEvent],
    window_seconds: int = 60,
    min_unique_targets: int = 8,
    min_unique_ports: int = 8,
) -> List[Dict[str, Any]]:
    """Detect horizontal/vertical scan candidates from flow fan-out within a window."""
    by_source = defaultdict(list)
    for event in events:
        if event.source_event_type == "flow":
            by_source[event.src_ip].append(event)

    findings = []
    for src_ip, group in by_source.items():
        ordered = sorted(group, key=lambda event: _dt(event.observed_at))
        found_horizontal = False
        found_vertical = False
        for start_index, start_event in enumerate(ordered):
            window = []
            start_ts = _dt(start_event.observed_at)
            for event in ordered[start_index:]:
                if (_dt(event.observed_at) - start_ts).total_seconds() > window_seconds:
                    break
                window.append(event)

            targets = {event.dst_ip for event in window}
            ports = {event.dst_port for event in window if event.dst_port is not None}
            if not found_horizontal and len(targets) >= min_unique_targets and len(ports) <= 2:
                findings.append({
                    "analytic": "scan",
                    "classification": "horizontal_scan_candidate",
                    "src_ip": src_ip,
                    "window_seconds": window_seconds,
                    "unique_targets": len(targets),
                    "unique_ports": len(ports),
                    "connection_attempts": len(window),
                    "related_event_ids": [event.event_id for event in window],
                })
                found_horizontal = True

            if not found_vertical and len(ports) >= min_unique_ports and len(targets) <= 2:
                findings.append({
                    "analytic": "scan",
                    "classification": "vertical_scan_candidate",
                    "src_ip": src_ip,
                    "window_seconds": window_seconds,
                    "unique_targets": len(targets),
                    "unique_ports": len(ports),
                    "connection_attempts": len(window),
                    "related_event_ids": [event.event_id for event in window],
                })
                found_vertical = True

            if found_horizontal and found_vertical:
                break
    return findings
