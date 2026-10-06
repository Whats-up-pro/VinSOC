"""Explicit synthetic instance builds and execution-based mutation diagnostics.

These fixtures are evaluator-only. They are not public source rows, model
predictions, official Spider test suites or a replacement for base-snapshot EX.
"""
from copy import deepcopy
import hashlib
import json
from pathlib import Path

import duckdb
from sqlglot import exp, parse_one

from .data import DatabaseContext, _logical_hash, _quote, _verify_duckdb_snapshot
from .safety import SafetyError, validate_sql
from .semantic_scoring import canonical_rows, compare_results
from .tools import DatabaseTools, ToolError


def build_fixture(spec, destination):
    destination = Path(destination)
    if destination.exists():
        raise ValueError("FIXTURE_ALREADY_EXISTS")
    if spec.get("fixture_only") is not True or type(spec.get("seed")) is not int:
        raise ValueError("EXPLICIT_SYNTHETIC_FIXTURE_REQUIRED")
    schema, relationships = deepcopy(spec["schema"]), deepcopy(spec["relationships"])
    if not schema or set(spec["rows"]) != {table["name"] for table in schema}:
        raise ValueError("FIXTURE_SCHEMA_ROWS_MISMATCH")
    destination.parent.mkdir(parents=True, exist_ok=True)
    with duckdb.connect(str(destination), config={"enable_external_access": False}) as connection:
        for table in schema:
            columns = table["columns"]
            if not columns or len({column["name"] for column in columns}) != len(columns):
                raise ValueError("FIXTURE_DUPLICATE_COLUMN")
            definitions = []
            for column in columns:
                kind = column["duckdb_type"]
                parsed_type = exp.DataType.build(kind, dialect="duckdb")
                if parsed_type.this.value not in {"BIGINT", "VARCHAR", "TEXT", "DOUBLE", "DECIMAL", "TIMESTAMP", "TIMESTAMPNTZ", "TIMESTAMPTZ", "DATE", "TIME", "INT", "SMALLINT", "BOOLEAN", "BINARY"}:
                    raise ValueError("FIXTURE_TYPE_NOT_SUPPORTED")
                if any(not isinstance(item.this, exp.Literal) or not item.this.this.isdigit() for item in parsed_type.expressions):
                    raise ValueError("FIXTURE_TYPE_NOT_SUPPORTED")
                datatype = parsed_type.sql(dialect="duckdb")
                definitions.append(_quote(column["name"]) + " " + datatype)
            connection.execute(f"CREATE TABLE {_quote(table['name'])} ({','.join(definitions)})")
            rows = spec["rows"][table["name"]]
            if len(rows) > 2000 or any(len(row) != len(columns) for row in rows):
                raise ValueError("FIXTURE_ROW_LIMIT_OR_WIDTH")
            if rows:
                connection.executemany(f"INSERT INTO {_quote(table['name'])} VALUES ({','.join('?' for _ in columns)})", rows)
        actual = {table["name"]: connection.execute(f"SELECT * FROM {_quote(table['name'])}").fetchall() for table in schema}
        for table in schema:
            columns = table["columns"]
            keys = [i for i, column in enumerate(columns) if column.get("primary_key_position")]
            values = [tuple(row[i] for i in keys) for row in actual[table["name"]]]
            if keys and (len(set(values)) != len(values) or any(None in value for value in values)):
                raise ValueError("FIXTURE_PRIMARY_KEY_INVALID")
            if any(column.get("not_null") and any(row[i] is None for row in actual[table["name"]]) for i, column in enumerate(columns)):
                raise ValueError("FIXTURE_NOT_NULL_INVALID")
        for edge in relationships:
            # Compare using the database's declared type coercion rather than
            # Python's int/string inequality (SQLite can declare mixed-affinity
            # FK edges; the registry preserves those physical types).
            child_table, parent_table = _quote(edge["from_table"]), _quote(edge["to_table"])
            child_column, parent_column = _quote(edge["from_column"]), _quote(edge["to_column"])
            invalid = connection.execute(f"SELECT 1 FROM {child_table} c WHERE c.{child_column} IS NOT NULL AND NOT EXISTS (SELECT 1 FROM {parent_table} p WHERE c.{child_column}=p.{parent_column}) LIMIT 1").fetchone()
            if invalid:
                raise ValueError("FIXTURE_FOREIGN_KEY_INVALID")
    logical = _logical_hash(spec["database_id"], schema, relationships, actual)
    _verify_duckdb_snapshot(destination, schema, spec["database_id"], logical, relationships)
    identity = {"schema": schema, "relationships": relationships, "logical_sha256": logical,
                "duckdb_binary_sha256": hashlib.sha256(destination.read_bytes()).hexdigest(),
                "identity_algorithm": "synthetic_fixture_v1", "fixture_only": True}
    spec_hash = hashlib.sha256(json.dumps(spec, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
    return {"instance_id": "fixture_" + spec_hash, "fixture_only": True, "seed": spec["seed"],
            "spec_sha256": spec_hash, "constraints_verified": True,
            "context": DatabaseContext(spec["database_id"], destination, identity)}


def generate_mutants(sql):
    tree = parse_one(sql, read="duckdb")
    nodes = list(tree.walk())
    candidates = []

    def edit(index, family, mutation):
        copy = tree.copy()
        target = list(copy.walk())[index]
        replacement = mutation(target)
        if target is copy and isinstance(replacement, exp.Expression):
            copy = replacement
        changed = copy.sql(dialect="duckdb")
        if changed != tree.sql(dialect="duckdb") and changed not in {item["sql"] for item in candidates}:
            candidates.append({"family": family, "sql": changed})

    for index, node in enumerate(nodes):
        if isinstance(node, exp.Select) and len(node.expressions) > 1:
            edit(index, "projection", lambda value: value.set("expressions", value.expressions[:-1]))
        if isinstance(node, exp.Select) and node.args.get("distinct"):
            edit(index, "distinct", lambda value: value.set("distinct", None))
        if isinstance(node, exp.Distinct) and isinstance(node.parent, exp.Count):
            edit(index, "distinct", lambda value: value.replace(value.expressions[0].copy()))
        if isinstance(node, exp.Where):
            edit(index, "missing_filter", lambda value: value.parent.set("where", None))
        if isinstance(node, exp.Having):
            edit(index, "group_having", lambda value: value.parent.set("having", None))
        if isinstance(node, (exp.And, exp.Or)):
            replacement = exp.Or if isinstance(node, exp.And) else exp.And
            edit(index, "boolean", lambda value, replacement=replacement: value.replace(replacement(this=value.this.copy(), expression=value.expression.copy())))
        boundary = {exp.GT: exp.GTE, exp.GTE: exp.GT, exp.LT: exp.LTE, exp.LTE: exp.LT, exp.EQ: exp.NEQ, exp.NEQ: exp.EQ}.get(type(node))
        if boundary:
            edit(index, "boundary", lambda value, boundary=boundary: value.replace(boundary(this=value.this.copy(), expression=value.expression.copy())))
        if isinstance(node, exp.Join):
            if node.args.get("side") == "LEFT":
                edit(index, "join_kind", lambda value: (value.set("side", None), value.set("kind", "INNER")))
            elif not node.args.get("side"):
                edit(index, "join_kind", lambda value: value.set("side", "LEFT"))
        if isinstance(node, exp.Ordered):
            edit(index, "ordering", lambda value: value.set("desc", not value.args.get("desc")))
        if isinstance(node, exp.Limit) and isinstance(node.expression, exp.Literal) and node.expression.this.isdigit():
            edit(index, "limit", lambda value: value.set("expression", exp.Literal.number(int(value.expression.this)+1)))
        if isinstance(node, exp.Count):
            if not isinstance(node.this, exp.Star):
                edit(index, "null_count", lambda value: value.set("this", exp.Star()))
            else:
                edit(index, "null_count", lambda value: value.set("this", exp.Null()))
        if isinstance(node, (exp.Max, exp.Min)):
            replacement = exp.Min if isinstance(node, exp.Max) else exp.Max
            edit(index, "aggregate", lambda value, replacement=replacement: value.replace(replacement(this=value.this.copy())))
        if isinstance(node, exp.Sum):
            edit(index, "aggregate", lambda value: value.replace(exp.Count(this=value.this.copy())))
        if isinstance(node, exp.StartsWith):
            edit(index, "prefix_contains", lambda value: value.replace(exp.Contains(this=value.this.copy(), expression=value.expression.copy())))
        if isinstance(node, exp.Like):
            edit(index, "case_sensitivity", lambda value: value.replace(exp.ILike(this=value.this.copy(), expression=value.expression.copy())))
        if isinstance(node, exp.Escape):
            edit(index, "wildcard_escape", lambda value: value.replace(value.this.copy()))
        if isinstance(node, (exp.Intersect, exp.Except)):
            for replacement in (exp.Union, exp.Except if isinstance(node, exp.Intersect) else exp.Intersect):
                edit(index, "set_operation", lambda value, replacement=replacement: value.replace(replacement(this=value.this.copy(), expression=value.expression.copy(), distinct=True)))
    return candidates


def equivalent_controls(sql):
    tree = parse_one(sql, read="duckdb")
    # Adding a tautology preserves NULL/duplicate/order semantics. This is an
    # actual execution control, not a string-equality comparator.
    for select in tree.find_all(exp.Select):
        original = select.args.get("where")
        root = exp.And(this=original.this.copy(), expression=exp.Boolean(this=True)) if original else exp.Boolean(this=True)
        select.set("where", exp.Where(this=root))
    return [tree.sql(dialect="duckdb")]


def audit_semantics(reference, instances, mutants, controls):
    if len(instances) < 2 or any(item.get("fixture_only") is not True or not item.get("constraints_verified") for item in instances):
        raise ValueError("TWO_VERIFIED_ADVERSARIAL_INSTANCES_REQUIRED")
    if len({item["context"].identity["logical_sha256"] for item in instances}) != len(instances):
        raise ValueError("ADVERSARIAL_INSTANCES_MUST_DIFFER")
    if any(item["context"].database_id != reference.database_id for item in instances):
        raise ValueError("WRONG_FIXTURE_DATABASE")

    def execute(sql, instance):
        validate_sql(sql, instance["context"])
        tools = DatabaseTools(instance["context"], row_cap=10000, payload_bytes=4_000_000)
        _, rows, truncated = tools._execute(sql)
        if truncated:
            raise ValueError("SEMANTIC_RESULT_LIMIT")
        return rows

    gold = [execute(reference.gold_sql, item) for item in instances]
    results = []
    for mutant in mutants:
        matches = []
        errors = []
        for index, instance in enumerate(instances):
            try:
                matches.append(compare_results(execute(mutant["sql"], instance), gold[index], reference.comparator))
            except (SafetyError, ToolError, ValueError) as error:
                matches.append(None)
                errors.append({"instance_id": instance["instance_id"], "error_type": type(error).__name__})
        # Syntax/execution failures never count as semantic kills.
        executable = all(value is not None for value in matches)
        status = "KILLED" if executable and not all(matches) else "NOT_DISTINGUISHED" if executable else "NONEXECUTABLE"
        results.append({**mutant, "status": status, "instance_matches": matches, "errors": errors})
    control_results = []
    for control in controls:
        accepted = all(compare_results(execute(control, instance), gold[index], reference.comparator) for index, instance in enumerate(instances))
        control_results.append({"sql": control, "accepted": accepted})
    return {"scope": "fixture_only_semantic_validation", "external_model_calls": 0,
            "instance_ids": [item["instance_id"] for item in instances],
            "gold_result_digests": [hashlib.sha256(json.dumps(canonical_rows(rows), sort_keys=True).encode()).hexdigest() for rows in gold],
            "mutant_results": results, "equivalent_controls": control_results,
            "semantic_mutants_executable": sum(item["status"] != "NONEXECUTABLE" for item in results),
            "semantic_mutants_killed": sum(item["status"] == "KILLED" for item in results),
            "equivalent_controls_accepted": sum(item["accepted"] for item in control_results)}
