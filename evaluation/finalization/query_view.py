"""Read-only projection of saved stages. Missing stages stay explicitly missing."""
from __future__ import annotations

from .query_pipeline_reporting import validate_review


def case_view(record, *, question=None, review=None):
    metadata = record.get('metadata', {})
    generation = record.get('generation', {})
    original = record.get('initial_indicator', {}).get('value', record.get('question', generation.get('question')))
    if question is not None and original is not None and original != question:
        raise ValueError('EXACT_ORIGINAL_QUESTION_REQUIRED')
    execution = metadata.get('query_execution', record.get('execution', generation.get('execution')))
    valid_review = bool(review and validate_review(review, record))
    return {'original_question': question if question is not None else original,
            'native_tool_call': [c for e in record.get('cost_events', []) if e.get('role') == 'routing'
                                 for c in e.get('native_tool_calls', [])] or None,
            'sql':generation.get('final_sql', (execution or {}).get('sql')),
            'typed_result': execution, 'evidence':record.get('evidence'),
            'assessment':metadata.get('query_policy', {}).get('assessment') or record.get('final_assessment'),
            'verification':metadata.get('query_policy', {}).get('validation'),
            'integrated_ex':record.get('score'),
            'technical_status':metadata.get('review_status', record.get('status', 'incomplete')),
            'human_review':review if valid_review else None,
            'review_status':'valid' if valid_review else 'hash_or_identity_mismatch' if review else 'pending',
            'limitations':record.get('limitations')}
