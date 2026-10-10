"""Durable single-allocation accounting for routing, R2 and assessment."""
from __future__ import annotations

import json
import math
import os
import uuid
from pathlib import Path
from time import monotonic
from types import SimpleNamespace

from evaluation.finalization.query_pipeline_contract import validate_release
from evaluation.r2_cross_domain_v1.release import canonical_hash


def persist(path, data):
    temporary = Path(path).with_suffix('.tmp')
    with temporary.open('w', encoding='utf-8') as out:
        json.dump(data, out, ensure_ascii=False, indent=2)
        out.flush()
        os.fsync(out.fileno())
    os.replace(temporary, path)
    if os.name == 'posix':
        os.chmod(path, 0o600)
        directory = os.open(Path(path).parent, os.O_DIRECTORY)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)


class RunJournal:
    @classmethod
    def claim(cls, release, *, ledger_path):
        release = validate_release(release)
        path = Path(ledger_path)
        canonical = Path.home()/'.vinsoc/live-windows'/release['window_id']/'ledger.json'
        if path.resolve() != canonical.resolve():
            raise ValueError('NONCANONICAL_RELEASE_LEDGER')
        if path.exists():
            raise ValueError('RELEASE_WINDOW_CONSUMED')
        path.parent.mkdir(parents=True, exist_ok=True)
        with (path.parent/'claim.json').open('x') as out:
            json.dump({'release_sha256': release['release_sha256']}, out)
            out.flush()
            os.fsync(out.fileno())
        self = cls()
        self.path, self.release = path, release
        self.data = {'window_id': release['window_id'], 'release_sha256': release['release_sha256'],
                     'attempted': 0, 'received': 0, 'valid_usage': 0, 'terminal': False,
                     'known_usd': release['gate_inputs']['account']['known_prior_cost_usd'],
                     'pending_exposure_usd': 0, 'cost_unknown': False, 'events': []}
        self.persist()
        return self

    def set_case(self, case_id, condition):
        if case_id not in self.release['case_ids'] or condition not in ('E0', 'E3'):
            raise ValueError('INVALID_COST_CASE_IDENTITY')
        self.case_id, self.condition = case_id, condition

    def case_events(self):
        return [{k: v for k, v in e.items() if k not in ('request', 'response')} for e in self.data['events']
                if e['case_id'] == self.case_id and e['condition'] == self.condition]

    def persist(self):
        persist(self.path, self.data)
        sink = getattr(self, 'checkpoint_sink', None)
        if sink and getattr(self, 'case_id', None):
            sink(self.case_events())

    def ensure_case_capacity(self, condition):
        required = {'routing': 1, 'r2': 6 if condition == 'E3' else 1, 'assessment': 1}
        for role, count in required.items():
            used = sum(e['role'] == role for e in self.data['events'])
            if used+count > self.release['role_caps'][role]:
                raise ValueError('WHOLE_CASE_REQUEST_CAP_INSUFFICIENT')
        if self.data['terminal'] or self.data['cost_unknown']:
            raise ValueError('TERMINAL_OR_UNKNOWN_COST')
        reserve = sum(self.release['reserves_usd'][r]*n for r, n in required.items())
        if self.data['known_usd']+reserve > self.release['gate_inputs']['budget']['limit_usd']:
            raise ValueError('WHOLE_CASE_BUDGET_INSUFFICIENT')

    def reserve(self, role, payload):
        if self.data['terminal'] or self.data['cost_unknown']:
            raise ValueError('TERMINAL_OR_UNKNOWN_COST')
        if not getattr(self, 'case_id', None) or not getattr(self, 'condition', None):
            raise ValueError('COST_CASE_IDENTITY_REQUIRED')
        from evaluation.finalization.query_runtime_validation import verify_transmission_files
        verify_transmission_files(self.release['gate_inputs']['identities'])
        cap = self.release['role_caps'][role]
        used = sum(e['role'] == role for e in self.data['events'])
        contract = self.release['contracts'][role]
        config = {k: contract[k] for k in ('model', 'max_completion_tokens', 'service_tier')}
        config['reasoning_effort' if role == 'r2' else 'temperature'] = contract['reasoning_effort' if role == 'r2' else 'temperature']
        if (used >= cap or any(payload.get(k) != v for k, v in config.items())
                or (role == 'r2' and 'temperature' in payload)
                or len(json.dumps(payload, ensure_ascii=False).encode()) > contract['max_request_bytes']
                or not isinstance(payload.get('messages'), list)
                or len(payload['messages']) > contract['max_messages']):
            raise ValueError('REQUEST_CONTRACT_OR_CAP_MISMATCH')
        allowed = set(config)|{'messages', 'tools', 'tool_choice', 'parallel_tool_calls'}
        if not set(payload) <= allowed or payload.get('tool_choice', 'auto') != 'auto':
            raise ValueError('REQUEST_CONTRACT_OR_CAP_MISMATCH')
        reserve = self.release['reserves_usd'][role]
        if self.data['known_usd']+reserve > self.release['gate_inputs']['budget']['limit_usd']:
            raise ValueError('BUDGET_EXCEEDED')
        event = {'role': role, 'case_id': self.case_id, 'condition': self.condition,
                 'request_id': uuid.uuid4().hex, 'request_sha256': canonical_hash(payload), 'received': False,
                 'request': payload,
                 'reserved_usd': reserve, 'cost_usd': None, 'usage': None}
        self.data['events'].append(event)
        self.data.update(attempted=self.data['attempted']+1, cost_unknown=True,
                         pending_exposure_usd=self.data['pending_exposure_usd']+reserve)
        self.persist()  # crash after reserve is paid exposure, never retry
        return len(self.data['events'])-1

    def fail(self, reservation_id, safe_code):
        event = self.data['events'][reservation_id]
        event['error_category'] = safe_code
        self.data['terminal'] = True
        self.persist()

    def record_response(self, reservation_id, response):
        event = self.data['events'][reservation_id]
        if event['received']:
            raise ValueError('RESPONSE_ALREADY_RECORDED')
        raw = response if isinstance(response, dict) else response.model_dump(mode='json')
        event.update(received=True, response=raw, actual_model=raw.get('model'),
                     response_id=raw.get('id'), provider_request_id=getattr(response, '_request_id', None))
        choices = raw.get('choices') or []
        event['native_tool_calls'] = (choices[0].get('message') or {}).get('tool_calls') or [] if choices else []
        self.data['received'] += 1
        self.persist()  # Full raw response and usage survive even validation/parse failure.
        usage = raw.get('usage') or {}
        inputs, outputs = usage.get('prompt_tokens'), usage.get('completion_tokens')
        cached = (usage.get('prompt_tokens_details') or {}).get('cached_tokens')
        if any(type(v) is not int or v < 0 for v in (inputs, outputs, cached)) or cached > inputs:
            self.fail(reservation_id, 'MISSING_OR_INVALID_USAGE')
            raise ValueError('MISSING_OR_INVALID_USAGE')
        event['usage'] = {'input_tokens': inputs, 'output_tokens': outputs, 'cached_tokens': cached}
        model = raw.get('model')
        pricing = self.release['gate_inputs']['pricing'].get(model)
        contract = self.release['contracts'][event['role']]
        if model != contract['model'] or not pricing or not raw.get('id'):
            self.fail(reservation_id, 'MODEL_MISMATCH')
            raise ValueError('MODEL_MISMATCH')
        cached_rate = pricing.get('cached_input_usd_per_million')
        if cached and (type(cached_rate) not in (int, float) or not math.isfinite(cached_rate)
                       or not 0 <= cached_rate <= pricing['input_usd_per_million']):
            self.fail(reservation_id, 'CACHED_PRICE_UNVERIFIED')
            raise ValueError('CACHED_PRICE_UNVERIFIED')
        cost = ((inputs-cached)*pricing['input_usd_per_million']+cached*(cached_rate or 0)
                + outputs*pricing['output_usd_per_million'])/1_000_000
        event['cost_usd'] = cost
        self.data.update(valid_usage=self.data['valid_usage']+1, known_usd=self.data['known_usd']+cost,
                         pending_exposure_usd=self.data['pending_exposure_usd']-event['reserved_usd'], cost_unknown=False)
        # Keep model response before any parsing. Private journal is never copied wholesale into Git.
        self.persist()
        if inputs > contract['max_request_bytes']+contract['frame_reserve_tokens'] or outputs > 1000 or cost > event['reserved_usd']:
            self.fail(reservation_id, 'USAGE_BOUND_EXCEEDED')
            raise ValueError('USAGE_BOUND_EXCEEDED')


