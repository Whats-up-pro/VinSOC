from scripts.run_vinsoc_query_acceptance import inventory_for


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
