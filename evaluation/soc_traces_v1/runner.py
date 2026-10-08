"""Offline preflight and one authorized 128-slot public-orchestrator execution."""
from collections import Counter
from datetime import datetime,timezone
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import urllib.request
from vinsoc_data.soc_corpus import SOURCE_MANIFEST,verify_sources,SocCorpusRepository,file_digest,digest,canonical
from evaluation.soc_traces_v1.dataset import validate_source_reviews
from evaluation.soc_traces_v1.release import ROOT,GATES,MODEL,private_directory,runtime_hashes,build_release,validate_release,read_bound_file
from evaluation.soc_traces_v1.accounting import atomic_json,SocRunJournal,SocTerminalError


def bound(path):
    path=Path(path).resolve();return {'path':str(path),'sha256':file_digest(path)}


def scan_visible(repository):
    forbidden={'ground_truth','success','decision','verdict','confidence','archetype','decisive','technique_hints'}
    def check(obj):
        if isinstance(obj,dict):
            if forbidden&set(obj):raise ValueError('SOC_VISIBLE_ORACLE_FIELD')
            for value in obj.values():check(value)
        elif isinstance(obj,list):
            for value in obj:check(value)
    for (value,) in repository._query('SELECT input_json FROM case_inputs UNION ALL SELECT record_json FROM observations'):
        check(json.loads(value))
    return {'status':'pass','method':'recursive allowlisted input/observation field scan','os_sandbox_claim':False}


def preflight(*,source_dir,corpus,inventory,reviews,private_dir):
    result={'status':'blocked','attempted_calls':0,'responses_received':0,'client_created':False,'new_inference_cost_usd':0,'blockers':[],'release':None}
    blockers=result['blockers'];repository=None
    try:
        inv=json.loads(Path(inventory).read_text());body={k:v for k,v in inv.items() if k!='inventory_sha256'}
        if digest(body)!=inv.get('inventory_sha256'):raise ValueError('SOC_INVENTORY_CHANGED')
        verify_sources(source_dir,SOURCE_MANIFEST)
        receipt_path=Path(corpus).parent/'corpus_receipt.json';receipt=json.loads(receipt_path.read_text())
        if receipt.get('importer_sha256')!=file_digest(ROOT/'vinsoc_data/soc_corpus.py'):raise ValueError('SOC_IMPORTER_RECEIPT_CHANGED')
        repository=SocCorpusRepository(Path(corpus),expected_sha256=receipt['database_sha256'])
        result['leakage_scan']=scan_visible(repository)
        if repository.metadata()['logical_sha256']!=receipt['logical_sha256']:raise ValueError('SOC_CORPUS_LOGICAL_CHANGED')
        ids=[c['scenario_id'] for c in inv['cases']]
        if len(set(ids))!=64 or Counter(c['label'] for c in inv['cases'])!={'malicious':32,'benign':32}:raise ValueError('SOC_INVENTORY_QUOTA_INVALID')
        result['inventory_sha256']=inv['inventory_sha256'];result['planned_records']=128
        audit=json.loads(Path(reviews).read_text()) if Path(reviews).is_file() else []
        review_gate=validate_source_reviews(audit,inventory=inv);result['source_review_gate']=review_gate
        if review_gate['status']!='pass':blockers.append('SOC_GATE_SOURCE_HUMAN_REVIEW_PENDING')
        if Path(private_dir).resolve()!=private_directory().resolve():blockers.append('SOC_CANONICAL_PRIVATE_DIR_REQUIRED')
        if (private_directory()/'ledger.json').exists():blockers.append('SOC_SCOPE_ALREADY_CONSUMED')
        gates={}
        for name in GATES:
            path=Path(reviews) if name=='source_reviews' else Path(private_dir)/(name+'.json')
            if path.is_file():gates[name]=bound(path)
            else:blockers.append('SOC_GATE_MISSING:'+name)
        try:runtime=runtime_hashes()
        except FileNotFoundError:blockers.append('SOC_RUNTIME_NOT_IMPLEMENTED');runtime={}
        import duckdb,openai,httpx
        environment={'python':'.'.join(map(str,sys.version_info[:3])),'duckdb':duckdb.__version__,'openai':openai.__version__,'httpx':httpx.__version__}
        artifacts=Path(inventory).parent
        identities={'implementation_sha':(read_bound_file(gates['ci']).get('implementation_sha') if 'ci' in gates else subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip()),'runtime':runtime,'environment':environment,
            'source_revision':receipt['source_revision'],'source_dir':str(Path(source_dir).resolve()),'corpus_path':str(Path(corpus).resolve()),
            'corpus_receipt':bound(receipt_path),'inventory':bound(inventory),'gold':bound(artifacts/'gold.json'),'demo_selection':bound(artifacts/'demo_selection.json')}
        result['runtime_closure_sha256']=digest(runtime);result['implementation_sha']=identities['implementation_sha']
        if not blockers:result['release']=build_release(identities=identities,gates=gates);result['status']='ready_to_live'
    except (ValueError,KeyError,OSError,TypeError,subprocess.CalledProcessError) as exc:
        code=str(exc) if isinstance(exc,ValueError) and str(exc).startswith('SOC_') else 'SOC_PREFLIGHT_IDENTITY_OR_INPUT_ERROR'
        blockers.append(code)
    finally:
        if repository:repository.close()
    return result


