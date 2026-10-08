"""Real filesystem persistence boundaries; no SDK/model response emulation."""
import json
import multiprocessing
import pytest
from tests.soc_support import feature

def claim_one(path,queue):
    m=__import__('evaluation.soc_traces_v1.accounting',fromlist=['_exclusive_claim'])
    try:m._exclusive_claim(path,{'unit_persistence_only':True});queue.put('claimed')
    except FileExistsError:queue.put('consumed')

def test_claim_race_and_crash_consumed(tmp_path):
    feature('evaluation.soc_traces_v1.accounting')
    ctx=multiprocessing.get_context('spawn');queue=ctx.Queue();path=str(tmp_path/'ledger.json')
    children=[ctx.Process(target=claim_one,args=(path,queue)) for _ in range(2)]
    for p in children:p.start()
    for p in children:p.join(10);assert p.exitcode==0
    assert sorted(queue.get(timeout=2) for _ in children)==['claimed','consumed']
    assert json.loads((tmp_path/'ledger.json').read_text())['unit_persistence_only'] is True

def test_response_persisted_before_validation(tmp_path):
    m=feature('evaluation.soc_traces_v1.accounting');p=tmp_path/'response.json'
    invalid={'unit_parser_input':True,'usage':None}
    with pytest.raises(ValueError):m.persist_and_validate_response(p,invalid,pricing={'input_usd_per_million':1,'output_usd_per_million':1})
    assert json.loads(p.read_text())==invalid

def test_canonical_ledger_cannot_be_moved(tmp_path):
    m=feature('evaluation.soc_traces_v1.accounting')
    with pytest.raises(ValueError):m.SocRunJournal.claim({},ledger_path=tmp_path/'ledger.json')
