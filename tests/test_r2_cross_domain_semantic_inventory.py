import json

import pytest


def test_source_qualification_accepts_subset_without_ctu_or_model(tmp_path):
    from scripts.audit_r2_cross_domain_semantics import read_references
    folder = tmp_path / 'evaluation'
    folder.mkdir()
    (folder / 'x.json').write_text(json.dumps({'reference': {'case_id': 'x', 'database_id': 'db'}}))
    assert read_references(tmp_path, None, external_only=True) == [{'case_id': 'x', 'database_id': 'db'}]


def test_primary_candidate_audit_cannot_silently_use_subset(tmp_path):
    from scripts.audit_r2_cross_domain_semantics import read_references
    with pytest.raises(ValueError, match='INCOMPLETE'):
        read_references(tmp_path, {'case_results': [], 'gold_execution_success_count': 40})
