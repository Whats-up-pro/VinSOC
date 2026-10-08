"""Offline metrics and complete rendering from immutable authentic receipts."""
from collections import Counter,defaultdict
from datetime import datetime,timezone
import html
import json
from pathlib import Path
import re
from vinsoc_data.soc_corpus import digest,REVISION,SOURCE_MANIFEST
from agent.soc_investigation_policy import validate_report,validate_schema
from evaluation.soc_traces_v1.release import MODEL
from evaluation.soc_traces_v1.accounting import atomic_json


def verify_receipt(receipt):
    body={k:v for k,v in receipt.items() if k!='receipt_sha256'}
    if digest(body)!=receipt.get('receipt_sha256'):raise ValueError('SOC_RECEIPT_HASH_INVALID')
    if receipt.get('status') not in ('not_run','blocked','partial','failed','completed'):raise ValueError('SOC_RECEIPT_STATUS_INVALID')
    if receipt.get('condition') not in ('S0','S1'):raise ValueError('SOC_RECEIPT_CONDITION_INVALID')
    return receipt


def technical_valid(receipt):
    try:
        verify_receipt(receipt)
        if receipt['status']!='completed' or receipt.get('cost_unknown'):return False
        case=receipt['case'];meta=case['metadata'];report=receipt['report'];provider=receipt['provider']
        if report!=meta['soc_report'] or case['final_assessment']!=report['summary'] or meta['technical_status']!='completed' or meta['errors'] or meta['terminal']:return False
        if not validate_schema(case)[0]:return False
        if meta['scenario_id']!=receipt['scenario_id'] or meta['condition']!=receipt['condition'] or meta['source_revision']!=REVISION or meta['data_origin']!='synthetic':return False
        if len(meta['corpus_sha256'])!=64 or len(receipt['release_sha256'])!=64 or len(receipt['implementation_sha'])!=40:return False
        evidence={e['evidence_id']:e for e in case['evidence']}
        if len(evidence)!=len(case['evidence']):return False
        validate_report(report,delivered_ids=set(evidence))
        if any(e['provenance'].get('scenario_id')!=receipt['scenario_id'] or e['provenance'].get('dataset_revision')!=REVISION or e['provenance'].get('file_sha256') not in SOURCE_MANIFEST['files'].values() for e in evidence.values()):return False
        calls=provider['calls'];outputs=receipt['model_outputs']
        if provider['provider']!='soc_openai_official' or provider['model']!=MODEL or not calls or len(calls)!=len(outputs) or len(calls)>(1 if receipt['condition']=='S0' else 6):return False
        if any(c['actual_model']!=MODEL or not c['request_id'] or c['estimated_cost_usd']<0 or not c.get('usage') for c in calls):return False
        if {c['completion_id'] for c in calls}!={o['id'] for o in outputs} or len({o['id'] for o in outputs})!=len(outputs):return False
        if json.loads(outputs[-1]['message']['content'])!=report:return False
        traces=case['tool_trace'];delivered=meta['delivered_tools']
        if len(traces)>5 or (receipt['condition']=='S0' and traces):return False
        if [t['call_id'] for t in traces]!=[d['native_call_id'] for d in delivered]:return False
        seen_input={eid for eid,e in evidence.items() if e['source_tool']=='soc_input'}
        seen_tool={row['source_record_id'] for d in delivered for row in d['result']['rows']}
        if set(evidence)!=seen_input|seen_tool or len(seen_input)!=1:return False
        if any(d['utf8_bytes']>20000 or len(d['result']['rows'])>20 for d in delivered):return False
        return True
    except (ValueError,KeyError,TypeError,IndexError):return False


