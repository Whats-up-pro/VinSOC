"""CLI case serialization regression; fake provider only, zero external calls."""
import pytest

from agent.provider import MockProvider
from skills.validators import validate_investigation_case


@pytest.mark.parametrize('context', [None, '', 'synthetic analyst context'])
def test_cli_investigation_optional_context_keeps_case_schema_valid(monkeypatch, context):
    import openai
    from cli import main

    def forbidden(*args, **kwargs):
        pytest.fail('offline context regression attempted a provider SDK call')

    monkeypatch.setattr(openai, 'OpenAI', forbidden)
    monkeypatch.setattr(openai, 'AsyncOpenAI', forbidden)
    # Exercise the CLI OpenAI branch with an explicitly injected fake provider.
    constructed = []
    def fake_provider(provider, model, api_key, **kwargs):
        constructed.append((provider, model))
        return MockProvider(model='synthetic-context-fixture')
    monkeypatch.setattr(main, 'create_provider', fake_provider)
    indicator = '192.0.2.17'
    result = main.run_investigation(
        indicator, indicator_type='ipv4', context=context, provider='openai', model='gpt-4.1-mini-2025-04-14',
        test_data={'cti_mock_data': {indicator: {'reputation': 'unknown', 'confidence': 'LOW'}},
                   'network_mock_data': {}, 'endpoint_mock_data': {}})
    valid, error = validate_investigation_case(result)
    assert valid, error
    assert result['metadata']['schema_valid'] is True
    assert not any('Case schema validation failed' in item for item in result['limitations'])
    assert constructed == [('openai', 'gpt-4.1-mini-2025-04-14')]
    if context is None:
        assert 'context' not in result['initial_indicator']
    else:
        assert result['initial_indicator']['context'] == context
