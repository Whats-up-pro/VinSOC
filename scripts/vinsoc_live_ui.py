"""Local durable controller for guarded Actions runs. No model SDK or SQL execution."""
from __future__ import annotations

import hashlib
import json
import re
import subprocess
from datetime import datetime, timezone
from pathlib import Path

from evaluation.finalization.cloud_window import REPOSITORY
from evaluation.finalization.query_pipeline_reporting import build_pipeline_report, validate_review
from evaluation.finalization.query_view import case_view
from scripts.render_query_pipeline_report import load_records
from scripts.run_query_demo_cloud import write_json
from scripts.run_vinsoc_query_acceptance import inventory_for
from scripts.vinsoc_demo_data import TITLES
from scripts.vinsoc_live_protocol import WORKFLOW, canonical_hash, validate_request


def gh(*args, payload=None):
    command = ['gh',*map(str,args)]
    try:
        result = subprocess.run(command,input=payload,text=True,encoding='utf-8',
                                capture_output=True,timeout=120,check=False)
    except (OSError,subprocess.TimeoutExpired):
        raise ValueError('GITHUB_CONNECTION_UNAVAILABLE') from None
    if result.returncode:
        raise ValueError('GITHUB_COMMAND_FAILED')
    return result.stdout


def local_identity(root):
    root = Path(root)
    def git(*args):
        return subprocess.check_output(['git','-C',str(root),*args],text=True).strip()
    if git('status','--porcelain','--untracked-files=no'):
        raise ValueError('SOURCE_NOT_COMMITTED')
    sha = git('rev-parse','HEAD')
    runs = json.loads(gh('run','list','--repo',REPOSITORY,'--workflow','ci.yml',
                        '--commit',sha,'--limit','5','--json','databaseId,status,conclusion,headSha'))
    ci = next((r for r in runs if r['headSha'] == sha and r['status'] == 'completed' and r['conclusion'] == 'success'),None)
    if ci is None:
        raise ValueError('EXACT_SHA_CI_REQUIRED')
    return {'head_sha':sha,'ci_run_id':ci['databaseId']}


class GitHubTransport:
    def dispatch(self, request, mode):
        inputs = {'mode':mode,'execution_id':request['execution_id'],
                  'ci_run_id':str(request['ci_run_id']), 'request_json':json.dumps(request,ensure_ascii=False)}
        gh('api','--method','POST',f'repos/{REPOSITORY}/actions/workflows/{WORKFLOW}/dispatches',
           '--input','-',payload=json.dumps({'ref':'master','inputs':inputs},ensure_ascii=False))

    def locate(self, request, mode):
        runs = json.loads(gh('run','list','--repo',REPOSITORY,'--workflow',WORKFLOW,'--limit','50',
                             '--json','databaseId,displayTitle,headSha,status,conclusion,url'))
        title = f"VinSOC UI {mode} / {request['execution_id']}"
        matches = [r for r in runs if r['displayTitle'] == title]
        if len(matches) > 1:
            raise ValueError('DUPLICATE_REMOTE_DISPATCH')
        return matches[0] if matches else None

    def view(self, run_id):
        return json.loads(gh('run','view',run_id,'--repo',REPOSITORY,
                             '--json','databaseId,status,conclusion,headSha,url,jobs'))

    def download(self, run_id, target):
        gh('run','download',run_id,'--repo',REPOSITORY,'--dir',target)
        return json.loads(gh('api',f'repos/{REPOSITORY}/actions/runs/{run_id}/artifacts'))

    def checkpoints(self, window_id):
        from scripts.run_query_live_ui_cloud import LiveUiStore
        prefix = LiveUiStore._tag_component(window_id)
        refs = json.loads(gh('api',f'repos/{REPOSITORY}/git/matching-refs/tags/{prefix}'))
        cache = getattr(self,'_objects',{})
        events = []
        for ref in refs:
            sha = ref['object']['sha']
            if sha not in cache:
                cache[sha] = json.loads(json.loads(gh('api',f'repos/{REPOSITORY}/git/tags/{sha}'))['message'])
            if 'request_number' in cache[sha]:
                events.append(cache[sha])
        self._objects = cache
        return sorted(events,key=lambda r:(r['request_number'],r['phase'] == 'end'))


