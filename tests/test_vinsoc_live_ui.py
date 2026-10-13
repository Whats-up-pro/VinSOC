import importlib
import importlib.util
from pathlib import Path

import pytest


def module():
    assert importlib.util.find_spec('scripts.vinsoc_live_ui'), 'Live UI controller missing'
    return importlib.import_module('scripts.vinsoc_live_ui')


class TransportFixture:
    """Only a dispatch boundary fixture; never a model prediction or live proof."""
    def __init__(self):
        self.calls = []
    def dispatch(self, request, mode):
        self.calls.append((request,mode))


def test_preflight_dispatch_is_durable_and_cannot_be_repeated(tmp_path):
    m = module()
    from scripts.vinsoc_live_protocol import catalog, create_request
    case = catalog('demo')[-1]
    request = create_request(scope='demo',case_id=case['case_id'],question=case['question'],
                             head_sha='a'*40,ci_run_id=123)
    transport = TransportFixture()
    controller = m.LiveController(Path.cwd(), storage=tmp_path, transport=transport)
    state = controller.submit_preflight(request)
    assert state['phase'] == 'preflight_submitted'
    assert controller.read(request['execution_id'])['request'] == request
    with pytest.raises(ValueError,match='DUPLICATE_DISPATCH_FORBIDDEN'):
        controller.submit_preflight(request)


def test_live_cannot_start_without_real_preflight(tmp_path):
    m = module()
    from scripts.vinsoc_live_protocol import catalog, create_request
    case = catalog('demo')[-1]
    request = create_request(scope='demo',case_id=case['case_id'],question=case['question'],
                             head_sha='a'*40,ci_run_id=123)
    controller = m.LiveController(Path.cwd(),storage=tmp_path,transport=TransportFixture())
    controller.submit_preflight(request)
    with pytest.raises(ValueError,match='PREFLIGHT_REQUIRED'):
        controller.start_live(request['execution_id'], consent=True, current_sha='a'*40)


def test_missing_new_run_never_loads_old_saved_example(tmp_path):
    m = module()
    state = {'phase':'live_running','download_dir':str(tmp_path)}
    assert m.load_live_cases(state) == []


def test_source_change_after_preflight_is_blocked_before_dispatch(tmp_path):
    m = module()
    from scripts.vinsoc_live_protocol import catalog, create_request
    case = catalog('demo')[-1]
    request = create_request(scope='demo',case_id=case['case_id'],question=case['question'],
                             head_sha='a'*40,ci_run_id=123)
    transport = TransportFixture()
    controller = m.LiveController(Path.cwd(),storage=tmp_path,transport=transport)
    state = controller.submit_preflight(request)
    # State-machine validation fixture, not a real preflight receipt or model record.
    state.update(phase='preflight_pass',control={'preflight_status':'preflight_pass'})
    controller.save(state)
    with pytest.raises(ValueError,match='SOURCE_CHANGED_AFTER_PREFLIGHT'):
        controller.start_live(request['execution_id'],consent=True,current_sha='b'*40)
    assert not (controller.directory(request['execution_id'])/'live.dispatch').exists()
