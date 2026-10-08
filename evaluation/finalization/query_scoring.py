"""Evaluator-only comparison. Never imported by production generation/skill."""
from decimal import Decimal

from evaluation.r2_cross_domain_v1.semantic_scoring import compare_results
from vinsoc_text2sql.executor import ExecutorError


def typed_rows(receipt):
    def value(v, t):
        if v is None:
            return None
        if t.startswith(('DECIMAL', 'HUGEINT', 'UHUGEINT')):
            return Decimal(str(v))
        if t == 'BLOB':
            return bytes.fromhex(v['bytes_hex'])
        return v
    return [[value(v, c['type']) for v, c in zip(row, receipt['columns'])] for row in receipt['rows']]


def score_saved_generation(reference, generation, *, context, executor):
    # Gold is validated before predictions; a gold infrastructure failure is terminal.
    gold = executor.query(context, reference['gold_sql'], row_cap=10000, timeout_seconds=10)
    if gold['truncated']:
        raise ValueError('GOLD_RESULT_LIMIT')
    score = {'case_id': reference['case_id'], 'execution_accurate': False,
             'execution_success': False, 'scoring_error_category': 'NO_FINAL_SQL'}
    if generation.get('error_category') != 'OK' or not generation.get('final_sql'):
        return score
    try:
        predicted = executor.query(context, generation['final_sql'], row_cap=10000, timeout_seconds=10)
    except ExecutorError as error:
        if str(error) in ('SQL_EXECUTION_FAILED', 'SQL_TIMEOUT'):
            return {**score, 'scoring_error_category': str(error)}
        raise  # Missing isolation/identity is infrastructure, not model accuracy zero.
    correct = not predicted['truncated'] and compare_results(
        typed_rows(predicted), typed_rows(gold), reference['comparator'])
    return {**score, 'execution_success': not predicted['truncated'], 'execution_accurate': correct,
            'scoring_error_category': 'OK' if correct else 'RESULT_MISMATCH',
            'gold_result_sha256': gold['result_sha256'], 'predicted_result_sha256': predicted['result_sha256']}
