from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
import ipaddress
from typing import Iterable, List, Optional

from telemetry.network.models import NormalizedNetworkEvent


def _parse_iso(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


@dataclass
class NetworkScope:
    local_networks: List[str] = field(default_factory=list)

    def classify(self, ip: str) -> str:
        try:
            addr = ipaddress.ip_address(ip)
        except ValueError:
            return "UNKNOWN"
        for network in self.local_networks:
            try:
                if addr in ipaddress.ip_network(network, strict=False):
                    return "INTERNAL"
            except ValueError:
                continue
        return "EXTERNAL" if self.local_networks else "UNKNOWN"


@dataclass
class NetworkQuery:
    indicator: str
    indicator_type: str = "ipv4"
    start: Optional[str] = None
    end: Optional[str] = None
    direction: str = "any"
    scope: Optional[NetworkScope] = None
    max_events: int = 5000

    def matches(self, event: NormalizedNetworkEvent) -> bool:
        if self.start and _parse_iso(event.observed_at) < _parse_iso(self.start):
            return False
        if self.end and _parse_iso(event.observed_at) > _parse_iso(self.end):
            return False

        src_match = event.src_ip == self.indicator
        dst_match = event.dst_ip == self.indicator

        if self.indicator_type == "domain":
            # conn/flow logs generally do not carry domains. Domain support requires
            # DNS/HTTP/TLS enrichment in a later milestone.
            return False

        if self.direction == "src":
            return src_match
        if self.direction == "dst":
            return dst_match
        if self.direction == "outbound":
            if not self.scope:
                return False
            return (
                self.scope.classify(event.src_ip) == "INTERNAL"
                and self.scope.classify(event.dst_ip) == "EXTERNAL"
                and src_match
            )
        if self.direction == "inbound":
            if not self.scope:
                return False
            return (
                self.scope.classify(event.src_ip) == "EXTERNAL"
                and self.scope.classify(event.dst_ip) == "INTERNAL"
                and dst_match
            )
        return src_match or dst_match

    def filter(self, events: Iterable[NormalizedNetworkEvent]):
        count = 0
        for event in events:
            if self.matches(event):
                yield event
                count += 1
                if count >= self.max_events:
                    break
