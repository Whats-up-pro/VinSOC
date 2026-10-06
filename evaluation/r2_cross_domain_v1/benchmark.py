"""Evaluator-only reference DTO and conservative pre-inference dialect audit."""
from contextlib import closing
from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
import sqlite3

import duckdb
from sqlglot import exp, parse_one
from sqlglot.optimizer.scope import traverse_scope

from .data import DatabaseContext, _quote
from .models import RuntimeCase
from .safety import validate_sql
from .semantic_scoring import canonical_rows, compare_results


class BenchmarkError(ValueError):
    pass


@dataclass(frozen=True)
class ReferenceCase:
    case_id: str
    database_id: str
    question: str
    gold_sql: str
    comparator: str
    difficulty: str
    features: list
    family_id: str
    accepted_links: list

    def runtime(self):
        return RuntimeCase(self.case_id, self.database_id, self.question)


def adapt_sqlite_gold(sql, schema):
    """Translate only proved rules; reject SQLite's arbitrary bare group columns.

    Callers must verify actual declared PK uniqueness/non-nullness before using
    functional dependencies. Adding dependent columns to GROUP BY is safe under
    those constraints; ANY_VALUE would conceal unsupported semantics and is banned.
    """
    tree = parse_one(sql, read="sqlite")
    catalog = {table["name"].casefold(): table for table in schema}
    transformations = []
    scope_types = {}
    for scope in traverse_scope(tree):
        if not isinstance(scope.expression, exp.Select):
            continue
        sources = {alias.casefold(): catalog[source.name.casefold()] for alias, source in scope.sources.items()
                   if isinstance(source, exp.Table) and source.name.casefold() in catalog}

        def resolve(column, sources=sources):
            aliases = [column.table.casefold()] if column.table else list(sources)
            matches = [(alias, item["name"].casefold()) for alias in aliases if alias in sources
                       for item in sources[alias]["columns"] if item["name"].casefold() == column.name.casefold()]
            return matches[0] if len(matches) == 1 else None

        def declared_type(column, resolver=resolve, sources=sources):
            item = resolver(column)
            if item is None:
                return None
            return next(entry.get("duckdb_type") for entry in sources[item[0]]["columns"] if entry["name"].casefold() == item[1])

        scope_types[id(scope.expression)] = declared_type

        for column in list(scope.columns):
            if not column.table and column.this.args.get("quoted") and resolve(column) is None:
                column.replace(exp.Literal.string(column.name))
                transformations.append({"rule": "sqlite_unresolved_double_quoted_string", "literal": column.name})

        # SQLite TEXT affinity converts a numeric literal to text before comparison.
        # Do not let DuckDB choose a different implicit numeric comparison.
        for predicate in scope.expression.walk(prune=lambda node: node is not scope.expression and isinstance(node, (exp.Select, exp.Subquery))):
            if isinstance(predicate, (exp.EQ, exp.NEQ, exp.GT, exp.GTE, exp.LT, exp.LTE)):
                left, right = predicate.this, predicate.expression
                for column, literal in ((left, right), (right, left)):
                    if isinstance(column, exp.Column) and declared_type(column) == "VARCHAR" and isinstance(literal, exp.Literal) and not literal.is_string:
                        literal.replace(exp.Literal.string(literal.this))
                        transformations.append({"rule": "sqlite_text_affinity_numeric_literal", "literal": literal.this})
            if isinstance(predicate, exp.In) and isinstance(predicate.this, exp.Column):
                query = predicate.args.get("query")
                inner = query.this if isinstance(query, exp.Subquery) else query
                if isinstance(inner, exp.Select) and len(inner.expressions) == 1 and isinstance(inner.expressions[0], exp.Column):
                    getter = scope_types.get(id(inner))
                    lhs_type, rhs_type = declared_type(predicate.this), getter(inner.expressions[0]) if getter else None
                    if lhs_type and rhs_type and (lhs_type == "VARCHAR") != (rhs_type == "VARCHAR"):
                        raise BenchmarkError("UNSUPPORTED_MIXED_AFFINITY")

        group = scope.expression.args.get("group")
        if group is None:
            continue
        known = {resolve(column) for column in group.expressions if isinstance(column, exp.Column)} - {None}
        equals = []

        def unconditional_equalities(node):
            if isinstance(node, exp.And):
                unconditional_equalities(node.this)
                unconditional_equalities(node.expression)
            elif isinstance(node, exp.EQ) and isinstance(node.this, exp.Column) and isinstance(node.expression, exp.Column):
                left, right = resolve(node.this), resolve(node.expression)
                if left is not None and right is not None:
                    equals.append((left, right))

        for join in scope.expression.args.get("joins") or []:
            # Outer-join null extension does not establish the same dependency.
            if not join.args.get("side"):
                unconditional_equalities(join.args.get("on"))
        where = scope.expression.args.get("where")
        if where:
            unconditional_equalities(where.this)
        changed = True
        while changed:
            before = set(known)
            for left, right in equals:
                if left in known:
                    known.add(right)
                if right in known:
                    known.add(left)
            for alias, table in sources.items():
                keys = {(alias, column["name"].casefold()) for column in table["columns"] if column.get("primary_key_position")}
                if keys and keys <= known:
                    known.update((alias, column["name"].casefold()) for column in table["columns"])
            changed = before != known

        roots = list(scope.expression.expressions)
        for key in ("having", "order"):
            if scope.expression.args.get(key):
                roots.append(scope.expression.args[key])
        added = set()
        grouped_sql = {item.sql(dialect="duckdb") for item in group.expressions}
        for root in roots:
            for column in root.find_all(exp.Column):
                node = column.parent
                protected = False
                while node is not None and node is not scope.expression:
                    if isinstance(node, (exp.AggFunc, exp.Subquery, exp.Select)):
                        protected = True
                        break
                    node = node.parent
                if protected or column.sql(dialect="duckdb") in grouped_sql:
                    continue
                resolved = resolve(column)
                if resolved is None or resolved not in known:
                    raise BenchmarkError("UNPROVEN_BARE_GROUP_COLUMN")
                if resolved not in added:
                    group.append("expressions", column.copy())
                    added.add(resolved)
                    transformations.append({"rule": "declared_key_dependent_group_column", "column": column.sql(dialect="duckdb")})
    return {"sql": tree.sql(dialect="duckdb"), "transformations": transformations}


