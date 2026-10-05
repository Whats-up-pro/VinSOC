"""Real evaluator counterexamples; these synthetic fixtures are NOT model scores."""
from dataclasses import replace

import pytest

from evaluation.r2_phase2.scoring import score_prediction
from tests.r2_remediation_fixtures import case
from tests.r2_phase2_semantic_fixtures import semantic_tools, predicate_sql, semantic_snapshot as Phase2Snapshot


@pytest.fixture
def tools(tmp_path, monkeypatch):
    import openai
    import agent.provider
    def forbidden(*args, **kwargs):
        pytest.fail('synthetic offline fixture tried creating a live provider')
    monkeypatch.setattr(openai, 'OpenAI', forbidden)
    monkeypatch.setattr(openai, 'AsyncOpenAI', forbidden)
    monkeypatch.setattr(agent.provider, 'create_provider', forbidden)
    return semantic_tools(tmp_path)


COUNTEREXAMPLES = [
    ('source_filter', "SELECT COUNT(*) FROM network_flows WHERE label='Family-A' AND source_dataset='alpha'",
     "SELECT COUNT(*) FROM network_flows WHERE label='Family-A'", [[2]]),
    ('prefix_not_contains', "SELECT COUNT(*) FROM network_flows WHERE label LIKE 'Family-%'",
     "SELECT COUNT(*) FROM network_flows WHERE label LIKE '%Family-%'", [[4]]),
    ('mixed_case', "SELECT COUNT(*) FROM network_flows WHERE label ILIKE 'Family-%'",
     "SELECT COUNT(*) FROM network_flows WHERE label LIKE 'Family-%'", [[5]]),
    ('literal_wildcards', r"SELECT COUNT(*) FROM network_flows WHERE label LIKE 'rack\%\_%' ESCAPE '\'",
     "SELECT COUNT(*) FROM network_flows WHERE label LIKE 'rack%_%'", [[1]]),
    ('mixed_case_literal_wildcards', r"SELECT COUNT(*) FROM network_flows WHERE label ILIKE 'rack\%\_%' ESCAPE '\'",
     "SELECT COUNT(*) FROM network_flows WHERE label ILIKE 'rack%_%'", [[2]]),
    ('multibyte_prior_literal', r"SELECT COUNT(*) FROM network_flows WHERE 'é'='é' AND label LIKE 'rack\%\_%' ESCAPE '\'",
     "SELECT COUNT(*) FROM network_flows WHERE 'é'='é' AND label LIKE 'rack%_%'", [[1]]),
    ('distinct', "SELECT COUNT(DISTINCT target) FROM network_flows WHERE source_dataset='alpha'",
     "SELECT COUNT(target) FROM network_flows WHERE source_dataset='alpha'", [[5]]),
    ('time_lower_inclusive', "SELECT COUNT(*) FROM network_flows WHERE source_dataset='alpha' AND event_time >= TIMESTAMP '2024-02-03 04:05:06' AND event_time < TIMESTAMP '2024-02-03 04:05:07'",
     "SELECT COUNT(*) FROM network_flows WHERE source_dataset='alpha' AND event_time > TIMESTAMP '2024-02-03 04:05:06' AND event_time < TIMESTAMP '2024-02-03 04:05:07'", [[6]]),
    ('time_upper_exclusive', "SELECT COUNT(*) FROM network_flows WHERE source_dataset='alpha' AND event_time >= TIMESTAMP '2024-02-03 04:05:06' AND event_time < TIMESTAMP '2024-02-03 04:05:07'",
     "SELECT COUNT(*) FROM network_flows WHERE source_dataset='alpha' AND event_time >= TIMESTAMP '2024-02-03 04:05:06' AND event_time <= TIMESTAMP '2024-02-03 04:05:07'", [[6]]),
    ('boolean_precedence', "SELECT COUNT(*) FROM network_flows WHERE (protocol='TCP' OR protocol='UDP') AND amount > 3",
     "SELECT COUNT(*) FROM network_flows WHERE protocol='TCP' OR protocol='UDP' AND amount > 3", [[6]]),
    ('top_k_tie', 'SELECT code, COUNT(*) AS n FROM network_flows GROUP BY code ORDER BY n DESC, code ASC LIMIT 2',
     'SELECT code, COUNT(*) AS n FROM network_flows GROUP BY code ORDER BY n DESC, code DESC LIMIT 2', [[4, 3], [9, 3]]),
]


