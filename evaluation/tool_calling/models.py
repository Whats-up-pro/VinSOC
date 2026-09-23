"""
R1 Tool Calling Evaluation - Data Models

Defines the formal contract for benchmark cases and evaluation results.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional


class CaseDifficulty(str, Enum):
    """Case difficulty levels."""
    BASIC = "basic"
    INTERMEDIATE = "intermediate"
    ADVANCED = "advanced"


class CaseCategory(str, Enum):
    """Case categories for tool calling evaluation."""
    CTI_ONLY = "cti_only"
    NETWORK_ONLY = "network_only"
    ENDPOINT_ONLY = "endpoint_only"
    CTI_NETWORK = "cti_network"
    CTI_ENDPOINT = "cti_endpoint"
    NETWORK_ENDPOINT = "network_endpoint"
    CTI_NETWORK_ENDPOINT = "cti_network_endpoint"
    HOSTNAME_LED = "hostname_led"
    HASH_LED = "hash_led"
    URL_LED = "url_led"
    NETWORK_ALERT = "network_alert"
    PROCESS_EDR = "process_edr"
    INVALID_IOC = "invalid_ioc"
    UNSUPPORTED_TYPE = "unsupported_type"
    MISSING_INFORMATION = "missing_information"
    NO_TOOL = "no_tool"
    MULTI_STEP_PIVOT = "multi_step_pivot"
    DUPLICATE_TRAP = "duplicate_trap"
    WRONG_ARGUMENT_TRAP = "wrong_argument_trap"


@dataclass
class ExpectedCall:
    """
    Formal specification of an expected tool call.

    Attributes:
        call_id: Unique identifier for this call within the case
        tool: Tool name (cti_enrichment | network_investigation | endpoint_investigation)
        required_arguments: Arguments that must be present
        critical_arguments: Arguments where wrong value invalidates the call
        optional: Whether this call is optional
    """
    call_id: str
    tool: str
    required_arguments: Dict[str, Any] = field(default_factory=dict)
    critical_arguments: List[str] = field(default_factory=list)
    optional: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return {
            "call_id": self.call_id,
            "tool": self.tool,
            "required_arguments": self.required_arguments,
            "critical_arguments": self.critical_arguments,
            "optional": self.optional,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> ExpectedCall:
        return cls(
            call_id=data["call_id"],
            tool=data["tool"],
            required_arguments=data.get("required_arguments", {}),
            critical_arguments=data.get("critical_arguments", []),
            optional=data.get("optional", False),
        )


@dataclass
class OrderingConstraint:
    """
    Semantic ordering constraint between calls.

    Example: endpoint must run before CTI because CTI needs IOC from endpoint result.
    """
    before_call: str  # call_id that must come first
    after_call: str   # call_id that must come second
    reason: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "before_call": self.before_call,
            "after_call": self.after_call,
            "reason": self.reason,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> OrderingConstraint:
        return cls(
            before_call=data["before_call"],
            after_call=data["after_call"],
            reason=data.get("reason", ""),
        )


@dataclass
class ToolCallCase:
    """
    Formal benchmark case for tool calling evaluation.

    This is the canonical representation of expected model behavior
    for a given investigation request.
    """
    case_id: str
    category: CaseCategory
    difficulty: CaseDifficulty
    request: str
    reference_time: str  # ISO 8601
    expected_calls: List[ExpectedCall] = field(default_factory=list)
    forbidden_tools: List[str] = field(default_factory=list)
    ordering_constraints: List[OrderingConstraint] = field(default_factory=list)
    acceptable_trajectories: List[List[str]] = field(default_factory=list)  # Optional: list of valid tool sequences
    notes: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "case_id": self.case_id,
            "category": self.category.value,
            "difficulty": self.difficulty.value,
            "request": self.request,
            "reference_time": self.reference_time,
            "expected_calls": [c.to_dict() for c in self.expected_calls],
            "forbidden_tools": self.forbidden_tools,
            "ordering_constraints": [c.to_dict() for c in self.ordering_constraints],
            "acceptable_trajectories": self.acceptable_trajectories,
            "notes": self.notes,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> ToolCallCase:
        return cls(
            case_id=data["case_id"],
            category=CaseCategory(data.get("category", "cti_only")),
            difficulty=CaseDifficulty(data.get("difficulty", "basic")),
            request=data["request"],
            reference_time=data.get("reference_time", datetime.utcnow().isoformat() + "Z"),
            expected_calls=[ExpectedCall.from_dict(c) for c in data.get("expected_calls", [])],
            forbidden_tools=data.get("forbidden_tools", []),
            ordering_constraints=[OrderingConstraint.from_dict(c) for c in data.get("ordering_constraints", [])],
            acceptable_trajectories=data.get("acceptable_trajectories", []),
            notes=data.get("notes", ""),
        )


# =============================================================================
# Predicted Call Model
# =============================================================================

@dataclass
class PredictedCall:
    """
    A tool call predicted by the model.
    """
    tool: str
    arguments: Dict[str, Any] = field(default_factory=dict)
    raw_arguments: Optional[Any] = None  # Original LLM output before parsing

    def to_dict(self) -> Dict[str, Any]:
        return {
            "tool": self.tool,
            "arguments": self.arguments,
        }


@dataclass
class NormalizedCall:
    """
    A tool call after normalization.
    """
    tool: str
    arguments: Dict[str, Any]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "tool": self.tool,
            "arguments": self.arguments,
        }


# =============================================================================
# Match Result Model
# =============================================================================

class MatchType(str, Enum):
    """Type of match between predicted and expected call."""
    EXACT = "exact"           # Tool + all critical args match
    PARTIAL = "partial"       # Tool matches, some args differ
    TOOL_ONLY = "tool_only"  # Only tool name matches
    NO_MATCH = "no_match"    # No compatibility


@dataclass
class CallMatch:
    """Result of matching a predicted call against an expected call."""
    predicted_call: PredictedCall
    expected_call: Optional[ExpectedCall]
    match_type: MatchType
    critical_arg_match: bool = True
    required_arg_match: bool = True
    matched_critical_args: List[str] = field(default_factory=list)
    mismatched_critical_args: List[str] = field(default_factory=list)

    @property
    def is_match(self) -> bool:
        return self.match_type != MatchType.NO_MATCH

    def to_dict(self) -> Dict[str, Any]:
        return {
            "predicted_tool": self.predicted_call.tool,
            "expected_tool": self.expected_call.tool if self.expected_call else None,
            "match_type": self.match_type.value,
            "critical_arg_match": self.critical_arg_match,
            "required_arg_match": self.required_arg_match,
            "matched_critical_args": self.matched_critical_args,
            "mismatched_critical_args": self.mismatched_critical_args,
        }


# =============================================================================
# Per-Case Result Model
# =============================================================================

@dataclass
class CaseResult:
    """Evaluation result for a single benchmark case."""
    case_id: str
    expected_calls: List[ExpectedCall]
    predicted_calls: List[PredictedCall]
    matches: List[CallMatch] = field(default_factory=list)

    # Counts
    true_positives: int = 0
    false_positives: int = 0
    false_negatives: int = 0

    # Specific metrics
    forbidden_tool_violations: List[str] = field(default_factory=list)
    duplicate_calls: List[str] = field(default_factory=list)
    ordering_violations: List[str] = field(default_factory=list)
    critical_arg_errors: int = 0
    required_arg_errors: int = 0

    # Success flags
    trajectory_success: bool = False
    exact_call_match: bool = False
    tool_set_match: bool = False

    # Error categories
    errors: List[str] = field(default_factory=list)  # WRONG_TOOL, MISSING_ARG, etc.

    # Metadata
    latency_ms: float = 0.0
    input_tokens: int = 0
    output_tokens: int = 0
    error_message: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "case_id": self.case_id,
            "expected_call_count": len(self.expected_calls),
            "predicted_call_count": len(self.predicted_calls),
            "true_positives": self.true_positives,
            "false_positives": self.false_positives,
            "false_negatives": self.false_negatives,
            "forbidden_tool_violations": self.forbidden_tool_violations,
            "critical_arg_errors": self.critical_arg_errors,
            "trajectory_success": self.trajectory_success,
            "exact_call_match": self.exact_call_match,
            "errors": self.errors,
        }


# =============================================================================
# Aggregate Result Model
# =============================================================================

@dataclass
class AggregateResult:
    """Aggregate evaluation result for a run."""
    run_id: str
    case_count: int

    # Tool-level metrics
    tool_precision: float = 0.0
    tool_recall: float = 0.0
    tool_f1: float = 0.0

    # Exact call metrics
    exact_call_precision: float = 0.0
    exact_call_recall: float = 0.0
    exact_call_f1: float = 0.0

    # Argument metrics
    argument_field_accuracy: float = 0.0
    critical_argument_accuracy: float = 0.0

    # Other metrics
    tool_set_exact_match_rate: float = 0.0
    no_tool_accuracy: Optional[float] = None
    forbidden_tool_rate: float = 0.0
    ordering_accuracy: float = 0.0
    trajectory_success_rate: float = 0.0

    # Cost/latency
    total_cost_usd: float = 0.0
    mean_latency_ms: float = 0.0
    p50_latency_ms: float = 0.0
    p95_latency_ms: float = 0.0

    # Per-case results
    case_results: List[CaseResult] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "run_id": self.run_id,
            "case_count": self.case_count,
            "tool_precision": round(self.tool_precision, 4),
            "tool_recall": round(self.tool_recall, 4),
            "tool_f1": round(self.tool_f1, 4),
            "exact_call_precision": round(self.exact_call_precision, 4),
            "exact_call_recall": round(self.exact_call_recall, 4),
            "exact_call_f1": round(self.exact_call_f1, 4),
            "argument_field_accuracy": round(self.argument_field_accuracy, 4),
            "critical_argument_accuracy": round(self.critical_argument_accuracy, 4),
            "tool_set_exact_match_rate": round(self.tool_set_exact_match_rate, 4),
            "no_tool_accuracy": round(self.no_tool_accuracy, 4) if self.no_tool_accuracy is not None else None,
            "forbidden_tool_rate": round(self.forbidden_tool_rate, 4),
            "ordering_accuracy": round(self.ordering_accuracy, 4) if self.ordering_accuracy > 0 else None,
            "trajectory_success_rate": round(self.trajectory_success_rate, 4),
            "mean_latency_ms": round(self.mean_latency_ms, 2),
            "p95_latency_ms": round(self.p95_latency_ms, 2),
        }
