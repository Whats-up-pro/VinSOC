"""Base investigation policy and ValidatedAssessment structure.

This module provides:
- InvestigationPolicy: Abstract base for investigation policies
- ValidatedAssessment: Structured assessment output with safety validation
"""
from __future__ import annotations

import json
import re
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any


SAFE_ERROR_FIELD = re.compile(r"[a-z][a-z0-9_.-]{0,63}")


def _safe_error_field(value: Any) -> str | None:
    """Return allowlisted error field or None if unsafe."""
    if not isinstance(value, str) or value.startswith("sk-"):
        return None
    return value if SAFE_ERROR_FIELD.fullmatch(value) else None


@dataclass
class ValidatedAssessment:
    """
    Structured final assessment from an investigation.

    This represents the validated output of an investigation with:
    - The assessment text
    - Referenced evidence IDs
    - Structured observations
    - Risk and confidence levels
    - Limitations
    """
    assessment: str
    evidence_ids: list[str]
    observations: list[dict[str, Any]] = field(default_factory=list)
    hypotheses: list[dict[str, Any]] = field(default_factory=list)
    risk_level: str = "UNKNOWN"  # LOW, MEDIUM, HIGH, CRITICAL, UNKNOWN
    confidence: str = "LOW"  # LOW, MEDIUM, HIGH
    limitations: list[str] = field(default_factory=list)
    raw_json: dict[str, Any] = field(default_factory=dict)

    # Validation metadata
    validation_passed: bool = True
    validation_errors: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "assessment": self.assessment,
            "evidence_ids": self.evidence_ids,
            "observations": self.observations,
            "hypotheses": self.hypotheses,
            "risk_level": self.risk_level,
            "confidence": self.confidence,
            "limitations": self.limitations,
            "validation_passed": self.validation_passed,
            "validation_errors": self.validation_errors,
        }

    @classmethod
    def from_json(cls, content: str, valid_evidence_ids: set[str] | None = None) -> "ValidatedAssessment":
        """
        Parse and validate JSON content into ValidatedAssessment.

        Args:
            content: JSON string from model
            valid_evidence_ids: Set of valid evidence IDs for validation

        Returns:
            ValidatedAssessment instance

        Raises:
            ValueError: If validation fails
        """
        errors = []

        # Parse JSON
        try:
            data = json.loads(content)
        except (TypeError, json.JSONDecodeError):
            raise ValueError("Assessment is not valid JSON")

        if not isinstance(data, dict):
            raise ValueError("Assessment must be a JSON object")

        # Validate required fields
        for field in ("assessment", "evidence_ids", "limitations"):
            if field not in data:
                errors.append(f"Missing required field: {field}")

        # Validate field types
        if "assessment" in data and not isinstance(data["assessment"], str):
            errors.append("assessment must be a string")
        if "evidence_ids" in data and not isinstance(data["evidence_ids"], list):
            errors.append("evidence_ids must be a list")
        if "limitations" in data and not isinstance(data["limitations"], list):
            errors.append("limitations must be a list")

        # Validate evidence IDs against known IDs
        if valid_evidence_ids is not None:
            for eid in data.get("evidence_ids", []):
                if not isinstance(eid, str):
                    errors.append(f"Evidence ID must be string: {eid}")
                elif eid not in valid_evidence_ids:
                    errors.append(f"Unknown evidence ID: {eid}")

        # Validate risk level
        risk_level = data.get("risk_level", "UNKNOWN")
        valid_risks = {"LOW", "MEDIUM", "HIGH", "CRITICAL", "UNKNOWN"}
        if risk_level not in valid_risks:
            errors.append(f"Invalid risk_level: {risk_level}")

        # Validate confidence
        confidence = data.get("confidence", "LOW")
        valid_confidences = {"LOW", "MEDIUM", "HIGH"}
        if confidence not in valid_confidences:
            errors.append(f"Invalid confidence: {confidence}")

        # Validate observations
        observations = data.get("observations", [])
        if not isinstance(observations, list):
            errors.append("observations must be a list")
        for i, obs in enumerate(observations):
            if not isinstance(obs, dict):
                errors.append(f"Observation {i} must be a dict")
            elif "evidence_id" not in obs:
                errors.append(f"Observation {i} missing evidence_id")

        # Validate hypotheses
        hypotheses = data.get("hypotheses", [])
        if not isinstance(hypotheses, list):
            errors.append("hypotheses must be a list")
        for i, hyp in enumerate(hypotheses):
            if not isinstance(hyp, dict):
                errors.append(f"Hypothesis {i} must be a dict")
            elif "id" not in hyp:
                errors.append(f"Hypothesis {i} missing id")

        # Raise on validation errors
        if errors:
            raise ValueError(f"Assessment validation failed: {'; '.join(errors)}")

        return cls(
            assessment=data.get("assessment", ""),
            evidence_ids=data.get("evidence_ids", []),
            observations=data.get("observations", []),
            hypotheses=data.get("hypotheses", []),
            risk_level=risk_level,
            confidence=confidence,
            limitations=data.get("limitations", []),
            raw_json=data,
            validation_passed=True,
            validation_errors=[],
        )


class InvestigationPolicy(ABC):
    """
    Abstract base class for investigation policies.

    A policy defines:
    - Which tools are available
    - System prompt for the model
    - Tool call validation
    - Evidence processing
    - Final response parsing
    """

    VERSION = "investigation_policy_base_v1"

    @abstractmethod
    def tool_schemas(self) -> list[dict[str, Any]]:
        """
        Return the list of available tool schemas.

        Returns:
            List of tool schema dicts
        """
        ...

    @abstractmethod
    def system_prompt(self) -> str:
        """
        Return the system prompt for this policy.

        Returns:
            System prompt string
        """
        ...

    def validate_tool_call(self, call: dict[str, Any]) -> dict[str, Any]:
        """
        Validate a tool call.

        Override to add policy-specific validation.

        Args:
            call: Tool call dict with name and arguments

        Returns:
            Validated arguments dict

        Raises:
            ValueError: If validation fails
        """
        return call.get("arguments", {})

    def tool_response(self, call: dict[str, Any], result: Any) -> str:
        """
        Format a tool response for the model.

        Override for custom formatting.

        Args:
            call: The tool call that was executed
            result: The tool result

        Returns:
            Formatted result string
        """
        import json
        return json.dumps(result, indent=2, default=str)

    @abstractmethod
    def parse_final_response(self, content: str) -> ValidatedAssessment:
        """
        Parse and validate the model's final response.

        Args:
            content: Raw content from model

        Returns:
            ValidatedAssessment

        Raises:
            ValueError: If validation fails
        """
        ...

    def validate_case(self, case: dict[str, Any]) -> dict[str, Any]:
        """
        Validate a complete case.

        Override for policy-specific case validation.

        Args:
            case: Case dict with evidence and assessment

        Returns:
            Validation result with pass/fail and issues
        """
        return {"valid": True, "issues": []}