def score_record(receipt,gold):
    valid=technical_valid(receipt);report=receipt.get('report') if valid else None
    prediction=report['verdict'] if report else None
    evidence={e['evidence_id']:e for e in receipt.get('case',{}).get('evidence',[])}
    candidate=report
    if candidate is None:
        try:candidate=json.loads(receipt['model_outputs'][-1]['message']['content'])
        except (ValueError,KeyError,TypeError,IndexError):candidate=None
    refs=candidate.get('evidence_ids',[]) if isinstance(candidate,dict) else []
    refs=refs if isinstance(refs,list) and all(isinstance(r,str) for r in refs) else []
    inputs=[r for r in refs if evidence.get(r,{}).get('source_tool')=='soc_input']
    tools=[r for r in refs if r in evidence and evidence[r].get('source_tool')!='soc_input']
    unknown=[r for r in refs if r not in evidence]
    return {'scenario_id':receipt.get('scenario_id'),'condition':receipt.get('condition'),'status':receipt.get('status','not_run'),
      'technical_valid':valid,'prediction':prediction,'correct':bool(valid and prediction==gold['label']),
      'abstained':prediction=='insufficient_evidence','label':gold['label'],'family':gold['family'],
      'citation_references':len(refs),'valid_citations':len(refs)-len(unknown),'unknown_citations':len(unknown),'citation_validity':(len(refs)-len(unknown))/len(refs) if refs else None,'input_citations':len(inputs),'tool_citations':len(tools),'input_citation_validity':1.0 if inputs else None,
      'tool_citation_validity':None if receipt.get('condition')=='S0' or not tools and not unknown else len(tools)/(len(tools)+len(unknown)),
      'delivered_records':sum(e.get('source_tool')!='soc_input' for e in evidence.values()),'prose_semantics_machine_verified':False}


def validate_review(review, *, receipt):
    verify_receipt(receipt)
    try:
        if review['receipt_sha256']!=receipt['receipt_sha256'] or review['scenario_id']!=receipt['scenario_id'] or review['condition']!=receipt['condition']:raise ValueError()
        if not review['analyst'].strip() or not review['rationale'].strip() or review['decision'] not in ('approved','rejected','escalated','more_evidence_requested'):raise ValueError()
        stamp=datetime.fromisoformat(review['reviewed_at'].replace('Z','+00:00'))
        if stamp.tzinfo is None or stamp>datetime.now(timezone.utc):raise ValueError()
        if review['decision']=='approved' and not technical_valid(receipt):raise ValueError()
    except (KeyError,TypeError,ValueError):raise ValueError('SOC_HUMAN_REVIEW_INVALID_OR_UNBOUND') from None
    return {'valid':True,'decision':review['decision'],'prose_semantics_machine_verified':False}


