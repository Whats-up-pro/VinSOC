"""Offline contract gates for the next, distinct R2 dev series."""
from __future__ import annotations

from pathlib import Path

import pytest


def test_bound_reserves_e0_e3_and_demo_without_cache_assumption():
    from evaluation.finalization.contract import build_preflight_bound

    contract = {"input_token_ceiling": 20512, "max_completion_tokens": 1000}
    pricing = {"input": 0.25, "output": 2.0}
    bound = build_preflight_bound(contract, pricing, max_calls=88)

    assert bound["per_call_ceiling_usd"] == pytest.approx(0.007128)
    assert bound["max_calls"] == 88
    assert bound["ceiling_usd"] == pytest.approx(0.627264)


def test_bound_rejects_unknown_tokenizer_and_oversized_payload(monkeypatch):
    from evaluation.finalization import contract

    monkeypatch.setattr(contract, "_tokenizer", lambda _model: None)
    with pytest.raises(contract.ContractError, match="TOKENIZER_UNAVAILABLE"):
        contract.count_request_tokens({"model": "gpt-5-mini-2025-08-07", "messages": []})

    monkeypatch.setattr(contract, "_tokenizer", lambda _model: type("Tokenizer", (), {"encode": lambda *_: list(range(20_513))})())
    with pytest.raises(contract.ContractError, match="REQUEST_TOKEN_LIMIT"):
        contract.validate_request_token_bound(
            {"model": "gpt-5-mini-2025-08-07", "messages": [{"role": "user", "content": "x"}]},
            input_token_ceiling=20_512,
        )


def test_release_lock_verifier_rejects_changed_source_before_client(tmp_path: Path):
    from evaluation.finalization.contract import ContractError, verify_release_inputs

    source = tmp_path / "source.py"
    source.write_text("value = 1\n", encoding="utf-8")
    snapshot = tmp_path / "snapshot.duckdb"
    snapshot.write_bytes(b"fixture")
    lock = tmp_path / "lock.json"
    lock.write_text(
        '{"contract_identity":"r2_finalization_v4","snapshot_binary_sha256":"' + "0" * 64 + '","files_portable_sha256":{"' + str(source).replace("\\", "\\\\") + '":"' + "0" * 64 + '"}}',
        encoding="utf-8",
    )

    with pytest.raises(ContractError, match="RELEASE_INPUT_MISMATCH"):
        verify_release_inputs(snapshot, lock)


def test_current_v4_lock_binds_verified_snapshot_and_controller_sources():
    from evaluation.finalization.contract import verify_release_inputs

    lock = verify_release_inputs(
        Path("data/ctu_network_public/snapshots/ctu_dev.duckdb"),
        Path("evaluation/r2_phase2/CONTRACT_v4.lock.json"),
    )
    assert lock["contract_identity"] == "r2_finalization_v4"
