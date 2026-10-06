"""Evaluator-only reference schema/predicate annotations, excluded from generation."""
from decimal import Decimal

from sqlglot import exp, parse_one
from sqlglot.optimizer.qualify import qualify
from sqlglot.optimizer.scope import traverse_scope


class AnnotationError(ValueError):
    pass


def annotate_reference(sql, context):
    catalog = {table["name"].casefold(): table for table in context.identity["schema"]}
    sql_schema = {name: {column["name"]: column["duckdb_type"] for column in table["columns"]} for name, table in catalog.items()}
    try:
        tree = qualify(parse_one(sql, read="duckdb"), dialect="duckdb", schema=sql_schema,
                       quote_identifiers=False, identify=False)
    except Exception as error:
        raise AnnotationError("REFERENCE_COLUMN_RESOLUTION_FAILED") from error
    tables, columns, resolved = set(), set(), {}
    for scope in traverse_scope(tree):
        for source in scope.sources.values():
            if isinstance(source, exp.Table) and source.name.casefold() in catalog:
                tables.add(catalog[source.name.casefold()]["name"])
        for column in scope.columns:
            current = scope
            table = None
            while current is not None:
                source = current.sources.get(column.table)
                if isinstance(source, exp.Table) and source.name.casefold() in catalog:
                    table = catalog[source.name.casefold()]
                    break
                current = current.parent
            if table is None:
                # Derived output aliases are not fabricated stored columns.
                continue
            candidates = [item for item in table["columns"] if item["name"].casefold() == column.name.casefold()]
            if len(candidates) != 1:
                raise AnnotationError("REFERENCE_COLUMN_RESOLUTION_FAILED")
            item = candidates[0]
            resolved[id(column)] = {"table": table["name"], "column": item["name"], "type": item["duckdb_type"]}
            columns.add((table["name"], item["name"]))
    relationships, stored, constraints = [], [], []
    operators = {exp.EQ: "=", exp.NEQ: "!=", exp.GT: ">", exp.GTE: ">=", exp.LT: "<", exp.LTE: "<="}
    for node in tree.walk():
        if isinstance(node, exp.Limit):
            literal = node.expression
            if isinstance(literal, exp.Literal) and literal.this.isdigit():
                constraints.append({"kind": "limit", "value": int(literal.this)})
            continue
        operator = operators.get(type(node))
        if operator is None:
            continue
        left, right = node.this, node.expression
        lhs, rhs = resolved.get(id(left)), resolved.get(id(right))
        if lhs and rhs and operator == "=":
            endpoints = {(lhs["table"], lhs["column"]), (rhs["table"], rhs["column"])}
            for relationship in context.identity["relationships"]:
                required = {(relationship["from_table"], relationship["from_column"]), (relationship["to_table"], relationship["to_column"])}
                if endpoints == required and relationship not in relationships:
                    relationships.append(relationship.copy())
            continue
        if lhs and isinstance(right, exp.Literal):
            location = {key: lhs[key] for key in ("table", "column")}
            if right.is_string:
                if lhs["type"] == "VARCHAR" and operator in ("=", "!="):
                    stored.append({**location, "operator": operator, "value": right.this})
                else:
                    constraints.append({**location, "kind": "time_threshold" if lhs["type"].startswith(("TIMESTAMP", "DATE")) else "lexical_threshold", "operator": operator, "value": right.this})
            else:
                number = Decimal(right.this)
                constraints.append({**location, "kind": "numeric_threshold", "operator": operator,
                                    "value": int(number) if number == number.to_integral_value() else float(number)})
    return [{"tables": sorted(tables), "columns": [{"table": table, "column": column} for table, column in sorted(columns)],
             "relationships": sorted(relationships, key=str), "stored_values": stored, "constraints": constraints,
             "annotation_scope": "Stored schema columns and direct binary predicates; nested/derived/pattern annotations require further validation"}]