def build_suite_report(inventory,records,reviews):
    cases=inventory['cases']
    if len(cases)!=64 or len({c['scenario_id'] for c in cases})!=64:raise ValueError('SOC_SUITE_DENOMINATOR_64_REQUIRED')
    lookup={};review_lookup={};review_errors=[]
    for record in records:
        key=(record.get('scenario_id'),record.get('condition'))
        if key in lookup or key[0] not in {c['scenario_id'] for c in cases} or key[1] not in ('S0','S1'):raise ValueError('SOC_DUPLICATE_OR_FOREIGN_RECORD')
        lookup[key]=record
    for review in reviews:
        key=(review.get('scenario_id'),review.get('condition'))
        try:
            if key in review_lookup:raise ValueError()
            validate_review(review,receipt=lookup[key]);review_lookup[key]=review
        except (KeyError,ValueError):review_errors.append('SOC_INVALID_REVIEW:'+str(key))
    conditions={};scored={}
    for condition in ('S0','S1'):
        scores=[score_record(lookup.get((c['scenario_id'],condition),{'scenario_id':c['scenario_id'],'condition':condition,'status':'not_run'}),c) for c in cases]
        scored[condition]={s['scenario_id']:s for s in scores};nvalid=sum(s['technical_valid'] for s in scores);correct=sum(s['correct'] for s in scores)
        statuses=Counter(s['status'] for s in scores);active=any(s['status'] not in ('not_run','blocked') for s in scores);confusion={label:{pred:sum(s['label']==label and s['prediction']==pred for s in scores) for pred in ('malicious','benign','insufficient_evidence')} for label in ('malicious','benign')}
        classes={}
        for label in ('malicious','benign'):
            tp=confusion[label][label];planned=sum(s['label']==label for s in scores);predicted=sum(s['prediction']==label for s in scores)
            precision=tp/predicted if predicted else 0;recall=tp/planned
            classes[label]={'planned':planned,'tp':tp,'fp':predicted-tp,'fn':planned-tp,'precision':precision if active else None,'recall':recall if active else None,'f1':(2*precision*recall/(precision+recall) if precision+recall else 0) if active else None}
        families={}
        for family in sorted({s['family'] for s in scores}):
            subset=[s for s in scores if s['family']==family];families[family]={'planned':len(subset),'correct':sum(s['correct'] for s in subset),'valid':sum(s['technical_valid'] for s in subset),'agreement':sum(s['correct'] for s in subset)/len(subset) if active else None}
        human=Counter(review_lookup[(c['scenario_id'],condition)]['decision'] if (c['scenario_id'],condition) in review_lookup else 'awaiting_human' for c in cases)
        consumed=[lookup[(c['scenario_id'],condition)] for c in cases if (c['scenario_id'],condition) in lookup]
        calls=[call for r in consumed for call in r.get('provider',{}).get('calls',[])]
        unknown=any(r.get('cost_unknown') for r in consumed)
        conditions[condition]={'planned':64,'correct':correct,'agreement':correct/64 if active else None,'technical_valid':nvalid,'completion_kind':'report_completion' if condition=='S0' else 'investigation_completion',
          'not_run':statuses.get('not_run',0),'statuses':dict(statuses),'abstained':sum(s['abstained'] for s in scores),'classes':classes,'confusion':confusion,'families':families,
          'macro_family_agreement':sum(f['agreement'] for f in families.values())/len(families) if active else None,'reviews':dict(human),'reviewed':64-human['awaiting_human'],
          'approved_completion':sum(s['technical_valid'] and review_lookup.get((s['scenario_id'],condition),{}).get('decision')=='approved' for s in scores),
          'input_citations':sum(s['input_citations'] for s in scores),'tool_citations':sum(s['tool_citations'] for s in scores),'citation_references':sum(s['citation_references'] for s in scores),'valid_citations':sum(s['valid_citations'] for s in scores),'case_citation_validity_over_planned':sum(s['technical_valid'] for s in scores)/64 if active else None,'tool_citation_validity':None if condition=='S0' or not sum(s['tool_citations']+s['unknown_citations'] for s in scores) else sum(s['tool_citations'] for s in scores)/sum(s['tool_citations']+s['unknown_citations'] for s in scores),
          'calls':len(calls),'tokens':sum(c.get('usage',{}).get('total_tokens',0) for c in calls),'model_latency_ms':sum(c.get('latency_ms',0) for c in calls),
          'estimated_cost_usd':None if unknown else sum(c.get('estimated_cost_usd',0) for c in calls),'cost_unknown':unknown,'scores':scores}
    paired=Counter()
    for c in cases:
        s0=scored['S0'][c['scenario_id']];s1=scored['S1'][c['scenario_id']]
        key='incomplete' if not s0['technical_valid'] or not s1['technical_valid'] else ('tie' if s0['correct']==s1['correct'] else ('S1_win' if s1['correct'] else 'S1_loss'))
        paired[key]+=1
    missing=paired['incomplete'];any_calls=any(c['calls'] or any(status not in ('not_run','blocked') for status in c['statuses']) for c in conditions.values())
    return {'status':'not_run' if not any_calls else ('complete' if not missing else 'incomplete'),'data_origin':'synthetic','inventory_sha256':inventory['inventory_sha256'],
      'conditions':conditions,'paired':{'planned':64,**{k:paired[k] for k in ('S1_win','S1_loss','tie','incomplete')},'agreement_delta':(conditions['S1']['correct']-conditions['S0']['correct'])/64 if not missing else None},
      'review_errors':review_errors,'prose_semantics_machine_verified':False,'limitations':['Public synthetic labels are agreement targets, not expert ground truth.','Templates/families overlap between source splits; possible pretraining exposure.','No causal or general SOC accuracy claim from this 64-case comparison.']}