def planned_records(inventory,repository):
    return [{'scenario_id':c['scenario_id'],'condition':condition,'status':'not_run','review_status':'awaiting_human','data_origin':'synthetic',
        'input':{'kind':'alert','alert':repository.input_for(c['scenario_id'])},'model_outputs':[],'report':None,'cost_unknown':False}
      for c in inventory['cases'] for condition in ('S0','S1')]


def checkpoint_case(*,case_id,condition,receipt,output_dir):
    if not re.fullmatch(r'[A-Za-z0-9_-]+',case_id) or condition not in ('S0','S1'):raise ValueError('SOC_CHECKPOINT_ID_INVALID')
    if receipt.get('scenario_id')!=case_id or receipt.get('condition')!=condition:raise ValueError('SOC_CHECKPOINT_SCOPE_MISMATCH')
    path=Path(output_dir)/'cases'/f'{case_id}_{condition}.json'
    body={k:v for k,v in receipt.items() if k!='receipt_sha256'};completed={**body,'receipt_sha256':digest(body)}
    if path.exists():
        old=json.loads(path.read_text())
        if old['status'] in ('completed','failed','blocked') and old!=completed:raise ValueError('SOC_FINAL_RECEIPT_IMMUTABLE')
    atomic_json(path,completed);return path


def _verify_account(evidence):
    key=os.environ.get('OPENAI_API_KEY')
    if not key or hashlib.sha256(key.encode()).hexdigest()!=evidence['account']['api_key_sha256']:raise ValueError('SOC_ACCOUNT_KEY_MISSING_OR_CHANGED')
    request=urllib.request.Request('https://api.openai.com/v1/models/'+MODEL,headers={'Authorization':'Bearer '+key})
    try:
        with urllib.request.urlopen(request,timeout=30) as response:record=json.load(response)
    except Exception:raise ValueError('SOC_ACCOUNT_OR_MODEL_AVAILABILITY_UNVERIFIED') from None
    if record.get('id')!=MODEL:raise ValueError('SOC_MODEL_UNAVAILABLE')
    return key


