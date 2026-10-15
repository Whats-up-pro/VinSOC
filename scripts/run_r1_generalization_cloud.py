"""Manual R1 preflight/live entrypoint. It never manufactures review decisions."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

from evaluation.finalization.cloud_window import atomic_json
from evaluation.finalization.query_token_bound import MODEL_DOCS, read_model_document
from evaluation.tool_calling.generalization_run import MODEL, SPLIT, cli_generalization


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--mode', choices=['preflight','live'], required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args(argv)
    args.output.mkdir(parents=True, exist_ok=False)
    control = {'status':'blocked','client_created':False,'attempted':0,'received':0,'cost_usd':0,
               'human_review':'NOT_PERFORMED_BY_RUNNER'}
    try:
        request = json.loads(os.environ['VINSOC_R1_REQUEST'])
        if (os.environ.get('GITHUB_REPOSITORY') != 'Whats-up-pro/VinSOC'
                or os.environ.get('GITHUB_REF') != 'refs/heads/master'
                or os.environ.get('GITHUB_EVENT_NAME') != 'workflow_dispatch'
                or os.environ.get('GITHUB_RUN_ATTEMPT') != '1'
                or request['model'] != MODEL or request['max_retries'] != 0
                or request.get('approved') is not True):
            raise ValueError('R1_EXPLICIT_MANUAL_CONTEXT_REQUIRED')
        lock = json.loads((SPLIT/'GENERALIZATION.lock').read_text())
        if request['split_sha256'] != lock['split_sha256']:
            raise ValueError('R1_EXPLICIT_SPLIT_SHA_MISMATCH')
        doc = Path(os.environ['VINSOC_R1_MODEL_DOCUMENT'])
        prices = read_model_document(doc, MODEL)
        ceiling = 120*(prices['input_token_ceiling']*prices['input_usd_per_million']
                       +1000*prices['output_usd_per_million'])/1_000_000
        auth = {'scope':'r1-generalization-v1','approved':True,
                'authorized_by':os.environ['GITHUB_ACTOR'],
                'reference':'explicit-user-all-remaining-experiments-20261015',
                'model':MODEL,'implementation_sha':os.environ['GITHUB_SHA'],
                'split_sha256':request['split_sha256'],'ci_run_id':int(request['ci_run_id']),
                'maximum_requests':120,'maximum_output_tokens':1000,'max_retries':0,
                'limit_usd':request['budget_usd'],'cost_ceiling_usd':ceiling,
                'checked_utc':datetime.now(timezone.utc).isoformat(),
                'model_document':{'source_url':MODEL_DOCS[MODEL],'path':str(doc.resolve()),
                                  'sha256':hashlib.sha256(doc.read_bytes()).hexdigest()}}
        auth_path = args.output/'authorization.json'
        atomic_json(auth_path, auth)
        cli_args = SimpleNamespace(command='preflight' if args.mode == 'preflight' else 'run',
            mode='decision',split='generalization_v1',cases=None,provider='openai',model=MODEL,
            temperature=0.,authorization=auth_path,budget_usd=request['budget_usd'],
            output=args.output/'preflight.json',output_dir=args.output/'live')
        result = cli_generalization(cli_args)
        if args.mode == 'preflight':
            control.update(status='preflight_pass',cost_ceiling_usd=ceiling,maximum_requests=120)
        else:
            control.update(status=result['run_status'],client_created=True,
                           attempted=result['journal']['attempted'],received=result['journal']['received'],
                           cost_usd=result['known_cost_usd'],cost_unknown=result['cost_unknown'],
                           official_eligible=result['official_eligible'])
    except Exception as error:
        message = str(error)
        control['failure_category'] = message if isinstance(error,ValueError) and re_literal(message) else type(error).__name__
    finally:
        live = args.output/'live'
        control['window_claimed'] = (live/'claim.json').is_file()
        control['client_created'] = (live/'client_created.json').is_file()
        if (live/'journal.json').is_file():
            journal = json.loads((live/'journal.json').read_text())
            control.update(attempted=journal['attempted'],received=journal['received'],
                           cost_usd=journal['known_usd'],cost_unknown=journal['cost_unknown'],
                           pending_exposure_usd=journal['pending_exposure_usd'])
        atomic_json(args.output/'cloud_run.json',control)
    print(json.dumps(control))
    return 0 if control['status'] in ('preflight_pass','completed') else 1


def re_literal(value):
    import re
    return bool(re.fullmatch(r'[A-Z0-9_]{1,100}',value))


if __name__ == '__main__':
    raise SystemExit(main())
