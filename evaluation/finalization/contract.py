"""Fail-closed identity and token/cost gates for a new R2 evaluation series."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any


class ContractError(RuntimeError):
    """A release input cannot be used for a paid request."""


def canonical_bytes(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")


def sha256(value: Any) -> str:
    return hashlib.sha256(value.read_bytes() if isinstance(value, Path) else canonical_bytes(value)).hexdigest()


def portable_text_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes().replace(b"\r\n", b"\n").replace(b"\r", b"\n")).hexdigest()


def _tokenizer(model: str):
    try:
        import tiktoken
        return tiktoken.encoding_for_model(model)
    except Exception:
        return None


def count_request_tokens(request: dict[str, Any]) -> int:
    model = request.get("model")
    tokenizer = _tokenizer(model) if isinstance(model, str) else None
    if tokenizer is None:
        raise ContractError("TOKENIZER_UNAVAILABLE")
    # Encode the entire request representation and reserve the documented chat framing separately.
    return len(tokenizer.encode(canonical_bytes(request).decode("utf-8"))) + 512


def validate_request_token_bound(request: dict[str, Any], input_token_ceiling: int = 20_512) -> int:
    tokens = count_request_tokens(request)
    if tokens > input_token_ceiling:
        raise ContractError("REQUEST_TOKEN_LIMIT")
    return tokens


def build_preflight_bound(request_contract: dict[str, Any], pricing: dict[str, float], max_calls: int) -> dict[str, Any]:
    input_cap = request_contract.get("input_token_ceiling")
    output_cap = request_contract.get("max_completion_tokens")
    if type(input_cap) is not int or input_cap < 1 or type(output_cap) is not int or output_cap < 1 or type(max_calls) is not int or max_calls < 1:
        raise ContractError("BOUND_CONTRACT_INVALID")
    if any(type(pricing.get(key)) not in (int, float) or pricing[key] < 0 for key in ("input", "output")):
        raise ContractError("PRICING_CONTRACT_INVALID")
    per_call = (input_cap * pricing["input"] + output_cap * pricing["output"]) / 1_000_000
    return {"input_token_ceiling": input_cap, "max_completion_tokens": output_cap,
            "max_calls": max_calls, "cache_assumption": "none", "per_call_ceiling_usd": per_call,
            "ceiling_usd": per_call * max_calls}


def verify_release_inputs(snapshot: Path, lock_path: Path) -> dict[str, Any]:
    """Verify only a new lock; old locks are neither edited nor repurposed."""
    try:
        lock = json.loads(lock_path.read_text(encoding="utf-8"))
        actual_snapshot = sha256(snapshot)
        if lock.get("snapshot_binary_sha256") != actual_snapshot:
            raise ValueError("snapshot")
        for name, expected in lock.get("files_portable_sha256", {}).items():
            path = Path(name)
            if not path.is_file() or portable_text_sha256(path) != expected:
                raise ValueError("source")
        if lock.get("contract_identity") != "r2_finalization_v4":
            raise ValueError("identity")
        from evaluation.ctu_network_public.contract import validate
        verified = validate(snapshot)
        for name in ("logical_snapshot_sha256", "manifest_sha256", "split_sha256"):
            if lock.get(name) != verified.get(name):
                raise ValueError(name)
        return lock
    except Exception:
        raise ContractError("RELEASE_INPUT_MISMATCH") from None
