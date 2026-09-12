"""
Evidence Store

Stores and manages evidence collected during investigations.
All evidence is immutable once stored for traceability.
"""
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional
import json


@dataclass
class Evidence:
    """Single piece of evidence from a tool execution."""
    evidence_id: str
    source_tool: str
    type: str
    data: Dict[str, Any]
    collected_at: str
    linked_from: Optional[str] = None  # Tool call ID that produced this

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "evidence_id": self.evidence_id,
            "source_tool": self.source_tool,
            "type": self.type,
            "data": self.data,
            "collected_at": self.collected_at,
            "linked_from": self.linked_from
        }


@dataclass
class ToolCall:
    """Record of a tool call during investigation."""
    call_id: str
    tool: str
    arguments: Dict[str, Any]
    timestamp: str
    result_summary: str
    evidence_ids: List[str]
    error: Optional[str] = None
    duration_ms: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "call_id": self.call_id,
            "tool": self.tool,
            "arguments": self.arguments,
            "timestamp": self.timestamp,
            "result_summary": self.result_summary,
            "evidence_ids": self.evidence_ids,
            "error": self.error,
            "duration_ms": self.duration_ms
        }


class EvidenceStore:
    """
    Store for investigation evidence and tool traces.

    Evidence is append-only (immutable) for audit purposes.
    """

    def __init__(self):
        """Initialize empty evidence store."""
        self.evidence: List[Evidence] = []
        self.tool_calls: List[ToolCall] = []
        self._id_counter = 0

    def _generate_id(self, prefix: str) -> str:
        """Generate unique ID with prefix."""
        self._id_counter += 1
        return f"{prefix}_{uuid.uuid4().hex[:8]}_{self._id_counter}"

    def add_evidence(
        self,
        source_tool: str,
        evidence_type: str,
        data: Dict[str, Any],
        linked_from: Optional[str] = None
    ) -> Evidence:
        """
        Add evidence to the store.

        Args:
            source_tool: Name of tool that produced this evidence
            evidence_type: Type of evidence (e.g., "cti_result", "network_analysis")
            data: Evidence data
            linked_from: Optional ID of tool call that produced this

        Returns:
            Evidence object
        """
        evidence = Evidence(
            evidence_id=self._generate_id("ev"),
            source_tool=source_tool,
            type=evidence_type,
            data=data,
            collected_at=datetime.utcnow().isoformat(),
            linked_from=linked_from
        )
        self.evidence.append(evidence)
        return evidence

    def add_tool_call(
        self,
        tool: str,
        arguments: Dict[str, Any],
        result_summary: str,
        evidence_ids: List[str],
        error: Optional[str] = None,
        duration_ms: float = 0.0
    ) -> ToolCall:
        """
        Record a tool call.

        Args:
            tool: Tool name
            arguments: Arguments passed to tool
            result_summary: Summary of result
            evidence_ids: IDs of evidence produced
            error: Optional error message
            duration_ms: Execution duration

        Returns:
            ToolCall object
        """
        call = ToolCall(
            call_id=self._generate_id("tc"),
            tool=tool,
            arguments=arguments,
            timestamp=datetime.utcnow().isoformat(),
            result_summary=result_summary,
            evidence_ids=evidence_ids,
            error=error,
            duration_ms=duration_ms
        )
        self.tool_calls.append(call)
        return call

    def get_evidence(self, evidence_id: str) -> Optional[Evidence]:
        """Get evidence by ID."""
        for ev in self.evidence:
            if ev.evidence_id == evidence_id:
                return ev
        return None

    def get_evidence_by_tool(self, tool: str) -> List[Evidence]:
        """Get all evidence from a specific tool."""
        return [ev for ev in self.evidence if ev.source_tool == tool]

    def get_all_evidence(self) -> List[Evidence]:
        """Get all evidence."""
        return self.evidence.copy()

    def get_all_tool_calls(self) -> List[ToolCall]:
        """Get all tool calls."""
        return self.tool_calls.copy()

    def to_dict(self) -> Dict[str, Any]:
        """Convert entire store to dictionary."""
        return {
            "evidence": [ev.to_dict() for ev in self.evidence],
            "tool_calls": [tc.to_dict() for tc in self.tool_calls],
            "summary": {
                "total_evidence": len(self.evidence),
                "total_tool_calls": len(self.tool_calls)
            }
        }

    def to_json(self) -> str:
        """Convert to JSON string."""
        return json.dumps(self.to_dict(), indent=2, default=str)

    def get_evidence_summary(self) -> str:
        """Get human-readable summary of collected evidence."""
        if not self.evidence:
            return "No evidence collected yet."

        lines = [f"Collected {len(self.evidence)} evidence items from {len(self.tool_calls)} tool calls:"]

        # Group by tool
        by_tool: Dict[str, List[Evidence]] = {}
        for ev in self.evidence:
            if ev.source_tool not in by_tool:
                by_tool[ev.source_tool] = []
            by_tool[ev.source_tool].append(ev)

        for tool, evs in by_tool.items():
            lines.append(f"  - {tool}: {len(evs)} items")

        return "\n".join(lines)

    def clear(self):
        """Clear all evidence (for new investigation)."""
        self.evidence = []
        self.tool_calls = []
        self._id_counter = 0