class LiveController:
    def __init__(self, root, *, storage=None, transport=None):
        self.root = Path(root)
        self.storage = Path(storage) if storage is not None else self.root/'.vinsoc/live-ui/sessions'
        self.transport = transport or GitHubTransport()

    def directory(self, execution_id):
        if not isinstance(execution_id,str) or not re.fullmatch(r'liveui-[a-f0-9]{24}',execution_id):
            raise ValueError('INVALID_EXECUTION_ID')
        return self.storage/execution_id

    def read(self, execution_id):
        return json.loads((self.directory(execution_id)/'state.json').read_text(encoding='utf-8'))

    def save(self, state):
        write_json(self.directory(state['request']['execution_id'])/'state.json',state)
        return state

    def submit_preflight(self, request):
        validate_request(request)
        directory = self.directory(request['execution_id'])
        try:
            directory.mkdir(parents=True,exist_ok=False)
        except FileExistsError:
            raise ValueError('DUPLICATE_DISPATCH_FORBIDDEN') from None
        state = {'request':request,'phase':'preflight_submitted','mode':'preflight',
                 'submitted_requests':{'preflight':request}, 'events':[]}
        self.save(state)
        try:
            self.transport.dispatch(request,'preflight')
        except Exception:
            state['phase'] = 'dispatch_delivery_unknown'
            self.save(state)
            raise
        return state

    def start_live(self, execution_id, *, consent, current_sha):
        state = self.read(execution_id)
        if state['phase'] != 'preflight_pass' or not state.get('control',{}).get('preflight_status') == 'preflight_pass':
            raise ValueError('PREFLIGHT_REQUIRED')
        if current_sha != state['request']['head_sha']:
            raise ValueError('SOURCE_CHANGED_AFTER_PREFLIGHT')
        request = {**state['request'],'live_consent':consent,
                   'confirmed_utc':datetime.now(timezone.utc).isoformat()}
        validate_request(request,mode='live')
        marker = self.directory(execution_id)/'live.dispatch'
        try:
            with marker.open('x') as out:
                out.write(canonical_hash(request))
        except FileExistsError:
            raise ValueError('DUPLICATE_DISPATCH_FORBIDDEN') from None
        state.update(phase='live_submitted',mode='live',events=[],control=None)
        state['submitted_requests']['live'] = request
        self.save(state)
        try:
            self.transport.dispatch(request,'live')
        except Exception:
            state['phase'] = 'dispatch_delivery_unknown'
            self.save(state)
            raise
        return state

    def poll(self, execution_id):
        state = self.read(execution_id)
        request = state['submitted_requests'][state['mode']]
        run = self.transport.locate(request,state['mode'])
        if run is None:
            return state
        if run['headSha'] != request['head_sha']:
            raise ValueError('WORKFLOW_SOURCE_IDENTITY_MISMATCH')
        details = self.transport.view(run['databaseId'])
        state.update(run_id=run['databaseId'],workflow=details)
        if run['status'] != 'completed':
            state['phase'] = state['mode']+'_running'
            if state['mode'] == 'live':
                from evaluation.finalization.query_runtime_validation import window_id_for
                window = window_id_for(request['scope'], request['case_id'],
                                       request['execution_id'] if request['scope'] == 'demo' else None)
                state['events'] = self.transport.checkpoints(window)
            return self.save(state)
        target = Path(state.get('download_dirs',{}).get(state['mode'], self.directory(execution_id)/state['mode']))
        if not (target/'.download_complete').is_file():
            import uuid
            if target.exists():
                target = self.directory(execution_id)/(state['mode']+'-'+uuid.uuid4().hex[:8])
            target.mkdir()
            metadata = self.transport.download(run['databaseId'],target)
            state['artifact_metadata'] = metadata
            (target/'.download_complete').write_text(str(run['databaseId']),encoding='utf-8')
            state.setdefault('download_dirs',{})[state['mode']] = str(target)
        controls = list(target.rglob('public/cloud_run.json'))
        if len(controls) != 1:
            state.update(phase='blocked',error='WORKFLOW_ARTIFACT_INCOMPLETE',download_dir=str(target))
            return self.save(state)
        control = json.loads(controls[0].read_text(encoding='utf-8'))
        if control.get('request') != request:
            raise ValueError('ARTIFACT_REQUEST_IDENTITY_MISMATCH')
        files = {str(p.relative_to(target)):hashlib.sha256(p.read_bytes()).hexdigest()
                 for p in controls[0].parent.rglob('*.json')}
        ledger = controls[0].parent.parent/'private/ledger.json'
        if ledger.is_file():
            files[str(ledger.relative_to(target))] = hashlib.sha256(ledger.read_bytes()).hexdigest()
        state.update(control=control,download_dir=str(target),public_dir=str(controls[0].parent),
                     artifact_files_sha256=files,phase=control['status'])
        return self.save(state)


