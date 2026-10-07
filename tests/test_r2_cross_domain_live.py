"""Exercise journal/transport with a fake external boundary; zero paid calls."""
from pathlib import Path
from types import SimpleNamespace
import json
import pytest


def sdk_response(*, model="gpt-5-mini-2025-08-07", usage=True):
    return SimpleNamespace(id="synthetic-response", model=model,
        usage=SimpleNamespace(prompt_tokens=100, completion_tokens=20,
            prompt_tokens_details=SimpleNamespace(cached_tokens=0)) if usage else None,
        choices=[SimpleNamespace(finish_reason="stop", message=SimpleNamespace(content='{"sql":"SELECT 1"}', tool_calls=[]))])


def config():
    return {"model": "gpt-5-mini-2025-08-07", "reasoning_effort": "low", "max_completion_tokens": 1000,
            "max_retries": 0, "max_request_bytes": 32768, "frame_reserve_tokens": 512,
            "max_messages": 20, "service_tier": "default"}


def journal(tmp_path, monkeypatch):
    from evaluation.r2_cross_domain_v1 import live
    monkeypatch.setattr(live, "canonical_release_root", lambda: tmp_path / "canonical")
    return live.RequestJournal.claim(tmp_path / "canonical/ledger.json", max_requests=672,
        budget_usd=20, prior_usd=0, reserve_usd=.02, implementation_sha="a"*40)


def payload():
    return {"model": "gpt-5-mini-2025-08-07", "reasoning_effort": "low", "max_completion_tokens": 1000,
            "service_tier": "default", "messages": [{"role": "user", "content": "Question"}]}


def test_claim_is_durable_across_outputs_and_process_instances(tmp_path, monkeypatch):
    from evaluation.r2_cross_domain_v1.live import RequestJournal
    first = journal(tmp_path, monkeypatch)
    assert first.data["attempted"] == 0
    with pytest.raises(ValueError, match="CONSUMED"):
        RequestJournal.claim(tmp_path / "canonical/ledger.json", max_requests=672,
            budget_usd=20, prior_usd=0, reserve_usd=.02, implementation_sha="a"*40)


def test_response_is_charged_before_invalid_model_content_is_parsed(tmp_path, monkeypatch):
    from evaluation.r2_cross_domain_v1.live import GuardedTransport
    j = journal(tmp_path, monkeypatch)
    response = sdk_response(); response.choices[0].message.content = "not JSON"
    sdk = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=lambda **kw: response)))
    transport = GuardedTransport(sdk, j, config(), {"input_usd_per_million": .25, "output_usd_per_million": 2})
    result = transport.request(payload())
    assert result["content"] == "not JSON"
    from evaluation.r2_cross_domain_v1.live import case_usage_valid
    assert case_usage_valid({"attempted_calls": 1, "response_count": 1, "responses": [{"response": result}]}) is True
    incomplete = {**result, "usage": None}
    assert case_usage_valid({"attempted_calls": 1, "response_count": 1, "responses": [{"response": incomplete}]}) is False
    saved = json.loads(j.path.read_text())
    assert saved["attempted"] == saved["received"] == saved["valid_usage"] == 1
    assert saved["known_usd"] == pytest.approx(.000065)


@pytest.mark.parametrize("model,usage,error", [("other", True, "MODEL_MISMATCH"),
    ("gpt-5-mini-2025-08-07", False, "MISSING_USAGE")])
def test_bad_response_latches_terminal_and_retains_partial_cost(tmp_path, monkeypatch, model, usage, error):
    from evaluation.r2_cross_domain_v1.live import GuardedTransport
    j = journal(tmp_path, monkeypatch)
    sdk = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=lambda **kw: sdk_response(model=model, usage=usage))))
    transport = GuardedTransport(sdk, j, config(), {"input_usd_per_million": .25, "output_usd_per_million": 2})
    with pytest.raises(ValueError, match=error): transport.request(payload())
    assert j.data["attempted"] == j.data["received"] == 1
    with pytest.raises(ValueError, match="TERMINAL"): transport.request(payload())
    assert j.data["attempted"] == 1
    if not usage:
        assert j.data["cost_unknown"] is True
        assert j.data["pending_exposure_usd"] == .02


def test_no_retry_or_raw_error_and_partial_survives_provider_exception(tmp_path, monkeypatch):
    from evaluation.r2_cross_domain_v1.live import GuardedTransport
    j = journal(tmp_path, monkeypatch)
    def fail(**kw): raise RuntimeError("sk-sensitive raw body must not persist")
    sdk = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=fail)))
    transport = GuardedTransport(sdk, j, config(), {"input_usd_per_million": .25, "output_usd_per_million": 2})
    with pytest.raises(ValueError, match="PROVIDER_ERROR"): transport.request(payload())
    assert "sk-sensitive" not in j.path.read_text()
    assert j.data["attempted"] == 1 and j.data["received"] == 0 and j.data["cost_unknown"]


