"""Offline benchmark governance. No provider/client imports or inferred provenance."""
from collections import Counter
import hashlib
import json
from pathlib import Path

from .benchmark import ReferenceCase, validate_gold_parity
from .data import DatabaseContext, verify_archive_sha256, verify_archive_member
from .module_metrics import score_modules
from .semantic_scoring import score_case
from .tools import DatabaseTools


FIELDS = tuple(ReferenceCase.__dataclass_fields__)
COMPARATORS = {'scalar','ordered_rows','unordered_multiset','unordered_set'}


def file_hash(path, *, portable=False):
    raw = Path(path).read_bytes()
    if portable:
        raw = raw.replace(b'\r\n', b'\n').replace(b'\r', b'\n')
    return hashlib.sha256(raw).hexdigest()


def validate_inventory(references):
    ids = [row['case_id'] for row in references]
    if len(ids) != 120 or len(set(ids)) != 120:
        raise ValueError('CASE_IDS_DUPLICATE_OR_INCOMPLETE')
    counts = Counter(row['split'] for row in references)
    if counts != {'calibration':24,'evaluation':96}:
        raise ValueError('SPLIT_QUOTA_UNMET')
    external = [row for row in references if row['database_id'] != 'ctu_dev']
    cal = {row['database_id'] for row in external if row['split']=='calibration'}
    eva = {row['database_id'] for row in external if row['split']=='evaluation'}
    if len(cal)!=4 or len(eva)!=8 or cal & eva:
        raise ValueError('DATABASE_SPLITS_OR_QUOTA_UNMET')
    for database in cal | eva:
        cases=[row for row in external if row['database_id']==database]
        if len(cases) != (4 if database in cal else 8):
            raise ValueError('DATABASE_CASE_QUOTA_UNMET')
        if database in eva and Counter(row['difficulty'] for row in cases) != {'basic':2,'medium':4,'advanced':2}:
            raise ValueError('DATABASE_DIFFICULTY_QUOTA_UNMET')
    evaluation = [row for row in references if row['split']=='evaluation']
    difficulty = Counter(row['difficulty'] for row in evaluation)
    if difficulty != {'basic':24,'medium':48,'advanced':24}:
        raise ValueError('EVALUATION_DIFFICULTY_QUOTA_UNMET')
    features = Counter(feature for row in evaluation for feature in row['features'])
    ext_features = Counter(feature for row in evaluation if row['database_id']!='ctu_dev' for feature in row['features'])
    if ext_features['join']<16 or ext_features['nested']<8 or any(features[k]<8 for k in ('distinct','group_having','order_limit')):
        raise ValueError('FEATURE_QUOTA_UNMET')
    domains = {row['domain'] for row in evaluation if row['database_id']!='ctu_dev'}
    if len(domains)<5:
        raise ValueError('DOMAIN_QUOTA_UNMET')
    for row in references:
        if (any(key not in row for key in FIELDS) or row['comparator'] not in COMPARATORS
            or not row['accepted_links'] or any(alt.get('annotations_complete') is not True for alt in row['accepted_links'])):
            raise ValueError('REFERENCE_ANNOTATIONS_INCOMPLETE')
    questions=[(row['database_id'],' '.join(row['question'].split())) for row in references]
    if len(set(questions)) != len(questions):
        raise ValueError('DUPLICATE_NORMALIZED_QUESTION')
    return {'counts':dict(counts), 'difficulty':dict(difficulty), 'external_features':dict(ext_features),
            'evaluation_features':dict(features),'external_domains':sorted(domains),
            'external_calibration_databases':sorted(cal),'external_evaluation_databases':sorted(eva),
            'evaluation_family_count':len({(row['database_id'],row['family_id']) for row in evaluation}),
            'external_evaluation_family_count':len({(row['database_id'],row['family_id']) for row in evaluation if row['database_id']!='ctu_dev'}),
            'family_independence_assumed':False}


def select_oracle(references, seed=20261005):
    groups={}
    for row in references:
        if row['split']=='evaluation':
            groups.setdefault(row['database_id'],[]).append(row)
    picked=[]
    for database,rows in sorted(groups.items()):
        order=sorted(rows,key=lambda row:hashlib.sha256(f"{seed}:oracle:{row['case_id']}".encode()).hexdigest())
        count=4 if database=='ctu_dev' else 1
        # Prefer varied difficulty for CTU; then fill in seeded order.
        selected=[]
        if count==4:
            for difficulty in ('basic','medium','advanced'):
                item=next((row for row in order if row['difficulty']==difficulty),None)
                if item is not None:
                    selected.append(item)
        for row in order:
            if len(selected)==count:
                break
            if row not in selected:
                selected.append(row)
        picked.extend(row['case_id'] for row in selected)
    if len(picked)!=12 or len(set(picked))!=12:
        raise ValueError('ORACLE_SUBSET_INCOMPLETE')
    return picked


