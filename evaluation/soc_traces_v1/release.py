"""Independent SOC release. Operator evidence is required; no inherited R1/R2 authority."""
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
import subprocess
import urllib.request
from vinsoc_data.soc_corpus import canonical, digest, file_digest, REVISION, SOURCE_MANIFEST
from evaluation.soc_traces_v1.dataset import validate_source_reviews, select_demo

ROOT=Path(__file__).resolve().parents[2]
WINDOW='soc-traces-20261008-v1'
MODEL='gpt-4.1-mini-2025-04-14'
GATES=('source_reviews','account','pricing','budget','request_bound','ci')


def private_directory():return Path.home()/'.vinsoc'/'live-windows'/WINDOW


def runtime_paths():
    paths=set()
    for folder in ('agent','skills','vinsoc_data','evaluation/soc_traces_v1','cli'):
        paths.update(str(p.relative_to(ROOT)) for p in (ROOT/folder).rglob('*.py'))
    paths.update(str(p.relative_to(ROOT)) for p in (ROOT/'schemas').glob('*.json'))
    paths.update(('requirements.txt','.github/workflows/ci.yml','scripts/prepare_soc_traces.py','scripts/run_soc_traces.py','scripts/render_soc_report.py','scripts/review_soc_case.py'))
    return sorted(paths)


def runtime_hashes():
    return {p:file_digest(ROOT/p) for p in runtime_paths()}


def read_bound_file(entry):
    if not isinstance(entry,dict) or set(entry)!={'path','sha256'}:raise ValueError('SOC_GATE_FILE_BINDING_REQUIRED')
    path=Path(entry['path']).resolve()
    if not path.is_file() or file_digest(path)!=entry['sha256']:raise ValueError('SOC_GATE_FILE_CHANGED')
    return json.loads(path.read_text(encoding='utf-8'))


def _operator(evidence, *, time_field):
    try:
        t=datetime.fromisoformat(evidence[time_field].replace('Z','+00:00'))
        now=datetime.now(timezone.utc)
        if not evidence['operator'].strip() or t.tzinfo is None or t.date()!=now.date() or t>now:raise ValueError()
    except (KeyError,TypeError,ValueError):raise ValueError('SOC_GATE_OPERATOR_EVIDENCE_REQUIRED') from None


def _positive(value):return type(value) in (int,float) and math.isfinite(value) and value>0


def validate_identities(release):
    identities=release['identities']
    if identities.get('source_revision')!=REVISION:raise ValueError('SOC_SOURCE_REVISION_MISMATCH')
    if identities.get('runtime')!=runtime_hashes():raise ValueError('SOC_RUNTIME_CLOSURE_CHANGED')
    for relative,sha in identities['runtime'].items():
        content=subprocess.check_output(['git','show',identities['implementation_sha']+':'+relative],cwd=ROOT)
        if hashlib.sha256(content).hexdigest()!=sha:raise ValueError('SOC_IMPLEMENTATION_COMMIT_MISMATCH')
    required=('corpus_receipt','inventory','gold','demo_selection')
    artifacts={k:read_bound_file(identities[k]) for k in required}
    receipt=artifacts['corpus_receipt'];inventory=artifacts['inventory']
    body={k:v for k,v in inventory.items() if k!='inventory_sha256'}
    if digest(body)!=inventory['inventory_sha256']:raise ValueError('SOC_INVENTORY_CHANGED')
    cases=inventory['cases'];ids=[c['scenario_id'] for c in cases]
    if len(set(ids))!=64 or any(sum(c['label']==label for c in cases)!=32 for label in ('malicious','benign')):raise ValueError('SOC_INVENTORY_QUOTA_INVALID')
    if release['case_ids']!=ids:raise ValueError('SOC_RELEASE_SCOPE_CHANGED')
    if artifacts['gold']!={c['scenario_id']:{'label':c['label'],'family':c['family']} for c in cases}:raise ValueError('SOC_GOLD_IDENTITY_MISMATCH')
    if receipt['source_revision']!=REVISION or receipt['source_hashes']!=SOURCE_MANIFEST['files']:raise ValueError('SOC_SOURCE_RECEIPT_INVALID')
    for name,sha in SOURCE_MANIFEST['files'].items():
        path=Path(identities['source_dir']).resolve()/name
        if file_digest(path)!=sha:raise ValueError('SOC_SOURCE_CHANGED')
    if file_digest(identities['corpus_path'])!=receipt['database_sha256']:raise ValueError('SOC_CORPUS_CHANGED')
    from vinsoc_data.soc_corpus import SocCorpusRepository
    repo=SocCorpusRepository(Path(identities['corpus_path']),expected_sha256=receipt['database_sha256'])
    try:
        if repo.metadata()['logical_sha256']!=receipt['logical_sha256']:raise ValueError('SOC_LOGICAL_CORPUS_CHANGED')
        demos=artifacts['demo_selection']
        if demos['inventory_sha256']!=inventory['inventory_sha256'] or demos['ids']!=select_demo(inventory,repo):raise ValueError('SOC_DEMO_SELECTION_CHANGED')
    finally:repo.close()
    import duckdb,openai,httpx,sys
    expected={'python':'.'.join(map(str,sys.version_info[:3])),'duckdb':duckdb.__version__,'openai':openai.__version__,'httpx':httpx.__version__}
    if identities['environment']!=expected or (expected['duckdb'],expected['openai'],expected['httpx'])!=('1.5.5','2.8.1','0.28.1'):raise ValueError('SOC_ENVIRONMENT_CHANGED')
    return artifacts