def render_case(receipt_path,output_dir, *, review_path=None):
    receipt=verify_receipt(json.loads(Path(receipt_path).read_text()));review=json.loads(Path(review_path).read_text()) if review_path else None
    if review:validate_review(review,receipt=receipt)
    scenario=receipt['scenario_id'];condition=receipt['condition']
    if not re.fullmatch(r'[A-Za-z0-9_-]+',scenario):raise ValueError('SOC_RENDER_SCOPE_INVALID')
    name=scenario+'_'+condition;output=Path(output_dir);output.mkdir(parents=True,exist_ok=True)
    esc=lambda value:html.escape(str(value),quote=True)
    pretty=lambda value:json.dumps(value,ensure_ascii=False,indent=2)
    report=receipt.get('report');case=receipt.get('case',{});meta=case.get('metadata',{})
    if report and (report!=meta.get('soc_report') or receipt.get('status')!='completed' or not technical_valid(receipt)):raise ValueError('SOC_RENDER_REPORT_INCONSISTENT')
    status=receipt['status'];human=review['decision'] if review else 'awaiting_human'
    parts=['<!doctype html><html lang="vi"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">',
      '<meta http-equiv="Content-Security-Policy" content="default-src \'none\'; style-src \'unsafe-inline\'">',
      '<title>'+esc(name)+'</title><style>body{font:16px/1.6 system-ui;margin:32px auto;padding:0 24px;max-width:1100px;color:#172b3a}h1,h2{color:#114d70}pre{white-space:pre-wrap;overflow-wrap:anywhere;background:#f0f4f7;padding:16px}table{border-collapse:collapse;width:100%;margin:16px 0}td,th{border:1px solid #cad6dd;padding:8px;text-align:left;vertical-align:top;overflow-wrap:anywhere}.status{padding:16px;background:#e6f1f7}p,li{overflow-wrap:anywhere}</style>',
      '<h1>VinSOC — Điều tra SOC</h1><div class="status">'+esc(scenario)+' / '+esc(condition)+' · Technical: '+esc(status)+' · Review: '+esc(human)+'</div>',
      '<p>Nguồn dữ liệu: tổng hợp. Kiểm schema và citation không xác minh ngữ nghĩa báo cáo.</p><h2>Đầu vào</h2><pre>'+esc(pretty(receipt.get('input')))+'</pre>']
    def table(heads,rows):
        return '<table><thead><tr>'+''.join('<th>'+esc(h)+'</th>' for h in heads)+'</tr></thead><tbody>'+''.join('<tr>'+''.join('<td>'+esc(pretty(c) if isinstance(c,(dict,list)) else c)+'</td>' for c in row)+'</tr>' for row in rows)+'</tbody></table>'
    if report:parts+=_format_report(report)
    else:parts+=['<h2>Chưa có báo cáo model</h2><p>'+esc(status)+'</p>']
    if case.get('tool_trace'):parts+=['<h2>Diễn biến công cụ</h2>',table(['Native call ID','Tool','UTC','Arguments','Evidence IDs','Duration ms','Error'],[[t['call_id'],t['tool'],t['timestamp'],t['arguments'],t['evidence_ids'],t.get('duration_ms'),t.get('error')] for t in case['tool_trace']])]
    if case.get('evidence'):parts+=['<h2>Bằng chứng và nguồn</h2>',table(['Evidence ID','Loại','Observed at','Nội dung đầy đủ','Provenance'],[[e['evidence_id'],e['type'],e.get('observed_at'),e['data'],e['provenance']] for e in case['evidence']])]
    for title,value in [('Kết quả tools đã delivered',meta.get('delivered_tools')),('Model outputs',receipt.get('model_outputs')),('Model, tokens và chi phí',receipt.get('provider')),('Lỗi / trạng thái',meta.get('errors') or receipt.get('error')),('Human review',review),('Danh tính và metadata',meta)]:
        if value:parts+=['<h2>'+esc(title)+'</h2><pre>'+esc(pretty(value))+'</pre>']
    parts+=['<p>Receipt SHA-256: '+esc(receipt['receipt_sha256'])+'</p></html>']
    h=output/(name+'.html');h.write_text('\n'.join(parts),encoding='utf-8')
    j=output/(name+'.json');atomic_json(j,receipt)
    # Variable fence prevents a source backtick run from escaping the code block.
    text=pretty(receipt);longest=max((len(x) for x in re.findall(r'`+',text)),default=0);fence='`'*max(3,longest+1)
    md=output/(name+'.md');md.write_text('# VinSOC — '+html.escape(name)+'\n\nTechnical: '+status+'; review: '+human+'; source: synthetic.\n\n'+('Báo cáo model đầy đủ và bằng chứng' if report else 'Chưa có báo cáo model')+'\n\n'+fence+'json\n'+text+'\n'+fence+'\n',encoding='utf-8')
    return {'html':str(h.resolve()),'json':str(j.resolve()),'markdown':str(md.resolve()),'status':status,'review_status':human}

