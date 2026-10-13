"""Read authentic demo artifacts and bind human reviews to immutable case bytes."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

from evaluation.finalization.query_pipeline_reporting import build_pipeline_report, validate_review
from evaluation.finalization.query_view import case_view
from scripts.render_query_pipeline_report import DEMO_IDS, load_records
from scripts.review_vinsoc_query_case import validate_review_utc
from scripts.run_vinsoc_query_acceptance import inventory_for

INTEGRATION = Path('results/evaluation_v1/text2sql_integration_v1')
PACKAGE = INTEGRATION / 'mentor_four_case_demo_20261013'
R1_SOURCE = Path('results/evaluation_v1/r1/r1_a1_dev_v2_852e543.json')
SOC_SOURCE = Path('results/evaluation_v1/soc_traces_v1/demo_e2e/SCT-087094_S1.json')
TITLES = dict(zip(DEMO_IDS, ('COUNT · IP chung', 'UDP · khác biệt hai tập',
                           'NULL · nhóm có count 0', 'AVG · so sánh trung bình')))
STATUS_LABELS = {'awaiting_human':'Đạt kỹ thuật · chờ người duyệt',
                 'incomplete':'Chưa hoàn tất', 'technical_failed':'Lỗi kỹ thuật / ngữ nghĩa',
                 'missing':'Chưa có record', 'integrity_failed':'Bằng chứng không khớp',
                 'approved':'Người duyệt đã chấp thuận', 'rejected':'Người duyệt từ chối',
                 'escalated':'Chuyển điều tra thêm'}


def read_json(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))


def checked_file(package, manifest, relative):
    target = (package / relative).resolve()
    if not target.is_relative_to(package.resolve()):
        raise ValueError('ARTIFACT_PATH_OUTSIDE_PACKAGE')
    if not target.is_file():
        raise FileNotFoundError(relative)
    digest = hashlib.sha256(target.read_bytes()).hexdigest()
    if digest != manifest.get('files', {}).get(relative):
        raise ValueError('ARTIFACT_HASH_MISMATCH: ' + relative)
    return target


def load_demo(root, *, package=None, review_dir=None):
    root = Path(root)
    package = Path(package) if package is not None else root / PACKAGE
    selection = read_json(root / INTEGRATION / 'demo_selection.json')['cases']
    if tuple(c['case_id'] for c in selection) != DEMO_IDS:
        raise ValueError('PINNED_DEMO_SELECTION_REQUIRED')
    errors, summary, manifest = [], {}, {}
    try:
        manifest = read_json(package / 'artifact_manifest.json')
        summary = read_json(checked_file(package, manifest, 'demo_summary.json'))
    except (OSError, ValueError) as exc:
        errors.append(str(exc))
    reviews = []
    if review_dir is not None and Path(review_dir).is_dir():
        for path in sorted(Path(review_dir).glob('*.json')):
            try:
                value = read_json(path)
                if not isinstance(value, dict):
                    raise ValueError('REVIEW_OBJECT_REQUIRED')
                reviews.append(value)
            except (OSError, ValueError) as exc:
                errors.append('REVIEW_UNREADABLE: ' + path.name + ': ' + str(exc))
    cases = []
    indexed = {r['case_id']: r for r in summary.get('cases', [])}
    for selected in selection:
        case_id = selected['case_id']
        item = {'case_id':case_id, 'title':TITLES[case_id], 'question':selected['question'],
                'status':'missing', 'record':None, 'metrics':{}, 'view':{},
                'review_status':'pending', 'reviews':[], 'raw_assessment':None,
                'cost_usd':None, 'calls':None, 'source':None, 'case_path':None,
                'explanation':indexed.get(case_id, {}).get('explanation', ''), 'error':None}
        try:
            row = indexed.get(case_id)
            if row is None:
                raise FileNotFoundError('Saved case is missing: ' + case_id)
            source = checked_file(package, manifest, row['source_report'])
            candidates = [source.parent / name for name in
                          (f'E0_{case_id}.json', f'E3_{case_id}.json', 'case_record.json')]
            present = [p for p in candidates if p.is_file()]
            if len(present) != 1:
                raise ValueError('DUPLICATE_OR_MISSING_CASE_ARTIFACT')
            artifact = checked_file(package, manifest, present[0].relative_to(package).as_posix())
            report = load_records(source)
            if len(report['case_records']) != 1 or report['case_records'][0]['case_id'] != case_id:
                raise ValueError('CASE_IDENTITY_MISMATCH')
            record = report['case_records'][0]
            matching = [r for r in reviews if r.get('case_id') == case_id]
            accepted = matching if len(matching) == 1 and validate_review(matching[0], record) else []
            projection = build_pipeline_report([record], inventory_for('pipeline'), reviews=accepted,
                identities=record.get('identities', {}), journal={'events':report.get('cost_events', [])})
            projected = next(c for c in projection['cases'] if c['case_id'] == case_id)
            view = case_view(record, question=selected['question'], review=accepted[0] if accepted else None)
            raw_path = f'assessment_responses/{case_id}.json'
            raw = read_json(checked_file(package, manifest, raw_path)) if raw_path in manifest['files'] else None
            events = record.get('cost_events', [])
            costs = [e.get('cost_usd') for e in events]
            known = bool(events) and all(isinstance(c, (int, float)) for c in costs)
            item.update(status=projected['status'], record=record, metrics=projected['metrics'],
                view=view, reviews=matching, raw_assessment=raw,
                review_status='duplicate' if len(matching) > 1 else
                              'valid' if accepted else 'hash_or_identity_mismatch' if matching else 'pending',
                cost_usd=sum(costs) if known else None, calls=len(events), source=source,
                case_path=artifact, source_report=report, producer_sha=row['producer_sha'],
                source_run_id=row['source_run_id'])
        except FileNotFoundError as exc:
            item['error'] = str(exc)
        except (OSError, ValueError, KeyError, TypeError) as exc:
            item.update(status='integrity_failed', error=str(exc))
        cases.append(item)
    return {'cases':cases, 'summary':summary, 'manifest':manifest, 'errors':errors,
            'package':package, 'selection':selection}


def save_review(case, output_dir, *, analyst, decision, rationale, utc):
    if not analyst.strip() or not rationale.strip() or decision not in ('approved','rejected','escalated'):
        raise ValueError('HUMAN_FIELDS_REQUIRED')
    validate_review_utc(utc)
    if not case.get('record') or not case.get('case_path'):
        raise ValueError('CASE_RECEIPT_REQUIRED')
    if decision == 'approved' and not case['metrics'].get('technical_workflow'):
        raise ValueError('TECHNICAL_APPROVAL_FORBIDDEN')
    digest = hashlib.sha256(case['case_path'].read_bytes()).hexdigest()
    if digest != case['record'].get('case_receipt_sha256'):
        raise ValueError('CASE_CHANGED_BEFORE_REVIEW')
    output_dir = Path(output_dir)
    for path in output_dir.glob('*.json'):
        value = read_json(path)
        if not isinstance(value, dict):
            raise ValueError('REVIEW_OBJECT_REQUIRED')
        if value.get('case_id') == case['case_id']:
            raise ValueError('DUPLICATE_REVIEW_FORBIDDEN')
    receipt = {'scope':'actual_human_review', 'case_id':case['case_id'],
               'case_receipt_sha256':digest, 'analyst':analyst.strip(), 'decision':decision,
               'rationale':rationale.strip(), 'utc':utc}
    if not validate_review(receipt, case['record']):
        raise ValueError('REVIEW_VALIDATION_FAILED')
    output_dir.mkdir(parents=True, exist_ok=True)
    target = output_dir / (case['case_id'] + '.json')
    with target.open('x', encoding='utf-8', newline='\n') as out:
        json.dump(receipt, out, ensure_ascii=False, indent=2)
    return target


def load_routing(root):
    root = Path(root)
    source = root / R1_SOURCE
    if not source.exists():
        return {'source':source, 'cases':[], 'report':{}, 'error':'R1 artifact missing'}
    report = read_json(source)
    cases = []
    for result in report.get('case_results', []):
        path = root / 'evaluation/tool_calling/benchmarks/dev' / (result['case_id'] + '.json')
        cases.append({'case_id':result['case_id'], 'result':result,
                      'benchmark':read_json(path) if path.is_file() else None})
    return {'source':source, 'report':report, 'cases':cases}


def load_soc(root):
    root = Path(root)
    source = root / SOC_SOURCE
    receipt = root / 'results/evaluation_v1/soc_traces_v1/demo_execution_receipt.json'
    return {'source':source, 'trace':read_json(source) if source.is_file() else None,
            'receipt':read_json(receipt) if receipt.is_file() else None}
