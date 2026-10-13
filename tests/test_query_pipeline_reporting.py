from scripts.run_vinsoc_query_acceptance import inventory_for
import copy
import json
from pathlib import Path

import pytest


def saved_demo():
    source = Path('results/evaluation_v1/text2sql_integration_v1/single_demo_full_e2e_10_20261013/runner_report.json')
    return json.loads(source.read_text(encoding='utf-8'))


def demo_projection(record):
    from evaluation.finalization.query_pipeline_reporting import build_pipeline_report
    result = build_pipeline_report([record], inventory_for('pipeline'), reviews=[],
                                  identities=record['identities'], journal={'events':record['cost_events']})
    return result, next(c for c in result['cases'] if c['case_id'] == record['case_id'])


def test_authentic_single_row_result_observation_is_verified_without_changing_artifact():
    record = saved_demo()['case_records'][0]
    original = copy.deepcopy(record)
    result, case = demo_projection(record)
    assert case['metrics']['factual_verification'] is True
    assert case['metrics']['technical_workflow'] is True
    assert case['status'] == 'awaiting_human'
    assert result['human_review']['approved'] == 0
    assert result['metrics']['technical_workflow']['denominator'] == 32
    assert result['metrics']['technical_workflow']['rate'] is None
    assert record == original


@pytest.mark.parametrize('mutation', ['value', 'type', 'field', 'unknown_evidence', 'duplicate', 'ambiguous_column', 'multiple_rows'])
def test_result_observation_mismatch_or_ambiguity_fails_closed(mutation):
    record = saved_demo()['case_records'][0]
    observations = record['metadata']['query_policy']['assessment']['observations']
    data = next(e['data'] for e in record['evidence'] if e['type'] == 'query_result')
    if mutation == 'value':
        observations[0]['value'] = 460
    elif mutation == 'type':
        observations[0]['value'] = '459'
    elif mutation == 'field':
        observations[0]['field'] = 'not_a_column'
    elif mutation == 'unknown_evidence':
        observations[0]['evidence_id'] = 'not_delivered'
    elif mutation == 'duplicate':
        observations.append(copy.deepcopy(observations[0]))
    elif mutation == 'ambiguous_column':
        data['columns'].append(copy.deepcopy(data['columns'][0]))
        data['rows'][0].append(459)
    elif mutation == 'multiple_rows':
        data['rows'].append([459])
    _, case = demo_projection(record)
    assert case['metrics']['factual_verification'] is False
    assert case['metrics']['technical_workflow'] is False


def test_result_evidence_cannot_change_cells_while_reusing_execution_hash():
    record = saved_demo()['case_records'][0]
    result = next(e['data'] for e in record['evidence'] if e['type'] == 'query_result')
    result['rows'] = [[460]]
    record['metadata']['query_policy']['assessment']['observations'][0]['value'] = 460
    _, case = demo_projection(record)
    assert case['metrics']['provenance'] is False
    assert case['metrics']['technical_workflow'] is False


@pytest.mark.parametrize('value', [1, 459])
def test_column_name_colliding_with_result_metadata_is_ambiguous(value):
    from evaluation.finalization.query_pipeline_reporting import query_observations_verified
    record = saved_demo()['case_records'][0]
    result = next(e['data'] for e in record['evidence'] if e['type'] == 'query_result')
    result['columns'][0]['name'] = 'row_count'
    assessment = record['metadata']['query_policy']['assessment']
    assessment['observations'][0].update(field='row_count', value=value)
    assert query_observations_verified(assessment, record['evidence']) is False


def test_pipeline_missing_preserves_denominator_32_for_every_stage():
    from evaluation.finalization.query_pipeline_reporting import build_pipeline_report
    report = build_pipeline_report([], inventory_for('pipeline'), reviews=[], identities={}, journal={})
    assert report['planned'] == 32
    assert report['completed'] == 0
    assert report['status'] == 'incomplete'
    assert len(report['cases']) == 32
    for metric in report['metrics'].values():
        assert metric['denominator'] == 32
        assert metric['rate'] is None
    assert report['human_review']['pending'] == 32
    assert report['human_review']['approved'] == 0
