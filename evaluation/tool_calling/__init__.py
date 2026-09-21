"""
R1 Tool Calling Evaluation Framework

Formal evaluation of LLM tool selection in SOC investigations.

Modules:
    models      - Benchmark case and result data models
    arguments   - Argument normalization
    matching    - One-to-one call matching
    metrics     - Metrics aggregation
    decision_runner - A1 decision-only evaluation
    integration_runner - A2 integration evaluation
"""
from evaluation.tool_calling.models import (
    ToolCallCase,
    ExpectedCall,
    PredictedCall,
    CaseResult,
    AggregateResult,
    CaseCategory,
    CaseDifficulty,
    MatchType,
)
from evaluation.tool_calling.arguments import normalize_arguments, compare_values
from evaluation.tool_calling.matching import compute_case_metrics
from evaluation.tool_calling.metrics import aggregate_case_results

__all__ = [
    "ToolCallCase",
    "ExpectedCall",
    "PredictedCall",
    "CaseResult",
    "AggregateResult",
    "CaseCategory",
    "CaseDifficulty",
    "MatchType",
    "normalize_arguments",
    "compare_values",
    "compute_case_metrics",
    "aggregate_case_results",
]
