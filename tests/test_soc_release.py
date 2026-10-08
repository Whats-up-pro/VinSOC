"""Gate/contract unit inputs, not operator authorization or live evidence."""

import pytest
from tests.soc_support import feature


def test_missing_gate_before_client():
    m = feature("evaluation.soc_traces_v1.release")
    with pytest.raises(ValueError, match="SOC_GATE"):
        m.build_release(identities={}, gates={})


def test_old_scope_rejected():
    with pytest.raises(ValueError):
        feature("evaluation.soc_traces_v1.release").validate_release({"window": "text2sql-e0"})


def test_request_contract_and_bytes():
    m = feature("evaluation.soc_traces_v1.accounting")
    payload = {
        "model": "gpt-4.1-mini-2025-04-14",
        "temperature": 0,
        "max_completion_tokens": 2000,
        "messages": [{"role": "user", "content": "Unit boundary input"}],
    }
    assert m.validate_request(payload, condition="S0", turn=0) > 0
    for mutation in (
        {"model": "other"},
        {"messages": [{"role": "user", "content": "界" * 50000}]},
        {"messages": [{"role": "user", "content": "x"}] * 17},
        {"tools": [{}]},
    ):
        with pytest.raises(ValueError):
            m.validate_request({**payload, **mutation}, condition="S0", turn=0)


def test_mock_transport_rejected_before_authority_or_transmission():
    import openai, httpx

    m = feature("agent.soc_provider")

    def forbidden(request):
        raise AssertionError("No SDK transmission permitted in this negative test")

    transport = httpx.MockTransport(forbidden)
    client = openai.OpenAI(
        api_key="unit-not-a-credential",
        max_retries=0,
        http_client=httpx.Client(transport=transport),
    )
    try:
        with pytest.raises(ValueError, match="REAL_HTTP_TRANSPORT"):
            m.SocProvider(client, journal=None, context=None)
    finally:
        client.close()


def test_mock_repository_rejected_before_lookup():
    m = feature("skills.soc_corpus_skill")
    with pytest.raises(ValueError, match="NATIVE_SOC_REPOSITORY"):
        m.SocCorpusContext(object(), "unit", "S1", "unit", "unit")