def load_live_cases(state):
    if not state.get('public_dir'):
        return []
    target = Path(state['download_dir'])
    for relative,digest in state.get('artifact_files_sha256',{}).items():
        path = (target/relative).resolve()
        if not path.is_relative_to(target.resolve()) or hashlib.sha256(path.read_bytes()).hexdigest() != digest:
            raise ValueError('NEW_RUN_ARTIFACT_CHANGED')
    source = Path(state['public_dir'])/'live/report.json'
    if not source.is_file():
        return []
    report = load_records(source)
    cases = []
    scope = state.get('request',{}).get('scope')
    review_dir = target.parent/'reviews'
    reviews = [json.loads(p.read_text(encoding='utf-8')) for p in review_dir.glob('*.json')]
    accepted = [r for r in reviews if isinstance(r,dict) and any(validate_review(r,record) for record in report['case_records'])]
    ledger_path = Path(state['public_dir']).parent/'private/ledger.json'
    ledger = json.loads(ledger_path.read_text(encoding='utf-8')) if ledger_path.is_file() else {}
    projection = (build_pipeline_report(report['case_records'],inventory_for('pipeline'),reviews=accepted,
                  identities=report.get('case_records',[{}])[0].get('identities',{}) if report['case_records'] else {},
                  journal={'events':report.get('cost_events',[])}) if scope in ('demo','pipeline') else None)
    projected = {r['case_id']:r for r in projection['cases']} if projection else {}
    for record in report['case_records']:
        row = projected.get(record['case_id'],{})
        matching = [r for r in reviews if isinstance(r,dict) and r.get('case_id') == record['case_id']]
        valid = matching[0] if len(matching) == 1 and validate_review(matching[0],record) else None
        raw_assessments = [e for e in ledger.get('events',[]) if e.get('role') == 'assessment'
                          and e.get('case_id') == record['case_id'] and e.get('condition') == record['condition']
                          and e.get('response')]
        raw_assessment = {k:v for k,v in raw_assessments[-1].items() if k in
                          ('response','usage','response_id','request_id','actual_model','cost_usd')} if raw_assessments else None
        cases.append({'case_id':record['case_id'],'title':TITLES.get(record['case_id'],record['case_id']),
                      'condition':record['condition'],'question':record.get('question',case_view(record)['original_question']),
                      'record':record,'view':case_view(record,review=valid),'metrics':row.get('metrics',{}),
                      'status':row.get('status',record.get('status','incomplete')),
                      'review_status':'valid' if valid else 'hash_or_identity_mismatch' if matching else 'pending',
                      'reviews':matching,'raw_assessment':raw_assessment,
                      'case_path':source.parent/(record['condition']+'_'+record['case_id']+'.json'),
                      'source':source,'producer_sha':state['request']['head_sha'],
                      'source_run_id':state['run_id'],'explanation':'Kết quả của lượt mới đang chọn; giữ nguyên cả lỗi/partial.'})
    return cases
