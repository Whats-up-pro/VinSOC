"""Standalone offline viewer: fixed 32-case inventory and four pinned demo IDs."""
import argparse
import hashlib
import html
import json
from pathlib import Path

from evaluation.finalization.query_pipeline_reporting import build_pipeline_report
from evaluation.finalization.query_view import case_view
from scripts.run_vinsoc_query_acceptance import ROOT, inventory_for

DEMO_IDS = ('ctu_cross_708b66575657429a', 'ctu_cross_66b8e92a76c3359b',
            'ctu_cross_3f659571f998adb0', 'ctu_cross_bce6d3679ade4cd6')


def escaped_json(value):
    return html.escape(json.dumps(value, ensure_ascii=False, indent=2))


def load_records(source):
    source = Path(source)
    if not source.is_file():
        return {'scope':'pipeline','status':'missing','case_records':[]}
    report = json.loads(source.read_text(encoding='utf-8'))
    records = report.get('case_records', [])
    ids = {r['case_id'] for r in records}
    # Interrupted cases remain in their durable checkpoints, even before report aggregation.
    for row in inventory_for('pipeline'):
        if row['case_id'] in ids:
            continue
        paths = [source.parent/(condition+'_'+row['case_id']+'.json') for condition in ('E0','E3')]
        present = [p for p in paths if p.is_file()]
        if len(present) > 1:
            raise ValueError('DUPLICATE_PIPELINE_CHECKPOINT')
        if present:
            value = json.loads(present[0].read_text(encoding='utf-8'))
            if value.get('case_id') != row['case_id'] or value.get('status') != 'partial':
                raise ValueError('UNBOUND_PIPELINE_CHECKPOINT')
            records.append(value)
    report['case_records'] = records
    for record in records:
        artifact = source.parent/(record.get('condition','')+'_'+record['case_id']+'.json')
        if artifact.is_file():
            bound = json.loads(artifact.read_text(encoding='utf-8'))
            if bound != {k:v for k,v in record.items() if k != 'case_receipt_sha256'}:
                raise ValueError('CASE_ARTIFACT_REPORT_MISMATCH')
            record['case_receipt_sha256'] = hashlib.sha256(artifact.read_bytes()).hexdigest()
    return report


def render_report(source, output, *, review_paths=(), demo_selection=None):
    report = load_records(source)
    inventory = inventory_for('pipeline')
    canonical = json.loads((ROOT/'results/evaluation_v1/text2sql_integration_v1/demo_selection.json').read_text())
    selection = canonical if demo_selection is None else (demo_selection if isinstance(demo_selection,dict)
                  else json.loads(Path(demo_selection).read_text(encoding='utf-8')))
    if selection != canonical or tuple(r['case_id'] for r in selection['cases']) != DEMO_IDS:
        raise ValueError('PINNED_DEMO_SELECTION_REQUIRED')
    questions = {r['case_id']:r['question'] for r in inventory}
    if any(r['question'] != questions[r['case_id']] for r in selection['cases']):
        raise ValueError('DEMO_QUESTION_IDENTITY_MISMATCH')
    reviews = [json.loads(Path(p).read_text(encoding='utf-8')) for p in review_paths]
    records = report.get('case_records', [])
    indexed = {r['case_id']:r for r in records}
    for record in records:
        if (record.get('metadata', {}).get('orchestration_mode') != 'query_evidence_driven'
                and record.get('status') != 'partial'):
            raise ValueError('REAL_QUERY_CASE_RECEIPT_REQUIRED')
    identities = report.get('identities', records[0].get('identities', {}) if records else {})
    metrics = build_pipeline_report(records, inventory, reviews=reviews, identities=identities,
                                    journal={'events': report.get('cost_events', [])})
    review_map = {r['case_id']:r for r in reviews}
    statuses = {r['case_id']:r['status'] for r in metrics['cases']}
    page = '<!doctype html><html lang="vi"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width"><title>VinSOC — pipeline artifacts</title>'
    page += '<style>body{font:16px system-ui;max-width:1200px;margin:32px auto;padding:0 20px;color:#173c58}table{width:100%;border-collapse:collapse}th,td{padding:10px;border-bottom:1px solid #ddd;text-align:left}pre{white-space:pre-wrap;overflow-wrap:anywhere;background:#f3f5f7;padding:16px}summary{cursor:pointer;padding:12px}a{color:#173c58}</style></head><body>'
    page += '<h1>VinSOC — xem artifacts pipeline ngoại tuyến</h1><p>Trang chỉ đọc artifacts đã lưu, không gọi API. Các stage chưa có hiện missing; người duyệt nhập quyết định qua CLI.</p>'
    page += '<h2>Bốn demo ID cố định</h2><ul>'
    for demo in selection['cases']:
        page += '<li><a href="#'+html.escape(demo['case_id'])+'">'+html.escape(demo['case_id'])+'</a> — '+html.escape(statuses[demo['case_id']])+'<p>'+html.escape(demo['question'])+'</p></li>'
    page += '</ul><h2>Toàn bộ 32 câu CTU</h2><table><thead><tr><th>Case</th><th>Câu hỏi gốc</th><th>Trạng thái</th></tr></thead><tbody>'
    for row in inventory:
        key = row['case_id']
        page += '<tr data-case-id="'+html.escape(key)+'"><td><a href="#'+html.escape(key)+'">'+html.escape(key)+'</a></td><td>'+html.escape(row['question'])+'</td><td>'+html.escape(statuses[key])+'</td></tr>'
    summary = {k:report.get(k) for k in ('scope','status','failure_category','planned','completed','attempted','received','client_created','known_usd','cost_unknown','pending_exposure_usd')}
    page += '</tbody></table><h2>Trạng thái lượt đã lưu</h2><pre>'+escaped_json(summary)+'</pre>'
    page += '<h2>Coverage, technical checks, human review và chi phí</h2><pre>'+escaped_json(metrics)+'</pre>'
    for row in inventory:
        key = row['case_id']
        page += '<details id="'+html.escape(key)+'"><summary>'+html.escape(key)+' — '+html.escape(statuses[key])+'</summary>'
        record = indexed.get(key)
        view = case_view(record, question=row['question'], review=review_map.get(key)) if record else {'original_question':row['question'], 'record':'missing'}
        for stage, value in view.items():
            page += '<h3>'+html.escape(stage)+'</h3><pre>'+('missing' if value is None else escaped_json(value))+'</pre>'
        page += '</details>'
    page += '</body></html>'
    with Path(output).open('x', encoding='utf-8') as out:
        out.write(page)
    return {'planned':32, 'cases':len(records), 'missing':32-len(records),
            'demo_ids':list(DEMO_IDS), 'api_calls':0, 'status':metrics['status']}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source', type=Path)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--review', type=Path, action='append', default=[])
    parser.add_argument('--demo-selection', type=Path)
    args = parser.parse_args(argv)
    print(json.dumps(render_report(args.source,args.output,review_paths=args.review,demo_selection=args.demo_selection)))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
