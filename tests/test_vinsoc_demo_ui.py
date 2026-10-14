"""Exercise mentor navigation without SDK clients or paid transmissions."""
from pathlib import Path

import openai
from streamlit.testing.v1 import AppTest

ROOT = Path(__file__).resolve().parents[1]


def app(monkeypatch):
    def forbidden_client(*args, **kwargs):
        raise AssertionError('Viewer must not create an API client')
    monkeypatch.setattr(openai, 'OpenAI', forbidden_client)
    monkeypatch.setenv('OPENAI_API_KEY', '')
    return AppTest.from_file(str(ROOT / 'scripts/vinsoc_demo_app.py'), default_timeout=20).run()


def test_viewer_opens_without_api_key_and_all_pages_are_usable(monkeypatch):
    at = app(monkeypatch)
    assert not at.exception
    assert len(at.radio) and at.radio(key='demo_page').options
    for page in at.radio(key='demo_page').options:
        at.radio(key='demo_page').set_value(page).run()
        assert not at.exception, page


def test_all_four_query_cases_expose_real_results_and_partial_state(monkeypatch):
    at = app(monkeypatch)
    at.radio(key='demo_page').set_value('Luồng query').run()
    for case_id in ('ctu_cross_708b66575657429a', 'ctu_cross_66b8e92a76c3359b',
                    'ctu_cross_3f659571f998adb0', 'ctu_cross_bce6d3679ade4cd6'):
        at.selectbox(key='demo_case').set_value(case_id).run()
        at.selectbox(key='demo_stage').set_value(4).run()
        assert not at.exception
    assert any('TCP' in str(df.value) for df in at.dataframe)


def test_review_form_has_no_default_identity_decision_or_utc(monkeypatch):
    at = app(monkeypatch)
    at.radio(key='demo_page').set_value('Luồng query').run()
    at.selectbox(key='demo_stage').set_value(7).run()
    assert not at.exception
    assert at.text_input(key='review_analyst').value == ''
    assert at.text_input(key='review_utc').value == ''
    assert at.selectbox(key='review_decision').value is None


def test_switching_case_resets_stage_and_review_inputs(monkeypatch):
    at = app(monkeypatch)
    at.radio(key='demo_page').set_value('Luồng query').run()
    at.selectbox(key='demo_stage').set_value(7).run()
    at.text_input(key='review_analyst').set_value('test-only, not a submitted review').run()
    at.selectbox(key='demo_case').set_value('ctu_cross_708b66575657429a').run()
    assert not at.exception
    assert at.selectbox(key='demo_stage').value == 0
    at.selectbox(key='demo_stage').set_value(7).run()
    assert at.text_input(key='review_analyst').value == ''


def test_query_stage_navigation_exposes_sql_evidence_and_actual_assessment(monkeypatch):
    at = app(monkeypatch)
    at.radio(key='demo_page').set_value('Luồng query').run()
    for stage in range(8):
        at.selectbox(key='demo_stage').set_value(stage).run()
        assert not at.exception
        if stage == 3:
            assert any('SELECT' in str(code.value) for code in at.code)
        if stage == 4:
            assert any('TCP' in str(frame.value) for frame in at.dataframe)
        if stage == 6:
            assert any('TCP' in text.value for text in at.text)


def test_cost_table_uses_actual_model_and_measured_latency(monkeypatch):
    at = app(monkeypatch)
    at.radio(key='demo_page').set_value('Chi phí & nghiệm thu').run()
    assert not at.exception
    costs = at.dataframe[0].value
    assert len(costs) == 30
    assert costs['Model'].notna().all()
    assert costs['Latency ms'].notna().all()
    assert (costs['Latency ms'] >= 0).all()


def test_live_page_has_separate_preflight_and_full_case_catalog(monkeypatch):
    at = app(monkeypatch)
    assert 'Chạy pipeline thật' in at.radio(key='demo_page').options
    at.radio(key='demo_page').set_value('Chạy pipeline thật').run()
    assert not at.exception
    assert at.text_area(key='live_question').value
    assert any('preflight' in b.label.lower() for b in at.button)
    at.selectbox(key='live_scope').set_value('pipeline').run()
    assert not at.exception
    assert any(len(frame.value) == 32 for frame in at.dataframe)


def test_blocked_live_run_exposes_safe_failure_reason_and_zero_cost():
    from scripts.vinsoc_demo_app import displayed_run_cost, live_failure_notice

    control = {
        'status': 'blocked',
        'failure_category': 'REMOTE_MASTER_CHANGED',
        'attempted': 0,
        'received': 0,
        'client_created': False,
        'cost_unknown': False,
    }
    assert live_failure_notice(control) == (
        'Lượt chạy bị chặn trước model: REMOTE_MASTER_CHANGED'
    )
    assert displayed_run_cost(control) == 0.0
    assert live_failure_notice({'status': 'preflight_pass'}) is None
    assert displayed_run_cost({'attempted': 1, 'received': 0}) is None
