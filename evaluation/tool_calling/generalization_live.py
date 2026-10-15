"""One-shot transport around the existing R1 DecisionRunner, never a new scorer."""
from __future__ import annotations

import hashlib
import json
import os
import re
from pathlib import Path
from time import perf_counter
from types import SimpleNamespace

from agent.provider import OpenAIProvider, ModelPricing
from agent.tools import get_tool_schemas
from evaluation.finalization.cloud_window import atomic_json, GitHubWindowStore
from evaluation.finalization.query_token_bound import read_model_document
from evaluation.tool_calling.decision_runner import A1Config, DecisionRunner
from evaluation.tool_calling.generalization_reporting import build_generalization_report
from evaluation.tool_calling.generalization_run import (
    MODEL, SPLIT, collect_git_identity, validate_generalization_run_gate,
)
from evaluation.tool_calling.provenance import canonical_sha256, build_a1_provenance

PREFIX = 'vinsoc-r1-generalization-v1-once'


class R1Store(GitHubWindowStore):
    def exists(self):
        return self.api.request('GET', self.prefix+'/git/ref/tags/'+PREFIX) is not None

    def claim(self, receipt):
        if self.exists():
            raise ValueError('R1_WINDOW_ALREADY_CONSUMED')
        self._tag(PREFIX, {'implementation_sha': self.sha, 'run_id': self.run_id,
                          'gate_sha256': canonical_sha256(receipt), 'maximum_requests': 120,
                          'max_retries': 0, 'consumed': True})
        self.claimed = True

    def checkpoint(self, number, phase, event):
        if not self.claimed or not 1 <= number <= 120 or phase not in ('begin', 'end'):
            raise ValueError('R1_CHECKPOINT_INVALID')
        self._tag(f'{PREFIX}-request-{number}-{phase}',
                  {'run_id': self.run_id, 'number': number, 'phase': phase, 'event': event})


