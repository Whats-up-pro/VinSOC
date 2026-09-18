from __future__ import annotations

from collections import defaultdict
from datetime import datetime
from statistics import mean, median, pstdev
from typing import Any, Dict, Iterable, List, Tuple

from telemetry.network.models import NormalizedNetworkEvent


def _dt(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def _mad(values: List[float], center: float) -> float:
    deviations = sorted(abs(value - center) for value in values)
    if not deviations:
        return 0.0
    mid = len(deviations) // 2
    if len(deviations) % 2:
        return deviations[mid]
    return (deviations[mid - 1] + deviations[mid]) / 2


def analyze_periodicity(
    events: Iterable[NormalizedNetworkEvent],
    min_samples: int = 4,
    max_cv_candidate: float = 0.30,
) -> List[Dict[str, Any]]:
    """Find low-jitter repeated flows without claiming C2 compromise."""
    groups: Dict[Tuple[str, str, int | None, str | None], List[NormalizedNetworkEvent]] = defaultdict(list)
    for event in events:
        if event.source_event_type != "flow":
            continue
        key = (event.src_ip, event.dst_ip, event.dst_port, event.protocol)
        groups[key].append(event)

    findings = []
    for (src_ip, dst_ip, dst_port, protocol), group in groups.items():
        if len(group) < min_samples:
            continue
        ordered = sorted(group, key=lambda event: _dt(event.observed_at))
        intervals = [
            (_dt(ordered[i].observed_at) - _dt(ordered[i - 1].observed_at)).total_seconds()
            for i in range(1, len(ordered))
        ]
        intervals = [value for value in intervals if value > 0]
        if len(intervals) < min_samples - 1:
            continue

        mean_interval = mean(intervals)
        median_interval = median(intervals)
        std_interval = pstdev(intervals) if len(intervals) > 1 else 0.0
        cv = std_interval / mean_interval if mean_interval > 0 else None
        mad = _mad(intervals, median_interval)
        candidate = cv is not None and cv <= max_cv_candidate

        findings.append({
            "analytic": "periodicity",
            "classification": "periodic_connection_candidate" if candidate else "irregular",
            "src_ip": src_ip,
            "dst_ip": dst_ip,
            "dst_port": dst_port,
            "protocol": protocol,
            "sample_count": len(ordered),
            "mean_interval_seconds": mean_interval,
            "median_interval_seconds": median_interval,
            "std_interval_seconds": std_interval,
            "mad_seconds": mad,
            "coefficient_of_variation": cv,
            "thresholds": {
                "min_samples": min_samples,
                "max_cv_candidate": max_cv_candidate,
            },
            "related_event_ids": [event.event_id for event in ordered],
        })
    return findings
