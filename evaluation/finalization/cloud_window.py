"""Cloud adaptation of the pinned local window, with append-only remote claims.

No existing runner/lock bytes are changed. An operator-attested sealed previous
host state is mandatory; an ephemeral runner never implies a fresh paid window.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
from pathlib import Path
from datetime import datetime, timezone
from types import SimpleNamespace
from urllib.error import HTTPError
from urllib.parse import urlparse
from urllib.request import Request, build_opener, HTTPRedirectHandler
import zipfile

from .live_window import (WINDOW_ID, _fresh_utc, _provider_error_details, _safe_request_id,
                          _GuardedCompletions, compute_request_reserve)

REPOSITORY = 'Whats-up-pro/VinSOC'
BUNDLE_SHA256 = 'c5c0cb5d6ed42f3acb303b041f1613d91d793dd518112b146d078d05f3768415'
SNAPSHOT_SHA256 = '91a13ab149453ca6db6246ada3d7a21708537a12865a01e6475df18dd9a9eac3'
MODEL = 'gpt-4.1-mini-2025-04-14'
TAG_PREFIX = 'vinsoc-window-'+WINDOW_ID


class CloudError(ValueError):
    """Literal codes only; no provider body, signed URL or credentials."""


def digest(data):
    return hashlib.sha256(json.dumps(data,sort_keys=True,separators=(',',':')).encode()).hexdigest()


def atomic_json(path,data):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    temp=path.with_suffix(path.suffix+'.tmp')
    with temp.open('w',encoding='utf-8') as out:
        json.dump(data,out,indent=2,sort_keys=True);out.flush();os.fsync(out.fileno())
    os.replace(temp,path)


def validate_migration(state):
    if not isinstance(state,dict) or state.get('window_id')!=WINDOW_ID:
        raise CloudError('MIGRATION_WINDOW_MISMATCH')
    if state.get('previous_hosts_sealed') is not True:raise CloudError('PREVIOUS_HOST_NOT_SEALED')
    if not _fresh_utc(state.get('confirmed_utc')):raise CloudError('MIGRATION_STATE_STALE')
    ledger=state.get('ledger')
    if not isinstance(ledger,dict) or digest(ledger)!=state.get('ledger_sha256'):
        raise CloudError('MIGRATION_LEDGER_HASH_MISMATCH')
    if ledger.get('window_id')!=WINDOW_ID or ledger.get('condition')!='NETWORK_DEMO':
        raise CloudError('MIGRATION_WINDOW_MISMATCH')
    if (any(ledger.get(k) is not False for k in ('consumed','active_claim','cost_unknown'))
        or any(type(ledger.get(k)) is not int or ledger[k]!=0 for k in ('attempted_requests','responses_received','valid_usage_records'))
        or ledger.get('attempts')!=[] or ledger.get('reservations')!=[] or ledger.get('terminal_status')):
        raise CloudError('WINDOW_ALREADY_USED')
    prior=ledger.get('known_cost_usd')
    if type(prior) not in (int,float) or not 0<=prior<=.25:
        raise CloudError('MIGRATION_COST_INVALID')
    return json.loads(json.dumps(ledger))


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self,*args,**kwargs):raise CloudError('REMOTE_REDIRECT_REJECTED')


class GitHubAPI:
    def __init__(self,token):
        if not token:raise CloudError('GITHUB_TOKEN_UNAVAILABLE')
        self.token=token
    def request(self,method,route,payload=None):
        prefix='/repos/'+REPOSITORY+'/'
        if method not in ('GET','POST') or not route.startswith(prefix):raise CloudError('REMOTE_ENDPOINT_REJECTED')
        body=json.dumps(payload).encode() if payload is not None else None
        request=Request('https://api.github.com'+route,data=body,method=method,
            headers={'Authorization':'Bearer '+self.token,'Accept':'application/vnd.github+json',
                     'X-GitHub-Api-Version':'2022-11-28','Content-Type':'application/json'})
        try:
            with build_opener(NoRedirect).open(request,timeout=30) as response:
                content=response.read(2*1024*1024+1)
            if len(content)>2*1024*1024:raise CloudError('REMOTE_PAYLOAD_TOO_LARGE')
            return json.loads(content)
        except HTTPError as error:
            if method=='GET' and error.code==404 and '/git/ref/' in route:return None
            raise CloudError('REMOTE_CLAIM_CONFLICT' if error.code==422 else 'REMOTE_STATE_UNAVAILABLE') from None
        except CloudError:raise
        except Exception:raise CloudError('REMOTE_STATE_UNAVAILABLE') from None


class GitHubWindowStore:
    def __init__(self,api,implementation_sha,run_id):
        if not re.fullmatch('[0-9a-f]{40}',implementation_sha) or not re.fullmatch('[0-9]{1,24}',run_id):
            raise CloudError('CLOUD_IDENTITY_INVALID')
        self.api,self.sha,self.run_id=api,implementation_sha,run_id
        self.prefix='/repos/'+REPOSITORY
        self.claimed=False
    def exists(self):
        return self.api.request('GET',self.prefix+'/git/ref/tags/'+TAG_PREFIX) is not None
    def _tag(self,name,data):
        # Tag objects point at the verified implementation commit; master is not moved.
        value={'tag':name,'message':json.dumps(data,sort_keys=True),'object':self.sha,'type':'commit',
               'tagger':{'name':'VinSOC guarded runner','email':'noreply@github.com',
                         'date':datetime.now(timezone.utc).isoformat()}}
        tag=self.api.request('POST',self.prefix+'/git/tags',value)
        if not isinstance(tag,dict) or not re.fullmatch('[0-9a-f]{40,64}',tag.get('sha','')):
            raise CloudError('REMOTE_TAG_RESPONSE_INVALID')
        self.api.request('POST',self.prefix+'/git/refs',{'ref':'refs/tags/'+name,'sha':tag['sha']})
    def claim(self,state_sha256):
        if self.exists():raise CloudError('WINDOW_ALREADY_USED')
        self._tag(TAG_PREFIX,{'window_id':WINDOW_ID,'consumed':True,'run_id':self.run_id,
                             'implementation_sha':self.sha,'migration_ledger_sha256':state_sha256})
        self.claimed=True
    def checkpoint(self,suffix,data):
        if not self.claimed:raise CloudError('REMOTE_CLAIM_REQUIRED')
        if not re.fullmatch(r'(request-[1-4]-(begin|end)|terminal)',suffix):raise CloudError('REMOTE_CHECKPOINT_INVALID')
        self._tag(TAG_PREFIX+'-'+suffix,{'window_id':WINDOW_ID,'run_id':self.run_id,**data})


class CloudCheckpointClient:
    def __init__(self,sdk,store,journal_path):
        self.sdk,self.store,self.path=sdk,store,Path(journal_path)
        self.data={'attempted_calls':0,'responses_received':0,'known_cost_usd':0.0,'cost_unknown':False,'events':[]}
        self.terminal=False
        self.chat=SimpleNamespace(completions=SimpleNamespace(create=self.create))
    def create(self,**request):
        if self.terminal:raise CloudError('CLOUD_TRANSPORT_TERMINAL')
        n=len(self.data['events'])+1
        if n>4:raise CloudError('CLOUD_REQUEST_LIMIT')
        event={'request_number':n,'request_sha256':digest(request),'status':'reserved_before_transmission',
               'reserved_exposure_usd':compute_request_reserve(),'usage':None,'cost_usd':None}
        self.data['events'].append(event);atomic_json(self.path,self.data)
        try:self.store.checkpoint(f'request-{n}-begin',event)
        except Exception:
            self.terminal=True
            raise CloudError('REMOTE_CHECKPOINT_BEFORE_REQUEST_FAILED') from None
        self.data['attempted_calls']+=1;self.data['cost_unknown']=True;atomic_json(self.path,self.data)
        try:response=self.sdk.chat.completions.create(**request)
        except Exception as error:
            self.terminal=True;event.update(status='provider_error',provider_error=_provider_error_details(error))
            atomic_json(self.path,self.data)
            try:self.store.checkpoint(f'request-{n}-end',event)
            except Exception:pass  # durable begin remains conservative unknown exposure
            raise CloudError('PROVIDER_ERROR') from None
        usage,cost=_GuardedCompletions._usage(response)
        model=getattr(response,'model',None)
        if not isinstance(model,str) or not re.fullmatch(r'gpt-[A-Za-z0-9._-]{1,90}',model):model=None
        if model!=MODEL:cost=None  # another model's pricing is not guessed
        event.update(status='response_received',actual_provider='openai',actual_model=model,
                     request_id=_safe_request_id(getattr(response,'_request_id',None)),usage=usage,cost_usd=cost)
        self.data['responses_received']+=1
        if cost is not None:self.data['known_cost_usd']+=cost;self.data['cost_unknown']=False
        atomic_json(self.path,self.data)  # authentic usage survives remote checkpoint failure
        try:self.store.checkpoint(f'request-{n}-end',event)
        except Exception:
            self.terminal=True;raise CloudError('REMOTE_CHECKPOINT_AFTER_RESPONSE_FAILED') from None
        if cost is None or usage is None or model!=MODEL:
            self.terminal=True;raise CloudError('RESPONSE_IDENTITY_OR_USAGE_UNVERIFIED')
        return response
    def close(self):
        close=getattr(self.sdk,'close',None)
        if callable(close):close()


def extract_snapshot_bundle(bundle,destination):
    bundle,destination=Path(bundle),Path(destination)
    if hashlib.sha256(bundle.read_bytes()).hexdigest()!=BUNDLE_SHA256:raise CloudError('SNAPSHOT_BUNDLE_HASH_MISMATCH')
    try:
        with zipfile.ZipFile(bundle) as archive:
            if archive.namelist()!=['ctu_e2e_20261007.duckdb','NETWORK_E2E_v1.lock.json','snapshot_qualification.json','README.txt']:
                raise CloudError('SNAPSHOT_BUNDLE_MEMBERS_INVALID')
            member=archive.getinfo('ctu_e2e_20261007.duckdb')
            if member.file_size>32*1024*1024:raise CloudError('SNAPSHOT_BUNDLE_TOO_LARGE')
            data=archive.read(member)
        if hashlib.sha256(data).hexdigest()!=SNAPSHOT_SHA256:raise CloudError('SNAPSHOT_BINARY_HASH_MISMATCH')
        destination.mkdir(parents=True,exist_ok=True)
        path=destination/'ctu_e2e_20261007.duckdb'
        with path.open('xb') as out:out.write(data)
        return path
    except CloudError:raise
    except Exception:raise CloudError('SNAPSHOT_BUNDLE_INVALID') from None


def download_bundle(url,destination):
    parsed=urlparse(url)
    allowed=(parsed.hostname=='release-assets.githubusercontent.com' or (parsed.hostname or '').endswith('.blob.core.windows.net'))
    if parsed.scheme!='https' or not allowed or parsed.username or parsed.password:
        raise CloudError('SNAPSHOT_URL_REJECTED')
    try:
        with build_opener(NoRedirect).open(Request(url),timeout=60) as response:content=response.read(8*1024*1024+1)
        if len(content)>8*1024*1024:raise CloudError('SNAPSHOT_BUNDLE_TOO_LARGE')
        with Path(destination).open('xb') as out:out.write(content)
    except CloudError:raise
    except Exception:raise CloudError('SNAPSHOT_DOWNLOAD_FAILED') from None
