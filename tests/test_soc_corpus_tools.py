import pytest
from tests.soc_support import feature, sources, corpus

def skill(corpus):
    m=feature('skills.soc_corpus_skill');r=corpus[0];scenario=r.scenario_ids('test')[0]
    return m.SocCorpusSkill(m.SocCorpusContext(r,scenario,'S1',r.metadata()['source_revision'],r.sha256))

def test_filters_never_cross_scope(corpus):
    s=skill(corpus);result=s.search_events()
    assert result['rows'] and all(r['provenance']['scenario_id']==s.context.scenario_id for r in result['rows'])
    assert not s.search_events(query="'; DROP TABLE observations; --")['rows']
    with pytest.raises(TypeError):s.search_events(scenario_id='OTHER')

def test_half_open_utc_and_null_times(corpus):
    s=skill(corpus);rows=s.search_events()['rows'];t=next(r['observed_at'] for r in rows if r['observed_at'])
    assert not s.search_events(start=t,end=t)['rows']
    for start,end in [('2026-01-01',None),('bad',None),('2026-10-08T00:00:00Z','2026-01-01T00:00:00Z')]:
        with pytest.raises(ValueError):s.search_events(start=start,end=end)

def test_unavailable_differs_from_no_match(corpus):
    m=feature('skills.soc_corpus_skill');r=corpus[0]
    missing=next(s for s in r.scenario_ids('test') if not r.available(s,'asset'))
    s=m.SocCorpusSkill(m.SocCorpusContext(r,missing,'S1',r.metadata()['source_revision'],r.sha256))
    assert s.get_context(resource='asset')['availability']=='unavailable'
    assert skill(corpus).search_events(host='NO-SUCH-HOST')['availability']=='no_match'

def test_utf8_payload_limit(corpus):
    from vinsoc_data.soc_corpus import canonical
    s=skill(corpus);result=s.search_events()
    assert len(canonical(result).encode())<=20000 and len(result['rows'])<=20
    with pytest.raises(ValueError):s._bound([{'text':'界'*8000}],available=True)

def test_unsupported_filter_rejected(corpus):
    s=skill(corpus)
    for limit in (True,0,21):
        with pytest.raises(ValueError):s.search_events(limit=limit)
    with pytest.raises(ValueError):s.get_context(resource='asset',user='alice')
    with pytest.raises(ValueError):s.get_context(resource='ground_truth')