def run_live(*,release_path,output_dir,private_dir):
    canonical=private_directory()
    if Path(private_dir).resolve()!=canonical.resolve() or Path(release_path).resolve()!=canonical/'release.json':raise ValueError('SOC_CANONICAL_RELEASE_REQUIRED')
    release=json.loads(Path(release_path).read_text());checked=validate_release(release)
    key=_verify_account(checked['evidence'])
    receipt=read_bound_file(release['identities']['corpus_receipt']);inventory=read_bound_file(release['identities']['inventory'])
    repository=SocCorpusRepository(Path(release['identities']['corpus_path']),expected_sha256=receipt['database_sha256'])
    scan_visible(repository)
    records=planned_records(inventory,repository)
    journal=SocRunJournal.claim(release,ledger_path=canonical/'ledger.json')
    client=None;terminal=False;fatal=None
    def write_summary():
        state=journal.snapshot()
        persisted=[]
        for record in records:
            path=Path(output_dir)/'cases'/f"{record['scenario_id']}_{record['condition']}.json"
            persisted.append(json.loads(path.read_text()) if path.is_file() else record)
        counts=dict(Counter(r['status'] for r in persisted))
        summary={'status':'partial' if terminal else ('completed' if counts.get('completed')==128 else 'failed'),
          'planned':128,'statuses':counts,'attempted_calls':len(state['reservations']),'responses_received':sum('response_sha256' in r for r in state['reservations']),
          'estimated_cost_usd':None if state['unknown_cost'] else state['estimated_cost_usd'],'known_partial_cost_usd':state['estimated_cost_usd'],'cost_unknown':state['unknown_cost'],
          'release_sha256':release['release_sha256'],'implementation_sha':release['identities']['implementation_sha'],'fatal':fatal,'data_origin':'synthetic','review_status':'awaiting_human'}
        atomic_json(Path(output_dir)/'suite_status.json',summary);return summary
    try:
        for record in records:checkpoint_case(case_id=record['scenario_id'],condition=record['condition'],receipt=record,output_dir=output_dir)
        import openai
        client=openai.OpenAI(api_key=key,base_url='https://api.openai.com/v1',max_retries=0,http_client=openai.DefaultHttpxClient(trust_env=False),timeout=60)
        journal.mark_client_created()
        from skills.soc_corpus_skill import SocCorpusContext
        from agent.soc_provider import SocProvider
        from agent.orchestrator import InvestigationOrchestrator
        for index,record in enumerate(records):
            context=SocCorpusContext(repository,record['scenario_id'],record['condition'],receipt['source_revision'],receipt['database_sha256'])
            provider=SocProvider(client,journal=journal,context=context)
            partial_outputs=[]
            def response_checkpoint(raw,metadata):
                partial_outputs.append({'id':raw.get('id'),'model':raw.get('model'),'message':(raw.get('choices') or [{}])[0].get('message'),'usage':raw.get('usage'),'metadata':metadata})
                partial={**record,'status':'partial','model_outputs':list(partial_outputs),'provider':provider.get_run_metadata()}
                checkpoint_case(case_id=record['scenario_id'],condition=record['condition'],receipt=partial,output_dir=output_dir)
            provider.response_checkpoint=response_checkpoint
            orchestrator=InvestigationOrchestrator(provider=provider)
            try:
                case=orchestrator.investigate_alert(record['input'],soc_context=context);meta=case.metadata
                final={**record,'status':meta['technical_status'],'case':case.to_dict(),'report':meta['soc_report'],'model_outputs':meta['model_outputs'],
                    'provider':meta['provider'],'cost_unknown':meta['cost_unknown'],'release_sha256':release['release_sha256'],'implementation_sha':release['identities']['implementation_sha']}
                terminal=meta['terminal']
            except ValueError as exc:
                final={**record,'status':'failed','error':str(exc) if str(exc).startswith(('SOC_','OFFICIAL_')) else 'SOC_CASE_INPUT_OR_CONTRACT_ERROR'}
            records[index]=final
            checkpoint_case(case_id=record['scenario_id'],condition=record['condition'],receipt=final,output_dir=output_dir)
            write_summary()
            if terminal:break
    except BaseException as exc:
        terminal=True;fatal=str(exc) if isinstance(exc,(SocTerminalError,ValueError)) and str(exc).startswith('SOC_') else 'SOC_RELEASE_INTERRUPTED'
    finally:
        if client:client.close()
        repository.close()
        summary=write_summary();journal.finish()
    return summary
