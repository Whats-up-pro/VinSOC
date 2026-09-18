"""
Network Investigation Skill

Analyzes network telemetry for patterns and anomalies:
- Connection frequency
- Port patterns
- Failed/success ratios
- Port scan detection
- Beaconing patterns
- Data exfiltration patterns

This skill is read-only. It queries logs but does not modify anything.
"""
import uuid
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Union

from skills.base import BaseSkill, SkillContract, SkillResult
from vinsoc_data.domain_queries import DuckDBNetworkRepository


class NetworkSkill(BaseSkill):
    """
    Network investigation skill for analyzing telemetry patterns.
    """

    skill_name = "network_investigation"
    skill_version = "1.0.0"

    # Suspicious port list
    SUSPICIOUS_PORTS = {
        22: "SSH",
        23: "Telnet",
        445: "SMB",
        3389: "RDP",
        4444: "Metasploit",
        5555: "Android ADB",
        6667: "IRC",
        31337: "Back Orifice",
    }

    def __init__(
        self,
        mock_data: Optional[Dict[str, Any]] = None,
        repository: Optional[DuckDBNetworkRepository] = None,
    ):
        """
        Initialize Network skill.

        Args:
            mock_data: Optional dict for testing. It takes precedence over the
                repository and is not benchmark data.
                {
                    "indicator_value": {
                        "connections": [...],
                        ...
                    }
                }
        """
        super().__init__()
        self.mock_data = mock_data or {}
        self.repository = repository

    def validate_input(self, **kwargs) -> tuple[bool, Optional[str]]:
        """Validate network investigation parameters."""
        if "indicator" not in kwargs:
            return False, "Missing required parameter: indicator"

        indicator = kwargs["indicator"]

        # Optional time range validation
        if "time_range" in kwargs:
            time_range = kwargs["time_range"]
            if not isinstance(time_range, dict):
                return False, "time_range must be a dict with start and end"
            if "start" not in time_range or "end" not in time_range:
                return False, "time_range must have start and end"

        # Optional indicator type
        if "indicator_type" in kwargs:
            valid_types = ["ipv4", "domain"]
            if kwargs["indicator_type"] not in valid_types:
                return False, f"indicator_type must be one of {valid_types}"

        return True, None

    def _execute(self, **kwargs) -> SkillResult:
        """
        Execute network investigation.

        Args:
            indicator: The IOC to investigate
            indicator_type: Optional type (auto-detected if not provided)
            time_range: Optional dict with start/end ISO timestamps
            direction: Optional "src" or "dst" to filter connections

        Returns:
            SkillResult with network analysis
        """
        indicator = kwargs.get("indicator")
        indicator_type = kwargs.get("indicator_type", "ipv4")
        time_range = kwargs.get("time_range")
        direction = kwargs.get("direction", "dst")

        evidence_id = f"net_{uuid.uuid4().hex[:8]}"

        # Check mock data
        if self.mock_data:
            mock_result = self.mock_data.get(indicator, self.mock_data.get("*", {}))
            if mock_result:
                return self._build_result_from_mock(indicator, indicator_type, mock_result, time_range, evidence_id)

        if self.repository is not None:
            try:
                query_result = self.repository.find_connections(indicator, time_range)
                connections = query_result.rows
                query_time_range = time_range or self.repository.coverage_time_range() or self._default_time_range()
            except Exception as exc:
                return SkillResult(
                    success=False,
                    error=f"Network DuckDB query failed: {exc}",
                    evidence_ids=[evidence_id],
                )
            return self._build_result_from_mock(
                indicator,
                indicator_type,
                {
                    "connections": connections,
                    "observed_evidence": [
                        {
                            "type": "connection_count",
                            "value": len(connections),
                            "context": "Connections returned from the frozen public-data snapshot",
                        },
                        *(
                            [
                                {
                                    "type": "query_truncated",
                                    "value": True,
                                    "context": "The read-only query reached the configured row limit.",
                                }
                            ]
                            if query_result.truncated
                            else []
                        ),
                    ],
                },
                query_time_range,
                evidence_id,
            )

        # Default empty result
        return self._build_empty_result(indicator, indicator_type, time_range, evidence_id)

    def _build_result_from_mock(
        self,
        indicator: str,
        indicator_type: str,
        mock_data: Dict[str, Any],
        time_range: Optional[Dict[str, Any]],
        evidence_id: str
    ) -> SkillResult:
        """Build result from mock data."""
        connections = mock_data.get("connections", [])

        # Analyze connections
        analysis = self._analyze_connections(connections, indicator)

        return SkillResult(
            success=True,
            data={
                "indicator": indicator,
                "indicator_type": indicator_type,
                "query_time_range": time_range or self._default_time_range(),
                "total_connections": len(connections),
                "unique_destinations": analysis["unique_destinations"],
                "unique_ports": analysis["unique_ports"],
                "failed_connections": analysis["failed_connections"],
                "successful_connections": analysis["successful_connections"],
                "patterns_detected": analysis["patterns"],
                "connection_summary": analysis["summary"],
                "observed_evidence": mock_data.get("observed_evidence", [
                    {"type": "connection_count", "value": len(connections), "context": "Total connections analyzed"}
                ])
            },
            evidence_ids=[evidence_id]
        )

    def _build_empty_result(
        self,
        indicator: str,
        indicator_type: str,
        time_range: Optional[Dict[str, Any]],
        evidence_id: str
    ) -> SkillResult:
        """Build empty result when no data available."""
        return SkillResult(
            success=True,
            data={
                "indicator": indicator,
                "indicator_type": indicator_type,
                "query_time_range": time_range or self._default_time_range(),
                "total_connections": 0,
                "unique_destinations": 0,
                "unique_ports": 0,
                "failed_connections": 0,
                "successful_connections": 0,
                "patterns_detected": [],
                "connection_summary": [],
                "observed_evidence": [
                    {"type": "lookup_status", "value": "no_data", "context": "No network logs found for this indicator"}
                ]
            },
            evidence_ids=[evidence_id]
        )

    def _default_time_range(self) -> Dict[str, str]:
        """Generate default time range (last 24 hours)."""
        now = datetime.utcnow()
        return {
            "start": (now - timedelta(hours=24)).isoformat(),
            "end": now.isoformat()
        }

    def _analyze_connections(
        self,
        connections: List[Dict[str, Any]],
        indicator: str
    ) -> Dict[str, Any]:
        """Analyze connection patterns."""
        if not connections:
            return {
                "unique_destinations": 0,
                "unique_ports": 0,
                "failed_connections": 0,
                "successful_connections": 0,
                "patterns": [],
                "summary": []
            }

        # Count metrics
        destinations = set()
        ports = set()
        failed = 0
        successful = 0
        port_counts = {}

        for conn in connections:
            dst = conn.get("dst", "")
            port = conn.get("dst_port", 0)
            action = conn.get("action", "").upper()

            if dst not in destinations:
                destinations.add(dst)
            if port not in ports:
                ports.add(port)
                port_counts[port] = 0
            port_counts[port] += 1

            if action in ["DROP", "DENY", "REJECT", "BLOCK"]:
                failed += 1
            elif action in ["ALLOW", "ACCEPT"]:
                successful += 1

        # Detect patterns
        patterns = self._detect_patterns(
            connections, destinations, ports, failed, successful, port_counts
        )

        # Build summary
        summary = self._build_summary(connections, port_counts)

        return {
            "unique_destinations": len(destinations),
            "unique_ports": len(ports),
            "failed_connections": failed,
            "successful_connections": successful,
            "patterns": patterns,
            "summary": summary
        }

    def _detect_patterns(
        self,
        connections: List[Dict[str, Any]],
        destinations: set,
        ports: set,
        failed: int,
        successful: int,
        port_counts: Dict[int, int]
    ) -> List[Dict[str, Any]]:
        """Detect suspicious network patterns."""
        patterns = []
        total = len(connections)

        if total == 0:
            return patterns

        # Port scan detection: repeated failed probes across multiple destinations/ports
        if failed >= 3 and (len(ports) >= 1 and len(destinations) >= 3) and failed / total >= 0.5:
            patterns.append({
                "pattern": "port_scan",
                "confidence": "high",
                "evidence": [f"{failed} failed connections across {len(destinations)} destinations and {len(ports)} ports"]
            })

        # High frequency: many connections in short time
        if total > 50:
            patterns.append({
                "pattern": "high_frequency",
                "confidence": "high" if total > 100 else "medium",
                "evidence": [f"{total} connections detected"]
            })

        # Beaconing: regular interval connections
        if self._detect_beaconing(connections):
            patterns.append({
                "pattern": "beaconing",
                "confidence": "medium",
                "evidence": ["Regular connection intervals detected"]
            })

        # Data exfiltration: large outbound data
        total_bytes = sum(c.get("bytes_out", 0) for c in connections)
        if total_bytes > 10 * 1024 * 1024:  # > 10MB
            patterns.append({
                "pattern": "data_exfiltration",
                "confidence": "medium",
                "evidence": [f"Large data transfer: {total_bytes / 1024 / 1024:.2f} MB"]
            })

        # Unusual port usage
        unusual_ports = [p for p in ports if p in self.SUSPICIOUS_PORTS]
        if unusual_ports:
            patterns.append({
                "pattern": "unusual_port",
                "confidence": "medium",
                "evidence": [f"Connections to suspicious ports: {unusual_ports}"]
            })

        # Lateral movement candidate: broad SMB/RDP fan-out to internal hosts
        lateral_ports = {445, 3389}
        if any(p in lateral_ports for p in ports) and len(destinations) >= 4 and successful >= 3:
            patterns.append({
                "pattern": "lateral_movement",
                "confidence": "medium",
                "evidence": [f"Fan-out to {len(destinations)} internal hosts over SMB/RDP"]
            })

        # Default to normal if no patterns detected
        if not patterns:
            patterns.append({
                "pattern": "normal",
                "confidence": "high",
                "evidence": ["No suspicious patterns detected"]
            })

        return patterns

    def _detect_beaconing(self, connections: List[Dict[str, Any]]) -> bool:
        """Detect beaconing pattern (regular intervals)."""
        if len(connections) < 3:
            return False

        try:
            timestamps = []
            for conn in connections:
                ts_str = conn.get("timestamp")
                if ts_str:
                    timestamps.append(datetime.fromisoformat(ts_str.replace("Z", "+00:00")))

            if len(timestamps) < 3:
                return False

            timestamps.sort()

            # Calculate intervals
            intervals = []
            for i in range(1, len(timestamps)):
                delta = (timestamps[i] - timestamps[i-1]).total_seconds()
                intervals.append(delta)

            if not intervals:
                return False

            # Check variance in intervals
            avg_interval = sum(intervals) / len(intervals)
            variance = sum((i - avg_interval) ** 2 for i in intervals) / len(intervals)

            # Low variance = regular beacon
            if avg_interval > 0:
                cv = (variance ** 0.5) / avg_interval  # Coefficient of variation
                if cv < 0.3:  # Low variance
                    return True

        except Exception:
            pass

        return False

    def _build_summary(
        self,
        connections: List[Dict[str, Any]],
        port_counts: Dict[int, int]
    ) -> List[Dict[str, Any]]:
        """Build connection summary."""
        summary = []
        sorted_ports = sorted(port_counts.items(), key=lambda x: x[1], reverse=True)[:10]

        for port, count in sorted_ports:
            relevant_conns = [c for c in connections if c.get("dst_port") == port]
            if relevant_conns:
                first = relevant_conns[0]
                last = relevant_conns[-1]
                summary.append({
                    "dst": first.get("dst", "unknown"),
                    "port": port,
                    "count": count,
                    "first_seen": first.get("timestamp"),
                    "last_seen": last.get("timestamp")
                })

        return summary

    def validate_output(self, data: Dict[str, Any]) -> tuple[bool, Optional[str]]:
        """Validate network output against schema."""
        from skills.validators import validate_network_result
        return validate_network_result(data)

    def get_contract(self) -> SkillContract:
        """Return network skill contract."""
        return SkillContract(
            skill_name=self.skill_name,
            version=self.skill_version,
            required_inputs=["indicator"],
            output_schema="NetworkResult",
            lifecycle_stage="investigate",
            read_only=True,
        )


# Convenience function
def investigate_network(
    indicator: str,
    indicator_type: Optional[str] = None,
    time_range: Optional[Dict[str, str]] = None,
    mock_data: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """
    Investigate network telemetry for an indicator.

    Args:
        indicator: The IOC to investigate
        indicator_type: Optional type override
        time_range: Optional dict with start/end timestamps
        mock_data: Optional mock data for testing

    Returns:
        Dict with network analysis
    """
    skill = NetworkSkill(mock_data=mock_data)
    result = skill.execute(
        indicator=indicator,
        indicator_type=indicator_type,
        time_range=time_range
    )

    if not result.success:
        raise ValueError(result.error)

    return result.data
