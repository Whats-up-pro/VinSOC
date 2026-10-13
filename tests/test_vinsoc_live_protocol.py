import importlib
import importlib.util
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
AVG = 'ctu_cross_bce6d3679ade4cd6'


def module():
    assert importlib.util.find_spec('scripts.vinsoc_live_protocol'), 'Live request protocol missing'
    return importlib.import_module('scripts.vinsoc_live_protocol')


def request(**changes):
    m = module()
    case = next(c for c in m.catalog('demo') if c['case_id'] == AVG)
    value = m.create_request(scope='demo', case_id=AVG, question=case['question'],
                             head_sha='a'*40, ci_run_id=123, live_consent=True)
    value.update(changes)
    return value


def test_request_preserves_question_and_binds_fresh_window():
    m = module()
    value = request()
    assert m.validate_request(value)['case_id'] == AVG
    assert value['execution_id'].startswith('liveui-')
    assert value['limit_usd'] == 3.0
    assert len(m.catalog('pipeline')) == 32
    assert len(m.catalog('calibration')) == 24
    assert len(m.catalog('evaluation')) == 96


@pytest.mark.parametrize('change', [{'question':'changed'}, {'case_id':'unknown'},
                                  {'limit_usd':30.0}, {'head_sha':'master'},
                                  {'execution_id':'../escape'}])
def test_bad_request_is_rejected_before_dispatch(change):
    with pytest.raises(ValueError):
        module().validate_request(request(**change))


def test_live_requires_explicit_consent():
    with pytest.raises(ValueError, match='LIVE_CONSENT_REQUIRED'):
        module().validate_request(request(live_consent=False), mode='live')


def test_reconciliation_keeps_real_base_cost():
    m = module()
    state = m.reconcile_allocation([])
    assert state['known_usd'] == pytest.approx(.0815592)
    assert state['remaining_usd'] == pytest.approx(2.9184408)
    assert state['cost_unknown'] is False


def test_open_claim_blocks_new_paid_run():
    with pytest.raises(ValueError, match='ALLOCATION_EXPOSURE_UNKNOWN'):
        module().reconcile_allocation([{'phase':'begin','execution_id':'liveui-'+'b'*24}])


def test_known_end_receipt_reconciles_from_actual_saved_demo_cost():
    m = module()
    execution = 'liveui-'+'b'*24
    entries = [{'phase':'begin','execution_id':execution,'request_sha256':'a'*64,'prior_cost_usd':.0815592},
               {'phase':'end','execution_id':execution,'request_sha256':'a'*64,'cost_unknown':False,
                'current_run_cost_usd':.00807805,'attempted':8,'received':8,'report_sha256':'c'*64}]
    result = m.reconcile_allocation(entries)
    assert result['known_usd'] == pytest.approx(.08963725)
    entries[-1]['cost_unknown'] = True
    with pytest.raises(ValueError,match='ALLOCATION_EXPOSURE_UNKNOWN'):
        m.reconcile_allocation(entries)
