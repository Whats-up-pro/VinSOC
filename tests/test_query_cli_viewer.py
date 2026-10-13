"""CLI selection and viewer consume locked inventory and real existing receipts."""
import json
import hashlib
from pathlib import Path

import pytest

from scripts.run_vinsoc_query_acceptance import inventory_for


def test_exact_original_question_is_required_before_any_action():
    from scripts.run_vinsoc_query_acceptance import verify_selected_question
    row = inventory_for('pipeline')[0]
    assert verify_selected_question(row['case_id'], row['question']) == row
    with pytest.raises(ValueError, match='EXACT_ORIGINAL_QUESTION_REQUIRED'):
        verify_selected_question(row['case_id'], row['question']+' ')


def test_demo_inventory_is_one_fixed_selection_with_exact_original_question():
    from scripts.run_vinsoc_query_acceptance import verify_selected_question

    selection = json.loads(Path('results/evaluation_v1/text2sql_integration_v1/demo_selection.json').read_text())
    chosen = selection['cases'][0]
    row = verify_selected_question(chosen['case_id'], chosen['question'], require_demo=True)
    assert inventory_for('demo', case_id=chosen['case_id'], question=chosen['question']) == [row]
    with pytest.raises(ValueError, match='FIXED_DEMO_SELECTION_REQUIRED'):
        verify_selected_question(inventory_for('pipeline')[0]['case_id'],
                                 inventory_for('pipeline')[0]['question'], require_demo=True)
    with pytest.raises(ValueError, match='EXACT_ORIGINAL_QUESTION_REQUIRED'):
        inventory_for('demo', case_id=chosen['case_id'], question=chosen['question']+' ')


def test_demo_cli_passes_one_locked_case_to_preflight(monkeypatch, tmp_path):
    import scripts.run_vinsoc_query_acceptance as runner

    chosen = json.loads(Path('results/evaluation_v1/text2sql_integration_v1/demo_selection.json').read_text())['cases'][0]
    captured = {}
    def fake_preflight(scope, condition, private, *, selected_input=None):
        captured.update(scope=scope, condition=condition, selected_input=selected_input)
        return {'release': {'status': 'preflight_pass', 'planned': 1, 'attempted': 0,
                            'received': 0, 'client_created': False, 'gate_inputs': {}},
                'diagnostics': [], 'client_created': False, 'attempted': 0, 'received': 0}
    monkeypatch.setattr(runner, 'run_preflight', fake_preflight)
    output = tmp_path/'preflight.json'
    assert runner.main(['--scope','demo','--condition','E3','--preflight-only',
                        '--case-id',chosen['case_id'],'--question',chosen['question'],
                        '--output',str(output)]) == 0
    assert captured == {'scope':'demo', 'condition':'E3', 'selected_input':chosen}
    saved = json.loads(output.read_text())
    assert saved['release']['attempted'] == saved['release']['received'] == 0
    assert saved['release']['client_created'] is False


def test_live_entrypoint_accepts_remote_store_for_ephemeral_runner():
    import inspect
    from scripts.run_vinsoc_query_acceptance import run_live
    assert 'remote_store' in inspect.signature(run_live).parameters


def test_demo_with_no_final_sql_is_technical_incomplete():
    from scripts.run_vinsoc_query_acceptance import technical_status
    failed = {'generation':{'error_category':'TOOL_LIMIT','final_sql':None},
              'metadata':{'review_status':'blocked_invalid_technical',
                          'query_policy':{'validation':{'valid':False}}}}
    assert technical_status('demo',[failed]) == 'technical_incomplete'
    passed = {'generation':{'error_category':'OK','final_sql':'SELECT 1'},
              'metadata':{'review_status':'awaiting_human',
                          'query_policy':{'validation':{'valid':True}}}}
    assert technical_status('demo',[passed]) == 'technical_complete_awaiting_human'


