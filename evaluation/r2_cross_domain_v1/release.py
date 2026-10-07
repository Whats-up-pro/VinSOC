"""Offline paid-release preflight, separate from the historical benchmark lock.

No provider client is created here. Private authorization, account and pricing
records are inputs, not facts inferred from old credit balances or smoke usage.
The live runner must revalidate code/data identities immediately before claim.
"""
from __future__ import annotations

import hashlib
import json
import math
import re
from datetime import datetime, timezone
from urllib.parse import urlparse

from .controller import MODEL, REQUEST_BYTES_CAP

VERSION = "r2_cross_domain_live_release_v1"
WINDOW_ID = "r2-cross-domain-v1-matched-20261007"
CONDITIONS = ("E0", "E3")
REQUEST_CONTRACT = {"model": MODEL, "reasoning_effort": "low", "max_completion_tokens": 1000,
                    "max_retries": 0, "max_request_bytes": REQUEST_BYTES_CAP,
                    "frame_reserve_tokens": 512, "max_messages": 20, "service_tier": "default"}


def canonical_hash(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()).hexdigest()


def _number(value):
    return type(value) in (int, float) and math.isfinite(value) and value >= 0


def _digest(value, length):
    return isinstance(value, str) and re.fullmatch("[0-9a-f]{"+str(length)+"}", value) is not None


def fresh(value):
    try:
        timestamp = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if timestamp.tzinfo is None:
            return False
        return -300 <= (datetime.now(timezone.utc)-timestamp).total_seconds() <= 21600
    except (ValueError, TypeError, AttributeError):
        return False


def preflight_release(inventory: dict, identities: dict, account: dict, pricing: dict, budget: dict) -> dict:
    inventory, identities, account, pricing, budget = (x if isinstance(x, dict) else {} for x in (inventory, identities, account, pricing, budget))
    reasons = []
    ids = inventory.get("case_ids", [])
    if (not isinstance(ids, list) or len(ids) != 96 or any(not isinstance(i, str) or not i for i in ids)
        or len(set(ids)) != 96 or inventory.get("validated") is not True
        or inventory.get("conditions") != list(CONDITIONS)):
        reasons.append("FULL_LOCKED_INVENTORY_UNVERIFIED")
    ci = identities.get("ci") or {}
    jobs = ci.get("jobs") or []
    if (identities.get("verified") is not True or not _digest(identities.get("implementation_sha"), 40)
        or not all(_digest(identities.get(k), 64) for k in ("registry_sha256", "benchmark_lock_sha256"))
        or ci.get("head_sha") != identities.get("implementation_sha") or ci.get("conclusion") != "success"
        or not isinstance(jobs, list) or not all(isinstance(j, dict) and j.get("conclusion") == "success" for j in jobs)
        or not all(any(version in j.get("name", "") for j in jobs) for version in ("3.11", "3.12"))):
        reasons.append("CODE_OR_CI_IDENTITY_UNVERIFIED")
    if (account.get("project_verified") is not True or not fresh(account.get("confirmed_utc"))
        or not _number(account.get("remaining_allocation_usd"))):
        reasons.append("ACCOUNT_UNAVAILABLE_OR_STALE")
    if account.get("unresolved_cost_unknown") is not False or not _number(account.get("known_prior_cost_usd")):
        reasons.append("UNRECONCILED_COST_EXPOSURE")
    url = urlparse(pricing.get("source_url", "") if isinstance(pricing.get("source_url", ""), str) else "")
    if (not fresh(pricing.get("checked_utc")) or pricing.get("model") != MODEL
        or url.scheme != "https" or url.netloc not in {"developers.openai.com", "platform.openai.com", "openai.com"}
        or any(not _number(pricing.get(k)) or pricing[k] <= 0 for k in ("input_usd_per_million", "output_usd_per_million"))
        or not _number(pricing.get("cached_input_usd_per_million"))
        or (_number(pricing.get("input_usd_per_million")) and pricing.get("cached_input_usd_per_million", 0) > pricing["input_usd_per_million"])):
        reasons.append("PRICING_UNAVAILABLE_OR_STALE")
    if pricing.get("input_bound_verified") is not True:
        reasons.append("TOKEN_BOUND_UNVERIFIED")
    if (budget.get("paid_authorized") is not True
        or budget.get("authorization_scope") != "r2_cross_domain_v1_matched_E0_E3"):
        reasons.append("PAID_RELEASE_NOT_AUTHORIZED")
    if not _number(budget.get("limit_usd")) or budget.get("limit_usd", 0) <= 0:
        reasons.append("BUDGET_NOT_SPECIFIED")
    max_requests = 96*(1+3+3)
    ceiling, reserve = None, None
    if (all(_number(pricing.get(k)) for k in ("input_usd_per_million", "output_usd_per_million"))
        and _number(account.get("known_prior_cost_usd"))):
        reserve = ((REQUEST_BYTES_CAP+REQUEST_CONTRACT["frame_reserve_tokens"])*pricing["input_usd_per_million"]
                   + 1000*pricing["output_usd_per_million"])/1_000_000
        ceiling = account["known_prior_cost_usd"] + max_requests*reserve
        if (_number(budget.get("limit_usd")) and ceiling > budget["limit_usd"]
            or _number(account.get("remaining_allocation_usd")) and max_requests*reserve > account["remaining_allocation_usd"]):
            reasons.append("FULL_RUN_BUDGET_INSUFFICIENT")
    inputs = {"inventory": inventory, "identities": identities, "account": account, "pricing": pricing, "budget": budget}
    result = {"version": VERSION, "window_id": WINDOW_ID, "authorized": not reasons,
              "status": "preflight_pass_runtime_revalidation_required" if not reasons else "blocked",
              "reasons": reasons, "model_calls": 0, "client_created": False,
              "case_ids": sorted(ids) if isinstance(ids, list) and all(isinstance(i, str) for i in ids) else [],
              "conditions": list(CONDITIONS), "max_requests": max_requests,
              "request_contract": dict(REQUEST_CONTRACT), "per_request_reserve_usd": reserve,
              "full_ceiling_usd": ceiling, "budget_usd": budget.get("limit_usd"),
              "bound_method": "serialized_utf8_payload_bytes_plus_verified_bounded_framing;uncached_input;all_672_caps",
              "gate_inputs": inputs}
    result["release_sha256"] = canonical_hash(result)
    return result