def test_request_model_or_temperature_change_blocked_before_attempt(tmp_path, monkeypatch):
    from evaluation.r2_cross_domain_v1.live import GuardedTransport
    j = journal(tmp_path, monkeypatch)
    sdk = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=lambda **kw: pytest.fail("API boundary reached"))))
    transport = GuardedTransport(sdk, j, config(), {"input_usd_per_million": .25, "output_usd_per_million": 2})
    p = payload();p["temperature"] = 0
    with pytest.raises(ValueError, match="REQUEST_CONTRACT"): transport.request(p)
    assert j.data["attempted"] == 0


def test_authorized_flag_alone_never_opens_provider(tmp_path):
    from evaluation.r2_cross_domain_v1.live import run_authorized_release
    result = run_authorized_release({"authorized": True}, case_ids=["invented"], conditions=("E0", "E3"),
        output_dir=tmp_path / "output", ledger_path=tmp_path / "ledger.json", env_file=tmp_path / ".env")
    assert result["attempted_calls"] == 0
    assert result["client_created"] is False
    assert result["status"] == "blocked"


def test_locked_semantic_fixtures_are_built_and_identity_checked_before_inference(tmp_path):
    from evaluation.r2_cross_domain_v1.live import build_locked_instances
    from evaluation.r2_cross_domain_v1.semantic_instances import build_fixture
    from evaluation.r2_cross_domain_v1.data import DatabaseContext
    from evaluation.r2_cross_domain_v1.benchmark import ReferenceCase
    from pathlib import Path
    spec = {"database_id": "fixture", "fixture_only": True, "seed": 1,
        "schema": [{"name": "items", "columns": [{"name": "id", "duckdb_type": "BIGINT"}]}],
        "relationships": [], "rows": {"items": [[1], [2]]}}
    source = tmp_path / "audit"; source.mkdir()
    identities = []
    for index in range(2):
        local = {**spec, "seed": index+1, "rows": {"items": [[index+1], [3]]}}
        (source/f"case_{index}.fixture.json").write_text(json.dumps(local))
        built = build_fixture(local, tmp_path/f"initial{index}.duckdb")
        identities.append({"instance_id": built["instance_id"], "logical_sha256": built["context"].identity["logical_sha256"]})
    audit = source/"case.audit.json";audit.write_text(json.dumps({"fixture_identities": identities}))
    base = build_fixture(spec, tmp_path/"base.duckdb")["context"]
    ref = ReferenceCase("case", "fixture", "Count", "SELECT count(*) FROM items", "scalar", "basic", [], "family", [])
    instances = build_locked_instances(ref, {"semantic_audit_path": str(audit)}, base, tmp_path/"materialized")
    assert len(instances) == 3
    assert [i["fixture_only"] for i in instances] == [False, True, True]
    identities[0]["logical_sha256"] = "invalid"
    audit.write_text(json.dumps({"fixture_identities": identities}))
    with pytest.raises(ValueError, match="SEMANTIC_FIXTURE_IDENTITY"):
        build_locked_instances(ref, {"semantic_audit_path": str(audit)}, base, tmp_path/"bad")


def test_live_controller_boundary_uses_runtime_only_and_preserves_linker_at_generator_limit(tmp_path, monkeypatch):
    from evaluation.r2_cross_domain_v1.live import GuardedTransport, run_live_case
    from evaluation.r2_cross_domain_v1.models import RuntimeCase
    from evaluation.r2_cross_domain_v1.semantic_instances import build_fixture
    from evaluation.r2_cross_domain_v1.tools import DatabaseTools
    spec = {"database_id": "fixture", "fixture_only": True, "seed": 1,
        "schema": [{"name": "items", "columns": [{"name": "id", "duckdb_type": "BIGINT"}]}],
        "relationships": [], "rows": {"items": [[1], [2]]}}
    context = build_fixture(spec, tmp_path/"fixture.duckdb")["context"]
    context.identity["primary_keys"] = {"items": []}
    link = {"tables": ["items"], "columns": [{"table": "items", "column": "id"}],
            "relationships": [], "grounded_values": [], "constraints": []}
    requests = []
    def create(**request):
        requests.append(request)
        response = sdk_response()
        if len(requests) == 3:
            response.choices[0].message.content = json.dumps(link)
        else:
            response.choices[0].finish_reason = "tool_calls"
            response.choices[0].message.content = None
            response.choices[0].message.tool_calls = [SimpleNamespace(id="test-call", function=SimpleNamespace(
                name="sql_probe", arguments='{"sql":"SELECT id FROM items"}'))]
        return response
    transport = GuardedTransport(SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create))),
        journal(tmp_path, monkeypatch), config(), {"input_usd_per_million": .25, "output_usd_per_million": 2})
    checkpoints = []
    result = run_live_case(RuntimeCase("case", "fixture", "List IDs"), "E3", DatabaseTools(context), transport, checkpoints.append)
    assert len(requests) == 6
    assert result["error_category"] == "TOOL_LIMIT"
    assert result["linked_schema"]["tables"] == ["items"]
    assert result["final_sql"] is None
    assert result["attempted_calls"] == result["response_count"] == 6
    assert len(checkpoints) == 6
    assert "gold_sql" not in json.dumps(requests) and "accepted_links" not in json.dumps(requests)