def _ci(evidence,sha):
    _operator(evidence,time_field='checked_at')
    run_id=evidence.get('run_id')
    if type(run_id)!=int or evidence.get('implementation_sha')!=sha:raise ValueError('SOC_GATE_EXACT_CI_REQUIRED')
    base='https://api.github.com/repos/Whats-up-pro/VinSOC/actions/runs/'+str(run_id)
    def fetch(url):
        req=urllib.request.Request(url,headers={'Accept':'application/vnd.github+json','User-Agent':'VinSOC-SOC-preflight'})
        with urllib.request.urlopen(req,timeout=30) as response:return json.load(response)
    run=fetch(base);jobs=fetch(base+'/jobs')['jobs']
    if run['head_sha']!=sha or run['conclusion']!='success':raise ValueError('SOC_GATE_CI_NOT_PASS')
    for version in ('3.11','3.12'):
        job=next((j for j in jobs if j['name']=='test ('+version+')'),None)
        if not job or job['conclusion']!='success':raise ValueError('SOC_GATE_CI_MATRIX_REQUIRED')
        steps={s['name']:s['conclusion'] for s in job['steps']}
        if steps.get('Restore pinned SOC corpus')!='success' or steps.get('Run full repository test suite')!='success':raise ValueError('SOC_GATE_REQUIRED_CORPUS_CI')


def validate_release(release):
    if release.get('window')!=WINDOW or release.get('model')!=MODEL:raise ValueError('SOC_RELEASE_SCOPE_INVALID')
    if any(k not in release.get('gates',{}) for k in GATES):raise ValueError('SOC_GATE_MISSING')
    if release.get('caps')!={'S0':1,'S1':6,'suite':448,'tool_calls':5,'output_tokens':2000,'request_bytes':128000,'messages':16}:raise ValueError('SOC_RELEASE_CAPS_INVALID')
    body={k:v for k,v in release.items() if k!='release_sha256'}
    if release.get('release_sha256')!=digest(body):raise ValueError('SOC_RELEASE_HASH_INVALID')
    evidence={k:read_bound_file(release['gates'][k]) for k in GATES}
    artifacts=validate_identities(release)
    if validate_source_reviews(evidence['source_reviews'],inventory=artifacts['inventory'])['status']!='pass':raise ValueError('SOC_GATE_SOURCE_HUMAN_REVIEW_PENDING')
    for name in ('account','budget'):
        _operator(evidence[name],time_field='approved_at')
        if evidence[name].get('window')!=WINDOW:raise ValueError('SOC_GATE_OLD_AUTHORITY_REJECTED')
    account=evidence['account'];budget=evidence['budget'];pricing=evidence['pricing'];bound=evidence['request_bound']
    if account.get('allowed_model')!=MODEL or not account.get('account_id') or not account.get('authorization_statement') or len(account.get('api_key_sha256',''))!=64:raise ValueError('SOC_GATE_ACCOUNT_AUTHORIZATION_REQUIRED')
    if budget.get('calls_limit')!=448 or not _positive(budget.get('limit_usd')):raise ValueError('SOC_GATE_CONCRETE_BUDGET_REQUIRED')
    _operator(pricing,time_field='checked_at');_operator(bound,time_field='checked_at')
    if pricing.get('model')!=MODEL or pricing.get('source') not in ('https://developers.openai.com/api/docs/pricing','https://platform.openai.com/docs/pricing') or pricing.get('model_available') is not True or len(pricing.get('source_evidence_sha256',''))!=64 or not all(_positive(pricing.get(k)) for k in ('input_usd_per_million','output_usd_per_million')):raise ValueError('SOC_GATE_CURRENT_PRICING_REQUIRED')
    if bound.get('method')!='utf8_bytes_plus_verified_framing' or bound.get('max_utf8_bytes')!=128000 or type(bound.get('framing_token_reserve'))!=int or bound['framing_token_reserve']<1 or len(bound.get('verification_evidence_sha256',''))!=64 or not bound.get('verification_rationale'):raise ValueError('SOC_GATE_REQUEST_BOUND_UNVERIFIED')
    for record,field in ((pricing,'source_evidence'),(bound,'verification_evidence')):
        path=record.get(field+'_path')
        if not path or not Path(path).is_file() or file_digest(path)!=record[field+'_sha256']:raise ValueError('SOC_GATE_SUPPORTING_DOCUMENT_REQUIRED')
    maximum=((128000+bound['framing_token_reserve'])*pricing['input_usd_per_million']+2000*pricing['output_usd_per_million'])/1000000
    if maximum*448>budget['limit_usd']:raise ValueError('SOC_GATE_SUITE_BUDGET_INSUFFICIENT')
    _ci(evidence['ci'],release['identities']['implementation_sha'])
    return {'status':'pass','evidence':evidence,'maximum_request_usd':maximum,'maximum_suite_usd':maximum*448}


def build_release(*,identities,gates):
    if any(k not in gates for k in GATES):raise ValueError('SOC_GATE_MISSING:'+','.join(k for k in GATES if k not in gates))
    inv=read_bound_file(identities['inventory'])
    body={'window':WINDOW,'model':MODEL,'identities':identities,'gates':gates,'case_ids':[c['scenario_id'] for c in inv['cases']],
      'caps':{'S0':1,'S1':6,'suite':448,'tool_calls':5,'output_tokens':2000,'request_bytes':128000,'messages':16}}
    release={**body,'release_sha256':digest(body)};validate_release(release);return release