def _verify_primary_keys(source, context):
    with closing(sqlite3.connect(f"file:{Path(source).resolve().as_posix()}?mode=ro", uri=True)) as conn:
        for table in context.identity["schema"]:
            keys = [column["name"] for column in table["columns"] if column.get("primary_key_position")]
            if not keys:
                continue
            null_predicate = " OR ".join(_quote(key) + " IS NULL" for key in keys)
            columns = ",".join(_quote(key) for key in keys)
            if conn.execute(f"SELECT 1 FROM {_quote(table['name'])} WHERE {null_predicate} LIMIT 1").fetchone():
                raise BenchmarkError("DECLARED_PRIMARY_KEY_HAS_NULL")
            if conn.execute(f"SELECT 1 FROM {_quote(table['name'])} GROUP BY {columns} HAVING COUNT(*)>1 LIMIT 1").fetchone():
                raise BenchmarkError("DECLARED_PRIMARY_KEY_NOT_UNIQUE")


def _verify_limit_determinism(sql, connection):
    tree = parse_one(sql, read="duckdb")
    limit = tree.args.get("limit")
    order = tree.args.get("order")
    if limit is None and order is None:
        return
    if not isinstance(tree, exp.Select) or tree.args.get("offset") or any(isinstance(item, exp.Star) for item in tree.expressions):
        raise BenchmarkError("UNSUPPORTED_LIMIT_STRUCTURE")
    count = None
    if limit is not None:
        quantity = limit.expression
        if not isinstance(quantity, exp.Literal) or quantity.is_string or not quantity.this.isdigit():
            raise BenchmarkError("UNSUPPORTED_LIMIT_QUANTITY")
        count = int(quantity.this)
        if count <= 0:
            raise BenchmarkError("NONPOSITIVE_LIMIT")
    tree.set("limit", None)
    width = len(tree.expressions)
    if order is None:
        if len(connection.execute(tree.sql(dialect="duckdb")).fetchall()) > count:
            raise BenchmarkError("LIMIT_WITHOUT_ORDER")
        return
    if tree.args.get("distinct"):
        raise BenchmarkError("DISTINCT_LIMIT_REQUIRES_SEPARATE_TIE_PROOF")
    originals = [item.copy() for item in tree.expressions]
    aliases = {item.alias.casefold(): item.this for item in originals if isinstance(item, exp.Alias)}
    for i, ordered in enumerate(order.expressions):
        expression = ordered.this.copy()
        if isinstance(expression, exp.Literal) and expression.this.isdigit():
            ordinal = int(expression.this)
            if ordinal < 1 or ordinal > width:
                raise BenchmarkError("INVALID_ORDER_ORDINAL")
            expression = originals[ordinal-1].copy()
            if isinstance(expression, exp.Alias):
                expression = expression.this
        elif isinstance(expression, exp.Column) and not expression.table and expression.name.casefold() in aliases:
            expression = aliases[expression.name.casefold()].copy()
        tree.append("expressions", exp.alias_(expression, "__audit_order_" + str(i), quoted=True))
    rows = connection.execute(tree.sql(dialect="duckdb")).fetchall()
    if count is not None and len(rows) > count and canonical_rows([rows[count-1][width:]]) == canonical_rows([rows[count][width:]]):
        # All members of the boundary tie must have the same visible projection;
        # checking only two adjacent rows could miss a third distinct candidate.
        tied = [row[:width] for row in rows if canonical_rows([row[width:]]) == canonical_rows([rows[count-1][width:]])]
        if len(set(canonical_rows(tied))) > 1:
            raise BenchmarkError("AMBIGUOUS_LIMIT_TIE")
    visible_rows = rows if count is None else rows[:count]
    seen = {}
    for row in visible_rows:
        key = canonical_rows([row[width:]])[0]
        projection = canonical_rows([row[:width]])[0]
        if key in seen and seen[key] != projection:
            raise BenchmarkError("AMBIGUOUS_ORDER_TIE")
        seen[key] = projection


