import importlib
import importlib.util

import openai


def test_missing_inputs_cannot_create_sdk_client(tmp_path, monkeypatch):
    assert importlib.util.find_spec('scripts.run_query_live_ui_cloud'), 'Live UI cloud runner missing'
    m = importlib.import_module('scripts.run_query_live_ui_cloud')
    def forbidden(*args, **kwargs):
        raise AssertionError('Missing release must not create SDK client')
    monkeypatch.setattr(openai, 'OpenAI', forbidden)
    result = m.run('preflight', tmp_path/'out', {})
    assert result['status'] == 'blocked'
    assert result['attempted'] == result['received'] == 0
    assert result['client_created'] is False
