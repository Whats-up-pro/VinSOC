"""Mentor presentation of authentic saved API runs; viewing never calls a model."""
from __future__ import annotations

import json
import math
import sys
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import streamlit as st

BASE_DIR = Path(__file__).resolve().parents[1]
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from evaluation.finalization.query_pipeline_reporting import validate_review  # noqa: E402
from scripts.vinsoc_demo_data import (  # noqa: E402
    INTEGRATION,
    PACKAGE,
    STATUS_LABELS,
    TITLES,
    load_demo,
    load_routing,
    load_soc,
    read_json,
    save_review,
)

REVIEW_DIR = BASE_DIR / '.vinsoc/mentor-reviews'
PAGES = ('Tổng quan', 'Luồng query', 'R1 chọn công cụ', 'SOC thiếu bằng chứng',
         'Chi phí & nghiệm thu', 'Hồ sơ & chạy mới', 'Chạy pipeline thật')
STAGES = ('Câu hỏi gốc', 'Model chọn công cụ', 'Schema & giá trị thực', 'SQL của model',
          'Kết quả DB', 'Bằng chứng & nguồn', 'Assessment & kiểm chứng', 'Người duyệt')
NOTES = (
    'Câu hỏi gắn với case ID đã chọn. Xác định dữ liệu và phép tính cần tìm trước khi đọc kết quả.',
    'Model gọi network_query bằng native tool call. Đây là response API đã lưu, kèm arguments và ID thật.',
    'R2 tra schema và giá trị trong DB. Trajectory cho biết model đã tìm bảng, cột và giá trị nào.',
    'SQL do model tạo. Với COUNT, xem candidate trước để giải thích vì sao UNION ALL không giải bài toán giao hai tập.',
    'Worker chạy SQL trên DB gốc. Kiểu cột, số hàng và trạng thái truncated đi cùng kết quả. SQL chạy được vẫn có thể trả sai.',
    'Evidence có ID, nguồn và hash. Assessment phải dẫn về những evidence này để người duyệt kiểm lại.',
    'Tách SQL đúng, facts, provenance và nhận định. TCP hoặc 459 chưa chứng minh có tấn công; diễn giải cần analyst.',
    'Người thật tự nhập identity, quyết định, lý do và UTC. Chỉ case đạt kỹ thuật mới được chấp thuận.',
)
CASE_GOALS = {
    'ctu_cross_708b66575657429a':'Đếm IP đích chung của hai scenario sau hai mốc thời gian riêng.',
    'ctu_cross_66b8e92a76c3359b':'Tìm UDP destination ở S5 nhưng không có ở S7, bỏ trùng.',
    'ctu_cross_3f659571f998adb0':'Đếm hai byte fields NULL cho từng protocol, giữ cả nhóm có count 0.',
    'ctu_cross_bce6d3679ade4cd6':'So sánh AVG từng protocol với AVG của toàn scenario 7.',
}


def fingerprint(*folders):
    values = []
    for folder in folders:
        folder = Path(folder)
        paths = [folder] if folder.is_file() else sorted(folder.rglob('*.json'))
        for path in paths:
            stat = path.stat()
            values.append((str(path), stat.st_mtime_ns, stat.st_size))
    return tuple(values)


@st.cache_data(ttl=60, max_entries=4, show_spinner=False)
def cached_demo(version):
    return load_demo(BASE_DIR, review_dir=REVIEW_DIR)


@st.cache_data(ttl=60, max_entries=4, show_spinner=False)
def cached_routing(version):
    return load_routing(BASE_DIR)


def navigate(page, case_id=None):
    st.session_state.demo_page = page
    if case_id is not None:
        st.session_state.demo_case = case_id
        reset_case_state()


def reset_case_state():
    st.session_state.demo_stage = 0
    for key in ('review_analyst', 'review_decision', 'review_rationale', 'review_utc'):
        st.session_state.pop(key, None)


def change_stage(delta):
    st.session_state.demo_stage = max(0, min(7, st.session_state.demo_stage + delta))


def status(case):
    value = case['status']
    color = 'green' if value == 'approved' else 'blue' if value == 'awaiting_human' else 'orange' if value in ('incomplete','missing','escalated') else 'red'
    st.badge(STATUS_LABELS.get(value, value), color=color)


def money(value):
    return 'Chưa xác định' if value is None else f'${value:.8f}'


def displayed_run_cost(control):
    value = control.get('current_run_cost_usd')
    if (value is None and control.get('attempted') == control.get('received') == 0
            and control.get('client_created') is False and control.get('cost_unknown') is False):
        return 0.0
    return value


