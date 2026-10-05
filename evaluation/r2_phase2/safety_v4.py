"""Narrow native ESCAPE adapter; the archived AST policy remains unchanged."""
from __future__ import annotations

import json

from evaluation.r2_phase2 import safety as archived

POLICY_IDENTITY = 'r2_snapshot_select_ast_typed_v4'


def parse_select(sql: str) -> dict:
    """The archived single-SELECT parse contract, with native UTF-8 positions."""
    import duckdb
    if not isinstance(sql, str) or not sql.strip() or len(sql) > 20000:
        archived._reject()
    try:
        encoded = sql.encode('utf-8')
        tokens = duckdb.tokenize(sql)
        semicolons = [i for i, (position, kind) in enumerate(tokens)
                      if kind == duckdb.token_type.operator and encoded[position:position + 1] == b';']
        if semicolons and (len(semicolons) != 1 or semicolons[0] != len(tokens) - 1):
            archived._reject()
        with duckdb.connect(':memory:', config=archived.CONNECTION_CONFIG) as connection:
            parsed = json.loads(connection.execute('SELECT json_serialize_sql(?)', [sql]).fetchone()[0])
        if parsed.get('error') or len(parsed.get('statements', [])) != 1:
            archived._reject()
        if parsed['statements'][0]['node'].get('type') not in {'SELECT_NODE', 'SET_OPERATION_NODE'}:
            archived._reject()
        return parsed
    except archived.QuerySafetyError:
        raise
    except Exception:
        archived._reject()


def validate_sql(sql: str) -> str:
    import duckdb
    parsed = parse_select(sql)
    try:
        # DuckDB locations/token positions refer to UTF-8 bytes, not Python characters.
        encoded = sql.encode('utf-8')
        tokens = duckdb.tokenize(sql)
        keywords = {position: encoded[position:(tokens[i + 1][0] if i + 1 < len(tokens) else len(encoded))].strip().lower()
                    for i, (position, kind) in enumerate(tokens) if kind == duckdb.token_type.keyword}
        for node in archived.walk_ast(parsed):
            operator = {'like_escape': b'like', 'ilike_escape': b'ilike'}.get(node.get('function_name'))
            if (node.get('class') == 'FUNCTION' and operator and node.get('schema') == 'main'
                    and not node.get('catalog') and len(node.get('children', [])) == 3
                    and keywords.get(node.get('query_location')) == operator):
                # Only parser-generated LIKE/ILIKE ... ESCAPE, never main.function(...).
                node['schema'] = ''
        archived._validate_tree(parsed)
        with duckdb.connect(':memory:', config=archived.CONNECTION_CONFIG) as connection:
            # Native deserialization must receive actual UTF-8, not JSON \u escapes.
            return connection.execute('SELECT json_deserialize_sql(?)', [json.dumps(parsed, ensure_ascii=False)]).fetchone()[0]
    except archived.QuerySafetyError:
        raise
    except Exception:
        archived._reject()


class Phase2V4Snapshot(archived.Phase2Snapshot):
    policy_identity = POLICY_IDENTITY

    def query(self, sql: str, parameters=None):
        statement = validate_sql(sql)
        # Reuse the archived read-only connection/config and result contract;
        # avoid its ASCII JSON roundtrip, which corrupts non-ASCII literal bytes.
        with self._connect() as connection:
            try:
                cursor = connection.execute(
                    f'SELECT * FROM ({statement}) AS vinsoc_result LIMIT {self.row_limit + 1}', parameters or [])
                columns = tuple(item[0] for item in cursor.description)
                rows = [dict(zip(columns, row)) for row in cursor.fetchall()]
            except Exception as error:
                raise RuntimeError('Snapshot SELECT execution failed') from error
        return archived.QueryResult(columns, rows[:self.row_limit], len(rows) > self.row_limit)
