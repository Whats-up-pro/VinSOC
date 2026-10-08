"""No SDK/transport stand-ins; release gates are checked without paid calls."""
import pytest

from evaluation.finalization.query_pipeline_contract import preflight, role_caps
from vinsoc_text2sql.accounting import RunJournal


def test_release_denies_missing_inputs_without_client():
    receipt = preflight('pipeline', 'E3', inventory=[], identities={}, account={}, pricing={}, budget={})
    assert receipt['authorized'] is False
    assert receipt['attempted'] == receipt['received'] == 0
    assert receipt['client_created'] is False
    assert 'FULL_LOCKED_INVENTORY_UNVERIFIED' in receipt['reasons']
    assert 'PAID_RELEASE_NOT_AUTHORIZED' in receipt['reasons']


def test_all_layers_counted_in_upper_bound():
    assert role_caps('calibration', 'E3') == {'routing': 0, 'r2': 168, 'assessment': 0}
    assert role_caps('evaluation', 'E3') == {'routing': 0, 'r2': 672, 'assessment': 0}
    assert role_caps('pipeline', 'E3') == {'routing': 32, 'r2': 192, 'assessment': 32}
    assert role_caps('pipeline', 'E0') == {'routing': 32, 'r2': 32, 'assessment': 32}


def test_denied_release_cannot_claim_window(tmp_path):
    release = preflight('pipeline', 'E3', inventory=[], identities={}, account={}, pricing={}, budget={})
    with pytest.raises(ValueError, match='RELEASE_NOT_AUTHORIZED'):
        RunJournal.claim(release, ledger_path=tmp_path/'ledger.json')
    assert not list(tmp_path.iterdir())