class JournalClient:
    """Persist native response and metering before OpenAIProvider parses it."""
    def __init__(self, sdk, output, gate, checkpoint, pricing, budget):
        self.sdk, self.output, self.gate, self.checkpoint = sdk, Path(output), gate, checkpoint
        self.pricing, self.budget = pricing, float(budget)
        self.case_id, self.expected_request_sha256 = None, None
        self.terminal = False
        self.data = {'attempted': 0, 'received': 0, 'known_usd': 0.,
                     'cost_unknown': False, 'pending_exposure_usd': 0., 'events': []}
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self.create))

    def save(self):
        atomic_json(self.output/'journal.json', self.data)

    def create(self, **request):
        if self.terminal:
            raise ValueError('R1_TRANSPORT_TERMINAL')
        self.gate()
        if (not re.fullmatch(r'gen_\d{3}', self.case_id or '')
                or not 1 <= int(self.case_id[4:]) <= 120
                or request.get('model') != MODEL or request.get('max_completion_tokens') != 1000
                or request.get('temperature') != 0 or self.data['cost_unknown']
                or self.data['attempted'] >= 120
                or self.case_id in {e['case_id'] for e in self.data['events']}):
            raise ValueError('R1_REQUEST_SCOPE_INVALID')
        digest = canonical_sha256(request)
        if self.expected_request_sha256 and digest != self.expected_request_sha256:
            raise ValueError('R1_NATIVE_REQUEST_CHANGED')
        reserve = (self.pricing['input_token_ceiling']*self.pricing['input_usd_per_million']
                   +1000*self.pricing['output_usd_per_million'])/1_000_000
        if self.data['known_usd']+reserve > self.budget:
            raise ValueError('R1_BUDGET_RESERVE_EXCEEDED')
        n = self.data['attempted']+1
        event = {'request_number': n, 'case_id': self.case_id, 'role': 'r1-decision',
                 'request_id': f'{os.environ.get("GITHUB_RUN_ID", "unit-test")}-r1-{n}',
                 'request_sha256': digest, 'reserved_usd': reserve,
                 'status': 'reserved_before_transmission', 'usage': None, 'cost_usd': None}
        self.data['events'].append(event)
        atomic_json(self.output/'requests'/f'{n:03d}-{self.case_id}.json', request)
        self.save()
        try:
            self.checkpoint(n, 'begin', event)
        except Exception:
            self.terminal = True
            raise ValueError('R1_REMOTE_BEGIN_FAILED') from None
        self.data.update(attempted=n, cost_unknown=True, pending_exposure_usd=reserve)
        self.save()
        started = perf_counter()
        try:
            response = self.sdk.chat.completions.create(**request)
        except Exception as error:
            self.terminal = True
            event.update(status='provider_error', error_class=type(error).__name__,
                         latency_seconds=perf_counter()-started)
            self.save()
            try:
                self.checkpoint(n, 'end', event)
            except Exception:
                pass
            raise ValueError('R1_PROVIDER_ERROR_UNKNOWN_EXPOSURE') from None
        # These durable bytes precede every tool-call/JSON parser in DecisionRunner.
        raw = response.model_dump(mode='json')
        path = self.output/'responses'/f'{n:03d}-{self.case_id}.json'
        atomic_json(path, raw)
        self.data['received'] += 1
        event.update(status='response_received', response_sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
                     response_id=getattr(response,'id',None),
                     provider_request_id=getattr(response,'_request_id',None),
                     actual_model=getattr(response,'model',None),
                     latency_seconds=perf_counter()-started)
        choices = raw.get('choices') or []
        event['finish_reason'] = choices[0].get('finish_reason') if choices else None
        usage = raw.get('usage') or {}
        inp, out = usage.get('prompt_tokens'), usage.get('completion_tokens')
        cached = (usage.get('prompt_tokens_details') or {}).get('cached_tokens',0)
        if (event['actual_model'] == MODEL and all(type(x) is int and x >= 0 for x in (inp,out,cached))
                and cached <= inp <= self.pricing['input_token_ceiling']
                and usage.get('total_tokens') == inp+out):
            cost = ((inp-cached)*self.pricing['input_usd_per_million']
                    +cached*self.pricing['cached_input_usd_per_million']
                    +out*self.pricing['output_usd_per_million'])/1_000_000
            event.update(usage={'input_tokens':inp,'cached_tokens':cached,'output_tokens':out}, cost_usd=cost)
            self.data.update(known_usd=self.data['known_usd']+cost, cost_unknown=False, pending_exposure_usd=0.)
        self.save()
        try:
            self.checkpoint(n, 'end', event)
        except Exception:
            self.terminal = True
            raise ValueError('R1_REMOTE_END_FAILED') from None
        prior = self.data['events'][:-1]
        if (self.data['cost_unknown'] or out > 1000 or event['cost_usd'] > reserve
                or not isinstance(event['response_id'], str) or not event['response_id'].strip()
                or not isinstance(event['provider_request_id'], str) or not event['provider_request_id'].strip()
                or event['finish_reason'] not in ('stop','tool_calls')
                or any(e.get('response_id') == event['response_id']
                       or e.get('provider_request_id') == event['provider_request_id'] for e in prior)):
            self.terminal = True
            raise ValueError('R1_RESPONSE_ID_USAGE_OR_CAP_INVALID')
        return response


