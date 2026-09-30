"""Historical entrypoints must have no provider, database or output side effects."""
import importlib
import sys
from pathlib import Path

import pytest

from scripts.frozen_run_guard import FrozenRunBlocked


@pytest.mark.parametrize("module", ["scripts.run_frozen_baseline_e0", "scripts.run_frozen_v2_e3"])
def test_historical_main_stops_before_client_database_or_output(monkeypatch, tmp_path, module):
    entry = importlib.import_module(module)
    def forbidden(*args, **kwargs):
        pytest.fail("historical entrypoint performed a side effect")
    monkeypatch.setattr("openai.OpenAI", forbidden)
    monkeypatch.setattr("duckdb.connect", forbidden)
    monkeypatch.setattr(Path, "write_text", forbidden)
    monkeypatch.setattr(Path, "mkdir", forbidden)
    monkeypatch.setattr(sys, "argv", [module, "--output-dir", str(tmp_path / "new")])
    with pytest.raises(FrozenRunBlocked, match="HISTORICAL_ENTRYPOINT_DISABLED"):
        entry.main()
