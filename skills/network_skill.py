"""Network Investigation Skill

Read-only investigation over normalized telemetry. Raw telemetry is emitted as
OBSERVED evidence; deterministic analytics are emitted as DERIVED evidence.
The skill does not classify hosts as compromised or declare C2/exfiltration.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from ipaddress import IPv4Address
from typing import Any, Dict, Iterable, List, Optional
import uuid

from analytics.network import (
    analyze_periodicity,
    analyze_scanning,
    analyze_service_fanout,
    analyze_transfer,
)
from skills.base import BaseSkill, SkillContract, SkillResult
from telemetry.network.base import NetworkDataSource
from telemetry.network.models import NormalizedNetworkEvent
from telemetry.network.query import NetworkQuery, NetworkScope


class NetworkSkill(BaseSkill):
    skill_name = "network_investigation"
    skill_version = "2.0.0"

    def __init__(
        self,
        mock_data: Optional[Dict[str, Any]] = None,
        data_sources: Optional[List[NetworkDataSource]] = None,
        local_networks: Optional[List[str]] = None,
        max_events: int = 5000,
    ):
        super().__init__()
        self.mock_data = mock_data or {}
        self.data_sources = list(data_sources or [])
        self.scope = NetworkScope(local_networks=list(local_networks or []))
        self.max_events = max_events

    def validate_input(self, **kwargs) -> tuple[bool, Optional[str]]:
        if "indicator" not in kwargs:
            return False, "Missing required parameter: indicator"

        indicator_type = kwargs.get("indicator_type") or "ipv4"
        if indicator_type != "ipv4":
            return False, "flow-only network lookup requires IPv4; domain lookup is unavailable"
        if not isinstance(kwargs["indicator"], str):
            return False, "flow-only network lookup requires a string IPv4 address"
        try:
            IPv4Address(kwargs["indicator"])
        except (ValueError, TypeError):
            return False, "flow-only network lookup requires a valid IPv4 address"

        direction = kwargs.get("direction", "any")
        if direction not in {"any", "src", "dst", "outbound", "inbound"}:
            return False, "direction must be any/src/dst/outbound/inbound"
        if direction in {"outbound", "inbound"} and not self.scope.local_networks:
            return False, "local_networks must be configured for inbound/outbound queries"

        time_range = kwargs.get("time_range")
        if time_range is not None:
            if not isinstance(time_range, dict) or "start" not in time_range or "end" not in time_range:
                return False, "time_range must be a dict with start and end"
            try:
                self._parse_time(time_range["start"])
                self._parse_time(time_range["end"])
            except (TypeError, ValueError):
                return False, "time_range timestamps must be ISO-8601"

        return True, None

    @staticmethod
    def _parse_time(value: str) -> datetime:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))

    def _default_time_range(self) -> Dict[str, str]:
        now = datetime.now(timezone.utc)
        return {
            "start": (now - timedelta(hours=24)).isoformat(),
            "end": now.isoformat(),
        }

    def _execute(self, **kwargs) -> SkillResult:
        indicator = kwargs["indicator"]
        indicator_type = kwargs.get("indicator_type") or "ipv4"
        explicit_time_range = kwargs.get("time_range")
        time_range = explicit_time_range or self._default_time_range()
        direction = kwargs.get("direction", "any")

        events = list(
            self._query_events(
                indicator=indicator,
                indicator_type=indicator_type,
                time_range=time_range,
                direction=direction,
                apply_time_filter=explicit_time_range is not None or not self.mock_data,
            )
        )
        return self._build_result(
            indicator=indicator,
            indicator_type=indicator_type,
            time_range=time_range,
            direction=direction,
            events=events,
        )

    def _query_events(
        self,
        indicator: str,
        indicator_type: str,
        time_range: Dict[str, str],
        direction: str,
        apply_time_filter: bool = True,
    ) -> Iterable[NormalizedNetworkEvent]:
        query = NetworkQuery(
            indicator=indicator,
            indicator_type=indicator_type,
            start=time_range["start"] if apply_time_filter else None,
            end=time_range["end"] if apply_time_filter else None,
            direction=direction,
            scope=self.scope,
            max_events=self.max_events,
        )

        if self.mock_data:
            mock = self.mock_data.get(indicator, self.mock_data.get("*", {}))
            for event in query.filter(self._normalize_mock_connections(mock.get("connections", []))):
                yield event
            return

        emitted = 0
        for source in self.data_sources:
            for event in source.query(query):
                yield event
                emitted += 1
                if emitted >= self.max_events:
                    return

    def _normalize_mock_connections(
        self, connections: List[Dict[str, Any]]
    ) -> Iterable[NormalizedNetworkEvent]:
        for index, row in enumerate(connections):
            timestamp = row.get("timestamp")
            if not timestamp:
                continue
            src = str(row.get("src") or row.get("src_ip") or "0.0.0.0")
            dst = str(row.get("dst") or row.get("dst_ip") or "0.0.0.0")
            yield NormalizedNetworkEvent.create(
                event_id=f"mock:{index}:{uuid.uuid4().hex[:6]}",
                source="mock",
                source_record_id=str(index),
                observed_at=str(timestamp),
                src_ip=src,
                src_port=row.get("src_port"),
                dst_ip=dst,
                dst_port=row.get("dst_port"),
                protocol=row.get("protocol"),
                app_protocol=row.get("service"),
                duration_seconds=row.get("duration"),
                bytes_src_to_dst=row.get("bytes_out"),
                bytes_dst_to_src=row.get("bytes_in"),
                packets_src_to_dst=row.get("packets_out"),
                packets_dst_to_src=row.get("packets_in"),
                state=row.get("state"),
                action=row.get("action"),
                source_event_type="flow",
                provenance={"format": "mock_fixture"},
                raw=row,
            )

    @staticmethod
    def _is_failed(event: NormalizedNetworkEvent) -> bool:
        action = (event.action or "").upper()
        state = (event.state or "").upper()
        return action in {"DROP", "DENY", "REJECT", "BLOCK"} or state in {
            "REJ", "RSTO", "RSTR", "SH", "SHR"
        }

    def _build_result(
        self,
        indicator: str,
        indicator_type: str,
        time_range: Dict[str, str],
        direction: str,
        events: List[NormalizedNetworkEvent],
    ) -> SkillResult:
        flows = [event for event in events if event.source_event_type == "flow"]
        alerts = [event for event in events if event.source_event_type == "alert"]

        unique_destinations = len({event.dst_ip for event in flows})
        unique_ports = len({event.dst_port for event in flows if event.dst_port is not None})
        failed_connections = sum(1 for event in flows if self._is_failed(event))
        successful_connections = max(len(flows) - failed_connections, 0)

        periodicity = [
            item for item in analyze_periodicity(flows)
            if item["classification"] == "periodic_connection_candidate"
        ]
        scans = analyze_scanning(flows)
        transfers = analyze_transfer(flows, self.scope if self.scope.local_networks else None)
        fanout = analyze_service_fanout(
            flows,
            self.scope if self.scope.local_networks else None,
        )

        evidence_items = self._build_evidence_items(
            flows=flows,
            alerts=alerts,
            periodicity=periodicity,
            scans=scans,
            transfers=transfers,
            fanout=fanout,
        )

        patterns_detected = []
        for item in periodicity:
            patterns_detected.append({
                "pattern": "beaconing",
                "confidence": "medium",
                "evidence": [
                    f"periodicity candidate CV={item['coefficient_of_variation']:.4f} "
                    f"over {item['sample_count']} flows"
                ],
            })
        for item in scans:
            patterns_detected.append({
                "pattern": "port_scan",
                "confidence": "medium",
                "evidence": [item["classification"]],
            })

        source_summary: Dict[str, int] = {}
        for event in events:
            source_summary[event.source] = source_summary.get(event.source, 0) + 1

        observed_evidence = [{
            "type": "network_event_count",
            "value": len(events),
            "context": "Normalized network telemetry matched by the investigation query",
        }]

        return SkillResult(
            success=True,
            data={
                "indicator": indicator,
                "indicator_type": indicator_type,
                "query_time_range": time_range,
                "query_direction": direction,
                "total_connections": len(flows),
                "total_alerts": len(alerts),
                "unique_destinations": unique_destinations,
                "unique_ports": unique_ports,
                "failed_connections": failed_connections,
                "successful_connections": successful_connections,
                "source_summary": source_summary,
                "analytics": {
                    "periodicity_candidates": periodicity,
                    "scan_candidates": scans,
                    "transfer_metrics": transfers,
                    "service_fanout_candidates": fanout,
                },
                # Compatibility surface for existing scenarios/tests. No "normal"
                # result is emitted because absence of a candidate is not proof
                # that traffic is benign.
                "patterns_detected": patterns_detected,
                "connection_summary": self._connection_summary(flows),
                "observed_evidence": observed_evidence,
                "evidence_items": evidence_items,
                "limitations": self._limitations(events, indicator_type),
                "provenance": {
                    "network_skill_version": self.skill_version,
                    "max_events": self.max_events,
                    "local_networks_configured": bool(self.scope.local_networks),
                },
            },
            evidence_ids=[],
        )

    def _build_evidence_items(
        self,
        flows: List[NormalizedNetworkEvent],
        alerts: List[NormalizedNetworkEvent],
        periodicity: List[Dict[str, Any]],
        scans: List[Dict[str, Any]],
        transfers: List[Dict[str, Any]],
        fanout: List[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        items: List[Dict[str, Any]] = []

        groups: Dict[tuple, List[NormalizedNetworkEvent]] = {}
        for event in flows:
            key = (event.source, event.src_ip, event.dst_ip, event.dst_port, event.protocol)
            groups.setdefault(key, []).append(event)

        event_to_group_key: Dict[str, str] = {}
        for index, (key, group) in enumerate(groups.items(), start=1):
            source, src_ip, dst_ip, dst_port, protocol = key
            local_key = f"obs_flow_{index}"
            for event in group:
                event_to_group_key[event.event_id] = local_key
            ordered = sorted(group, key=lambda event: self._parse_time(event.observed_at))
            items.append({
                "local_key": local_key,
                "evidence_class": "OBSERVED",
                "type": "network_flow_aggregate",
                "source_name": source,
                "observed_at": ordered[0].observed_at,
                "data": {
                    "src_ip": src_ip,
                    "dst_ip": dst_ip,
                    "dst_port": dst_port,
                    "protocol": protocol,
                    "connection_count": len(group),
                    "first_seen": ordered[0].observed_at,
                    "last_seen": ordered[-1].observed_at,
                    "bytes_src_to_dst": sum(event.bytes_src_to_dst or 0 for event in group),
                    "bytes_dst_to_src": sum(event.bytes_dst_to_src or 0 for event in group),
                },
                "provenance": {
                    "source_record_ids": [
                        event.source_record_id for event in group[:100] if event.source_record_id
                    ],
                    "source_event_count": len(group),
                    "record_ids_truncated": len(group) > 100,
                },
            })

        for index, event in enumerate(alerts, start=1):
            alert = event.provenance.get("alert") or {}
            items.append({
                "local_key": f"obs_alert_{index}",
                "evidence_class": "OBSERVED",
                "type": "network_ids_alert",
                "source_name": event.source,
                "observed_at": event.observed_at,
                "data": {
                    "src_ip": event.src_ip,
                    "dst_ip": event.dst_ip,
                    "dst_port": event.dst_port,
                    "signature_id": alert.get("signature_id"),
                    "signature": alert.get("signature"),
                    "category": alert.get("category"),
                    "severity": alert.get("severity"),
                    "action": event.action,
                },
                "provenance": event.provenance,
            })

        analytic_sets = [
            ("periodicity_candidate", periodicity),
            ("scan_candidate", scans),
            ("transfer_metrics", transfers),
            ("service_fanout_candidate", fanout),
        ]
        derived_index = 0
        for evidence_type, findings in analytic_sets:
            for finding in findings:
                derived_index += 1
                related_local_keys = sorted({
                    event_to_group_key[event_id]
                    for event_id in finding.get("related_event_ids", [])
                    if event_id in event_to_group_key
                })
                data = {
                    key: value for key, value in finding.items()
                    if key != "related_event_ids"
                }
                items.append({
                    "local_key": f"derived_{derived_index}",
                    "evidence_class": "DERIVED",
                    "type": evidence_type,
                    "source_name": f"network_{finding.get('analytic', 'analytic')}_v1",
                    "data": data,
                    "provenance": {
                        "algorithm": finding.get("analytic"),
                        "deterministic": True,
                    },
                    "related_local_keys": related_local_keys,
                })
        return items

    @staticmethod
    def _connection_summary(flows: List[NormalizedNetworkEvent]) -> List[Dict[str, Any]]:
        groups: Dict[tuple, List[NormalizedNetworkEvent]] = {}
        for event in flows:
            key = (event.dst_ip, event.dst_port, event.protocol)
            groups.setdefault(key, []).append(event)

        summary = []
        for (dst, port, protocol), group in sorted(
            groups.items(), key=lambda item: len(item[1]), reverse=True
        )[:20]:
            ordered = sorted(group, key=lambda event: event.observed_at)
            summary.append({
                "dst": dst,
                "port": port,
                "protocol": protocol,
                "count": len(group),
                "first_seen": ordered[0].observed_at,
                "last_seen": ordered[-1].observed_at,
            })
        return summary

    def _limitations(self, events: List[NormalizedNetworkEvent], indicator_type: str) -> List[str]:
        limitations = []
        if not events:
            limitations.append("No matching network telemetry was found")
        if indicator_type == "domain":
            limitations.append(
                "Domain lookup is not available from flow-only telemetry; DNS/TLS enrichment is deferred"
            )
        if len(events) >= self.max_events:
            limitations.append("Network result reached max_events and may be truncated")
        return limitations

    def validate_output(self, data: Dict[str, Any]) -> tuple[bool, Optional[str]]:
        from skills.validators import validate_network_result
        return validate_network_result(data)

    def get_contract(self) -> SkillContract:
        return SkillContract(
            skill_name=self.skill_name,
            version=self.skill_version,
            required_inputs=["indicator"],
            output_schema="NetworkResult",
            lifecycle_stage="investigate",
            read_only=True,
        )


def investigate_network(
    indicator: str,
    indicator_type: Optional[str] = None,
    time_range: Optional[Dict[str, str]] = None,
    mock_data: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    skill = NetworkSkill(mock_data=mock_data)
    result = skill.execute(
        indicator=indicator,
        indicator_type=indicator_type or "ipv4",
        time_range=time_range,
    )
    if not result.success:
        raise ValueError(result.error)
    return result.data