def test_default_viewer_keeps_four_fixed_ids_and_32_missing_cases(tmp_path):
    from scripts.render_query_pipeline_report import render_report
    source = Path('results/evaluation_v1/text2sql_integration_v1/preflight_pipeline.json')
    output = tmp_path/'viewer.html'
    result = render_report(source, output)
    selection = json.loads(Path('results/evaluation_v1/text2sql_integration_v1/demo_selection.json').read_text())
    assert result['planned'] == 32
    assert result['cases'] == 0
    assert result['missing'] == 32
    assert result['api_calls'] == 0
    page = output.read_text(encoding='utf-8')
    for row in selection['cases']:
        assert row['case_id'] in page and row['question'] in page
    assert page.count('data-case-id=') == 32
    assert '<script' not in page


def test_saved_single_demo_case_file_binds_review_to_report(tmp_path):
    from scripts.render_query_pipeline_report import load_records, render_report
    source = Path('results/evaluation_v1/text2sql_integration_v1/single_demo_full_e2e_10_20261013')
    for name in ('runner_report.json', 'case_record.json'):
        (tmp_path/name).write_bytes((source/name).read_bytes())
    report = load_records(tmp_path/'runner_report.json')
    assert report['case_records'][0]['case_receipt_sha256'] == hashlib.sha256(
        (tmp_path/'case_record.json').read_bytes()).hexdigest()
    result = render_report(tmp_path/'runner_report.json', tmp_path/'view.html')
    assert (result['cases'], result['missing'], result['status'], result['api_calls']) == (1, 31, 'incomplete', 0)
    assert 'awaiting_human' in (tmp_path/'view.html').read_text(encoding='utf-8')


def test_saved_single_demo_mismatched_case_file_is_rejected(tmp_path):
    from scripts.render_query_pipeline_report import load_records
    source = Path('results/evaluation_v1/text2sql_integration_v1/single_demo_full_e2e_10_20261013')
    (tmp_path/'runner_report.json').write_bytes((source/'runner_report.json').read_bytes())
    case = json.loads((source/'case_record.json').read_text(encoding='utf-8'))
    case['final_assessment'] = 'tampered'
    (tmp_path/'case_record.json').write_text(json.dumps(case), encoding='utf-8')
    with pytest.raises(ValueError, match='CASE_ARTIFACT_REPORT_MISMATCH'):
        load_records(tmp_path/'runner_report.json')


def run_saved_review(monkeypatch, tmp_path, extra=(), *, decision='escalated', mutate=None):
    from scripts.review_vinsoc_query_case import main
    source = Path('results/evaluation_v1/text2sql_integration_v1/single_demo_full_e2e_10_20261013/case_record.json')
    case = tmp_path/'case.json'
    if mutate:
        record = json.loads(source.read_text(encoding='utf-8'))
        mutate(record)
        case.write_text(json.dumps(record), encoding='utf-8')
    else:
        case.write_bytes(source.read_bytes())
    answers = iter(['test-only analyst', decision, 'Test-only review receipt; never published.', '2026-10-13T00:00:00Z'])
    monkeypatch.setattr('builtins.input', lambda prompt: next(answers))
    output = tmp_path/'review.json'
    assert main([str(case), '--output', str(output), *extra]) == 0
    return json.loads(output.read_text(encoding='utf-8')), case


def test_review_default_shows_sql_once_and_preserves_bound_receipt(monkeypatch, tmp_path, capsys):
    receipt, case = run_saved_review(monkeypatch, tmp_path)
    preview = capsys.readouterr().out
    assert preview.count('SELECT COUNT(DISTINCT dst_ip)') == 1
    assert '459' in preview and 'Evidence:' in preview and 'factual=PASS' in preview
    assert 'provider_request_id' not in preview and 'snapshot_binary_sha256' not in preview
    assert '--verbose' in preview
    assert receipt['scope'] == 'actual_human_review'
    assert receipt['analyst'] == 'test-only analyst' and receipt['decision'] == 'escalated'
    assert receipt['case_receipt_sha256'] == hashlib.sha256(case.read_bytes()).hexdigest()


def test_review_verbose_retains_complete_saved_projection(monkeypatch, tmp_path, capsys):
    from evaluation.finalization.query_view import case_view
    _, case = run_saved_review(monkeypatch, tmp_path, ['--verbose'])
    preview = json.loads(capsys.readouterr().out)
    assert preview == case_view(json.loads(case.read_text(encoding='utf-8')))


