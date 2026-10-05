"""Paid-window safety checks using no-network synthetic collaborators."""
from __future__ import annotations

from pathlib import Path

import pytest


def test_duplicate_or_consumed_condition_blocks_before_client(tmp_path: Path):
    from scripts import run_vinsoc_finalization_dev as runner

    output = tmp_path / "out"
    claim_root = tmp_path / "claims"
    claim_root.mkdir()
    (claim_root / "v4-E0.claim.json").write_text("{}", encoding="utf-8")

    def forbidden():
        pytest.fail("client must not be created")

    with pytest.raises(runner.GateError, match="ATTEMPT_ALREADY_CONSUMED"):
        runner.claim_attempt("v4", "E0", output, claim_root, forbidden)


def test_historical_phase2_cli_is_retired():
    from scripts import run_r2_phase2_dev_live as historical

    assert historical.HISTORICAL_ENTRYPOINT_STATUS == "RETIRED_FAIL_CLOSED"


def test_v4_request_contract_separates_e0_from_e3_tools(monkeypatch):
    from scripts import run_vinsoc_finalization_dev as runner

    monkeypatch.setattr(runner, "validate_request_token_bound", lambda request, _cap: 1)
    e0 = runner._request_validator("E0")
    e3 = runner._request_validator("E3")
    common = {"model": runner.MODEL, "reasoning_effort": "low", "max_completion_tokens": 1000, "messages": []}
    e0(common)
    with pytest.raises(runner.GateError, match="REQUEST_CONTRACT_ERROR"):
        e0(dict(common, tools=runner.TOOL_SCHEMAS))
    with pytest.raises(runner.GateError, match="REQUEST_CONTRACT_ERROR"):
        e3(common)
    e3(dict(common, tools=runner.TOOL_SCHEMAS))
