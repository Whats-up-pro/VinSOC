import copy
import random
import pytest
from tests.soc_support import feature, sources, corpus

@pytest.fixture(scope='module')
def candidates(sources, corpus):
    return feature('evaluation.soc_traces_v1.dataset').build_candidates(sources, corpus[0])

def test_selection_is_balanced_and_deterministic(candidates):
    m=feature('evaluation.soc_traces_v1.dataset')
    a=m.select_inventory(candidates,exclusions=[])
    b=list(candidates);random.Random(13).shuffle(b)
    assert a==m.select_inventory(b,exclusions=[])
    assert len(a['cases'])==64
    assert len({x['scenario_id'] for x in a['cases']})==64
    assert sum(x['label']=='malicious' for x in a['cases'])==32

def test_no_success_filter(candidates):
    m=feature('evaluation.soc_traces_v1.dataset');changed=copy.deepcopy(candidates)
    for c in changed:c['success']=not c.get('success',True)
    assert m.select_inventory(changed,exclusions=[])==m.select_inventory(candidates,exclusions=[])

def test_insufficient_quota_blocks(candidates):
    with pytest.raises(ValueError,match='BLOCKED_DATASET_COVERAGE'):
        feature('evaluation.soc_traces_v1.dataset').select_inventory(candidates[:20],exclusions=[])

def test_demo_is_subset_and_missing_context_is_natural(candidates,corpus):
    m=feature('evaluation.soc_traces_v1.dataset');inv=m.select_inventory(candidates,exclusions=[])
    ids=m.select_demo(inv,corpus[0]);assert len(set(ids))==4
    assert set(ids)<= {x['scenario_id'] for x in inv['cases']}
    assert any(not corpus[0].available(ids[-1],r) for r in ('asset','process_tree','related_alerts'))
    assert m.validate_source_reviews([],inventory=inv)['status']=='pending_human_review'