def run_guarded(auth, gate, api, output):
    if output.exists():
        raise ValueError('R1_OUTPUT_ALREADY_EXISTS')
    if not api or not os.environ.get('OPENAI_API_KEY') or os.environ.get('OPENAI_BASE_URL'):
        raise ValueError('R1_OFFICIAL_TRANSPORT_REQUIRED')
    if os.environ.get('GITHUB_RUN_ATTEMPT') != '1':
        raise ValueError('R1_RERUN_FORBIDDEN')
    doc = Path(auth['model_document']['path'])
    doc_hash = auth['model_document']['sha256']
    prices = read_model_document(doc, MODEL)
    ceiling = 120*(prices['input_token_ceiling']*prices['input_usd_per_million']
                   +1000*prices['output_usd_per_million'])/1_000_000
    if (hashlib.sha256(doc.read_bytes()).hexdigest() != doc_hash
            or abs(float(auth['cost_ceiling_usd'])-ceiling) > 1e-10):
        raise ValueError('R1_PRICING_BOUND_UNVERIFIED')
    def recheck():
        if hashlib.sha256(doc.read_bytes()).hexdigest() != doc_hash:
            raise ValueError('R1_PRICING_DOCUMENT_CHANGED')
        checked = validate_generalization_run_gate(SPLIT, SPLIT/'GENERALIZATION.lock', auth,
            MODEL, auth['limit_usd'], collect_git_identity(auth, api))
        if not checked['passed'] or checked['authorization_sha256'] != gate['authorization_sha256']:
            raise ValueError('R1_TRANSMISSION_GATE_CHANGED')
    recheck()
    store = R1Store(api, gate['git']['commit_sha'], os.environ['GITHUB_RUN_ID'])
    store.claim(gate)
    output.mkdir(parents=True)
    atomic_json(output/'claim.json', {'claimed':True,'run_id':store.run_id,'implementation_sha':store.sha})
    atomic_json(output/'gate.json', gate)
    from openai import OpenAI
    sdk = OpenAI(max_retries=0, timeout=120)
    atomic_json(output/'client_created.json', {'client_created':True})
    journal = JournalClient(sdk, output, recheck, store.checkpoint, prices, auth['limit_usd'])
    provider = OpenAIProvider(model=MODEL, client=journal, max_retries=0,
        pricing=ModelPricing(prices['input_usd_per_million'], prices['output_usd_per_million'],
                             auth['model_document']['source_url'], auth['checked_utc']))
    runner = DecisionRunner(A1Config(model=MODEL,temperature=0.,max_tokens=1000), provider=provider)
    cases = runner.load_cases('generalization_v1')
    runner._run_cases = cases
    results, failed_case_id = [], None
    def save_report():
        report = build_generalization_report(cases, results, journal.data, gate, failed_case_id=failed_case_id)
        report.update(config={'provider':'openai','model':MODEL,'temperature':0,'max_completion_tokens':1000,'max_retries':0},
                      pricing={**prices, 'model_document':auth['model_document']},
                      github_run_id=os.environ['GITHUB_RUN_ID'], client_created=True)
        report['provenance'] = {**build_a1_provenance(runner,'generalization_v1',results),
                                'generalization_gate':gate,'provider_created_after_gate':True}
        atomic_json(output/'report.json', report)
        return report
    journal.save()
    save_report()
    try:
        for case in cases:
            failed_case_id = case.case_id
            journal.case_id = case.case_id
            system, question = runner.build_prompt(case)
            journal.expected_request_sha256 = canonical_sha256({
                'model':MODEL,'messages':[{'role':'system','content':system},{'role':'user','content':question}],
                'tools':get_tool_schemas(),'temperature':0.,'max_completion_tokens':1000})
            result = runner.run_decision(case)
            results.append(result)
            save_report()
            if journal.terminal or {'PROVIDER_ERROR','EXECUTION_ERROR','INVALID_TOOL_CALL'} & set(result.errors):
                break
            failed_case_id = None
    finally:
        report = save_report()
        sdk.close()
        try:
            store._tag(PREFIX+'-terminal', {'run_id':store.run_id,'attempted':journal.data['attempted'],
                'received':journal.data['received'],'known_usd':journal.data['known_usd'],
                'cost_unknown':journal.data['cost_unknown'],
                'report_sha256':hashlib.sha256((output/'report.json').read_bytes()).hexdigest()})
        except Exception:
            report['remote_terminal_checkpoint'] = 'UNCONFIRMED'
            report['official_eligible'] = False
            atomic_json(output/'report.json', report)
    return report
