"""Evaluator-only reference schema/predicate annotations, excluded from generation."""
from decimal import Decimal

from sqlglot import exp, parse_one
from sqlglot.optimizer.qualify import qualify
from sqlglot.optimizer.scope import traverse_scope


class AnnotationError(ValueError):
    pass


def _constant(node):
    if isinstance(node, exp.Null):
        return {"value": None, "value_type": "null"}
    if isinstance(node, exp.Boolean):
        return {"value": node.this, "value_type": "boolean"}
    if isinstance(node, exp.Neg):
        value = _constant(node.this)
        if value and value["value_type"] == "numeric":
            return {**value, "value": -value["value"]}
        return None
    if isinstance(node, exp.Cast):
        value = _constant(node.this)
        target = node.args["to"].sql(dialect="duckdb").upper()
        if value and target.startswith(("TIMESTAMP", "DATE", "TIME")):
            return {**value, "value_type": "timestamp", "cast_type": target}
        return None
    if isinstance(node, exp.Literal):
        if node.is_string:
            return {"value": node.this, "value_type": "string"}
        number = Decimal(node.this)
        return {"value": int(number) if number == number.to_integral_value() else float(number), "value_type": "numeric"}
    return None


def _literal_leaves(node):
    value = _constant(node)
    if value is not None:
        return [value]
    if isinstance(node, exp.Anonymous) and node.name.upper() == "TRANSLATE":
        # Alphabet mappings are dialect infrastructure, not analyst/catalog
        # literals. The translated operand retains its own real constants.
        return _literal_leaves(node.expressions[0])
    values = []
    for child in node.iter_expressions():
        # A subquery has its own predicates; do not attribute its constants to
        # the outer predicate (except its separate EXISTS/IN structure).
        if not isinstance(child, (exp.Select, exp.Subquery)):
            values.extend(_literal_leaves(child))
    return values


