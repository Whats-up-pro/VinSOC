"""Public query API must not accept the historical default mock provider."""
import json
from pathlib import Path

import pytest

from agent.orchestrator import InvestigationOrchestrator
from skills.network_query_skill import QueryContext


def test_default_orchestrator_cannot_open_query_profile():
    entry = json.loads(Path('evaluation/r2_cross_domain_v1/runtime_registry.json').read_text())['databases'][-1]
    scope = QueryContext('ctu_dev', Path('missing.duckdb'), entry['logical_sha256'], ('network_flows',), 'pipeline')
    with pytest.raises(ValueError, match='GUARDED_QUERY_PROVIDER_REQUIRED'):
        InvestigationOrchestrator().investigate_query('Count all flows', query_context=scope)


def test_cli_preflight_blocked_has_nonzero_exit_and_no_client(tmp_path):
    import subprocess
    import sys
    output = tmp_path/'preflight.json'
    process = subprocess.run([sys.executable, '-m', 'cli.main', 'query', '--preflight-only',
                              '--output', str(output)], capture_output=True, text=True)
    assert process.returncode == 1
    receipt = json.loads(output.read_text())
    assert receipt['client_created'] is False
    assert receipt['attempted'] == receipt['received'] == 0
    assert receipt['release']['authorized'] is False