def live_failure_notice(control):
    category = control.get('failure_category')
    if not category:
        return None
    before_model = (control.get('attempted') == control.get('received') == 0
                    and control.get('client_created') is False)
    prefix = 'Lượt chạy bị chặn trước model' if before_model else 'Lượt chạy dừng với lỗi'
    return f'{prefix}: {category}'


def download(path, label, key):
    if path and Path(path).is_file():
        st.download_button(label, Path(path).read_bytes(), file_name=Path(path).name,
                           mime='application/json' if str(path).endswith('.json') else 'text/plain',
                           key=key, icon=':material/download:')


def gate_table(case):
    labels = {'routing':'Routing', 'runtime':'DB / runtime', 'integrated_ex':'SQL đúng (EX)',
              'provenance':'Nguồn & liên kết', 'factual_verification':'Facts theo kết quả',
              'technical_workflow':'Luồng kỹ thuật', 'human_review_coverage':'Có review hợp lệ',
              'human_approved_completion':'Người duyệt chấp thuận'}
    st.dataframe([{'Gate':labels[k], 'Trạng thái':'Đạt' if v is True else
                  'Chưa chấm' if v is None else 'Chưa đạt'} for k,v in case['metrics'].items()],
                 hide_index=True, alt='Các gate độc lập của case đang chọn')


def overview(data):
    st.title('Demo VinSOC từ câu hỏi đến bằng chứng')
    st.caption('Bốn query đã gọi API thật, các nhánh routing R1 và một case SOC thiếu dữ liệu.')
    cases, summary = data['cases'], data['summary']
    with st.container(horizontal=True):
        st.metric('Query có record', f"{sum(c['record'] is not None for c in cases)}/4", border=True)
        st.metric('Đạt kỹ thuật', f"{sum(c['metrics'].get('technical_workflow') is True for c in cases)}/4", border=True)
        st.metric('Response ở lượt mới', summary.get('new_run_received', 'Chưa có'), border=True)
        st.metric('Chi phí lượt mới', money(summary.get('new_run_cost_usd')), border=True)
    st.info('Bắt đầu với AVG → TCP để trình bày luồng mới. COUNT → 459 giải thích giao tập; NULL và UDP là hai edge case thật.')
    for pair in (cases[:2], cases[2:]):
        for col, case in zip(st.columns(2), pair):
            with col.container(border=True):
                st.subheader(case['title'])
                status(case)
                st.text(CASE_GOALS[case['case_id']])
                with st.expander('Câu hỏi và giải thích đầy đủ'):
                    st.text(case['question'])
                    st.caption(case['explanation'] or case.get('error') or 'Chưa có giải thích từ receipt.')
                st.button('Trình bày case', key='open_' + case['case_id'], width='stretch',
                          on_click=navigate, args=('Luồng query', case['case_id']), icon=':material/play_arrow:')
    st.subheader('Lộ trình trình bày 15–20 phút')
    st.markdown('1. **R1:** network, CTI, endpoint, nhiều tool và no-tool.\n'
                '2. **AVG:** đi tám bước, đọc SQL, TCP, evidence và assessment.\n'
                '3. **Edge cases:** NULL sai cách đếm; UDP vượt giới hạn payload.\n'
                '4. **SOC:** no_match khác unavailable; chưa đủ kết luận host sạch.\n'
                '5. **Kết thúc:** chi phí, gate đã kiểm và phần còn mở.')
    st.caption('Coverage demo 4 case. Calibration 0/48, evaluation 0/192 và pipeline chính thức 32 câu chưa chạy. Các producer giữ riêng.')


def typed_result(case):
    result = case['view'].get('typed_result')
    if result is None:
        st.warning('Bước DB chưa có artifact; không tạo kết quả thay thế.')
        return
    rows, columns = result.get('rows') or [], result.get('columns') or []
    st.caption(f"{result.get('row_count', len(rows)):,} hàng · truncated={result.get('truncated')} · full rows giữ trong JSON gốc")
    if not rows:
        st.info('DB trả 0 hàng. Đối chiếu yêu cầu giữ các nhóm có count bằng 0.')
        return
    page_count = max(1, math.ceil(len(rows) / 50))
    page = int(st.number_input('Trang kết quả (50 hàng/trang)', min_value=1, max_value=page_count,
                               value=1, step=1, key='rows_' + case['case_id'])) if page_count > 1 else 1
    names = [c.get('name', str(i)) if isinstance(c, dict) else c[0] if isinstance(c, (list,tuple)) else str(c)
             for i,c in enumerate(columns)]
    st.dataframe(pd.DataFrame(rows[(page-1)*50:page*50], columns=names or None),
                 hide_index=True, alt='Trang kết quả typed của SQL đã chạy thật')
    st.caption(f'Trang {page}/{page_count}. Phân trang màn hình không sửa kết quả hoặc scorer.')
    with st.expander('Kiểu cột và hash kết quả'):
        st.json({'columns':columns, 'result_sha256':result.get('result_sha256')})


