"""Prepare an append-only decision package without creating clients or ledgers."""
from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

from evaluation.finalization.query_pipeline_contract import CONTRACTS, role_caps
from evaluation.finalization.query_token_bound import MODEL_DOCS, read_model_document, verified_input_bound


def inspect_canonical(root):
    result = {'status': 'unverified', 'authoritative_host_verified': False,
              'allocation_verified': False, 'known_prior_cost_usd': None,
              'unknown_exposure_usd': None, 'verified_remaining_allocation_usd': None,
              'prior_hosts_sealed': False, 'ledgers_observed': [], 'scope_states': {}}
    try:
        result['canonical_directory_exists'] = root.is_dir()
        for scope in ('calibration', 'evaluation', 'pipeline'):
            window = root/('text2sql-integration-20261008-'+scope)
            present = [name for name in ('claim.json','ledger.json','migration.json') if (window/name).exists()]
            result['scope_states'][scope] = {'local_state': 'consumed' if present else 'no_local_claim_observed',
                                            'observed_files': present, 'authoritative_state': 'unknown'}
        for path in sorted(root.glob('**/ledger.json')):
            raw = path.read_bytes()
            item = {'relative_path': path.relative_to(root).as_posix(), 'sha256': hashlib.sha256(raw).hexdigest()}
            try:
                ledger = json.loads(raw)
                # These amounts are observations; inherited prior totals must never be added across windows.
                for field in ('attempted','received','valid_usage','known_usd','cost_unknown','pending_exposure_usd','terminal'):
                    value = ledger.get(field)
                    item[field] = value if type(value) in (int,float,bool) or value is None else 'invalid_type'
                item['event_count'] = len(ledger.get('events', [])) if isinstance(ledger.get('events'), list) else None
            except (ValueError, TypeError):
                item['status'] = 'unreadable_ledger_schema'
            result['ledgers_observed'].append(item)
    except OSError as error:
        result['scan_error_class'] = type(error).__name__
    result['blockers'] = ['canonical_allocation_and_prior_cost_not_authoritatively_reconciled',
                          'unknown_exposure_and_remaining_not_verified', 'prior_hosts_not_sealed']
    return result


def cost_bound(pricing, method):
    reserves = {}
    for role, contract in CONTRACTS.items():
        p = pricing[contract['model']]
        inputs = (verified_input_bound(p, contract['model']) if method == 'documented_context_window'
                  else contract['max_request_bytes']+contract['frame_reserve_tokens'])
        reserves[role] = (Decimal(inputs)*Decimal(str(p['input_usd_per_million']))
                         + Decimal(contract['max_completion_tokens'])*Decimal(str(p['output_usd_per_million'])))/Decimal(1000000)
    scopes = {}
    for scope, condition in [('calibration','E3'),('evaluation','E3'),('pipeline','E0'),('pipeline','E3'),('demo','E3')]:
        caps = role_caps(scope, condition)
        scopes[scope+('_'+condition if scope in ('pipeline','demo') else '')] = {
            'request_caps_by_role': caps,
            'request_caps_by_model': {model:sum(caps[role] for role,c in CONTRACTS.items() if c['model']==model) for model in pricing},
            'max_requests': sum(caps.values()), 'new_cost_ceiling_usd': str(sum(caps[r]*reserves[r] for r in caps))}
    combined = {c:{'max_requests':sum(scopes[s]['max_requests'] for s in ('calibration','evaluation','pipeline_'+c)),
                   'new_cost_ceiling_usd':str(sum(Decimal(scopes[s]['new_cost_ceiling_usd']) for s in ('calibration','evaluation','pipeline_'+c)))}
                for c in ('E0','E3')}
    return {'method':method, 'request_reserves_usd':{r:str(v) for r,v in reserves.items()},
            'scopes':scopes, 'combined':combined, 'cached_discount_used':False,
            'scope_condition_pending':True, 'viewer_new_requests':0,
            'includes_prior_cost':False, 'paid_authorized':False}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--gpt5-document', type=Path, required=True)
    parser.add_argument('--gpt41-document', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args(argv)
    stamp = datetime.now(timezone.utc).isoformat()
    pricing = {}
    for model,path in zip(MODEL_DOCS, (args.gpt5_document,args.gpt41_document)):
        pricing[model] = {**read_model_document(path, model), 'checked_utc':stamp,
            'source_url':'https://developers.openai.com/api/docs/pricing',
            'token_bound_method':'documented_context_window',
            'model_document':{'source_url':MODEL_DOCS[model], 'path':str(path.resolve()),
                              'sha256':hashlib.sha256(path.read_bytes()).hexdigest()}}
    conservative = cost_bound(pricing, 'documented_context_window')
    conditional = cost_bound(pricing, 'serialized_bytes_plus_unverified_512_framing')
    public_pricing = {model:{**{k:v for k,v in p.items() if k!='model_document'},
                       'model_document':{k:v for k,v in p['model_document'].items() if k!='path'}} for model,p in pricing.items()}
    data = {'status':'decision_preparation_only', 'checked_utc':stamp, 'pricing':public_pricing,
            'contracts':CONTRACTS, 'conservative_documented_bound':conservative,
            'conditional_old_bound_not_transmission_authority':conditional,
            'canonical_reconciliation':inspect_canonical(Path.home()/'.vinsoc/live-windows'),
            'attempted':0, 'received':0, 'client_created':False, 'new_model_cost_usd':0,
            'authorization_required':['demo_single_case_E3','calibration','evaluation_after_48_record_selection','pipeline_after_selection'],
            'pending_real_artifacts':{'calibration_records':48, 'evaluation_records':192, 'pipeline_cases':32},
            'framing_512_verified':False,
            'bound_explanation':'Entire documented context window covers all input/history/schema/results and hidden framing. It over-reserves input and output independently. Request bytes/messages/output caps are still enforced; the 512-token framing estimate does not authorize transmission.'}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open('x', encoding='utf-8') as out:
        json.dump(data, out, ensure_ascii=False, indent=2)
        out.write('\n')
    print(json.dumps({'status':data['status'],'combined':conservative['combined'],
                      'canonical_status':data['canonical_reconciliation']['status'],
                      'attempted':0,'received':0,'client_created':False}))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
