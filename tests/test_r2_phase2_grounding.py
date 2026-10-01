"""Counterexamples use synthetic catalogs, arbitrary source names and quantities."""
import json
import pytest

from tests.r2_remediation_fixtures import FakeClient, response, call, case, make_tools


def tools_fixture(tmp_path):
    old, manifest = make_tools(tmp_path)
    try:
        from evaluation.r2_phase2.grounding import Phase2Tools
    except ModuleNotFoundError:
        return old
    return Phase2Tools(old.snapshot_path, manifest)


def test_numeric_constraints_do_not_require_catalog_search(tmp_path):
    tools = tools_fixture(tmp_path)
    result = tools.value_search({'query': '12', 'column': 'n'})
    assert result['ok'] and result['resolution'] == 'typed_constraint_not_catalog_value'
    assert result['matches'] == []


def test_source_metadata_is_grounded_by_controller_without_model_search(tmp_path):
    tools = tools_fixture(tmp_path)
    try:
        from evaluation.r2_phase2.runner import run_case
    except ModuleNotFoundError:
        from evaluation.dualsql_lite_ctu_gpt5_v2.runner import run_case
    payload = {'tables': [{'table': 'network_flows', 'columns': ['source_dataset']}], 'grounded_values': []}
    client = FakeClient([response(json.dumps(payload)), response('SELECT count(*) FROM network_flows')])
    record = run_case(case('Count Capture Group 7 flows'), 'E3', tools, client, tools.schema_context())
    assert record['error_category'] == 'OK'
    assert record['linked_schema']['source_metadata'][0]['value'] == 'beta'
    assert len(record['usage']) == 2


def test_probe_direct_column_gets_lineage_but_aggregate_does_not(tmp_path):
    tools = tools_fixture(tmp_path)
    r = tools.sql_probe({'sql': 'SELECT protocol, count(*) AS total FROM network_flows GROUP BY protocol'})
    assert r['ok']
    assert r['column_provenance']['protocol'] == {'table': 'network_flows', 'column': 'protocol', 'type': 'VARCHAR'}
    assert 'total' not in r['column_provenance']
    assert {(v['column'],v['value']) for v in r['matches']} == {('protocol','TCP'),('protocol','UDP')}


def test_probe_computed_literal_is_not_provenance(tmp_path):
    tools = tools_fixture(tmp_path)
    r = tools.sql_probe({'sql': "SELECT 'invented' AS label FROM network_flows"})
    assert r['ok'] and not r['matches'] and not r['column_provenance']


def test_truncated_search_is_an_open_domain_with_operator_witness(tmp_path):
    tools = tools_fixture(tmp_path)
    # Simulate a large typed catalog, independent of dev rows or case IDs.
    tools.catalog.extend({'table':'network_flows','column':'label','value':f'prefix-family-{i}'} for i in range(80))
    r = tools.value_search({'query':'prefix-family', 'column':'label'})
    assert r['ok'] and r['truncated'] and r['domain_complete'] is False
    assert r['grouping_predicates'][0]['operator'] == 'ILIKE'
    assert r['grouping_predicates'][0]['pattern'] == '%prefix-family%'
    assert r['grouping_predicates'][0]['witness']['value'].startswith('prefix-family')


def test_forged_probe_column_and_evidence_cannot_cross_handoff(tmp_path):
    tools = tools_fixture(tmp_path)
    try:
        from evaluation.r2_phase2.grounding import validate_link
    except ModuleNotFoundError:
        from evaluation.dualsql_lite_ctu_gpt5_v2.agents import validate_link
    r = tools.sql_probe({'sql':'SELECT protocol FROM network_flows'})
    event = {'tool':'sql_probe','arguments':{'sql':'SELECT protocol FROM network_flows'},'result':r}
    selected = [{'table':'network_flows','columns':['protocol']}]
    submitted = [{'table':'network_flows','column':'protocol','value':'TCP','evidence_id':r['evidence_id']}]
    valid = validate_link('Return TCP traffic', selected, [event], tools, submitted)
    assert valid['error'] is None
    forged = [dict(submitted[0], column='label')]
    assert validate_link('Return TCP traffic', selected, [event], tools, forged)['error'] == 'INVALID_TOOL_PROVENANCE'