def evidence_view(case):
    evidence = case['view'].get('evidence') or []
    if not evidence:
        st.warning('Chưa có evidence cho bước này.')
        return
    st.dataframe([{'ID':e.get('evidence_id'), 'Loại':e.get('type'), 'Nguồn':e.get('source_tool'),
                   'Class':e.get('evidence_class'), 'Parent':e.get('linked_from')} for e in evidence],
                 hide_index=True, alt='Evidence IDs và liên kết nguồn của query')
    selected = st.selectbox('Mở evidence', range(len(evidence)),
                            format_func=lambda i:str(evidence[i].get('evidence_id')), key='evidence_' + case['case_id'])
    ev = evidence[selected]
    st.json({k:v for k,v in ev.items() if k != 'data'}, expanded=False)
    st.json(ev.get('data'), expanded=False)


def assessment_view(case):
    assessment = case['view'].get('assessment')
    if assessment:
        st.subheader('Assessment được pipeline chấp nhận')
        st.text(assessment.get('assessment', str(assessment)) if isinstance(assessment,dict) else assessment)
        if isinstance(assessment, dict):
            st.caption(f"Risk {assessment.get('risk_level','UNKNOWN')} · confidence {assessment.get('confidence','UNKNOWN')}")
            st.json({'observations':assessment.get('observations'), 'evidence_ids':assessment.get('evidence_ids'),
                     'limitations':assessment.get('limitations')}, expanded=False)
    else:
        st.warning('Chưa có assessment hợp lệ. Giữ partial hoặc response bị từ chối.')
    if case['raw_assessment']:
        with st.expander('Response assessment nguyên gốc, kể cả response bị từ chối'):
            st.json(case['raw_assessment'])
    gate_table(case)
    st.json({'verification':case['view'].get('verification'), 'integrated_ex':case['view'].get('integrated_ex')}, expanded=False)
    st.caption('Independent replay kiểm kết quả và nguồn. Ngữ nghĩa phần diễn giải cần người thật review.')


def human_review(case, review_dir=None):
    st.subheader('Quyết định của người duyệt')
    if case['review_status'] == 'valid':
        st.success('Review liên kết đúng hash của case gốc.')
        st.json(case['reviews'][0])
        return
    if case['review_status'] != 'pending':
        st.error('Review duplicate hoặc không khớp hash/identity. Chưa tính chấp thuận.')
        st.json(case['reviews'])
        return
    st.caption('Identity do người nhập tự khai báo. Rationale là lý do quyết định dựa trên SQL, kết quả và bằng chứng.')
    if not case['metrics'].get('technical_workflow'):
        st.warning('Case chưa đạt kỹ thuật: chỉ có thể từ chối hoặc chuyển điều tra thêm.')
    st.caption('UTC hiện tại để đối chiếu: ' + datetime.now(timezone.utc).isoformat(timespec='seconds'))
    with st.form('human_review_' + case['case_id']):
        analyst = st.text_input('Identity / tên người duyệt', key='review_analyst')
        choices = ('approved','rejected','escalated') if case['metrics'].get('technical_workflow') else ('rejected','escalated')
        decision = st.selectbox('Quyết định', choices, index=None, placeholder='Tự chọn quyết định', key='review_decision')
        rationale = st.text_area('Rationale / lý do quyết định', key='review_rationale')
        utc = st.text_input('UTC thực tế (ISO 8601, kết thúc bằng Z hoặc +00:00)', key='review_utc')
        submit = st.form_submit_button('Lưu quyết định của tôi', type='primary', icon=':material/save:')
    if submit:
        try:
            save_review(case, review_dir or REVIEW_DIR, analyst=analyst, decision=decision, rationale=rationale, utc=utc)
        except (OSError, ValueError) as exc:
            st.error(str(exc))
        else:
            st.rerun()
    uploaded = st.file_uploader('Đối chiếu review JSON có sẵn', type=['json'], key='review_upload_' + case['case_id'])
    if uploaded:
        try:
            receipt = json.loads(uploaded.getvalue())
            valid = validate_review(receipt, case['record'])
            st.success('Hash/identity khớp. File chỉ được xem, chưa nhập vào ledger.') if valid else st.error('Review hash/identity mismatch; không tính chấp thuận.')
            st.json(receipt)
        except (ValueError, TypeError, AttributeError) as exc:
            st.error('Review không hợp lệ: ' + str(exc))