def verify_runtime(references,runtime):
    expected={row['case_id']:{key:row[key] for key in ('case_id','database_id','question')} for row in references}
    if len(runtime)!=len(expected) or any(set(row)!=set(('case_id','database_id','question')) for row in runtime):
        raise ValueError('RUNTIME_FIELDS_OR_COUNT_MISMATCH')
    actual={row['case_id']:row for row in runtime}
    if len(actual)!=len(runtime) or actual!=expected:
        raise ValueError('RUNTIME_REFERENCE_IDENTITY_MISMATCH')


def verify_file_identities(root,lock):
    root=Path(root).resolve()
    for key,portable in (('files',False),('source_files',True)):
        for name,expected in lock[key].items():
            path=(root/name).resolve()
            if not path.is_relative_to(root) or not path.is_file() or file_hash(path,portable=portable)!=expected:
                raise ValueError('LOCKED_FILE_IDENTITY_MISMATCH:'+name)


def validate_benchmark(registry,benchmarks,lock_path, *, replay=True):
    registry,benchmarks,lock_path=map(Path,(registry,benchmarks,lock_path))
    root=Path.cwd().resolve()
    lock=json.loads(lock_path.read_text(encoding='utf-8'))
    if lock.get('version')!='r2_cross_domain_v1' or lock.get('external_model_calls_at_lock')!=0:
        raise ValueError('BENCHMARK_LOCK_VERSION_OR_PROVENANCE')
    verify_file_identities(root,lock)
    if file_hash(registry)!=lock['registry_sha256']:
        raise ValueError('REGISTRY_IDENTITY_MISMATCH')
    refs=[json.loads(path.read_text(encoding='utf-8')) for path in sorted((benchmarks/'references').glob('*/*.json'))]
    inventory=validate_inventory(refs)
    runtime=[]
    for split in ('calibration','evaluation'):
        runtime.extend(json.loads((benchmarks/f'{split}_runtime.json').read_text(encoding='utf-8')))
    verify_runtime(refs,runtime)
    oracle=json.loads((benchmarks/'oracle_subset.json').read_text())['case_ids']
    if oracle!=select_oracle(refs):
        raise ValueError('ORACLE_SUBSET_IDENTITY_MISMATCH')
    entries=json.loads(registry.read_text())['databases']
    contexts={item['database_id']:DatabaseContext.from_manifest(registry,item['database_id']) for item in entries}
    manifest=Path(lock['source_manifest'])
    source=json.loads(manifest.read_text())
    sources=Path(lock['external_source_root'])
    archive=sources/source['archive_filename']
    verify_archive_sha256(archive,source['archive_sha256'])
    verify_archive_member(archive,source['split_member'],sources/source['split_member'])
    for context in contexts.values():
        if context.identity.get('source_type')=='verified_ctu_csv_manifest':
            from evaluation.ctu_network_public.contract import validate
            observed=validate(context.snapshot_path)
            if observed['logical_snapshot_sha256']!=context.identity['origin_logical_sha256']:
                raise ValueError('CTU_ORIGIN_IDENTITY_MISMATCH')
        else:
            verify_archive_member(archive,context.identity['source_sqlite_member'],sources/context.identity['source_sqlite_member'])
    scored=[]
    for ref in refs:
        audit_path=Path(ref['semantic_audit_path'])
        audit=json.loads(audit_path.read_text())
        if (audit['case_id']!=ref['case_id'] or audit['status']!='PASS' or len(audit['fixture_identities'])!=2
            or audit['semantic']['semantic_mutants_killed']<1 or audit['semantic']['equivalent_controls_accepted']<1):
            raise ValueError('SEMANTIC_GATE_INCOMPLETE')
        if any(not row['parity'] or row['ordering_validation']!='PASS' for row in audit['fixture_sqlite_duckdb_parity']):
            raise ValueError('SEMANTIC_GOLD_PARITY_UNVERIFIED')
        if replay:
            context=contexts[ref['database_id']]
            if ref.get('source_gold_sql'):
                parity=validate_gold_parity(ref['source_gold_sql'],sources/context.identity['source_sqlite_member'],context,ref['comparator'])
                if not parity['parity'] or parity['adapted_sql']!=ref['gold_sql']:
                    raise ValueError('GOLD_BASE_PARITY_MISMATCH')
            reference=ReferenceCase(**{key:ref[key] for key in FIELDS})
            record=score_case(reference,{'final_sql':ref['gold_sql'],'error_category':'OK'},[{'instance_id':'base_'+context.database_id,'context':context,'fixture_only':False}])
            if record['execution_accurate'] is not True:
                raise ValueError('BASE_GOLD_SCORE_FAILED')
            scored.append({'case_id':ref['case_id'],'gold_execution_accurate':True})
    return {'scope':'offline_benchmark_validation_not_model_score', 'inventory':inventory,
            'benchmark_lock_sha256':file_hash(lock_path),'base_gold_replayed':len(scored),
            'oracle_count':len(oracle), 'external_model_calls':0, 'new_inference_cost_usd':0,
            'release_paid_authorized':False,'frozen_closed':True}
