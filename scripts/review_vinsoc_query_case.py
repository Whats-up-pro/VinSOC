"""Interactive actual analyst review; the original technical receipt is immutable."""
import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

from evaluation.finalization.query_view import case_view


def validate_review_utc(value):
    try:
        parsed = datetime.fromisoformat(value.replace('Z','+00:00'))
    except (ValueError,TypeError):
        raise ValueError('ACTUAL_UTC_REQUIRED') from None
    if parsed.tzinfo is None or parsed.utcoffset().total_seconds() != 0:
        raise ValueError('ACTUAL_UTC_REQUIRED')
    return value


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('case', type=Path)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args(argv)
    case = json.loads(args.case.read_text())
    metadata = case.get('metadata', {})
    technical_valid = (metadata.get('review_status') == 'awaiting_human'
        and metadata.get('schema_valid') is True
        and metadata.get('query_policy', {}).get('validation', {}).get('valid') is True
        and metadata.get('query_policy', {}).get('validation', {}).get('independent_query_replay') is True
        and metadata.get('query_policy', {}).get('termination') == 'FINAL_ASSESSMENT'
        and case.get('score', {}).get('execution_accurate') is True)
    if (metadata.get('review_status') != 'awaiting_human'
        or metadata.get('schema_valid') is not True
        or metadata.get('query_policy', {}).get('validation', {}).get('valid') is not True
        or metadata.get('query_policy', {}).get('termination') != 'FINAL_ASSESSMENT'):
        parser.error('Technical-invalid cases cannot be approved')
    if args.output.exists():
        parser.error('Refusing to overwrite analyst review')
    print(json.dumps(case_view(case), ensure_ascii=False, indent=2))
    analyst = input('Analyst name: ').strip()
    decision = input('Decision [approved/rejected/escalated]: ').strip()
    rationale = input('Rationale: ').strip()
    utc = input('UTC timestamp entered by analyst (ISO 8601, Z or +00:00): ').strip()
    if not analyst or not rationale or decision not in ('approved','rejected','escalated'):
        parser.error('Actual analyst identity, decision and rationale are required')
    if decision == 'approved' and not technical_valid:
        parser.error('Approval requires integrated EX, independent provenance/facts and technical validity')
    try:
        validate_review_utc(utc)
    except ValueError:
        parser.error('Actual analyst-entered UTC timestamp required')
    receipt = {'scope':'actual_human_review', 'case_id':case['case_id'],
        'case_receipt_sha256':hashlib.sha256(args.case.read_bytes()).hexdigest(),
        'analyst':analyst,'decision':decision,'rationale':rationale,
        'utc':utc}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open('x', encoding='utf-8') as out:
        json.dump(receipt, out, ensure_ascii=False, indent=2)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