def query_flow(data):
    st.title('Một query, tám bước có bằng chứng')
    cases = {c['case_id']:c for c in data['cases']}
    case_id = st.selectbox('Chọn query demo', list(cases), index=3, key='demo_case',
                           on_change=reset_case_state,
                           format_func=lambda c:cases[c]['title'] + ' · ' + STATUS_LABELS.get(cases[c]['status'],cases[c]['status']))
    case = cases[case_id]
    status(case)
    st.text(case['question'])
    stage = st.selectbox('Bước đang trình bày', range(8), key='demo_stage', format_func=lambda i:f'{i+1}. {STAGES[i]}')
    with st.container(horizontal=True):
        st.button('Bước trước', on_click=change_stage, args=(-1,), disabled=stage == 0, icon=':material/arrow_back:')
        st.button('Bước tiếp', on_click=change_stage, args=(1,), disabled=stage == 7, type='primary', icon=':material/arrow_forward:')
        download(case['case_path'], 'Case JSON gốc', 'case_download')
    with st.container(border=True):
        st.caption('GIẢI THÍCH CHO MENTOR')
        st.text(NOTES[stage])
        if case['explanation']:
            st.caption(case['explanation'])
    if not case['record']:
        st.error(case['error'] or 'Case missing. Không có prediction thay thế.')
        return
    generation = case['record'].get('generation', {})
    if stage == 0:
        st.subheader('Yêu cầu giữ nguyên')
        st.text(case['question'])
        st.code(case_id, language=None)
    elif stage == 1:
        st.json(case['view'].get('native_tool_call'))
        st.caption('Routing dùng API thật; schema/value tools truy cập dữ liệu.')
    elif stage == 2:
        st.subheader('Trajectory đã lưu')
        st.json(generation.get('trajectory'), expanded=False)
        with st.expander('Linked schema và responses R2 nguyên gốc'):
            st.json({'linked_schema':generation.get('linked_schema'), 'responses':generation.get('responses')})
    elif stage == 3:
        st.code(case['view'].get('sql') or 'Chưa có SQL cuối', language='sql')
        with st.expander('Candidate / response đã lưu trước parse'):
            st.json(generation.get('responses'))
    elif stage == 4:
        typed_result(case)
    elif stage == 5:
        evidence_view(case)
    elif stage == 6:
        assessment_view(case)
    else:
        human_review(case)
    st.caption('Producer ' + case['producer_sha'])
    st.link_button('Workflow của lượt này', 'https://github.com/Whats-up-pro/VinSOC/actions/runs/' + str(case['source_run_id']), icon=':material/open_in_new:')


def routing_page():
    st.title('R1: model chọn công cụ nào?')
    data = cached_routing(fingerprint(BASE_DIR / 'results/evaluation_v1/r1'))
    cases = {c['case_id']:c for c in data['cases']}
    if not cases:
        st.warning(data.get('error', 'Chưa có R1 records.'))
        return
    succeeded = sum(c['result'].get('trajectory_success') is True for c in cases.values())
    with st.container(horizontal=True):
        st.metric('Trajectory đạt ở dev', f'{succeeded}/{len(cases)}', border=True)
        st.metric('Model', data['report']['config']['model'], border=True)
    st.caption('Records chứng minh quyết định routing, chưa chứng minh tất cả tool cùng thực thi trong incident. Holdout cần nghiệm thu riêng.')
    st.dataframe([{'Ví dụ':label, 'Case':case_id} for label,case_id in
        (('Network','case_001'),('CTI','case_004'),('Endpoint','case_003'),('Ba công cụ','case_005'),
         ('CTI + endpoint','case_007'),('No-tool','case_022'),('Routing sai thật','case_002'))],
        hide_index=True, alt='Các nhánh routing chính để demo')
    selected = st.selectbox('Chọn case R1 (đủ 24 case)', list(cases), key='r1_case',
        format_func=lambda c:c + ' · ' + data['report'].get('case_metadata',{}).get(c,{}).get('category',''))
    case, benchmark = cases[selected], cases[selected]['benchmark']
    if benchmark is None:
        st.warning('Thiếu câu hỏi/expected calls gốc; không tự dựng benchmark.')
    else:
        st.text(benchmark['request'])
        left,right = st.columns(2)
        with left:
            st.subheader('Theo benchmark')
            st.json(benchmark.get('expected_calls'))
        with right:
            st.subheader('Model thực sự chọn')
            st.json(case['result']['predicted_calls'])
        if benchmark.get('notes'):
            st.caption(benchmark['notes'])
    st.success('Trajectory khớp benchmark.') if case['result'].get('trajectory_success') else st.error('Routing chưa khớp; giữ lỗi thật.')
    with st.expander('Scorer, breakdown và nguồn producer'):
        st.json({'case_result':case['result'], 'aggregate':data['report'].get('aggregate'),
                 'producer':data['report'].get('evaluator_commit_sha'), 'provenance':data['report'].get('provenance')})
    download(data['source'], 'R1 results gốc', 'r1_download')