def test_e0_has_one_request_no_tools_and_no_retry_on_invalid_json(tmp_path, monkeypatch):
    from evaluation.r2_cross_domain_v1.live import GuardedTransport, run_live_case
    from evaluation.r2_cross_domain_v1.models import RuntimeCase
    from evaluation.r2_cross_domain_v1.semantic_instances import build_fixture
    from evaluation.r2_cross_domain_v1.tools import DatabaseTools
    spec = {"database_id": "fixture", "fixture_only": True, "seed": 1,
        "schema": [{"name": "items", "columns": [{"name": "id", "duckdb_type": "BIGINT"}]}],
        "relationships": [], "rows": {"items": [[1]]}}
    context = build_fixture(spec, tmp_path/"fixture.duckdb")["context"]
    context.identity["primary_keys"] = {"items": []}
    requests = []
    def create(**request):
        requests.append(request)
        result = sdk_response(); result.choices[0].message.content = "broken JSON"
        return result
    transport = GuardedTransport(SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create))),
        journal(tmp_path, monkeypatch), config(), {"input_usd_per_million": .25, "output_usd_per_million": 2})
    result = run_live_case(RuntimeCase("case", "fixture", "Count rows"), "E0", DatabaseTools(context), transport, lambda _: None)
    assert len(requests) == 1 and "tools" not in requests[0]
    assert result["error_category"] == "MODEL_PARSE_ERROR"
    assert result["attempted_calls"] == result["response_count"] == 1


def test_cached_usage_without_verified_cache_price_is_not_claimed_as_exact_cost(tmp_path, monkeypatch):
    from evaluation.r2_cross_domain_v1.live import GuardedTransport
    j = journal(tmp_path, monkeypatch)
    response = sdk_response();response.usage.prompt_tokens_details.cached_tokens = 50
    sdk = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=lambda **kw: response)))
    transport = GuardedTransport(sdk, j, config(), {"input_usd_per_million": .25, "output_usd_per_million": 2})
    with pytest.raises(ValueError, match="CACHED_PRICE_UNVERIFIED"):
        transport.request(payload())
    assert j.data["cost_unknown"] is True
    assert j.data["known_usd"] == 0
    assert j.data["pending_exposure_usd"] == .02


def test_cached_usage_is_priced_from_reported_counts_not_uncached_estimate(tmp_path, monkeypatch):
    from evaluation.r2_cross_domain_v1.live import GuardedTransport
    j = journal(tmp_path, monkeypatch)
    response = sdk_response();response.usage.prompt_tokens_details.cached_tokens = 50
    sdk = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=lambda **kw: response)))
    transport = GuardedTransport(sdk, j, config(), {"input_usd_per_million": .25, "cached_input_usd_per_million": .025, "output_usd_per_million": 2})
    result = transport.request(payload())
    assert result["cost_usd"] == pytest.approx(.00005375)
    assert j.data["known_usd"] == pytest.approx(.00005375)
    assert j.data["cost_unknown"] is False


def test_request_contract_failure_is_terminal_without_a_followup_request(tmp_path, monkeypatch):
    from evaluation.r2_cross_domain_v1.live import GuardedTransport
    j = journal(tmp_path, monkeypatch)
    sdk = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=lambda **kw: pytest.fail("API reached"))))
    transport = GuardedTransport(sdk, j, config(), {"input_usd_per_million": .25, "output_usd_per_million": 2})
    bad = payload();bad["model"] = "other"
    with pytest.raises(ValueError, match="REQUEST_CONTRACT"):
        transport.request(bad)
    with pytest.raises(ValueError, match="TERMINAL"):
        transport.request(payload())
    assert j.data["attempted"] == 0


def test_alternate_benchmark_directory_rejected_before_client_even_with_matching_ids(tmp_path, monkeypatch):
    from evaluation.r2_cross_domain_v1.live import run_authorized_release
    from evaluation.r2_cross_domain_v1.release import preflight_release
    import openai
    from tests.test_r2_cross_domain_release import inputs
    args = list(inputs());args[4]["paid_authorized"] = True
    alternate = tmp_path/"substituted";alternate.mkdir()
    (alternate/"evaluation_runtime.json").write_text(json.dumps([{"case_id": "case_0", "question": "Changed question"}]))
    args[0].update(benchmark_dir=str(alternate))
    release = preflight_release(*args)
    assert release["authorized"] is True  # pure preflight is not runtime authority
    monkeypatch.setattr(openai, "OpenAI", lambda **kw: pytest.fail("Client reached"))
    result = run_authorized_release(release, case_ids=release["case_ids"], conditions=("E0", "E3"),
        output_dir=tmp_path/"blocked", ledger_path=tmp_path/"ledger.json", env_file=tmp_path/"env")
    assert result["status"] == "blocked"
    assert result["failure_category"] == "NONCANONICAL_BENCHMARK_INPUT"
    assert result["attempted_calls"] == 0 and result["client_created"] is False


def test_zero_requests_never_qualify_as_valid_live_usage():
    from evaluation.r2_cross_domain_v1.live import case_usage_valid
    assert case_usage_valid({"attempted_calls": 0, "response_count": 0, "responses": []}) is False
