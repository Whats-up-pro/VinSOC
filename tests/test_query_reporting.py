"""Coverage of the actual locked inventory, with no invented predictions."""
import json
from pathlib import Path

from evaluation.finalization.query_reporting import build_query_report


def test_missing_model_results_are_unavailable_not_zero_accuracy():
    root=Path('evaluation/r2_cross_domain_v1/benchmarks/references/evaluation')
    inventory=[json.loads(p.read_text()) for p in sorted(root.glob('*.json'))]
    report=build_query_report([],inventory)
    for condition in ('E0','E3'):
        groups=report['conditions'][condition]
        assert groups['external']['planned']==64
        assert groups['ctu']['planned']==32
        assert groups['total']['planned']==96
        assert groups['total']['completed']==0
        assert groups['total']['execution_accuracy'] is None
        assert groups['total']['status']=='incomplete'
    assert report['official_eligible'] is False