def soc_page():
    st.title('SOC: biết dừng khi thiếu bằng chứng')
    data = load_soc(BASE_DIR)
    trace, receipt = data['trace'], data['receipt']
    if not trace or not receipt:
        st.warning('Thiếu SOC trace hoặc receipt; không tạo incident thay thế.')
        return
    st.badge('Dữ liệu synthetic · model API thật', color='orange')
    st.caption(f"{receipt['responses_received']} responses · {money(receipt['new_inference_cost_usd'])} · {receipt['acceptance_scope']}")
    st.text(str(trace['input'].get('alert', trace['input'])))
    for output in trace['model_outputs']:
        for call in output.get('message', {}).get('tool_calls') or []:
            with st.expander(call['function']['name'] + ' · native tool call', expanded=True):
                st.json(call)
    st.subheader('Kết quả công cụ')
    for tool in trace['case']['metadata'].get('delivered_tools', []):
        with st.container(border=True):
            st.markdown('**' + tool['tool'] + '**')
            st.json(tool['result'])
    st.info('no_match: đã tra nhưng không có event khớp. unavailable: nguồn context không có. Cả hai chưa đủ để kết luận host sạch.')
    st.subheader('Assessment thật: insufficient_evidence')
    st.text(trace['case']['final_assessment'])
    with st.expander('Evidence, report, limitations và response IDs'):
        st.json({'evidence':trace['case']['evidence'], 'report':trace['report'], 'model_outputs':trace['model_outputs']})
    st.warning('Người duyệt pending. Một case integration không thay điểm toàn suite.')
    st.link_button('Workflow SOC gốc', f"https://github.com/Whats-up-pro/VinSOC/actions/runs/{receipt['workflow_run_id']}")
    download(data['source'], 'SOC JSON gốc', 'soc_download')


