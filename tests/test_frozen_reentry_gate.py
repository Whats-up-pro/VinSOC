"""A historical frozen attempt cannot be reopened by changing output paths."""

import importlib
import sys

import pytest

from scripts.frozen_run_guard import FrozenRunBlocked, require_unconsumed_frozen


@pytest.mark.parametrize("module", [
    "scripts.run_frozen_baseline_e0", "scripts.run_frozen_v2_e3",
])
def test_consumed_frozen_script_stops_before_client_creation(monkeypatch, tmp_path, module):
    def client_forbidden(*args, **kwargs):
        raise AssertionError("API client was created before the frozen gate")

    monkeypatch.setattr("openai.OpenAI", client_forbidden)
    monkeypatch.setattr(sys, "argv", [module, "--output-dir", str(tmp_path / "fresh")])
    with pytest.raises(FrozenRunBlocked, match="consumed"):
        importlib.import_module(module).main()


def test_missing_frozen_registry_fails_closed(tmp_path):
    with pytest.raises(FrozenRunBlocked, match="registry"):
        require_unconsumed_frozen(tmp_path / "missing.lock")
