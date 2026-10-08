"""Offline HTML from saved query receipts; never creates traces or calls APIs."""
import argparse
import html
import json
from pathlib import Path


def render_report(source, output):
    report = json.loads(Path(source).read_text())
    records = report.get('case_records', [])
    sections = []
    for record in records:
        if record.get('metadata', {}).get('orchestration_mode') != 'query_evidence_driven':
            raise ValueError('REAL_QUERY_CASE_RECEIPT_REQUIRED')
        title = html.escape(record['case_id'])
        sections.append('<details><summary>'+title+'</summary><pre>'+html.escape(
            json.dumps(record, ensure_ascii=False, indent=2))+'</pre></details>')
    title = 'VinSOC — lượt pipeline đã lưu' if records else 'VinSOC — chưa có lượt pipeline thật'
    page = '<!doctype html><html lang="vi"><meta charset="utf-8"><title>'+title+'</title>'
    page += '<style>body{font:16px system-ui;max-width:1100px;margin:40px auto;padding:0 20px}pre{white-space:pre-wrap;overflow-wrap:anywhere;background:#f3f5f7;padding:18px}summary{padding:16px;cursor:pointer}h1{color:#173c58}</style>'
    page += '<h1>'+title+'</h1><p>Đây là xem lại receipt đã lưu; mở trang không gọi API.</p>'
    page += '<pre>'+html.escape(json.dumps({k:report.get(k) for k in
        ('scope','status','planned','planned_records','completed','attempted','received','cost_unknown','known_usd')},ensure_ascii=False,indent=2))+'</pre>'
    page += ''.join(sections) if records else '<p>Không tạo SQL, dẫn chứng, nhận định hoặc quyết định giả để lấp dữ liệu thiếu.</p>'
    page += '</html>'
    with Path(output).open('x',encoding='utf-8') as out:
        out.write(page)
    return {'cases':len(records), 'api_calls':0}


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source',type=Path)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args(argv)
    print(json.dumps(render_report(args.source,args.output)))
    return 0


if __name__=='__main__':
    raise SystemExit(main())
