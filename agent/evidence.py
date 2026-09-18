"""
Evidence Store

Stores and manages evidence collected during investigations.
All evidence is immutable once stored for traceability.

Evidence V2: Added explicit epistemic classes (OBSERVED, DERIVED, EXTERNAL_INTEL)
with full provenance tracking.
"""
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional
import json


EVIDENCE_CLASSES = {"OBSERVED", "DERIVED", "EXTERNAL_INTEL"}


@dataclass
class Evidence:
    """Single evidence item with explicit epistemic class and provenance."""
    evidence_id: str
    source_tool: str
    type: str
    data: Dict[str, Any]
    collected_at: str
    linked_from: Optional[str] = None
    evidence_class: str = "OBSERVED"
    source_name: Optional[str] = None
    observed_at: Optional[str] = None
    confidence: Optional[str] = None
    provenance: Dict[str, Any] = field(default_factory=dict)
    references: List[str] = field(default_factory=list)
    related_evidence_ids: List[str] = field(default_factory=list)

    def __post_init__(self):
        if self.evidence_class not in EVIDENCE_CLASSES:
            raise ValueError(
                f"Invalid evidence_class={self.evidence_class}. "
                f"Expected one of {sorted(EVIDENCE_CLASSES)}"
            )

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "evidence_id": self.evidence_id,
            "source_tool": self.source_tool,
            "source_name": self.source_name or self.source_tool,
            "evidence_class": self.evidence_class,
            "type": self.type,
            "data": self.data,
            "collected_at": self.collected_at,
            "observed_at": self.observed_at,
            "confidence": self.confidence,
            "provenance": self.provenance,
            "references": self.references,
            "related_evidence_ids": self.related_evidence_ids,
            "linked_from": self.linked_from,
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
        linked_from: Optional[str] = None,
        evidence_class: str = "OBSERVED",
        source_name: Optional[str] = None,
        observed_at: Optional[str] = None,
        confidence: Optional[str] = None,
        provenance: Optional[Dict[str, Any]] = None,
        references: Optional[List[str]] = None,
        related_evidence_ids: Optional[List[str]] = None,
    ) -> Evidence:
        """
        Add evidence to the store.

        Args:
            source_tool: Name of tool that produced this evidence
            evidence_type: Semantic evidence type (e.g. ioc_reputation, network_connection)
            data: Evidence payload
            linked_from: Optional tool-call ID that produced this evidence
            evidence_class: OBSERVED, DERIVED, or EXTERNAL_INTEL
            source_name: Concrete source/provider (e.g. zeek, threatfox)
            observed_at: Timestamp carried by the source event, if available
            confidence: Source/analytic confidence, if applicable
            provenance: Structured source metadata used for auditability
            references: External references/URLs/IDs
            related_evidence_ids: Parent evidence used to derive/correlate this item

        Returns:
            Evidence object
        """
        evidence = Evidence(
            evidence_id=self._generate_id("ev"),
            source_tool=source_tool,
            type=evidence_type,
            data=data,
            collected_at=datetime.utcnow().isoformat(),
            linked_from=linked_from,
            evidence_class=evidence_class,
            source_name=source_name or source_tool,
            observed_at=observed_at,
            confidence=confidence,
            provenance=provenance or {},
            references=references or [],
            related_evidence_ids=related_evidence_ids or [],
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
