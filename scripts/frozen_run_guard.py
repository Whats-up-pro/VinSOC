"""Fail closed before reusing a holdout already consumed by model calls."""

from __future__ import annotations

import json
from pathlib import Path


REGISTRY = Path(__file__).resolve().parents[1] / "evaluation/ctu_network_frozen/CONSUMED.lock"


class FrozenRunBlocked(RuntimeError):
    """The holdout cannot support another authorized frozen attempt."""


def require_unconsumed_frozen(registry: Path = REGISTRY) -> None:
    try:
        state = json.loads(Path(registry).read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise FrozenRunBlocked("Frozen registry is missing or invalid; API gate is closed") from exc
    if state.get("consumed") is True:
        raise FrozenRunBlocked(
            "Frozen holdout was already consumed; preserve historical artifacts and do not rerun"
        )
    # These historical entry points have no approved replacement protocol.
    raise FrozenRunBlocked("Frozen registry has no approved unconsumed protocol; API gate is closed")