def cost_page(data):
    st.title('Chi phí thực và trạng thái nghiệm thu')
    summary = data['summary']
    with st.container(horizontal=True):
        st.metric('Lượt mới', money(summary.get('new_run_cost_usd')), border=True)
        st.metric('Query-demo tích lũy', money(summary.get('query_demo_allocation_cumulative_cost_usd')), border=True)
        st.metric('Allocation còn lại', money(summary.get('remaining_allocation_cap_usd')), border=True)
    st.caption('Allocation query-demo $3. R1 và SOC có scope riêng; số dư này không phải số dư tài khoản nhà cung cấp.')
    events = [e for c in data['cases'] if c['record'] for e in c['record'].get('cost_events', [])]
    selected = st.selectbox('Lọc chi phí theo case', ['Tất cả'] + [c['case_id'] for c in data['cases']], key='cost_case')
    filtered = [e for e in events if selected == 'Tất cả' or e['case_id'] == selected]
    st.caption(f'{len(filtered)} events hiển thị. COUNT thuộc run trước; 23 events mới thuộc ba case còn lại.')
    st.dataframe([{'Case':e['case_id'], 'Condition':e.get('condition'), 'Role':e.get('role'),
                   'Model':e.get('actual_model'), 'USD':e.get('cost_usd'),
                   'Input tokens':e.get('usage',{}).get('input_tokens'),
                   'Output tokens':e.get('usage',{}).get('output_tokens'),
                   'Cached tokens':e.get('usage',{}).get('cached_tokens'),
                   'Latency ms':e['latency_seconds'] * 1000 if e.get('latency_seconds') is not None else None,
                   'Request ID':e.get('request_id'),
                   'Response ID':e.get('response_id')} for e in filtered],
                 hide_index=True, alt='Usage, chi phí và request response IDs thật')
    st.subheader('Các thước đo độc lập')
    st.dataframe([{'Case':c['title'], 'Trạng thái':STATUS_LABELS.get(c['status'],c['status']),
                   'SQL EX':c['metrics'].get('integrated_ex'), 'Facts':c['metrics'].get('factual_verification'),
                   'Provenance':c['metrics'].get('provenance'), 'Kỹ thuật':c['metrics'].get('technical_workflow'),
                   'Human approved':c['metrics'].get('human_approved_completion')} for c in data['cases']],
                 hide_index=True, alt='Gate kỹ thuật và human review riêng của bốn demo')
    st.warning('Gate mở: UDP payload; NULL zero-group semantics / assessment; human review. Calibration 0/48, evaluation 0/192, pipeline32 NOT_RUN.')
    validation = BASE_DIR / INTEGRATION / 'original_data_20261010/real_data_validation.json'
    if validation.is_file():
        receipt = read_json(validation)
        with st.expander('R2: DB gốc và 120 gold queries đã kiểm ngoại tuyến'):
            st.json({k:receipt.get(k) for k in ('status','original_databases_verified',
                      'base_gold_replayed','replayed_by_database','source_archive_sha256','external_model_calls')})
            st.caption('Đây là kiểm DB và gold SQL; không tính thành điểm model. Model calibration/evaluation vẫn chưa chạy.')
    observation = BASE_DIR / INTEGRATION / 'offline_release_20261010/r2_independent_kernel_observation.json'
    if observation.is_file():
        with st.expander('Giới hạn worker: bằng chứng kernel độc lập'):
            st.json(read_json(observation))
    st.link_button('CI của gói demo trên Python 3.11/3.12', 'https://github.com/Whats-up-pro/VinSOC/actions/runs/38381443972')
    st.caption('CI artifacts bbc66f1: full 1398 passed, 7 skipped; required offline 102/0 skip; real-data 13/0 skip mỗi Python. CI này không tự nghiệm thu các thay đổi sau đó.')


def artifacts_page(data):
    st.title('Hồ sơ đối chiếu và lượt chạy mới')
    st.caption('Viewer đọc lượt đã gọi API thật. Mỗi case giữ producer riêng; xem/download là ngoại tuyến.')
    for case in data['cases']:
        with st.expander(case['title'] + ' · ' + case['case_id']):
            if case['record']:
                st.code(str(case['case_path'].relative_to(BASE_DIR)), language=None)
                st.code(case['record'].get('case_receipt_sha256'), language=None)
                download(case['source'], 'Report gốc', 'report_' + case['case_id'])
                download(case['case_path'], 'Case gốc', 'raw_' + case['case_id'])
                st.link_button('Workflow nguồn', 'https://github.com/Whats-up-pro/VinSOC/actions/runs/' + str(case['source_run_id']))
            else:
                st.warning(case['error'] or 'Missing')
    for name,label in (('README.md','Runbook mentor'), ('demo_summary.json','Demo summary'),
                       ('artifact_manifest.json','Hashes và nguồn artifacts'), ('source_artifacts.json','Receipts Actions')):
        download(data['package'] / name, label, 'artifact_' + name)
    st.subheader('Trạng thái lượt gọi mới')
    st.info('Scope demo đã dùng giữ consumed. Một lượt mới cần execution scope, ngân sách, selection lock và preflight riêng. Windows viewer xem được trace Linux đã chạy thật.')
    st.markdown('CLI query nhận **case ID và đúng câu hỏi gốc**, đi qua public `investigate_query`.\n'
                'Preflight đạt trước khi tạo SDK client; SQL chạy trong worker cách ly.\n'
                'Viewer không cấp scope mới hoặc gọi model khi chuyển trang.')
    st.code('py -m cli.main query --help', language='powershell')
    st.caption('Chạy mới qua workflow có guard và CI đúng SHA; authorization của lượt consumed không được tái sử dụng.')


@st.cache_resource
def live_controller():
    from scripts.vinsoc_live_ui import LiveController
    return LiveController(BASE_DIR)


def reset_live_input():
    st.session_state.pop('live_question',None)
    st.session_state.pop('live_case',None)