@pytest.mark.parametrize('feature,gold,wrong,expected', COUNTEREXAMPLES, ids=[c[0] for c in COUNTEREXAMPLES])
def test_executable_semantic_mutation_is_result_mismatch(tools, feature, gold, wrong, expected):
    snapshot = Phase2Snapshot(tools.snapshot_path)
    comparator = 'ordered_rows' if feature == 'top_k_tie' else 'scalar'
    fixture_case = case(f'Synthetic counterexample: {feature}', gold, comparator)
    # Independently hand-counted fixture results, not an expectation computed by the scorer.
    assert [list(row.values()) for row in snapshot.query(gold).rows] == expected
    record = {'case_id': fixture_case.case_id, 'error_category': 'OK', 'final_sql': wrong}
    result = score_prediction(fixture_case, record, snapshot)
    assert result['validation_passed'] and result['syntax_valid'] and result['execution_success']
    assert result['execution_accurate'] is False
    assert result['pipeline_error_category'] == 'OK'
    assert result['scoring_error_category'] == 'RESULT_MISMATCH'


def test_ordered_rows_rejects_order_while_unordered_rows_accepts_same_set(tools):
    gold = 'SELECT code FROM network_flows GROUP BY code ORDER BY code ASC'
    reversed_order = 'SELECT code FROM network_flows GROUP BY code ORDER BY code DESC'
    ordered = case('Return category codes in ascending order', gold, 'ordered_rows')
    record = {'case_id': ordered.case_id, 'error_category': 'OK', 'final_sql': reversed_order}
    snapshot = Phase2Snapshot(tools.snapshot_path)
    assert [list(r.values()) for r in snapshot.query(gold).rows] == [[2], [4], [7], [9]]
    assert score_prediction(ordered, record, snapshot)['execution_accurate'] is False
    unordered = replace(ordered, result_comparator='unordered_rows')
    assert score_prediction(unordered, record, snapshot)['execution_accurate'] is True


@pytest.mark.parametrize('query,case_sensitive,gold', [
    ('Family-', True, "SELECT COUNT(*) FROM network_flows WHERE label LIKE 'Family-%'"),
    ('Family-', False, "SELECT COUNT(*) FROM network_flows WHERE label ILIKE 'Family-%'"),
    ('rack%_', False, r"SELECT COUNT(*) FROM network_flows WHERE label ILIKE 'rack\%\_%' ESCAPE '\'"),
])
def test_explicit_prefix_tool_predicate_scores_but_contains_fails(tools, query, case_sensitive, gold):
    prefix = tools.value_search({'column': 'label', 'query': query,
                                'match_mode': 'prefix', 'case_sensitive': case_sensitive})
    contains = tools.value_search({'column': 'label', 'query': query,
                                  'match_mode': 'contains', 'case_sensitive': case_sensitive})
    assert prefix['ok'] and contains['ok']
    assert prefix['matches'] and prefix['domain_complete'] is False
    fixture_case = case('Return literal prefix matches', gold)
    snapshot = Phase2Snapshot(tools.snapshot_path)
    record = {'case_id': fixture_case.case_id, 'error_category': 'OK'}
    good = score_prediction(fixture_case, {**record, 'final_sql': predicate_sql(prefix['grouping_predicates'][0])}, snapshot)
    bad = score_prediction(fixture_case, {**record, 'final_sql': predicate_sql(contains['grouping_predicates'][0])}, snapshot)
    assert good['execution_accurate'] is True
    assert bad['execution_success'] is True and bad['execution_accurate'] is False


@pytest.mark.parametrize('options', [{'match_mode': 'raw_sql'}, {'case_sensitive': 'false'}])
def test_bad_matching_contract_arguments_fail_closed(tools, options):
    assert tools.value_search({'column': 'label', 'query': 'Family-', **options})['ok'] is False


