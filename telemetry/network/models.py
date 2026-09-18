from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, Optional
import uuid


@dataclass(frozen=True)
class NormalizedNetworkEvent:
    """Canonical session/alert representation independent of telemetry vendor."""

    event_id: str
    source: str
    source_record_id: Optional[str]
    observed_at: str

    src_ip: str
    src_port: Optional[int]
    dst_ip: str
    dst_port: Optional[int]

    protocol: Optional[str] = None
    app_protocol: Optional[str] = None
    duration_seconds: Optional[float] = None

    bytes_src_to_dst: Optional[int] = None
    bytes_dst_to_src: Optional[int] = None
    packets_src_to_dst: Optional[int] = None
    packets_dst_to_src: Optional[int] = None

    state: Optional[str] = None
    action: Optional[str] = None
    source_event_type: str = "flow"
    provenance: Dict[str, Any] = field(default_factory=dict)
    raw: Dict[str, Any] = field(default_factory=dict)

    @classmethod
    def create(cls, **kwargs) -> "NormalizedNetworkEvent":
        if not kwargs.get("event_id"):
            kwargs["event_id"] = f"netevt_{uuid.uuid4().hex[:12]}"
        return cls(**kwargs)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "event_id": self.event_id,
            "source": self.source,
            "source_record_id": self.source_record_id,
            "observed_at": self.observed_at,
            "src_ip": self.src_ip,
            "src_port": self.src_port,
            "dst_ip": self.dst_ip,
            "dst_port": self.dst_port,
            "protocol": self.protocol,
            "app_protocol": self.app_protocol,
            "duration_seconds": self.duration_seconds,
            "bytes_src_to_dst": self.bytes_src_to_dst,
            "bytes_dst_to_src": self.bytes_dst_to_src,
            "packets_src_to_dst": self.packets_src_to_dst,
            "packets_dst_to_src": self.packets_dst_to_src,
            "state": self.state,
            "action": self.action,
            "source_event_type": self.source_event_type,
            "provenance": self.provenance,
        }
