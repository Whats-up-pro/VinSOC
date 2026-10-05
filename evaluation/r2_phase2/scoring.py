"""Score saved SQL with the locked evaluator; pipeline completion is separate."""
from __future__ import annotations

from copy import deepcopy
from pathlib import Path

from evaluation.r2_phase2.safety import Phase2Snapshot
from evaluation.text_to_sql import SQLBenchmarkCase, evaluate_sql_case

SCORE_FIELDS = ('syntax_valid', 'execution_success', 'execution_accurate', 'safety_rejected')


def unscored_prediction(record: dict, reason: str) -> dict:
    """An infrastructure/provenance failure has unknown flags, not false scores."""
    result = deepcopy(record)
    result['pipeline_error_category'] = record.get('pipeline_error_category', record.get('error_category', 'UNKNOWN'))
    result.update({field: None for field in SCORE_FIELDS})
    result.update(scoring_status='unscored', validation_passed=False, scoring_error_category=reason)
    return result


def score_prediction(case: SQLBenchmarkCase, record: dict, snapshot) -> dict:
    """Return a copy scored by evaluate_sql_case, after validating all gold SQL."""
    if record.get('case_id') != case.case_id:
        return unscored_prediction(record, 'CASE_ID_MISMATCH')
    if isinstance(snapshot, (str, Path)):
        snapshot = Phase2Snapshot(snapshot)
    if snapshot is None or not Path(snapshot.database_path).is_file():
        return unscored_prediction(record, 'SNAPSHOT_MISSING')
    # A controller failure cannot turn invalid gold into a scored model failure.
    try:
        if not case.gold_sql:
            raise ValueError('gold missing')
        for sql in case.gold_sql:
            if snapshot.query(sql).truncated:
                raise ValueError('gold truncated')
    except Exception:
        return unscored_prediction(record, 'GOLD_VALIDATION_FAILED')
    sql = record.get('final_sql')
    if sql is not None and not isinstance(sql, str):
        return unscored_prediction(record, 'PREDICTION_RECORD_INVALID')
    try:
        evaluation = evaluate_sql_case(case, sql or '', snapshot)
    except Exception:
        return unscored_prediction(record, 'SCORING_VALIDATION_FAILED')
    result = deepcopy(record)
    result['pipeline_error_category'] = record.get('pipeline_error_category', record.get('error_category', 'UNKNOWN'))
    result['archived_score_flags'] = {field: record[field] for field in SCORE_FIELDS if field in record}
    result.update({field: getattr(evaluation, field) for field in SCORE_FIELDS})
    error = ('NO_FINAL_SQL' if not sql or not sql.strip() else
             'SAFETY_REJECTION' if evaluation.safety_rejected else
             'SYNTAX_ERROR' if not evaluation.syntax_valid else
             'EXECUTION_ERROR' if not evaluation.execution_success else
             'RESULT_MISMATCH' if not evaluation.execution_accurate else 'OK')
    result.update(scoring_status='scored', validation_passed=True, scoring_error_category=error,
                  scoring_policy_identity=getattr(snapshot, 'policy_identity', 'original_snapshot_policy'))
    return result