def _format_report(report):
    esc=lambda value:html.escape(str(value),quote=True)
    pretty=lambda value:json.dumps(value,ensure_ascii=False,indent=2)
    def table(heads,rows):
        return '<table><thead><tr>'+''.join('<th>'+esc(h)+'</th>' for h in heads)+'</tr></thead><tbody>'+''.join('<tr>'+''.join('<td>'+esc(pretty(c) if isinstance(c,(dict,list)) else c)+'</td>' for c in row)+'</tr>' for row in rows)+'</tbody></table>'
    return ['<h2>Tóm tắt và kết luận model</h2><p>'+esc(report['summary'])+'</p>',table(['Verdict','Risk','Lý do risk','Confidence','Lý do confidence'],[[report['verdict'],report['risk_level'],report['risk_rationale'],report['confidence'],report['confidence_rationale']]]),
          '<h2>Giả thuyết</h2>',table(['Mô tả','Ủng hộ','Mâu thuẫn','Confidence'],[[h['description'],h['supporting_evidence'],h['contradicting_evidence'],h['confidence']] for h in report['hypotheses']]),
          '<h2>Findings</h2>',table(['Loại','Nhận định','Evidence IDs'],[[f['kind'],f['claim'],f['evidence_ids']] for f in report['findings']]),
          '<h2>Giới hạn</h2><ul>'+''.join('<li>'+esc(x)+'</li>' for x in report['limitations'])+'</ul>',
          '<h2>Hành động đề xuất</h2>',table(['Đề xuất','Lý do','Evidence IDs'],[[a['action'],a['rationale'],a['evidence_ids']] for a in report['recommended_actions']]),
          '<h2>Toàn bộ báo cáo JSON</h2><pre>'+esc(pretty(report))+'</pre>']


def render_suite(summary, *, demo_ids,output_dir):
    """Index retains all planned cases and all four preselected demos, including missing."""
    if len(set(demo_ids))!=4:raise ValueError('SOC_FOUR_DEMO_IDS_REQUIRED')
    output=Path(output_dir);output.mkdir(parents=True,exist_ok=True)
    lookup={condition:{s['scenario_id']:s for s in summary['conditions'][condition]['scores']} for condition in ('S0','S1')}
    esc=lambda v:html.escape(str(v),quote=True)
    rows=[];demos=[]
    for scenario in lookup['S0']:
        def cell(condition):
            s=lookup[condition][scenario];filename=scenario+'_'+condition+'.html'
            label=s['status']+' / '+str(s['prediction'] or 'chưa có final')
            return '<a href="'+esc(filename)+'">'+esc(label)+'</a>' if (output/filename).is_file() else esc(label)
        row='<tr><td>'+esc(scenario)+'</td><td>'+cell('S0')+'</td><td>'+cell('S1')+'</td></tr>'
        rows.append(row)
        if scenario in demo_ids:demos.append(row)
    if len(demos)!=4:raise ValueError('SOC_DEMO_OUTSIDE_INVENTORY')
    table=lambda data:'<table><tr><th>Scenario</th><th>S0</th><th>S1</th></tr>'+''.join(data)+'</table>'
    text='<!doctype html><html lang="vi"><meta charset="utf-8"><title>VinSOC SOC experiment</title><style>body{font:16px/1.6 system-ui;max-width:1100px;margin:32px auto;padding:24px}td,th{padding:8px;border:1px solid #bccbd6}table{border-collapse:collapse;width:100%}pre{white-space:pre-wrap;overflow-wrap:anywhere}</style><h1>VinSOC — Thực nghiệm SOC</h1><p>Trạng thái: '+esc(summary['status'])+'. Nguồn tổng hợp; chưa có output thì không có accuracy mới.</p><h2>Bốn demo đã chọn</h2>'+table(demos)+'<h2>Toàn bộ64 cặp</h2>'+table(rows)+'<h2>Phép đo và giới hạn</h2><pre>'+esc(json.dumps(summary,ensure_ascii=False,indent=2))+'</pre></html>'
    (output/'index.html').write_text(text,encoding='utf-8')
    atomic_json(output/'suite_report.json',summary)
    (output/'suite_report.md').write_text('# VinSOC SOC\n\nSource: synthetic; status: '+summary['status']+'\n\n```json\n'+json.dumps(summary,ensure_ascii=False,indent=2)+'\n```\n',encoding='utf-8')
    return str((output/'index.html').resolve())
