from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Iterable

from telemetry.network.models import NormalizedNetworkEvent
from telemetry.network.query import NetworkQuery


class NetworkDataSource(ABC):
    """Read-only source of normalized network telemetry."""

    name = "network_source"

    @abstractmethod
    def query(self, query: NetworkQuery) -> Iterable[NormalizedNetworkEvent]:
        raise NotImplementedError