@st.fragment(run_every='5s')
def live_monitor(execution_id, current_input):
    from scripts.vinsoc_live_ui import load_live_cases, local_identity
    controller = live_controller()
    state = controller.read(execution_id)
    if state['phase'] in ('preflight_submitted','preflight_running','live_submitted','live_running','dispatch_delivery_unknown'):
        try:
            state = controller.poll(execution_id)
        except (OSError,ValueError) as exc:
            st.warning('Chưa lấy được trạng thái: ' + str(exc))
    st.subheader('Lượt chạy mới: ' + execution_id)
    st.badge(state['phase'],color='blue' if state['phase'].endswith('running') else 'orange')
    workflow = state.get('workflow') or {}
    if workflow.get('url'):
        st.link_button('Mở job Linux đang chạy',workflow['url'],icon=':material/open_in_new:')
    steps = [{'Job':job['name'],'Bước':step['name'],'Trạng thái':step['status'],
              'Kết quả':step.get('conclusion')} for job in workflow.get('jobs',[]) for step in job.get('steps',[])]
    if steps:
        with st.expander('Tiến độ thật từ GitHub Actions',expanded=state['phase'].endswith('running')):
            st.dataframe(steps,hide_index=True,alt='Tiến độ thực của các bước runner Linux')
    events = state.get('events',[])
    if events:
        st.dataframe([{'Request':e['request_number'],'Phase':e['phase'],'Role':e['event'].get('role'),
                       'Response ID':e['event'].get('response_id'),'USD':e['event'].get('cost_usd')} for e in events],
                     hide_index=True,alt='Checkpoints của các request model thật trong lượt đang chạy')
    control = state.get('control') or {}
    if control:
        with st.container(horizontal=True):
            st.metric('Attempted / received',f"{control.get('attempted',0)} / {control.get('received',0)}",border=True)
            st.metric('Chi phí lượt này',money(displayed_run_cost(control)),border=True)
            st.metric('Allocation còn lại',money(control.get('remaining_cap_usd')),border=True)
        if control.get('gate_reasons'):
            st.error('Preflight bị chặn: ' + ', '.join(control['gate_reasons']))
        failure_notice = live_failure_notice(control)
        if failure_notice:
            st.error(failure_notice)
        st.caption(f"client_created={control.get('client_created')} · cost_unknown={control.get('cost_unknown')}")
    request = state['request']
    unchanged = current_input == (request['scope'],request['case_id'],request['question'])
    if state['phase'] == 'preflight_pass':
        st.success('Preflight Linux đạt; chưa gọi model. Kiểm cận tiền trước khi bắt đầu.')
        st.json({'cost_ceiling_usd':control.get('cost_ceiling_usd'),'role_caps':control.get('role_caps')},expanded=False)
        consent = st.checkbox('Tôi cho phép lượt API thật này trong allocation tích lũy $3',key='live_consent_'+execution_id)
        if not unchanged:
            st.warning('Input đã đổi sau preflight; cần tạo preflight mới cho input này.')
        if st.button('Chạy pipeline API thật',type='primary',disabled=not consent or not unchanged,
                     key='start_'+execution_id,icon=':material/play_arrow:'):
            try:
                identity = local_identity(BASE_DIR)
                controller.start_live(execution_id,consent=consent,current_sha=identity['head_sha'])
                st.rerun(scope='fragment')
            except (OSError,ValueError) as exc:
                st.error(str(exc))
    try:
        cases = load_live_cases(state)
    except (OSError,ValueError) as exc:
        st.error('Artifact của lượt mới chưa hợp lệ: ' + str(exc))
        cases = []
    if cases:
        st.subheader('Kết quả của chính lượt mới')
        selected = st.selectbox('Case / condition nhận được',range(len(cases)),
                               format_func=lambda i:cases[i]['case_id']+' / '+cases[i]['condition'],key='fresh_case_'+execution_id)
        case = cases[selected]
        status(case)
        st.text(case['view'].get('original_question') or case['question'])
        stage = st.selectbox('Bước pipeline thật',range(8),format_func=lambda i:f'{i+1}. {STAGES[i]}',key='fresh_stage_'+execution_id)
        st.caption(NOTES[stage])
        if stage == 0:
            st.text(case['question'])
        elif stage == 1:
            st.json(case['view'].get('native_tool_call'))
        elif stage == 2:
            st.json(case['record'].get('generation',{}).get('trajectory'),expanded=False)
        elif stage == 3:
            st.code(case['view'].get('sql') or 'Chưa có final SQL',language='sql')
        elif stage == 4:
            typed_result(case)
        elif stage == 5:
            evidence_view(case)
        elif stage == 6:
            assessment_view(case)
        else:
            human_review(case,review_dir=controller.directory(execution_id)/'reviews')
        download(case['case_path'],'Case mới nguyên gốc','fresh_download_'+execution_id)
        with st.expander('Usage, request/response IDs và chi phí thật'):
            st.json(case['record'].get('cost_events'))
    elif state['mode'] == 'live':
        st.caption('Lượt này chưa có case artifact để đọc. Không dùng kết quả cũ thay thế.')
    if state.get('error'):
        st.error(state['error'])


