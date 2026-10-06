"""Deterministic evaluator-only synthetic rows from schema and SQL constants.

No base rows, case IDs, CTU mappings or model outputs are consulted. Generated
instances still need execution, constraint, dialect and mutation-coverage audits;
generation alone never certifies semantic coverage.
"""
from copy import deepcopy
from datetime import datetime, timedelta
import hashlib
from itertools import product
from math import prod

from .annotations import annotate_reference


def _unique(values):
    result = []
    for value in values:
        if value not in result:
            result.append(value)
    return result


def _pattern_example(pattern, escape):
    output = []
    escaped = False
    for char in pattern:
        if escaped:
            output.append(char)
            escaped = False
        elif escape and char == escape:
            escaped = True
        else:
            output.append("tail" if char == "%" else "x" if char == "_" else char)
    return "".join(output)


def generate_fixture_spec(context, sql, *, variant, seed=20261005):
    if type(variant) is not int or variant < 0:
        raise ValueError("INVALID_FIXTURE_VARIANT")
    annotations = annotate_reference(sql, context)[0]
    hints, coverage_domains = {}, {}
    for predicate in annotations["predicates"]:
        dependencies = predicate["column_dependencies"]
        if len(dependencies) != 1:
            continue
        dependency = dependencies[0]
        key = (dependency["table"], dependency["column"])
        values = hints.setdefault(key, [])
        coverage = coverage_domains.setdefault(key, [])
        for literal in predicate["literals"]:
            value = literal["value"]
            if literal["value_type"] == "numeric":
                values.extend([value-1, value, value+1])
                coverage.extend([value-1, value, value+1])
            elif literal["value_type"] == "timestamp":
                at = datetime.fromisoformat(value)
                values.extend([(at+timedelta(seconds=delta)).isoformat() for delta in (-1, 0, 1)])
                coverage.extend([(at+timedelta(seconds=delta)).isoformat() for delta in (-1, 0, 1)])
            elif literal["value_type"] == "string":
                exact = _pattern_example(value, predicate.get("escape")) if predicate["operator"] in ("like", "ilike") else value
                values.extend([exact, "x"+exact, exact+"_tail", exact.lower(), exact.upper()])
                coverage.append(exact)
    schema = deepcopy(context.identity["schema"])
    relationships = deepcopy(context.identity["relationships"])
    count = 28 + variant*7
    rows = {}
    for table in schema:
        discriminator = max((column.get("primary_key_position", 0) for column in table["columns"]), default=0)
        table_rows = []
        for i in range(count):
            row = []
            for column in table["columns"]:
                kind, key = column["duckdb_type"], (table["name"], column["name"])
                offset = int(hashlib.sha256((str(seed+variant)+"/"+"/".join(key)).encode()).hexdigest()[:8], 16)
                values = hints.get(key, [])
                if kind.startswith(("BIGINT", "INTEGER", "DOUBLE", "DECIMAL")):
                    domain = _unique([value for value in values if isinstance(value, (int, float))] + [0, 1, 2, 5, 17])
                elif kind.startswith(("TIMESTAMP", "DATE", "TIME")):
                    domain = _unique([value for value in values if isinstance(value, str) and ":" in value] + ["2020-01-01T00:00:00", "2020-01-01T00:00:01"])
                elif kind == "VARCHAR":
                    domain = _unique([value for value in values if isinstance(value, str)] + ["fixture_A", "fixture_B", "fixture_C"])
                else:
                    raise ValueError("FIXTURE_GENERATOR_TYPE_UNSUPPORTED:" + kind)
                if discriminator and column.get("primary_key_position") == discriminator:
                    # String key values are numeric strings so declared numeric
                    # FK/TEXT-affinity edges can be validated in both engines.
                    value = str(i+1) if kind == "VARCHAR" else i+1
                elif not column.get("not_null") and not column.get("primary_key_position") and i % 11 == 10:
                    value = None
                else:
                    value = domain[(i+offset) % len(domain)]
                row.append(value)
            table_rows.append(row)
        selected = [(i, _unique(coverage_domains[(table["name"], column["name"])]))
                    for i, column in enumerate(table["columns"])
                    if coverage_domains.get((table["name"], column["name"])) and
                    (not discriminator or column.get("primary_key_position") != discriminator)]
        if prod(len(values) for _, values in selected) > 512:
            raise ValueError("FIXTURE_HINT_COMBINATION_LIMIT")
        if selected:
            for combination in product(*(values for _, values in selected)):
                row = table_rows[0].copy()
                for (index, _), value in zip(selected, combination):
                    row[index] = value
                for index, column in enumerate(table["columns"]):
                    if discriminator and column.get("primary_key_position") == discriminator:
                        row[index] = str(len(table_rows)+1) if column["duckdb_type"] == "VARCHAR" else len(table_rows)+1
                # The common values in unconstrained projection columns permit
                # intersecting conjunctive branches. Coverage is still proved
                # by executed mutation tests, never assumed from these rows.
                table_rows.append(row)
        rows[table["name"]] = table_rows
    size = max(len(values) for values in rows.values())
    for table in schema:
        table_rows = rows[table["name"]]
        discriminator = max((column.get("primary_key_position", 0) for column in table["columns"]), default=0)
        while len(table_rows) < size:
            row = table_rows[0].copy()
            for index, column in enumerate(table["columns"]):
                if discriminator and column.get("primary_key_position") == discriminator:
                    row[index] = str(len(table_rows)+1) if column["duckdb_type"] == "VARCHAR" else len(table_rows)+1
            table_rows.append(row)
    by_table = {table["name"]: table for table in schema}
    for _ in range(len(schema)+1):
        for edge in relationships:
            child = by_table[edge["from_table"]]
            parent = by_table[edge["to_table"]]
            child_index = next(i for i, column in enumerate(child["columns"]) if column["name"] == edge["from_column"])
            parent_index = next(i for i, column in enumerate(parent["columns"]) if column["name"] == edge["to_column"])
            metadata = child["columns"][child_index]
            parent_values = _unique([row[parent_index] for row in rows[parent["name"]] if row[parent_index] is not None])
            if not parent_values:
                raise ValueError("FIXTURE_FOREIGN_KEY_PARENT_EMPTY")
            for i, row in enumerate(rows[child["name"]]):
                if row[child_index] is None and not metadata.get("primary_key_position") and not metadata.get("not_null"):
                    continue
                # Repeated non-key FKs create grouping multiplicities and leave
                # parent rows unmatched; key FKs remain unique/non-null.
                span = len(parent_values) if metadata.get("primary_key_position") else max(1, len(parent_values)//2)
                row[child_index] = parent_values[i % span]
    return {"fixture_only": True, "seed": seed+variant, "database_id": context.database_id,
            "schema": schema, "relationships": relationships, "rows": rows,
            "generator_policy": "typed_constants_declared_keys_v1",
            "generation_is_not_semantic_validation": True}
