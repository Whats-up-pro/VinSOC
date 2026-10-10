"""Preflight or one authorized real batch through the public query lifecycle."""
from __future__ import annotations

import argparse
import json
import os
from copy import deepcopy
from pathlib import Path

from evaluation.finalization.query_pipeline_contract import CONTRACTS, preflight, validate_release
from evaluation.finalization.query_runtime_validation import (
    ROOT,
    source_hashes,
    validate_data,
    verify_code_and_ci,
    verify_selection_lock,
    verify_scope_unused,
    selection_identities,
    build_selection_lock,
    transmission_files,
    verify_transmission_files,
)


def inventory_for(scope):
    path = ROOT/'evaluation/r2_cross_domain_v1/benchmarks'/('calibration_runtime.json' if scope == 'calibration' else 'evaluation_runtime.json')
    rows = json.loads(path.read_text())
    return [r for r in rows if r['database_id'] == 'ctu_dev'] if scope == 'pipeline' else rows


def write_new(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('x', encoding='utf-8') as handle:
        json.dump(value, handle, ensure_ascii=False, indent=2)
        handle.write('\n')


def run_preflight(scope, condition, private):
    identities = deepcopy(private.get('identities', {}))
    identities.update(data_verified=False, source_verified=False, ci_verified=False, worker_verified=False)
    diagnostics = []
    try:
        verify_code_and_ci(identities)
        identities.update(source_verified=True, ci_verified=True)
    except Exception as error:
        diagnostics.append({'gate': 'code_ci', 'error_class': type(error).__name__})
    try:
        contexts, _ = validate_data()
        identities['transmission_files_sha256'] = transmission_files(contexts)
        identities.update(data_verified=True, worker_verified=True)
    except Exception as error:
        diagnostics.append({'gate': 'real_data_and_worker', 'error_class': type(error).__name__})
    result = preflight(scope, condition, inventory=inventory_for(scope), identities=identities,
                       account=private.get('account', {}), pricing=private.get('pricing', {}),
                       budget=private.get('budget', {}))
    return {'release': result, 'diagnostics': diagnostics,
            'current_source_sha256': source_hashes(), 'client_created': False, 'attempted': 0, 'received': 0}


def run_live(release, output):
    release = validate_release(release)
    verify_scope_unused(release['scope'])
    verify_code_and_ci(release['gate_inputs']['identities'])
    contexts, references = validate_data()  # Exact locked bytes + same worker, before SDK.
    if release['gate_inputs']['identities'].get('transmission_files_sha256') != transmission_files(contexts):
        raise ValueError('TRANSMISSION_DATA_BINDING_REQUIRED')
    verify_transmission_files(release['gate_inputs']['identities'])
    inventory = inventory_for(release['scope'])
    if inventory != release['gate_inputs']['inventory']:
        raise ValueError('LOCKED_INVENTORY_CHANGED')
    output = Path(output)
    if output.exists():
        raise ValueError('OUTPUT_ALREADY_EXISTS')
    if not os.environ.get('OPENAI_API_KEY') or os.environ.get('OPENAI_BASE_URL'):
        raise ValueError('OFFICIAL_KEY_REQUIRED')
    # Evaluation must have an actual frozen calibration selection, not a hand-picked condition.
    if release['scope'] in ('evaluation', 'pipeline'):
        selection_path = release['gate_inputs']['identities'].get('selection_lock_path')
        if not selection_path:
            raise ValueError('CALIBRATION_SELECTION_LOCK_REQUIRED')
        selection = verify_selection_lock(Path(selection_path), identities=release['gate_inputs']['identities'])
        if selection['selected_condition'] != release['condition']:
            raise ValueError('CALIBRATION_SELECTION_LOCK_REQUIRED')
    import openai

    from agent.orchestrator import InvestigationOrchestrator
    from evaluation.finalization.query_scoring import score_saved_generation
    from evaluation.r2_cross_domain_v1.benchmark import ReferenceCase
    from evaluation.r2_cross_domain_v1.module_metrics import score_modules
    from skills.network_query_skill import NetworkQuerySkill, QueryContext
    from vinsoc_text2sql.accounting import RunJournal, ScopedOpenAIClient, persist
    from vinsoc_text2sql.provider import QueryProvider
    from vinsoc_text2sql.service import QueryRequest, TextToSQLService
    output.mkdir(parents=True, exist_ok=False)
    report = {'scope': release['scope'], 'status': 'blocked', 'planned': release['planned'], 'completed': 0,
              'planned_records': release['planned']*(1 if release['scope']=='pipeline' else 2),
              'client_created': False, 'attempted': 0, 'received': 0, 'case_records': []}
    persist(output/'report.json', report)
    journal = None
    sdk = None
    active = None
    run_identities = {**selection_identities(), 'implementation_sha': release['gate_inputs']['identities']['implementation_sha']}
    conditions = [release['condition']] if release['scope'] == 'pipeline' else ['E0', 'E3']
    try:
        journal = RunJournal.claim(release, ledger_path=Path.home()/'.vinsoc/live-windows'/release['window_id']/'ledger.json')
        sdk = openai.OpenAI(api_key=os.environ['OPENAI_API_KEY'], max_retries=0,
                            base_url='https://api.openai.com/v1', timeout=60)
        report['client_created'] = True
        clients = {role: ScopedOpenAIClient(sdk, role=role, contract=c, journal=journal)
                   for role, c in CONTRACTS.items()}
        service = TextToSQLService()
        refs = {r['case_id']: r for r in references}
        conditions = [release['condition']] if release['scope'] == 'pipeline' else ['E0', 'E3']
        for condition in conditions:
            for row in inventory:  # Locked file order, no output-based selection.
                if journal.data['terminal'] or journal.data['cost_unknown']:
                    raise ValueError('TERMINAL_OR_UNKNOWN_COST')
                journal.set_case(row['case_id'], condition)
                context = contexts[row['database_id']]
                target = output/(condition+'_'+row['case_id']+'.json')
                active = {'case_id': row['case_id'], 'condition': condition, 'question': row['question'],
                          'status': 'partial', 'identities': run_identities, 'cost_events': []}
                def checkpoint(record):
                    active['generation'] = deepcopy(record)
                    active['cost_events'] = journal.case_events()
                    active['cost_unknown'] = journal.data['cost_unknown']
                    persist(target, active)
                def journal_checkpoint(events):
                    active['cost_events'] = events
                    active['cost_unknown'] = journal.data['cost_unknown']
                    persist(target, active)
                    report.update(active_case_id=row['case_id'], active_condition=condition,
                                  **{k: journal.data[k] for k in ('attempted','received','valid_usage','cost_unknown','known_usd')})
                    persist(output/'report.json', report)
                journal.checkpoint_sink = journal_checkpoint
                persist(target, active)
                if release['scope'] == 'pipeline':
                    provider = QueryProvider(routing=clients['routing'], assessment=clients['assessment'],
                                             r2=clients['r2'], condition=condition)
                    scope = QueryContext(context.database_id, context.snapshot_path, context.identity['logical_sha256'],
                                         ('network_flows',), 'pipeline')
                    skill = NetworkQuerySkill(context=context, query_context=scope, condition=condition,
                                              transport=clients['r2'], service=service, telemetry_sink=checkpoint)
                    orchestrator = InvestigationOrchestrator(provider=provider, query_skill=skill, max_steps=2, max_review_cycles=0)
                    case = orchestrator.investigate_query(row['question'], query_context=scope)
                    record = case.to_dict()
                    generation = skill.last_generation or {'error_category': 'NO_FINAL_SQL'}
                else:
                    generation = service.generate(QueryRequest(row['case_id'], row['database_id'], row['question']),
                        condition=condition, context=context, transport=clients['r2'], telemetry_sink=checkpoint)
                    record = deepcopy(generation)
                    if generation['error_category'] == 'OK':
                        from vinsoc_text2sql.executor import ExecutorError
                        try:
                            record['execution'] = service.execute(generation, context=context)
                        except ExecutorError as error:
                            if str(error) not in ('SQL_EXECUTION_FAILED', 'SQL_TIMEOUT'):
                                raise
                            record['execution_error'] = str(error)
                if journal.data['terminal'] or journal.data['cost_unknown']:
                    checkpoint(generation)
                    raise ValueError('TERMINAL_OR_UNKNOWN_COST')
                # Evaluator-only answers are read only after runtime returned.
                score = score_saved_generation(refs[row['case_id']], generation,
                    context=context, executor=service.executor)
                reference = ReferenceCase(**{k: refs[row['case_id']][k] for k in ReferenceCase.__dataclass_fields__})
                record.update(case_id=row['case_id'], condition=condition, generation=deepcopy(generation), score=score,
                    modules=score_modules(reference, generation, context), runtime_source_sha256=source_hashes(),
                    identities=run_identities, cost_events=journal.case_events(), cost_unknown=journal.data['cost_unknown'])
                active.clear()
                active.update(record)
                persist(target, active)
                report['case_records'].append(record)
                report.update(completed=len(report['case_records']), status='partial', **clients['r2'].counters(),
                              known_usd=journal.data['known_usd'], cost_unknown=journal.data['cost_unknown'])
                persist(output/'report.json', report)
                if journal.data['terminal']:
                    return report
        report['status'] = 'technical_complete_awaiting_human' if release['scope'] == 'pipeline' else 'completed'
        from evaluation.finalization.query_reporting import build_query_report
        report['metrics'] = build_query_report(report['case_records'], [refs[r['case_id']] for r in inventory], conditions=tuple(conditions))
        report['official_eligible'] = False  # Full identity/scoring/report audit is a separate gate.
        if release['scope'] == 'calibration':
            import hashlib
            artifacts = []
            for row in report['case_records']:
                wrapper = output/('binding_'+row['condition']+'_'+row['case_id']+'.json')
                write_new(wrapper, {'case_records': [row]})
                artifacts.append({'path': wrapper.name, 'sha256': hashlib.sha256(wrapper.read_bytes()).hexdigest()})
            write_new(output/'selection_lock.json', build_selection_lock(report['case_records'], identities=run_identities, artifacts=artifacts))
        return report
    except Exception as error:
        report.update(status='partial' if journal else 'blocked', failure_category=type(error).__name__)
        if journal:
            report.update(**{k: journal.data[k] for k in ('attempted','received','valid_usage','cost_unknown','known_usd')})
        return report
    finally:
        if journal:
            journal.checkpoint_sink = None
            report['cost_events'] = [{k:v for k,v in e.items() if k not in ('request','response')}
                                     for e in journal.data['events']]
            if active is not None:
                persist(target, active)
            report.update(**{k:journal.data[k] for k in ('attempted','received','valid_usage','cost_unknown','known_usd','pending_exposure_usd')})
        from evaluation.finalization.query_reporting import build_query_report
        report['metrics'] = build_query_report(report['case_records'], inventory, conditions=tuple(conditions),
                                             identities=run_identities, journal={'events':report.get('cost_events', [])})
        if release['scope'] == 'pipeline':
            from evaluation.finalization.query_pipeline_reporting import build_pipeline_report
            report['pipeline_metrics'] = build_pipeline_report(report['case_records'], inventory, reviews=[],
                                                              identities=run_identities, journal={'events':report.get('cost_events', [])})
        persist(output/'report.json', report)
        if sdk:
            try:
                sdk.close()
            except Exception:
                report.update(status='partial', close_error='SDK_CLOSE_FAILED')
                persist(output/'report.json', report)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--scope', choices=['calibration','evaluation','pipeline'], default='pipeline')
    parser.add_argument('--condition', choices=['E0','E3'], default='E3')
    parser.add_argument('--preflight-only', action='store_true')
    parser.add_argument('--private-inputs', type=Path)
    parser.add_argument('--release', type=Path)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args(argv)
    if args.preflight_only:
        private = json.loads(args.private_inputs.read_text()) if args.private_inputs else {}
        result = run_preflight(args.scope, args.condition, private)
        public = deepcopy(result)
        public['release'].pop('gate_inputs', None)
        write_new(args.output, public)
        receipt = result['release']
    else:
        if not args.release:
            parser.error('Live requires a separately authorized new release; old network window is insufficient')
        raw = json.loads(args.release.read_text())
        receipt = run_live(raw.get('release',raw), args.output)
    print(json.dumps({k: receipt.get(k) for k in ('status','reasons','planned','completed','attempted','received','client_created')}))
    return 0 if receipt['status'] in ('completed','technical_complete_awaiting_human','preflight_pass') else 1


if __name__ == '__main__':
    raise SystemExit(main())
