"""Safety boundary regressions: new policy must accept layout, reject effects."""
import pytest

from vinsoc_data.duckdb_store import QuerySafetyError

from evaluation.r2_phase2.safety import validate_sql


@pytest.mark.parametrize('sql', [
    '  SELECT * FROM network_flows', '\n\tSELECT\n* FROM network_flows',
    'SELECT\t* FROM network_flows;', 'SELECT * FROM network_flows;  ',
    "SELECT 'DROP; read_csv' AS label FROM network_flows",
    'SELECT "protocol" FROM "network_flows"',
    '-- SELECT layout\nSELECT * FROM network_flows',
])
def test_read_only_layout_and_literals_are_not_rejected(sql):
    assert validate_sql(sql)


@pytest.mark.parametrize('sql', [
    'SELECT * FROM network_flows; SELECT 2', 'SELECT 1;;',
    'INSERT INTO network_flows VALUES (1)', 'UPDATE network_flows SET label=\'a\'',
    'DELETE FROM network_flows', 'DROP TABLE network_flows',
    "ATTACH 'another.db'", "COPY network_flows TO 'x.csv'", 'INSTALL httpfs', 'LOAD httpfs',
    "SELECT * FROM read_csv('x.csv')", 'SELECT * FROM information_schema.tables',
    "SELECT getenv('HOME')", "SELECT query('DELETE FROM network_flows')",
    "SELECT * FROM query_table('network_flows')", 'SELECT * FROM other.network_flows',
    'SELECT * FROM (SELECT * FROM secret_table) x',
    'SELECT * FROM network_flows UNION SELECT * FROM secret_table',
    'SELECT * FROM network_flows WHERE EXISTS (SELECT * FROM secret_table)',
    'SELECT custom_function(protocol) FROM network_flows', '', 'SELECT FROM',
])
def test_nonselect_multiple_and_external_access_fail_closed(sql):
    with pytest.raises(QuerySafetyError):
        validate_sql(sql)
