import copy
import json
import pytest
from tests.soc_support import feature, sources, corpus, raw_case

def test_pin_and_digest_required(tmp_path):
    m = feature('vinsoc_data.soc_corpus')
    with pytest.raises(ValueError):
        m.verify_sources(tmp_path, {'revision': 'main', 'files': {}})

def test_no_oracle_fields(corpus):
    repository, receipt = corpus
    assert receipt['cases'] == {'test': 5031, 'validation': 4984}
    assert receipt['imported_records'] > 10015
    for scenario in repository.scenario_ids()[:50]:
        visible = json.dumps([repository.input_for(scenario), repository.records(scenario, 'events')])
        for key in ('decisive', 'ground_truth', 'success', 'verdict', 'archetype', 'technique_hints'):
            assert f'"{key}":' not in visible
    assert repository.tables() == {'case_inputs', 'observations', 'source_availability', 'ioc_index', 'corpus_metadata'}

def test_cross_case_native_id(sources):
    m = feature('vinsoc_data.soc_corpus')
    row = raw_case(sources)
    other = copy.deepcopy(row); other['scenario_id'] = 'OTHER-SOURCE-CASE'
    one = m.extract_case(row, split='test', file_sha256='source-digest')
    two = m.extract_case(other, split='test', file_sha256='source-digest')
    assert one['observations'] and two['observations']
    assert {r['source_record_id'] for r in one['observations']}.isdisjoint({r['source_record_id'] for r in two['observations']})

def test_conflicting_native_id_quarantined(sources):
    m = feature('vinsoc_data.soc_corpus')
    row = raw_case(sources)
    trace = json.loads(row['trace'])
    payload = next(x for x in trace if x['role'] == 'tool' and '"events"' in x['content'])
    data = json.loads(payload['content'])
    native = data['events'][0]['event_id']
    conflict = copy.deepcopy(data['events'][0]); conflict['message'] = 'Conflicting unit-test input'
    data['events'].append(conflict); payload['content'] = json.dumps(data); row['trace'] = json.dumps(trace)
    result = m.extract_case(row, split='test', file_sha256='source-digest')
    assert any(x['reason'] == 'CONFLICTING_NATIVE_KEY' for x in result['quarantine'])
    assert all(r['data'].get('event_id') != native for r in result['observations'])
