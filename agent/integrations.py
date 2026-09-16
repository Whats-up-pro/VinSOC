"""
Future MCP integration abstractions for SOC platforms.

Read-only adapters aligned to planned Google SecOps / GTI / SCC integrations.
"""
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, Dict, List, Optional


@dataclass
class IntegrationQuery:
    """Normalized read-only integration query."""
    source: str
    entity: str
    entity_type: str
    time_range: Optional[Dict[str, str]] = None
    filters: Optional[Dict[str, Any]] = None


class ReadOnlySOCIntegration(ABC):
    """Read-only integration interface."""

    name: str = "integration"

    @abstractmethod
    def search(self, query: IntegrationQuery) -> List[Dict[str, Any]]:
        """Search telemetry/threat context in read-only mode."""
        raise NotImplementedError


class SecOpsIntegration(ReadOnlySOCIntegration):
    """Placeholder adapter for Google SecOps/SIEM."""

    name = "google_secops"

    def search(self, query: IntegrationQuery) -> List[Dict[str, Any]]:
        return []


class GTIIntegration(ReadOnlySOCIntegration):
    """Placeholder adapter for Google Threat Intelligence."""

    name = "google_gti"

    def search(self, query: IntegrationQuery) -> List[Dict[str, Any]]:
        return []


class SCCIntegration(ReadOnlySOCIntegration):
    """Placeholder adapter for Security Command Center."""

    name = "google_scc"

    def search(self, query: IntegrationQuery) -> List[Dict[str, Any]]:
        return []


def get_default_integrations() -> Dict[str, ReadOnlySOCIntegration]:
    """Return default integration registry."""
    return {
        "secops": SecOpsIntegration(),
        "gti": GTIIntegration(),
        "scc": SCCIntegration(),
    }