class ScopedOpenAIClient:
    """SDK-compatible client view; the real OpenAI SDK is mandatory."""
    def __init__(self, client, *, role, contract, journal):
        from openai import OpenAI
        if type(client) is not OpenAI or client.max_retries != 0 or str(client.base_url) != 'https://api.openai.com/v1/':
            raise ValueError('VERIFIED_OFFICIAL_OPENAI_CLIENT_REQUIRED')
        if contract != journal.release['contracts'][role]:
            raise ValueError('REQUEST_CONTRACT_MISMATCH')
        self.client, self.role, self.contract, self.journal = client, role, contract, journal
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self.create))

    def create(self, **payload):
        reservation = self.journal.reserve(self.role, payload)
        started = monotonic()
        try:
            response = self.client.chat.completions.create(**payload)
        except Exception:
            self.journal.fail(reservation, 'PROVIDER_ERROR')
            raise ValueError('PROVIDER_ERROR') from None
        self.journal.data['events'][reservation]['latency_seconds'] = monotonic()-started
        self.journal.record_response(reservation, response)
        return response

    def counters(self):
        return {k: self.journal.data[k] for k in ('attempted', 'received', 'valid_usage', 'terminal')}

    def request(self, payload):
        response = self.create(**payload)
        choice = response.choices[0]
        if choice.finish_reason not in ('stop', 'tool_calls'):
            raise ValueError('INVALID_FINISH_REASON')
        calls = [c.model_dump(mode='json') for c in (choice.message.tool_calls or [])]
        return {'content': choice.message.content, 'tool_calls': calls, 'model': response.model,
                'actual_model': response.model, 'response_id': response.id, 'finish_reason': choice.finish_reason,
                'usage': self.journal.data['events'][-1]['usage'], 'cost_usd': self.journal.data['events'][-1]['cost_usd']}