def validate_gold_parity(original_sql, source_path, context: DatabaseContext, comparator):
    source = Path(source_path)
    if hashlib.sha256(source.read_bytes()).hexdigest() != context.identity["source_sha256"]:
        raise BenchmarkError("SOURCE_SQLITE_IDENTITY_MISMATCH")
    _verify_primary_keys(source, context)
    adapted = adapt_sqlite_gold(original_sql, context.identity["schema"])
    validate_sql(adapted["sql"], context)
    with closing(sqlite3.connect(f"file:{source.resolve().as_posix()}?mode=ro", uri=True)) as conn:
        conn.enable_load_extension(False)
        conn.execute("PRAGMA query_only=ON")
        conn.set_progress_handler(lambda: 1, 2000000)
        try:
            original_rows = conn.execute(original_sql).fetchall()
        except sqlite3.Error as error:
            raise BenchmarkError("ORIGINAL_GOLD_EXECUTION_ERROR:" + type(error).__name__) from error
    with duckdb.connect(str(context.snapshot_path), read_only=True, config={"enable_external_access": False, "threads": 1}) as conn:
        try:
            _verify_limit_determinism(adapted["sql"], conn)
            adapted_rows = conn.execute(adapted["sql"]).fetchall()
        except duckdb.Error as error:
            raise BenchmarkError("ADAPTED_GOLD_EXECUTION_ERROR:" + type(error).__name__) from error
    parity = compare_results(adapted_rows, original_rows, comparator)
    return {"original_sql": original_sql, "adapted_sql": adapted["sql"], "transformations": adapted["transformations"],
            "comparator": comparator, "parity": parity, "sqlite_row_count": len(original_rows), "duckdb_row_count": len(adapted_rows),
            "sqlite_result_sha256": hashlib.sha256(json.dumps(canonical_rows(original_rows), sort_keys=True).encode()).hexdigest(),
            "duckdb_result_sha256": hashlib.sha256(json.dumps(canonical_rows(adapted_rows), sort_keys=True).encode()).hexdigest(),
            "sample_original_rows": [list(row) for row in original_rows[:3]], "sample_adapted_rows": [list(row) for row in adapted_rows[:3]],
            "primary_keys_verified_nonnull_unique": True,
            "semantic_scope": "Observed base-instance result parity only; adversarial semantic instances remain required"}
