"""Trusted scope must reject missing real data before any model request."""
import json
from pathlib import Path

import pytest

from evaluation.r2_cross_domain_v1.data import DatabaseContext
from skills.network_query_skill import NetworkQuerySkill, QueryContext


def test_context_cannot_grant_other_tables():
    entry = json.loads(Path('evaluation/r2_cross_domain_v1/runtime_registry.json').read_text())['databases'][-1]
    context = DatabaseContext('ctu_dev', Path('missing.duckdb'), entry)
    query_scope = QueryContext('ctu_dev', context.snapshot_path, entry['logical_sha256'],
                               ('dataset_provenance',), 'pipeline')
    with pytest.raises(ValueError, match='QUERY_SCOPE_MISMATCH'):
        NetworkQuerySkill(context=context, query_context=query_scope, condition='E0', transport=None)


def test_missing_bytes_do_not_become_empty_evidence():
    entry = json.loads(Path('evaluation/r2_cross_domain_v1/runtime_registry.json').read_text())['databases'][-1]
    context = DatabaseContext('ctu_dev', Path('missing.duckdb'), entry)
    scope = QueryContext('ctu_dev', context.snapshot_path, entry['logical_sha256'], ('network_flows',), 'pipeline')
    with pytest.raises(ValueError, match='REAL_DATA_REQUIRED'):
        NetworkQuerySkill(context=context, query_context=scope, condition='E0', transport=None)
