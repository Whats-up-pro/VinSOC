from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Iterable

from telemetry.network.base import NetworkDataSource
from telemetry.network.models import NormalizedNetworkEvent
from telemetry.network.query import NetworkQuery


def _zeek_ts(value) -> str:
    if isinstance(value, (int, float)):
        return datetime.fromtimestamp(value, tz=timezone.utc).isoformat()
    return str(value)


class ZeekJSONDataSource(NetworkDataSource):
    """Streaming reader for Zeek JSON conn.log."""

    name = "zeek"

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

                src_ip = row.get("id.orig_h")
                dst_ip = row.get("id.resp_h")
                ts = row.get("ts")
                if not src_ip or not dst_ip or ts is None:
                    continue

                yield NormalizedNetworkEvent.create(
                    event_id=f"zeek:{row.get('uid') or line_number}",
                    source=self.name,
                    source_record_id=row.get("uid"),
                    observed_at=_zeek_ts(ts),
                    src_ip=str(src_ip),
                    src_port=row.get("id.orig_p"),
                    dst_ip=str(dst_ip),
                    dst_port=row.get("id.resp_p"),
                    protocol=row.get("proto"),
                    app_protocol=row.get("service"),
                    duration_seconds=row.get("duration"),
                    bytes_src_to_dst=row.get("orig_bytes"),
                    bytes_dst_to_src=row.get("resp_bytes"),
                    packets_src_to_dst=row.get("orig_pkts"),
                    packets_dst_to_src=row.get("resp_pkts"),
                    state=row.get("conn_state"),
                    source_event_type="flow",
                    provenance={
                        "format": "zeek_conn_json",
                        "path": str(self.path),
                        "line_number": line_number,
                        "sensor_version": self.sensor_version,
                    },
                    raw=row,
                )

    def query(self, query: NetworkQuery):
        return query.filter(self._events())
