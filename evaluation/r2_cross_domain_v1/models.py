"""Generation receives this DTO, never evaluator-only gold/annotations."""
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class RuntimeCase:
    case_id: str
    database_id: str
    question: str

    def __post_init__(self):
        if not all(isinstance(value, str) and value.strip() for value in (self.case_id, self.database_id, self.question)):
            raise ValueError("INVALID_RUNTIME_CASE")
