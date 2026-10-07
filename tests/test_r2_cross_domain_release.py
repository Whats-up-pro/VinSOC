"""Synthetic private-gate fixtures; no account/model/pricing assertion."""
from datetime import datetime, timezone, timedelta
import pytest


def inputs():
    now = datetime.now(timezone.utc).isoformat()
    ids = ["case_"+str(i) for i in range(96)]
    return ({"case_ids": ids, "validated": True, "registry_path": "registry.json", "benchmark_dir": "benchmarks",
             "benchmark_lock_path": "lock.json", "case_count": 96, "conditions": ["E0", "E3"]},
            {"verified": True, "implementation_sha": "a"*40, "registry_sha256": "b"*64,
             "benchmark_lock_sha256": "c"*64, "ci": {"head_sha": "a"*40, "conclusion": "success",
             "jobs": [{"name": "test (3.11)", "conclusion": "success"}, {"name": "test (3.12)", "conclusion": "success"}]}},
            {"project_verified": True, "confirmed_utc": now, "remaining_allocation_usd": 10,
             "unresolved_cost_unknown": False, "known_prior_cost_usd": .01},
            {"checked_utc": now, "source_url": "https://developers.openai.com/api/docs/pricing",
             "model": "gpt-5-mini-2025-08-07", "input_usd_per_million": .25, "cached_input_usd_per_million": .025,
             "output_usd_per_million": 2, "input_bound_verified": True},
            {"limit_usd": 10, "paid_authorized": False, "authorization_scope": "r2_cross_domain_v1_matched_E0_E3"})


def test_no_paid_authority_even_when_data_and_budget_fit():
    from evaluation.r2_cross_domain_v1.release import preflight_release
    result = preflight_release(*inputs())
    assert not result["authorized"]
    assert result["max_requests"] == 672
    assert result["request_contract"]["max_completion_tokens"] == 1000
    assert "temperature" not in result["request_contract"]
    assert "PAID_RELEASE_NOT_AUTHORIZED" in result["reasons"]
    assert result["client_created"] is False


def test_budget_uses_all_672_maximum_payload_requests_not_mean_of_smoke():
    from evaluation.r2_cross_domain_v1.release import preflight_release
    inv, ident, account, pricing, budget = inputs()
    budget.update(paid_authorized=True, limit_usd=2.5)
    result = preflight_release(inv, ident, account, pricing, budget)
    # 672 * (8320 + 2000) / 1e6 + .01 = 6.94504
    assert result["full_ceiling_usd"] == pytest.approx(6.94504)
    assert "FULL_RUN_BUDGET_INSUFFICIENT" in result["reasons"]
    assert result["authorized"] is False


@pytest.mark.parametrize("which,key,value,reason", [
    (2, "confirmed_utc", "2000-01-01T00:00:00Z", "ACCOUNT_UNAVAILABLE_OR_STALE"),
    (3, "input_bound_verified", False, "TOKEN_BOUND_UNVERIFIED"),
    (3, "model", "other", "PRICING_UNAVAILABLE_OR_STALE"),
    (1, "implementation_sha", None, "CODE_OR_CI_IDENTITY_UNVERIFIED"),
    (2, "unresolved_cost_unknown", True, "UNRECONCILED_COST_EXPOSURE"),
])
def test_missing_or_stale_gate_is_explicit(which, key, value, reason):
    from evaluation.r2_cross_domain_v1.release import preflight_release
    args = list(inputs()); args[which][key] = value
    result = preflight_release(*args)
    assert reason in result["reasons"]
    assert result["authorized"] is False


def test_nominal_private_authority_still_needs_runtime_revalidation():
    from evaluation.r2_cross_domain_v1.release import preflight_release
    args = list(inputs());args[4]["paid_authorized"] = True
    result = preflight_release(*args)
    assert result["authorized"] is True
    assert result["status"] == "preflight_pass_runtime_revalidation_required"
    assert result["model_calls"] == 0


def test_cli_preflight_never_creates_openai_client_and_preserves_existing_output(tmp_path, monkeypatch, capsys):
    import openai
    import json
    from scripts.run_r2_cross_domain import main
    monkeypatch.setattr(openai, "OpenAI", lambda **kwargs: pytest.fail("Client constructed during preflight"))
    output = tmp_path/"preflight.json"
    assert main(["--preflight-only", "--output", str(output)]) == 1
    public = json.loads(capsys.readouterr().out)
    assert public["model_calls"] == 0 and public["client_created"] is False
    assert public["full_ceiling_usd"] is None
    assert "PAID_RELEASE_NOT_AUTHORIZED" in public["reasons"]
    original = output.read_bytes()
    with pytest.raises(SystemExit):
        main(["--preflight-only", "--output", str(output)])
    assert output.read_bytes() == original
