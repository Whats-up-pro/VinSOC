"""
Base Skill Interface

All investigation skills must inherit from BaseSkill and implement:
- execute(): Main skill logic
- validate_input(): Input parameter validation
- validate_output(): Output schema validation
"""
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, Optional
import json


@dataclass
class SkillResult:
    """Container for skill execution results."""
    success: bool
    data: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
    evidence_ids: list = field(default_factory=list)
    execution_time_ms: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary representation."""
        return {
            "success": self.success,
            "data": self.data,
            "error": self.error,
            "evidence_ids": self.evidence_ids,
            "execution_time_ms": self.execution_time_ms,
        }

    def to_json(self) -> str:
        """Convert to JSON string."""
        return json.dumps(self.to_dict(), indent=2, default=str)


@dataclass
class SkillContract:
    """Declarative skill contract for lifecycle/tooling mapping."""
    skill_name: str
    version: str
    required_inputs: list[str]
    output_schema: str
    lifecycle_stage: str = "investigate"
    read_only: bool = True

    def to_dict(self) -> Dict[str, Any]:
        return {
            "skill_name": self.skill_name,
            "version": self.version,
            "required_inputs": self.required_inputs,
            "output_schema": self.output_schema,
            "lifecycle_stage": self.lifecycle_stage,
            "read_only": self.read_only,
        }


class BaseSkill(ABC):
    """
    Abstract base class for investigation skills.

    All skills must:
    1. Implement execute() method
    2. Validate input parameters
    3. Return SkillResult with validated data
    4. Log all operations
    5. Be read-only (no side effects on external systems)
    """

    skill_name: str = "base_skill"
    skill_version: str = "1.0.0"

    def __init__(self):
        self.execution_log: list = []

    @abstractmethod
    def validate_input(self, **kwargs) -> tuple[bool, Optional[str]]:
        """
        Validate input parameters.

        Returns:
            tuple: (is_valid, error_message)
        """
        pass

    @abstractmethod
    def _execute(self, **kwargs) -> SkillResult:
        """
        Internal execution logic (implemented by subclasses).

        Returns:
            SkillResult with execution results
        """
        pass

    def validate_output(self, data: Dict[str, Any]) -> tuple[bool, Optional[str]]:
        """Validate output payload. Subclasses may override."""
        return True, None

    def get_contract(self) -> SkillContract:
        """Return declared contract for this skill."""
        return SkillContract(
            skill_name=self.skill_name,
            version=self.skill_version,
            required_inputs=[],
            output_schema="Unknown",
            lifecycle_stage="investigate",
            read_only=True,
        )

    def execute(self, **kwargs) -> SkillResult:
        """
        Execute the skill with validation and logging.

        Args:
            **kwargs: Skill-specific parameters

        Returns:
            SkillResult with validated output
        """
        start_time = datetime.utcnow()

        # Log input
        self.execution_log.append({
            "timestamp": start_time.isoformat(),
            "action": "input_received",
            "parameters": kwargs,
        })

        # Validate input
        is_valid, error = self.validate_input(**kwargs)
        if not is_valid:
            self.execution_log.append({
                "timestamp": datetime.utcnow().isoformat(),
                "action": "validation_failed",
                "error": error,
            })
            return SkillResult(
                success=False,
                error=f"Input validation failed: {error}",
            )

        # Execute skill
        result = self._execute(**kwargs)

        if result.success and result.data is not None:
            is_valid, validation_error = self.validate_output(result.data)
            if not is_valid:
                self.execution_log.append({
                    "timestamp": datetime.utcnow().isoformat(),
                    "action": "output_validation_failed",
                    "error": validation_error,
                })
                return SkillResult(
                    success=False,
                    error=f"Output validation failed: {validation_error}",
                    evidence_ids=result.evidence_ids,
                )

        # Calculate execution time
        end_time = datetime.utcnow()
        result.execution_time_ms = (end_time - start_time).total_seconds() * 1000

        # Log result
        self.execution_log.append({
            "timestamp": end_time.isoformat(),
            "action": "execution_completed",
            "success": result.success,
            "execution_time_ms": result.execution_time_ms,
        })

        return result

    def get_execution_log(self) -> list:
        """Return the execution log for this skill."""
        return self.execution_log.copy()