def test_literals_are_classified_without_searching_numeric_or_time_domains(tmp_path):
    tools = tools_fixture(tmp_path)
    assert hasattr(tools, 'question_literals')
    literals = tools.question_literals("Count Group 5 where n > 99 since 2024-02-03T04:05:06 and label 'Example'")
    assert any(v['kind']=='numeric_constraint' and v['surface']=='99' for v in literals)
    assert any(v['kind']=='timestamp_constraint' for v in literals)
    assert any(v['kind']=='text_literal' and v['surface']=='Example' for v in literals)


def test_schema_context_declares_controller_owned_source_and_open_domains(tmp_path):
    tools = tools_fixture(tmp_path)
    context = tools.schema_context()
    assert 'source_metadata' in context and 'alpha' in context and 'beta' in context
    assert 'numeric_and_timestamp_constraints_require_catalog_search' in context
    assert 'false' in context


def test_unscoped_numeric_search_does_not_return_accidental_text_matches(tmp_path):
    tools = tools_fixture(tmp_path)
    result = tools.value_search({'query':'2'})
    assert result['resolution'] == 'typed_constraint_not_catalog_value' and not result['matches']


def test_duplicate_probe_aliases_cannot_misattribute_catalog_values(tmp_path):
    tools = tools_fixture(tmp_path)
    result = tools.sql_probe({'sql':'SELECT protocol AS v, label AS v FROM network_flows'})
    assert result['ok'] and 'v' not in result['column_provenance'] and not result['matches']


def test_new_controller_keeps_charged_usage_when_arguments_fail(tmp_path):
    from evaluation.r2_phase2.runner import run_case
    tools = tools_fixture(tmp_path)
    client = FakeClient([response(calls=[call(arguments='bad-json')])])
    result = run_case(case(), 'E3', tools, client, tools.schema_context())
    assert result['error_category']=='MALFORMED_TOOL_ARGUMENTS'
    assert result['attempted_calls']==result['response_count']==1
    assert result['usage'][0]['input_tokens']==10
    assert result['roles']['generator'] is None


def test_new_controller_does_not_reassign_source_intent_to_another_column(tmp_path):
    from evaluation.r2_phase2.runner import run_case
    tools = tools_fixture(tmp_path)
    client = FakeClient([response('{"tables":[{"table":"network_flows","columns":["label"]}],"grounded_values":[]}')])
    result = run_case(case('Count Capture Group 5 flows'), 'E3', tools, client, tools.schema_context())
    assert result['error_category']=='WRONG_COLUMN_FOR_INTENT' and result['roles']['generator'] is None


def test_grouping_operator_really_matches_casefolded_catalog_witness(tmp_path):
    import duckdb
    tools = tools_fixture(tmp_path)
    predicate = tools.value_search({'query':'botnet','column':'label'})['grouping_predicates'][0]
    with duckdb.connect(':memory:') as connection:
        assert connection.execute('SELECT ? ' + predicate['operator'] + " ? ESCAPE '\\'",
                                  [predicate['witness']['value'],predicate['pattern']]).fetchone()[0]


def test_low_cardinality_domain_fallback_is_observed_provenance(tmp_path):
    from evaluation.r2_phase2.grounding import validate_link
    tools = tools_fixture(tmp_path)
    result = tools.value_search({'query':'no-match','column':'protocol'})
    selected=[{'table':'network_flows','columns':['protocol']}]
    submitted=[{'table':'network_flows','column':'protocol','value':'TCP'}]
    event={'tool':'value_search','arguments':{'query':'no-match','column':'protocol'},'result':result}
    assert validate_link('Return TCP',selected,[event],tools,submitted)['error'] is None


@pytest.mark.parametrize('sql',[
    "SELECT *, protocol AS label FROM network_flows WHERE source_dataset='alpha'",
    "SELECT protocol FROM network_flows AS f(source_dataset,protocol,label,n) WHERE source_dataset='alpha'",
])
def test_wildcard_or_relation_column_alias_cannot_certify_wrong_lineage(tmp_path,sql):
    import duckdb
    from evaluation.r2_phase2.grounding import Phase2Tools
    old,manifest=make_tools(tmp_path)
    with duckdb.connect(str(old.snapshot_path)) as connection:
        connection.execute("UPDATE network_flows SET label='TCP',protocol='UDP' WHERE source_dataset='alpha'")
        connection.execute("UPDATE network_flows SET protocol='TCP' WHERE source_dataset='beta'")
    tools=Phase2Tools(old.snapshot_path,manifest)
    result=tools.sql_probe({'sql':sql})
    assert result['ok'] and result['column_provenance']=={} and result['matches']==[]
