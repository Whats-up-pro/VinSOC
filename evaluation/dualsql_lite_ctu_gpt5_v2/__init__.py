"""v2 package - separate from v1, with corrected value grounding validation."""

from evaluation.dualsql_lite_ctu_gpt5_v2.prompts import (
    LINKER_INSTRUCTIONS,
    GENERATOR_INSTRUCTIONS,
    LINKER_PROMPT_VERSION,
    GENERATOR_PROMPT_VERSION,
)
from evaluation.dualsql_lite_ctu_gpt5_v2.runner import (
    run_case,
    run_role,
    validate_linked_schema,
    RoleResult,
    MODEL,
)
from evaluation.dualsql_lite_ctu_gpt5_v2.tools import (
    CTUDatabaseTools,
    TOOL_VERSION,
    TOOL_SCHEMAS,
)
from evaluation.dualsql_lite_ctu_gpt5_v2.experiment import (
    SERIES_VERSION,
    CONDITIONS,
    load_cases,
    run_condition,
)

__all__ = [
    "LINKER_INSTRUCTIONS",
    "GENERATOR_INSTRUCTIONS",
    "LINKER_PROMPT_VERSION",
    "GENERATOR_PROMPT_VERSION",
    "run_case",
    "run_role",
    "validate_linked_schema",
    "RoleResult",
    "CTUDatabaseTools",
    "TOOL_VERSION",
    "TOOL_SCHEMAS",
    "SERIES_VERSION",
    "CONDITIONS",
    "load_cases",
    "run_condition",
    "MODEL",
]
