"""Record a named person's supplied decision; never calls model/tools or auto-approves."""
import argparse,json,sys
from datetime import datetime,timezone
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from evaluation.soc_traces_v1.reporting import validate_review,verify_receipt
from evaluation.soc_traces_v1.accounting import atomic_json

def main(argv=None):
    p=argparse.ArgumentParser();p.add_argument('--receipt',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    p.add_argument('--analyst',required=True);p.add_argument('--decision',choices=['approved','rejected','escalated','more_evidence_requested'],required=True);p.add_argument('--rationale',required=True)
    a=p.parse_args(argv);r=verify_receipt(json.loads(a.receipt.read_text()))
    review={'receipt_sha256':r['receipt_sha256'],'scenario_id':r['scenario_id'],'condition':r['condition'],'analyst':a.analyst,'decision':a.decision,'rationale':a.rationale,'reviewed_at':datetime.now(timezone.utc).isoformat()}
    validate_review(review,receipt=r)
    if a.output.exists():raise ValueError('SOC_REVIEW_ALREADY_EXISTS')
    atomic_json(a.output,review);print(json.dumps({'status':'recorded','decision':review['decision'],'new_model_calls':0}));return 0
if __name__=='__main__':raise SystemExit(main())