@pytest.mark.parametrize('function', ['main.like_escape', 'main.ilike_escape', 'main.count'])
def test_parser_escape_adapter_does_not_authorize_qualified_function_calls(tools, function):
    from vinsoc_data.duckdb_store import QuerySafetyError
    with pytest.raises(QuerySafetyError):
        Phase2Snapshot(tools.snapshot_path).query(f"SELECT {function}(label, 'rack%', '!') FROM network_flows")


def test_escape_adapter_preserves_non_ascii_stored_literal(tools):
    import duckdb
    # Mutation is confined to this test's synthetic fixture, never the CTU snapshot.
    with duckdb.connect(str(tools.snapshot_path)) as connection:
        connection.execute("UPDATE network_flows SET label='réseau-A' WHERE source_dataset='beta' AND label='Family-A'")
    snapshot = Phase2Snapshot(tools.snapshot_path)
    sql = r"SELECT COUNT(*) FROM network_flows WHERE label LIKE 'réseau-%' ESCAPE '\'"
    assert [list(row.values()) for row in snapshot.query(sql).rows] == [[1]]


@pytest.mark.parametrize('terminator', ['', ';', '; \n\t'])
def test_native_unicode_byte_positions_accept_single_statement_terminator(tools, terminator):
    snapshot = Phase2Snapshot(tools.snapshot_path)
    assert list(snapshot.query("SELECT 'é' AS literal" + terminator).rows[0].values()) == ['é']
    sql = r"SELECT COUNT(*) FROM network_flows WHERE 'é'='é' AND label LIKE 'rack\%\_%' ESCAPE '\'"
    assert [list(row.values()) for row in snapshot.query(sql + terminator).rows] == [[1]]


@pytest.mark.parametrize('sql', ["SELECT 'é'; SELECT 2", "SELECT 'é';;", "SELECT 'é'; DROP TABLE network_flows",
                                "COPY (SELECT 'é') TO '/tmp/forbidden'", "SELECT 'é' FROM main.network_flows"])
def test_utf8_parser_keeps_multi_statement_and_non_readonly_boundary_closed(tools, sql):
    from vinsoc_data.duckdb_store import QuerySafetyError
    with pytest.raises(QuerySafetyError):
        Phase2Snapshot(tools.snapshot_path).query(sql)


@pytest.mark.parametrize('mode', ['exact', 'prefix', 'contains'])
def test_search_unicode_witness_uses_actual_duckdb_predicate_semantics(tools, mode):
    import duckdb
    # A synthetic catalog includes a Unicode case-fold expansion and an ASCII peer.
    with duckdb.connect(str(tools.snapshot_path)) as connection:
        connection.execute("UPDATE network_flows SET label='Straße' WHERE source_dataset='beta' AND label='Family-A'")
        connection.execute("UPDATE network_flows SET label='STRASSE' WHERE label='Family-B'")
    from evaluation.r2_phase2.grounding import Phase2Tools
    tools = Phase2Tools(tools.snapshot_path, tools.snapshot_path.parent / 'synthetic_manifest.json')
    result = tools.value_search({'column': 'label', 'query': 'STRASSE', 'match_mode': mode,
                                 'case_sensitive': False})
    assert result['ok'] and result['matches']
    assert [m['value'] for m in result['matches']] == ['STRASSE']
    predicate = result['grouping_predicates'][0]
    fixture_case = case('Count the case-insensitive literal ASCII name',
                        "SELECT COUNT(*) FROM network_flows WHERE label ILIKE 'STRASSE'")
    snapshot = Phase2Snapshot(tools.snapshot_path)
    scored = score_prediction(fixture_case, {'case_id': fixture_case.case_id, 'error_category': 'OK',
                                            'final_sql': predicate_sql(predicate)}, snapshot)
    assert scored['execution_accurate'] is True
    witness = predicate['witness']['value'].replace("'", "''")
    statement = predicate_sql(predicate).replace('COUNT(*)', f"COUNT(*) FILTER (WHERE label='{witness}')")
    assert [list(row.values()) for row in snapshot.query(statement).rows] == [[1]]
