"""
Agent Orchestration Package

This package contains the LLM-based investigation orchestrator.
"""
from agent.orchestrator import InvestigationOrchestrator
from agent.provider import LLMProvider, OpenAIProvider
from agent.tools import InvestigationTool, get_tool_schemas
from agent.evidence import EvidenceStore
from agent.integrations import (
    IntegrationQuery,
    ReadOnlySOCIntegration,
    SecOpsIntegration,
    GTIIntegration,
    SCCIntegration,
    get_default_integrations,
)
from agent.runbooks import InvestigationPersona, InvestigationRunbook, default_soc_runbook
from agent.hitl import (
    HumanDecision,
    HumanReviewGate,
    ScriptedHumanReviewGate,
    TRIAGE_CLOSE,
    TRIAGE_CONTINUE,
    REVIEW_APPROVE,
    REVIEW_REQUEST_MORE_EVIDENCE,
    REVIEW_ESCALATE,
    REVIEW_REJECT,
)

__all__ = [
    "InvestigationOrchestrator",
    "LLMProvider",
    "OpenAIProvider",
    "InvestigationTool",
    "get_tool_schemas",
    "EvidenceStore",
    "IntegrationQuery",
    "ReadOnlySOCIntegration",
    "SecOpsIntegration",
    "GTIIntegration",
    "SCCIntegration",
    "get_default_integrations",
    "InvestigationPersona",
    "InvestigationRunbook",
    "default_soc_runbook",
    "HumanDecision",
    "HumanReviewGate",
    "ScriptedHumanReviewGate",
    "TRIAGE_CLOSE",
    "TRIAGE_CONTINUE",
    "REVIEW_APPROVE",
    "REVIEW_REQUEST_MORE_EVIDENCE",
    "REVIEW_ESCALATE",
    "REVIEW_REJECT",
]
