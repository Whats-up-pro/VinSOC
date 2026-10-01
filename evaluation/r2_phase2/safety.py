"""Native DuckDB AST boundary: one SELECT, verified relations, pure functions."""
from __future__ import annotations

import json
from pathlib import Path

from vinsoc_data.duckdb_store import DuckDBSnapshot, QueryResult, QuerySafetyError

POLICY_IDENTITY = 'r2_snapshot_select_ast_v2'
CONNECTION_CONFIG = {'enable_external_access': 'false', 'autoload_known_extensions': 'false',
                     'autoinstall_known_extensions': 'false'}
PURE_FUNCTIONS = frozenset({
    'count', 'count_star', 'sum', 'min', 'max', 'avg', 'lower', 'upper', 'length',
    'trim', 'ltrim', 'rtrim', 'substring', 'substr', 'coalesce', 'ifnull', 'nullif',
    'abs', 'round', 'floor', 'ceil', 'ceiling', 'date_trunc', 'date_part', 'strftime',
    'strptime', 'try_strptime', 'concat', 'concat_ws', 'starts_with', 'ends_with',
    'contains', 'like_escape', 'ilike_escape', '~~', '!~~', '~~*', '!~~*',
    '+', '-', '*', '/', '//', '%', '**', '||', 'row_number', 'rank', 'dense_rank',
})


def _reject():
    raise QuerySafetyError('SQL outside versioned snapshot SELECT policy')


def walk_ast(value):
    if isinstance(value, dict):
        yield value
        for child in value.values():
            yield from walk_ast(child)
    elif isinstance(value, list):
        for child in value:
            yield from walk_ast(child)


def parse_select(sql: str) -> dict:
    """Parse only; never bind/execute the supplied statement or load extensions."""
    import duckdb
    if not isinstance(sql, str) or not sql.strip() or len(sql) > 20000:
        _reject()
    try:
        tokens = duckdb.tokenize(sql)
        semicolons = [i for i, (position, kind) in enumerate(tokens)
                      if kind == duckdb.token_type.operator and sql[position] == ';']
        if semicolons and (len(semicolons) != 1 or semicolons[0] != len(tokens) - 1):
            _reject()
        with duckdb.connect(':memory:', config=CONNECTION_CONFIG) as connection:
            parsed = json.loads(connection.execute('SELECT json_serialize_sql(?)', [sql]).fetchone()[0])
        if parsed.get('error') or len(parsed.get('statements', [])) != 1:
            _reject()
        node = parsed['statements'][0]['node']
        if node.get('type') not in {'SELECT_NODE', 'SET_OPERATION_NODE'}:
            _reject()
        return parsed
    except QuerySafetyError:
        raise
    except Exception:
        _reject()


def _validate_tree(value, scope=frozenset()):
    if isinstance(value, list):
        for item in value:
            _validate_tree(item, scope)
    elif isinstance(value, dict):
        ctes = value.get('cte_map', {}).get('map', [])
        local = scope | {entry['key'].casefold() for entry in ctes}
        node_type = value.get('type', '')
        if not isinstance(node_type, str):
            node_type = ''  # literal type descriptors are data, not AST nodes
        if node_type.endswith('_NODE') and node_type not in {'SELECT_NODE', 'SET_OPERATION_NODE'}:
            _reject()
        if node_type == 'BASE_TABLE':
            if (value.get('schema_name') or value.get('catalog_name') or value.get('at_clause')
                    or value.get('table_name', '').casefold() not in {'network_flows'} | local):
                _reject()
        if node_type in {'TABLE_FUNCTION', 'PIVOT', 'EXPRESSION_LIST', 'SHOW_REF'}:
            _reject()
        if value.get('class') in {'FUNCTION', 'WINDOW'}:
            if (value.get('schema') or value.get('catalog') or value.get('export_state')
                    or value.get('function_name', '').casefold() not in PURE_FUNCTIONS):
                _reject()
        for child in value.values():
            _validate_tree(child, local)


def validate_sql(sql: str) -> str:
    import duckdb
    parsed = parse_select(sql)
    try:
        _validate_tree(parsed)
        with duckdb.connect(':memory:', config=CONNECTION_CONFIG) as connection:
            return connection.execute('SELECT json_deserialize_sql(?)', [json.dumps(parsed)]).fetchone()[0]
    except QuerySafetyError:
        raise
    except Exception:
        _reject()


class Phase2Snapshot(DuckDBSnapshot):
    policy_identity = POLICY_IDENTITY

    def _connect(self):
        import duckdb
        return duckdb.connect(str(self.database_path), read_only=True, config=CONNECTION_CONFIG)

    def query(self, sql: str, parameters=None):
        statement = validate_sql(sql)
        with self._connect() as connection:
            try:
                cursor = connection.execute(
                    f'SELECT * FROM ({statement}) AS vinsoc_result LIMIT {self.row_limit + 1}', parameters or [])
                columns = tuple(item[0] for item in cursor.description)
                rows = [dict(zip(columns, row)) for row in cursor.fetchall()]
            except Exception as error:
                raise RuntimeError('Snapshot SELECT execution failed') from error
        return QueryResult(columns, rows[:self.row_limit], len(rows) > self.row_limit)