def _stage(node):
    while node.parent is not None:
        node = node.parent
        if isinstance(node, exp.Where):
            return "where"
        if isinstance(node, exp.Having):
            return "having"
        if isinstance(node, exp.Join):
            return "join"
        if isinstance(node, exp.Select):
            break
    return "expression"


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
    relationships, stored, constraints, predicates, structures = [], [], [], [], []
    atomic_conditions = set()

    def condition(node):
        if isinstance(node, (exp.And, exp.Or)):
            condition(node.this)
            condition(node.expression)
        elif isinstance(node, (exp.Paren, exp.Not)):
            condition(node.this)
        elif isinstance(node, exp.Escape):
            atomic_conditions.add(id(node.this))
        elif node is not None:
            atomic_conditions.add(id(node))

    for node in tree.walk():
        root = None
        if isinstance(node, (exp.Where, exp.Having, exp.Qualify)):
            root = node.this
        elif isinstance(node, exp.Join):
            root = node.args.get("on")
        elif isinstance(node, exp.If):
            root = node.this
        if root is not None:
            condition(root)
            structures.append({"stage": node.key, "expression": root.sql(dialect="duckdb")})
    operators = {exp.EQ: "=", exp.NEQ: "!=", exp.GT: ">", exp.GTE: ">=", exp.LT: "<", exp.LTE: "<="}

    def typed_item(location, constant, operator):
        item = {key: location[key] for key in ('table', 'column')}
        if constant['value_type'] == 'string' and location['type'] == 'VARCHAR' and operator in ('=', '!='):
            stored.append({**item, 'operator': operator, 'value': constant['value']})
        else:
            kind = 'numeric_threshold' if constant['value_type'] == 'numeric' else 'time_threshold' if constant['value_type'] == 'timestamp' or location['type'].startswith(('TIMESTAMP', 'DATE')) else 'lexical_threshold'
            constraints.append({**item, 'kind': kind, 'operator': operator, 'value': constant['value']})

    for node in tree.walk():
        if isinstance(node, exp.Predicate) or id(node) in atomic_conditions:
            dependencies = sorted({(item["table"], item["column"]) for column in node.find_all(exp.Column)
                                   if (item := resolved.get(id(column)))})
            parent = node.parent
            escape = parent.expression.this if isinstance(parent, exp.Escape) and isinstance(parent.expression, exp.Literal) else None
            negated = isinstance(parent, exp.Not) or isinstance(parent, exp.Escape) and isinstance(parent.parent, exp.Not)
            predicates.append({"operator": node.key, "stage": _stage(node), "expression": node.sql(dialect="duckdb"),
                               "negated": negated, "escape": escape, "literals": _literal_leaves(node),
                               "column_dependencies": [{"table": table, "column": column} for table, column in dependencies]})
        if isinstance(node, exp.Limit):
            literal = node.expression
            if isinstance(literal, exp.Literal) and literal.this.isdigit():
                constraints.append({"kind": "limit", "value": int(literal.this)})
            continue
        location = resolved.get(id(node.this)) if isinstance(node.this, exp.Column) else None
        negated = isinstance(node.parent, exp.Not)
        if isinstance(node, exp.In) and location:
            for literal in node.expressions:
                if (constant := _constant(literal)) is not None:
                    typed_item(location, constant, '!=' if negated else '=')
        if isinstance(node, exp.Between) and location:
            for bound, op in (('low', '<' if negated else '>='), ('high', '>' if negated else '<=')):
                if (constant := _constant(node.args[bound])) is not None:
                    typed_item(location, constant, op)
        if isinstance(node, exp.Is) and location and isinstance(node.expression, exp.Null):
            constraints.append({'table':location['table'],'column':location['column'],
                'kind':'null_test','operator':'is_not_null' if negated else 'is_null'})
        if isinstance(node, (exp.Like, exp.ILike, exp.StartsWith)):
            dependencies = [resolved[id(c)] for c in node.this.find_all(exp.Column) if id(c) in resolved]
            literals = _literal_leaves(node.expression)
            if len(dependencies) == 1 and len(literals) == 1 and literals[0]['value_type'] == 'string':
                target = dependencies[0]
                pattern = {'table':target['table'],'column':target['column'],'kind':'domain_predicate',
                    'operator':'prefix' if isinstance(node, exp.StartsWith) else 'ilike' if isinstance(node, exp.ILike) else 'like',
                    'value':literals[0]['value']}
                if isinstance(node.parent, exp.Escape):
                    pattern['escape'] = node.parent.expression.this
                if negated or isinstance(node.parent, exp.Escape) and isinstance(node.parent.parent, exp.Not):
                    pattern['negated'] = True
                if any(isinstance(part, exp.Anonymous) and part.name.upper() == 'TRANSLATE' for part in node.this.walk()):
                    pattern['ascii_fold'] = True
                constraints.append(pattern)
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
        if rhs and not lhs and _constant(left) is not None:
            left, right, lhs = right, left, rhs
            operator = {">": "<", ">=": "<=", "<": ">", "<=": ">="}.get(operator, operator)
        constant = _constant(right)
        if lhs and constant is not None:
            location = {key: lhs[key] for key in ("table", "column")}
            if constant["value_type"] in ("string", "timestamp"):
                if lhs["type"] == "VARCHAR" and operator in ("=", "!="):
                    stored.append({**location, "operator": operator, "value": constant["value"]})
                else:
                    constraints.append({**location, "kind": "time_threshold" if constant["value_type"] == "timestamp" or lhs["type"].startswith(("TIMESTAMP", "DATE")) else "lexical_threshold", "operator": operator, "value": constant["value"]})
            elif constant["value_type"] == "numeric":
                constraints.append({**location, "kind": "numeric_threshold", "operator": operator, "value": constant["value"]})
        elif constant is not None and constant["value_type"] in ("numeric", "timestamp") and not isinstance(left, (exp.Column, exp.Literal)):
            constraints.append({"kind": "derived_expression", "expression": left.sql(dialect="duckdb"),
                                "operator": operator, **constant})
    return [{"tables": sorted(tables), "columns": [{"table": table, "column": column} for table, column in sorted(columns)],
             "relationships": sorted(relationships, key=str), "stored_values": stored, "constraints": constraints,
             "predicates": predicates, "boolean_structure": structures, "annotations_complete": True,
             "annotation_scope": "Qualified physical schema dependencies and exhaustive parsed predicate structures; alternative SQL semantics require execution controls, not identical ASTs"}]
