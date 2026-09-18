from __future__ import annotations

import json
from pathlib import Path
from typing import Iterable

from telemetry.network.base import NetworkDataSource
from telemetry.network.models import NormalizedNetworkEvent
from telemetry.network.query import NetworkQuery


class SuricataEVEDataSource(NetworkDataSource):
    """Streaming reader for Suricata EVE JSON flow and alert records."""

    name = "suricata"

    def __init__(self, path: str, sensor_version: str | None = None):
        self.path = Path(path)
        self.sensor_version = sensor_version

    def _events(self) -> Iterable[NormalizedNetworkEvent]:
        with self.path.open("r", encoding="utf-8") as fh:
            for line_number, line in enumerate(fh, start=1):
                line = line.strip()
                if not line:
                    continue
                try:
                    row = json.loads(line)
                except json.JSONDecodeError:
                    continue

                event_type = row.get("event_type")
                if event_type not in {"flow", "alert"}:
                    continue
                if not row.get("timestamp") or not row.get("src_ip") or not row.get("dest_ip"):
                    continue

                flow = row.get("flow", {}) if isinstance(row.get("flow"), dict) else {}
                alert = row.get("alert", {}) if isinstance(row.get("alert"), dict) else {}
                raw_action = alert.get("action") or flow.get("state")

                yield NormalizedNetworkEvent.create(
                    event_id=f"suricata:{row.get('flow_id') or line_number}:{event_type}",
                    source=self.name,
                    source_record_id=str(row.get("flow_id")) if row.get("flow_id") is not None else None,
                    observed_at=str(row["timestamp"]),
                    src_ip=str(row["src_ip"]),
                    src_port=row.get("src_port"),
                    dst_ip=str(row["dest_ip"]),
                    dst_port=row.get("dest_port"),
                    protocol=row.get("proto"),
                    app_protocol=row.get("app_proto"),
                    duration_seconds=None,
                    bytes_src_to_dst=flow.get("bytes_toserver"),
                    bytes_dst_to_src=flow.get("bytes_toclient"),
                    packets_src_to_dst=flow.get("pkts_toserver"),
                    packets_dst_to_src=flow.get("pkts_toclient"),
                    state=flow.get("state"),
                    action=raw_action,
                    source_event_type=event_type,
                    provenance={
                        "format": "suricata_eve_json",
                        "path": str(self.path),
                        "line_number": line_number,
                        "sensor_version": self.sensor_version,
                        "alert": {
                            "signature_id": alert.get("signature_id"),
                            "signature": alert.get("signature"),
                            "category": alert.get("category"),
                            "severity": alert.get("severity"),
                        } if event_type == "alert" else None,
                    },
                    raw=row,
                )

    def query(self, query: NetworkQuery):
        return query.filter(self._events())