def test_review_cannot_approve_fact_mismatch_even_when_saved_stage_flag_is_valid(monkeypatch, tmp_path):
    def mutate(record):
        record['metadata']['query_policy']['assessment']['observations'][0]['value'] = 460
    with pytest.raises(SystemExit) as raised:
        run_saved_review(monkeypatch, tmp_path, decision='approved', mutate=mutate)
    assert raised.value.code == 2
    assert not (tmp_path/'review.json').exists()


def test_review_missing_assessment_can_be_escalated_with_failed_facts(monkeypatch, tmp_path, capsys):
    def mutate(record):
        record['metadata']['query_policy']['assessment'] = None
    receipt, _ = run_saved_review(monkeypatch, tmp_path, mutate=mutate)
    assert receipt['decision'] == 'escalated'
    assert 'factual=FAIL' in capsys.readouterr().out


@pytest.mark.parametrize('mutation', ['execution_cell', 'execution_rehashed', 'lineage', 'execution_evidence_hash'])
def test_review_cannot_approve_execution_evidence_disagreement(monkeypatch, tmp_path, mutation):
    def mutate(record):
        execution = record['metadata']['query_execution']
        if mutation in ('execution_cell', 'execution_rehashed'):
            execution['rows'] = [[460]]
            if mutation == 'execution_rehashed':
                data = {k:execution[k] for k in ('columns', 'rows', 'truncated')}
                execution['result_sha256'] = hashlib.sha256(json.dumps(
                    data, sort_keys=True, ensure_ascii=False, separators=(',', ':')).encode()).hexdigest()
        elif mutation == 'lineage':
            next(e for e in record['evidence'] if e['type'] == 'query_result')['related_evidence_ids'] = []
        else:
            next(e for e in record['evidence'] if e['type'] == 'query_execution')['data']['result_sha256'] = 'wrong'
    with pytest.raises(SystemExit) as raised:
        run_saved_review(monkeypatch, tmp_path, decision='approved', mutate=mutate)
    assert raised.value.code == 2
    assert not (tmp_path/'review.json').exists()


def test_public_cli_forwards_verbose_to_review(monkeypatch, tmp_path):
    import cli.main as cli
    import scripts.review_vinsoc_query_case as review
    captured = []
    monkeypatch.setattr(review, 'main', lambda argv: captured.extend(argv) or 0)
    monkeypatch.setattr('sys.argv', ['vinsoc', 'query-review', 'case.json', '--output', 'review.json', '--verbose'])
    assert cli.main() == 0
    assert captured == ['case.json', '--output', 'review.json', '--verbose']


@pytest.mark.parametrize('index', range(4))
def test_public_query_preflight_accepts_each_locked_demo_without_live_execution(monkeypatch, tmp_path, index):
    import cli.main as cli
    import scripts.run_vinsoc_query_acceptance as runner
    chosen = json.loads(Path('results/evaluation_v1/text2sql_integration_v1/demo_selection.json').read_text())['cases'][index]
    def forbidden_live(*args, **kwargs):
        pytest.fail('Preflight must stop before live/provider creation')
    monkeypatch.setattr(runner, 'run_live', forbidden_live)
    output = tmp_path/'preflight.json'
    monkeypatch.setattr('sys.argv', ['vinsoc', 'query', '--scope', 'demo', '--condition', 'E3',
                                   '--case-id', chosen['case_id'], '--question', chosen['question'],
                                   '--preflight-only', '--output', str(output)])
    assert cli.main() == 1  # No private authorization/CI/runtime data are supplied.
    result = json.loads(output.read_text(encoding='utf-8'))
    assert result['release']['case_ids'] == [chosen['case_id']]
    assert result['release']['authorized'] is False
    assert result['release']['client_created'] is False
    assert result['release']['attempted'] == result['release']['received'] == 0


def test_public_demo_cli_requires_e3_before_preflight_or_provider(monkeypatch, tmp_path, capsys):
    import cli.main as cli
    chosen = json.loads(Path('results/evaluation_v1/text2sql_integration_v1/demo_selection.json').read_text())['cases'][0]
    output = tmp_path/'preflight.json'
    monkeypatch.setattr('sys.argv', ['vinsoc', 'query', '--scope', 'demo', '--condition', 'E0',
                                   '--case-id', chosen['case_id'], '--question', chosen['question'],
                                   '--preflight-only', '--output', str(output)])
    with pytest.raises(SystemExit) as raised:
        cli.main()
    assert raised.value.code == 2
    assert 'single-case demo requires --condition E3' in capsys.readouterr().err
    assert not output.exists()


