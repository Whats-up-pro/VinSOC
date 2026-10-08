"""Official SDK-only adapter for the independent, single-use SOC release."""
import hashlib
import json
import time
import openai
import httpx
from agent.provider import LLMProvider,LLMResponse
from evaluation.soc_traces_v1.release import MODEL
from evaluation.soc_traces_v1.accounting import SocRunJournal,SocTerminalError

class SocProvider(LLMProvider):
    def __init__(self,client, *, journal,context):
        if type(client) is not openai.OpenAI or openai.__version__!='2.8.1' or httpx.__version__!='0.28.1' or str(client.base_url)!='https://api.openai.com/v1/' or client.max_retries!=0:raise ValueError('SOC_OFFICIAL_CLIENT_CONTRACT_REQUIRED')
        if not isinstance(journal,SocRunJournal) or not journal._claimed:raise ValueError('SOC_CLAIMED_RELEASE_REQUIRED')
        if hashlib.sha256(client.api_key.encode()).hexdigest()!=journal.checked['evidence']['account']['api_key_sha256']:raise ValueError('SOC_ACCOUNT_KEY_MISMATCH')
        from evaluation.soc_traces_v1.release import read_bound_file
        receipt=read_bound_file(journal.release['identities']['corpus_receipt'])
        if context.source_revision!=receipt['source_revision'] or context.corpus_sha256!=receipt['database_sha256']:raise ValueError('SOC_PROVIDER_CONTEXT_MISMATCH')
        journal.ensure_case_capacity(context.scenario_id,context.condition)
        self.client=client;self.journal=journal;self.context=context;self.model=MODEL;self.turn=0;self.calls=[]

    def ensure_case_capacity(self,case_id,condition):
        if (case_id,condition)!=(self.context.scenario_id,self.context.condition):raise ValueError('SOC_PROVIDER_SCOPE_MISMATCH')
        self.journal.ensure_case_capacity(case_id,condition)

    def generate(self,messages,tools=None,system_prompt=None,temperature=0.0):
        if temperature!=0.0:raise ValueError('SOC_TEMPERATURE_LOCKED')
        self.ensure_case_capacity(self.context.scenario_id,self.context.condition)
        payload={'model':MODEL,'temperature':0,'max_completion_tokens':2000,'messages':([{'role':'system','content':system_prompt}] if system_prompt else [])+messages}
        if tools:payload.update(tools=tools,parallel_tool_calls=False,tool_choice='auto')
        reservation=self.journal.reserve(case_id=self.context.scenario_id,condition=self.context.condition,turn=self.turn,payload=payload)
        started=time.perf_counter()
        try:
            response=self.client.chat.completions.with_raw_response.create(**payload)
            body=response.http_response.content
        except Exception:
            self.journal.fail(reservation,'transport_unknown_cost');raise SocTerminalError('SOC_TRANSPORT_UNKNOWN_COST') from None
        raw,measured=self.journal.record_response_bytes(reservation,body)
        self.last_raw=raw
        self.turn+=1
        metadata={'reservation_id':reservation,'actual_model':raw.get('model'),'request_id':raw.get('id'),'latency_ms':(time.perf_counter()-started)*1000,**measured}
        self.calls.append(metadata)
        checkpoint=getattr(self,'response_checkpoint',None)
        if checkpoint:
            try:checkpoint(raw,metadata)
            except Exception:
                self.journal.fail(reservation,'public_checkpoint_failed');raise SocTerminalError('SOC_CHECKPOINT_FAILED') from None
        choices=raw.get('choices')
        if raw.get('model')!=MODEL or not raw.get('id') or not isinstance(choices,list) or len(choices)!=1 or choices[0].get('finish_reason') not in ('stop','tool_calls'):
            self.journal.fail(reservation,'response_contract_invalid');raise SocTerminalError('SOC_RESPONSE_CONTRACT_INVALID')
        message=choices[0].get('message',{});calls=[]
        for call in message.get('tool_calls') or []:
            # Raw bytes were already durable before argument decoding.
            try:args=json.loads(call['function']['arguments'])
            except (ValueError,KeyError,TypeError):raise ValueError('SOC_TOOL_ARGUMENTS_NOT_JSON') from None
            calls.append({'id':call.get('id'),'name':call['function'].get('name'),'arguments':args})
        return LLMResponse(content=message.get('content') or '',tool_calls=calls,raw=raw,metadata=metadata)

    def get_name(self):return 'soc_openai_official'
    def reset_tracking(self):
        if self.turn:raise ValueError('SOC_PROVIDER_CANNOT_REPLAY')
    def get_run_metadata(self):
        return {'provider':self.get_name(),'model':MODEL,'calls':self.calls,'total_calls':len(self.calls),'estimated_cost_usd':sum(c['estimated_cost_usd'] for c in self.calls),'authentic_responses_received':len(self.calls)}
