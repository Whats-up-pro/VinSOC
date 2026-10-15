"""The added split must never reach a provider through the legacy CLI."""
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[1]
SPLIT = ROOT / 'evaluation/tool_calling/benchmarks/generalization_v1'
MODEL = 'gpt-4.1-mini-2025-04-14'
SHA = 'a' * 40


def inputs():
    import json
    lock = json.loads((SPLIT / 'GENERALIZATION.lock').read_text())
    return dict(
        split_dir=SPLIT, lock_path=SPLIT / 'GENERALIZATION.lock',
        authorization={'scope': 'r1-generalization-v1', 'approved': True,
                       'authorized_by': 'Whats-up-pro', 'reference': 'explicit user instruction',
                       'model': MODEL, 'split_sha256': lock['split_sha256'],
                       'implementation_sha': SHA, 'maximum_requests': 120,
                       'maximum_output_tokens': 1000, 'limit_usd': '100',
                       'cost_ceiling_usd': '1', 'max_retries': 0},
        requested_model=MODEL, budget_limit_usd=Decimal('100'),
        git_identity={'commit_sha': SHA, 'branch': 'master', 'working_tree_clean': True,
                      'remote_master_sha': SHA, 'ci_sha': SHA, 'ci_success': True},
    )


def test_real_locked_split_passes_without_provider():
    from evaluation.tool_calling.generalization_run import validate_generalization_run_gate
    receipt = validate_generalization_run_gate(**inputs())
    assert receipt['passed'], receipt
    assert receipt['case_count'] == 120
    assert receipt['provider_created'] is False
    assert receipt['model_calls'] == 0


@pytest.mark.parametrize('target,key,value', [
    ('git_identity', 'branch', 'feature'),
    ('git_identity', 'working_tree_clean', False),
    ('git_identity', 'remote_master_sha', 'b' * 40),
    ('git_identity', 'ci_sha', 'b' * 40),
    ('git_identity', 'ci_success', False),
    ('authorization', 'approved', False),
    ('authorization', 'model', 'other-model'),
    ('authorization', 'split_sha256', 'b' * 64),
    ('authorization', 'implementation_sha', 'b' * 40),
    ('authorization', 'maximum_requests', 121),
    ('authorization', 'max_retries', 1),
    ('authorization', 'cost_ceiling_usd', '101'),
    ('authorization', 'cost_ceiling_usd', 'NaN'),
])
def test_run_gate_blocks_before_provider(target, key, value):
    from evaluation.tool_calling.generalization_run import validate_generalization_run_gate
    args = inputs()
    args[target][key] = value
    receipt = validate_generalization_run_gate(**args)
    assert not receipt['passed']
    assert receipt['provider_created'] is False
    assert receipt['model_calls'] == 0


def test_modified_or_missing_lock_is_blocked(tmp_path):
    from evaluation.tool_calling.generalization_run import validate_generalization_run_gate
    args = inputs()
    args['lock_path'] = tmp_path / 'missing.lock'
    assert not validate_generalization_run_gate(**args)['passed']


def test_official_cli_rejects_generalization_before_runner(monkeypatch):
    import evaluation.tool_calling.generalization_cli as cli
    import evaluation.tool_calling.decision_runner as runner
    def forbidden(*args, **kwargs):
        pytest.fail('provider/runner created before generalization gate')
    monkeypatch.setattr(runner, 'DecisionRunner', forbidden)
    monkeypatch.setattr(runner, 'create_provider', forbidden)
    args = SimpleNamespace(mode='decision', split='generalization_v1', cases=None,
                           authorization=None, budget_usd=None)
    with pytest.raises(ValueError, match='AUTHORIZATION'):
        cli.run_benchmark(args)


def test_cli_lists_real_120_cases(capsys):
    import evaluation.tool_calling.generalization_cli as cli
    cli.main(['list', 'generalization_v1'])
    assert '120' in capsys.readouterr().out


def test_historical_entrypoint_and_runner_remain_byte_identical():
    import subprocess
    for path in ['evaluation/tool_calling/__main__.py','evaluation/tool_calling/decision_runner.py']:
        assert (ROOT/path).read_bytes() == subprocess.check_output(['git','show','3573496a165876f36116b2716ca737d17091aaf7:'+path],cwd=ROOT)