@pytest.mark.parametrize('mismatch', ['scope', 'condition', 'case_id'])
def test_cli_rejects_a_release_that_disagrees_with_selected_demo_before_live(monkeypatch, tmp_path, mismatch):
    import cli.main as cli
    import scripts.run_vinsoc_query_acceptance as runner
    cases = json.loads(Path('results/evaluation_v1/text2sql_integration_v1/demo_selection.json').read_text())['cases']
    chosen = cases[1]
    release = {'scope':'demo','condition':'E3','case_ids':[chosen['case_id']]}
    if mismatch == 'scope':
        release['scope'] = 'pipeline'
    elif mismatch == 'condition':
        release['condition'] = 'E0'
    else:
        release['case_ids'] = [cases[0]['case_id']]
    # Deliberately incomplete release: no paid authorization, model output or SDK stand-in.
    path = tmp_path/'invalid-release.json'
    path.write_text(json.dumps(release))
    def forbidden_live(*args, **kwargs):
        pytest.fail('Mismatched release must be rejected before entering live execution')
    monkeypatch.setattr(runner, 'run_live', forbidden_live)
    monkeypatch.setattr('sys.argv', ['vinsoc','query','--scope','demo','--condition','E3',
                                   '--case-id',chosen['case_id'],'--question',chosen['question'],
                                   '--release',str(path),'--output',str(tmp_path/'live')])
    with pytest.raises(SystemExit) as raised:
        cli.main()
    assert raised.value.code == 2
    assert not (tmp_path/'live').exists()


def test_saved_artifact_text_is_escaped():
    from scripts.render_query_pipeline_report import escaped_json
    saved = json.loads(Path('results/evaluation_v1/ctu_network_public/r2_phase2_live/20261001_3f9d72d/suite/report.json').read_text())
    sql = next(r['final_sql'] for r in saved['case_results'] if r['final_sql'] and '<' in r['final_sql'])
    encoded = escaped_json(sql)
    assert '<' not in encoded
    assert '&lt;' in encoded


def test_human_review_hash_mismatch_does_not_join():
    from evaluation.finalization.query_pipeline_reporting import validate_review
    real = json.loads(Path('results/evaluation_v1/text2sql_integration_v1/original_data_20261010/ci_verification.json').read_text())
    assert validate_review(real, real) is False


@pytest.mark.parametrize('value', ['', '2026-10-10T12:00:00', '2026-10-10T12:00:00+07:00'])
def test_review_requires_analyst_entered_utc(value):
    from scripts.review_vinsoc_query_case import validate_review_utc
    with pytest.raises(ValueError, match='ACTUAL_UTC_REQUIRED'):
        validate_review_utc(value)


def test_duplicate_real_inventory_is_rejected():
    from evaluation.finalization.query_pipeline_reporting import build_pipeline_report
    inventory = inventory_for('pipeline')
    with pytest.raises(ValueError, match='DUPLICATE_PLANNED_CASE'):
        build_pipeline_report([], inventory+[inventory[0]], reviews=[], identities={}, journal={})


@pytest.mark.parametrize('utc', ['2026-10-10T00:00:00Z', None])
def test_null_analyst_and_rationale_are_missing_review_fields(utc):
    import hashlib
    from evaluation.finalization.query_pipeline_reporting import validate_review
    actual_receipt = Path('results/evaluation_v1/text2sql_integration_v1/original_data_20261010/ci_verification.json')
    record = {'case_id':inventory_for('pipeline')[0]['case_id'],
              'case_receipt_sha256':hashlib.sha256(actual_receipt.read_bytes()).hexdigest()}
    # Malformed review metadata only: no human decision or prediction is created/exported.
    invalid = {'scope':'actual_human_review','case_id':record['case_id'],
               'case_receipt_sha256':record['case_receipt_sha256'], 'decision':'escalated',
               'analyst':None,'rationale':None,'utc':utc}
    assert validate_review(invalid, record) is False