def live_page():
    from scripts.vinsoc_live_protocol import catalog, create_request
    from scripts.vinsoc_live_ui import local_identity
    st.title('Chạy pipeline thật từ giao diện')
    st.caption('Nhập câu hỏi gốc, kiểm preflight, cho phép chạy mới rồi theo dõi model → SQL worker → evidence → assessment → review.')
    labels = {'demo':'Một query end-to-end (4 demo đã pin)','pipeline':'Toàn bộ pipeline CTU32',
              'calibration':'Calibration 24 cases × E0/E3','evaluation':'Evaluation 96 cases × E0/E3'}
    scope = st.selectbox('Phạm vi chạy',list(labels),format_func=labels.get,key='live_scope',on_change=reset_live_input)
    inventory = catalog(scope)
    if scope == 'demo':
        case_id = st.selectbox('Case ID', [r['case_id'] for r in inventory], index=3,
                               format_func=lambda c:TITLES.get(c,c),key='live_case',on_change=lambda:st.session_state.pop('live_question',None))
        original = next(r['question'] for r in inventory if r['case_id'] == case_id)
        question = st.text_area('Câu hỏi điều tra (đúng câu hỏi gốc của case)',value=original,key='live_question',height=110)
        st.caption('Bạn có thể nhập/dán câu hỏi. Câu hỏi khác case gốc sẽ bị chặn trước SDK.')
    else:
        case_id,question = None,None
        st.dataframe([{'Case ID':r['case_id'],'Database':r['database_id'],'Câu hỏi gốc':r['question']} for r in inventory],
                     hide_index=True,alt='Toàn bộ catalog case chuẩn của phạm vi đã chọn')
        if scope == 'calibration':
            st.caption('Calibration tạo 48 records thật cho E0/E3 và selection lock; cận cả lượt phải nằm trong allocation.')
        else:
            st.warning('Selection lock cần 48 calibration records thật; cận cả lượt phải nằm trong allocation. Chưa có artifacts thì giữ NOT_RUN.')
    if st.button('Chạy preflight Linux (0 model calls)',key='live_preflight',icon=':material/fact_check:'):
        try:
            identity = local_identity(BASE_DIR)
            request = create_request(scope=scope,case_id=case_id,question=question,**identity)
            live_controller().submit_preflight(request)
            st.session_state.live_session_id = request['execution_id']
            st.session_state.live_history = request['execution_id']
        except (OSError,ValueError) as exc:
            st.error(str(exc))
    sessions = live_controller().storage
    existing = sorted([p.name for p in sessions.glob('liveui-*') if (p/'state.json').is_file()],reverse=True)
    if existing:
        current = st.session_state.get('live_session_id')
        selected = st.selectbox('Mở / tiếp tục một lượt đã gửi',existing,
                               index=existing.index(current) if current in existing else 0,key='live_history')
        live_monitor(selected,(scope,case_id,question))


def main():
    st.set_page_config(page_title='VinSOC | Mentor demo', page_icon=':material/security:',
                       layout='wide', initial_sidebar_state='expanded')
    st.session_state.setdefault('demo_page', 'Tổng quan')
    st.session_state.setdefault('demo_stage', 0)
    with st.sidebar:
        st.title('VinSOC')
        st.caption('ĐIỀU TRA · BẰNG CHỨNG · NGƯỜI DUYỆT')
        page = st.radio('Điều hướng demo', PAGES, key='demo_page', label_visibility='collapsed')
        st.badge('Xem trace đã gọi API thật', icon=':material/verified:', color='blue')
        st.caption('Chuyển trang không gọi API, không tốn thêm tiền.')
    data = cached_demo(fingerprint(BASE_DIR / PACKAGE, REVIEW_DIR, BASE_DIR / INTEGRATION / 'demo_selection.json'))
    for error in data['errors']:
        st.warning('Artifact chưa đọc được: ' + error)
    if page == 'Tổng quan':
        overview(data)
    elif page == 'Luồng query':
        query_flow(data)
    elif page == 'R1 chọn công cụ':
        routing_page()
    elif page == 'SOC thiếu bằng chứng':
        soc_page()
    elif page == 'Chi phí & nghiệm thu':
        cost_page(data)
    elif page == 'Chạy pipeline thật':
        live_page()
    else:
        artifacts_page(data)


if __name__ == '__main__':
    main()
