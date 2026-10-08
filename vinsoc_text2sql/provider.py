"""Orchestrator provider backed by the shared, role-aware real SDK journal."""
import json
from copy import deepcopy

from agent.provider import LLMProvider, LLMResponse

from .accounting import ScopedOpenAIClient


class QueryProvider(LLMProvider):
    def __init__(self, *, routing, assessment, r2, condition):
        if (any(type(c) is not ScopedOpenAIClient for c in (routing, assessment, r2))
                or routing.role != 'routing' or assessment.role != 'assessment' or r2.role != 'r2'
                or not routing.journal is assessment.journal is r2.journal
                or condition not in ('E0', 'E3')):
            raise ValueError('GUARDED_QUERY_PROVIDER_REQUIRED')
        self.routing, self.assessment, self.r2 = routing, assessment, r2
        self.journal, self.condition = routing.journal, condition
        self.turn = 0

    def reset_tracking(self):
        self.turn = 0  # Never resets the durable run ledger.
        self.start_event = len(self.journal.data['events'])

    def generate(self, messages, tools=None, system_prompt=None, temperature=0):
        if self.turn >= 2:
            raise ValueError('QUERY_OUTER_TURN_LIMIT')
        client = self.routing if self.turn == 0 else self.assessment
        c = client.contract
        payload = {k: c[k] for k in ('model', 'temperature', 'max_completion_tokens', 'service_tier')}
        payload['messages'] = ([{'role': 'system', 'content': system_prompt}] if system_prompt else [])+deepcopy(messages)
        if tools:
            payload.update(tools=deepcopy(tools), tool_choice='auto', parallel_tool_calls=False)
        response = client.request(payload)
        self.turn += 1
        calls = [{'id': c['id'], 'name': c['function']['name'],
                  'arguments': json.loads(c['function']['arguments'])}
                 for c in response['tool_calls']]
        return LLMResponse(content=response['content'] or '', tool_calls=calls, raw=response,
                           metadata={'role': client.role, 'model': response['actual_model']})

    def get_name(self):
        return 'openai_query_guarded'

    def get_run_metadata(self):
        return {'roles': [e['role'] for e in self.journal.data['events'][self.start_event:]],
                **self.routing.counters(), 'known_usd': self.journal.data['known_usd'],
                'cost_unknown': self.journal.data['cost_unknown']}
