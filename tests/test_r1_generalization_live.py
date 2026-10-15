"""Transport failure injection only; these tests produce no acceptance evidence."""
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[1]


def test_workflow_is_manual_master_and_preserves_partial():
    text = (ROOT/'.github/workflows/r1-generalization-v1.yml').read_text()
    assert 'workflow_dispatch:' in text
    assert 'pull_request:' not in text and '\n  push:' not in text
    for token in ('refs/heads/master', "python-version: '3.11'", 'ci_run_id:',
                  'split_sha256:', 'budget_usd:', 'model:', 'if: always()',
                  'actions/upload-artifact@v4', 'max_retries', '120'):
        assert token in text


def test_transport_failure_keeps_unknown_and_never_retries(tmp_path):
    from evaluation.tool_calling.generalization_live import JournalClient
    calls = []
    def create(**request):
        calls.append(request)
        raise RuntimeError('private provider body must not be published')
    sdk = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)))
    client = JournalClient(sdk, tmp_path, lambda: None, lambda *args: None,
                           {'input_token_ceiling': 1047576, 'input_usd_per_million': .4,
                            'cached_input_usd_per_million': .1, 'output_usd_per_million': 1.6}, 100)
    client.case_id = 'gen_001'
    with pytest.raises(ValueError, match='PROVIDER'):
        client.create(model='gpt-4.1-mini-2025-04-14', max_completion_tokens=1000,
                      temperature=0, messages=[], tools=[])
    journal = json.loads((tmp_path/'journal.json').read_text())
    assert journal['attempted'] == 1 and journal['received'] == 0
    assert journal['cost_unknown'] is True
    assert 'private provider body' not in json.dumps(journal)
    with pytest.raises(ValueError, match='TERMINAL'):
        client.create()
    assert len(calls) == 1


def test_transport_rechecks_gate_before_transmission(tmp_path):
    from evaluation.tool_calling.generalization_live import JournalClient
    def blocked():
        raise ValueError('SOURCE_CHANGED')
    sdk = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(
        create=lambda **kwargs: pytest.fail('SDK reached'))))
    client = JournalClient(sdk, tmp_path, blocked, lambda *args: None,
                           {'input_token_ceiling': 1047576, 'input_usd_per_million': .4,
                            'cached_input_usd_per_million': .1, 'output_usd_per_million': 1.6}, 100)
    client.case_id = 'gen_001'
    with pytest.raises(ValueError, match='SOURCE_CHANGED'):
        client.create(model='gpt-4.1-mini-2025-04-14',max_completion_tokens=1000,temperature=0)
    assert client.data['attempted'] == 0


def test_unit_response_metering_survives_provider_json_parse_failure(tmp_path):
    # Deliberately malformed unit response; never an acceptance/model record.
    from agent.provider import OpenAIProvider, ProviderError
    from evaluation.tool_calling.generalization_live import JournalClient
    raw = {'id':'unit-response','model':'gpt-4.1-mini-2025-04-14',
           'usage':{'prompt_tokens':100,'completion_tokens':10,'total_tokens':110},
           'choices':[{'finish_reason':'tool_calls'}]}
    response = SimpleNamespace(id='unit-response',model=raw['model'],_request_id='unit-header',
        model_dump=lambda **kwargs: raw,
        choices=[SimpleNamespace(message=SimpleNamespace(content='',tool_calls=[
            SimpleNamespace(id='unit-call',function=SimpleNamespace(name='network_investigation',arguments='{'))]))])
    sdk = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=lambda **kwargs: response)))
    client = JournalClient(sdk,tmp_path,lambda:None,lambda *args:None,
        {'input_token_ceiling':1047576,'input_usd_per_million':.4,
         'cached_input_usd_per_million':.1,'output_usd_per_million':1.6},100)
    client.case_id='gen_001'
    provider=OpenAIProvider(model=raw['model'],client=client,
                            request_overrides={'max_completion_tokens':1000},max_retries=0)
    with pytest.raises(ProviderError):
        provider.generate(messages=[],tools=[],temperature=0)
    saved=json.loads((tmp_path/'journal.json').read_text())
    assert saved['received']==1 and saved['cost_unknown'] is False
    assert saved['events'][0]['provider_request_id']=='unit-header'
    assert saved['events'][0]['usage']['input_tokens']==100
    assert saved['known_usd']==pytest.approx(.000056)
    assert json.loads(next((tmp_path/'responses').glob('*.json')).read_text())==raw


def test_truncated_unit_response_stops_but_preserves_known_cost(tmp_path):
    from evaluation.tool_calling.generalization_live import JournalClient
    raw={'id':'unit-truncated','model':'gpt-4.1-mini-2025-04-14',
         'usage':{'prompt_tokens':100,'completion_tokens':1000,'total_tokens':1100},
         'choices':[{'finish_reason':'length'}]}
    response=SimpleNamespace(id=raw['id'],model=raw['model'],_request_id='unit-truncated-header',
                             model_dump=lambda **kwargs:raw)
    sdk=SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=lambda **kwargs:response)))
    client=JournalClient(sdk,tmp_path,lambda:None,lambda *args:None,
        {'input_token_ceiling':1047576,'input_usd_per_million':.4,
         'cached_input_usd_per_million':.1,'output_usd_per_million':1.6},100)
    client.case_id='gen_001'
    with pytest.raises(ValueError,match='RESPONSE'):
        client.create(model=raw['model'],temperature=0,max_completion_tokens=1000)
    assert client.terminal is True
    assert client.data['received']==1 and client.data['cost_unknown'] is False
    assert client.data['known_usd']==pytest.approx(.00164)
