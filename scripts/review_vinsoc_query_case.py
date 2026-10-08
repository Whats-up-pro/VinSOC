"""Interactive actual analyst review; the original technical receipt is immutable."""
import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('case', type=Path)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args(argv)
    case = json.loads(args.case.read_text())
    metadata = case.get('metadata', {})
    if (metadata.get('review_status') != 'awaiting_human'
        or metadata.get('schema_valid') is not True
        or metadata.get('query_policy', {}).get('validation', {}).get('valid') is not True
        or metadata.get('query_policy', {}).get('termination') != 'FINAL_ASSESSMENT'):
        parser.error('Technical-invalid cases cannot be approved')
    if args.output.exists():
        parser.error('Refusing to overwrite analyst review')
    print(json.dumps({'case_id':case['case_id'],'question':case['initial_indicator']['value'],
        'assessment':case['final_assessment'],'evidence':case['evidence'],
        'limitations':case['limitations']}, ensure_ascii=False, indent=2))
    analyst = input('Analyst name: ').strip()
    decision = input('Decision [approved/rejected/escalated]: ').strip()
    rationale = input('Rationale: ').strip()
    if not analyst or not rationale or decision not in ('approved','rejected','escalated'):
        parser.error('Actual analyst identity, decision and rationale are required')
    receipt = {'scope':'actual_human_review', 'case_id':case['case_id'],
        'case_receipt_sha256':hashlib.sha256(args.case.read_bytes()).hexdigest(),
        'analyst':analyst,'decision':decision,'rationale':rationale,
        'utc':datetime.now(timezone.utc).isoformat()}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open('x', encoding='utf-8') as out:
        json.dump(receipt, out, ensure_ascii=False, indent=2)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
