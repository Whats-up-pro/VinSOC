"""Validate links against controller-owned typed witnesses and the public catalog."""
import math
from datetime import datetime, time

from sqlglot import exp, parse_one

from .data import DatabaseContext, _quote
from .safety import SafetyError, validate_sql
from .tools import witness_id


class GroundingError(ValueError):
    pass


def validate_link(question, submitted_link, trajectory, context: DatabaseContext):
    if not isinstance(submitted_link, dict) or not all(key in submitted_link for key in ("tables", "columns", "relationships", "grounded_values", "constraints")):
        raise GroundingError("INVALID_LINK_SCHEMA")
    schema = {table["name"]: {column["name"]: column for column in table["columns"]} for table in context.identity["schema"]}
    tables = submitted_link["tables"]
    if not isinstance(tables, list) or not tables or len(tables) != len(set(tables)) or any(table not in schema for table in tables):
        raise GroundingError("INVALID_LINKED_TABLE")
    columns = submitted_link["columns"]
    if not isinstance(columns, list):
        raise GroundingError("INVALID_LINKED_COLUMNS")
    if any(not isinstance(submitted_link[key], list) for key in ("relationships", "grounded_values", "constraints")):
        raise GroundingError("INVALID_LINK_SCHEMA")
    chosen = set()
    for column in columns:
        if not isinstance(column, dict) or column.get("table") not in tables or column.get("column") not in schema[column["table"]]:
            raise GroundingError("INVALID_LINKED_COLUMN")
        chosen.add((column["table"], column["column"]))
    for relationship in submitted_link["relationships"]:
        if relationship not in context.identity["relationships"]:
            raise GroundingError("INVALID_RELATIONSHIP_PATH")
        endpoints = {(relationship["from_table"], relationship["from_column"]), (relationship["to_table"], relationship["to_column"])}
        if not endpoints <= chosen:
            raise GroundingError("UNLINKED_RELATIONSHIP_COLUMN")
    witnesses = {}
    for entry in trajectory:
        if entry.get("tool") != "value_search":
            continue
        result = entry.get("result", {})
        for witness in result.get("matches", []) + result.get("domain_witnesses", []):
            if witness.get("database_id") != context.database_id or witness.get("snapshot_identity") != context.identity["logical_sha256"]:
                raise GroundingError("INVALID_TOOL_PROVENANCE")
            if witness.get("evidence_id") != witness_id(witness):
                raise GroundingError("INVALID_TOOL_PROVENANCE")
            table, column = witness.get("table"), witness.get("column")
            if table not in schema or column not in schema[table] or witness.get("type") != schema[table][column]["duckdb_type"]:
                raise GroundingError("INVALID_TOOL_PROVENANCE")
            witnesses[witness["evidence_id"]] = witness
    grounded = []
    for value in submitted_link["grounded_values"]:
        witness = witnesses.get(value.get("evidence_id")) if isinstance(value, dict) else None
        if witness is None or (witness["table"], witness["column"]) not in chosen:
            raise GroundingError("MISSING_OR_UNRELATED_WITNESS")
        if any(key in value and value[key] != witness.get(key) for key in ("value", "table", "column", "type", "database_id")):
            raise GroundingError("FORGED_GROUNDED_VALUE")
        grounded.append(witness.copy())
    for constraint in submitted_link["constraints"]:
        if not isinstance(constraint, dict):
            raise GroundingError("INVALID_TYPED_CONSTRAINT")
        kind, value = constraint.get("kind"), constraint.get("value")
        if kind == "limit":
            if type(value) is not int or value <= 0:
                raise GroundingError("WRONG_LIMIT_TYPE")
            continue
        if kind == "derived_expression":
            expression = constraint.get("expression")
            temporal = constraint.get("value_type") == "timestamp"
            numeric = not isinstance(value, bool) and isinstance(value, (int, float)) and math.isfinite(value)
            if not isinstance(expression, str) or constraint.get("operator") not in ("=", "!=", ">", ">=", "<", "<=") or not (numeric or temporal):
                raise GroundingError("INVALID_DERIVED_CONSTRAINT")
            query = "SELECT " + expression + " FROM " + ", ".join(_quote(table) for table in tables)
            try:
                validate_sql(query, context)
                tree = parse_one(query, read="duckdb")
                if temporal:
                    targets = [node.args.get("to") for node in tree.find_all(exp.Cast)]
                    if not isinstance(value, str) or not any(target and target.sql(dialect="duckdb").upper().startswith(("TIMESTAMP", "DATE")) for target in targets):
                        raise GroundingError("WRONG_DERIVED_TIME_TYPE")
                    try:
                        datetime.fromisoformat(value)
                    except ValueError as error:
                        raise GroundingError("WRONG_DERIVED_TIME_TYPE") from error
                if any(table.name not in tables for table in tree.find_all(exp.Table)):
                    raise GroundingError("UNLINKED_DERIVED_TABLE")
                for column_node in tree.find_all(exp.Column):
                    matches = {(table, column) for table, column in chosen if column == column_node.name and (not column_node.table or table == column_node.table)}
                    if len(matches) != 1:
                        raise GroundingError("AMBIGUOUS_OR_UNLINKED_DERIVED_COLUMN")
            except SafetyError as error:
                raise GroundingError("UNSAFE_DERIVED_EXPRESSION") from error
            continue
        table, column = constraint.get("table"), constraint.get("column")
        if kind == "domain_predicate":
            witness = witnesses.get(constraint.get("evidence_id"))
            if witness is None or (table, column) not in chosen or (table, column) != (witness["table"], witness["column"]) or witness["type"] != "VARCHAR" or not isinstance(value, str):
                raise GroundingError("MISSING_OR_UNRELATED_WITNESS")
            operator = constraint.get("operator")
            actual = witness["value"]
            if not (operator == "exact" and actual == value or operator == "prefix" and actual.startswith(value) or operator == "contains" and value in actual):
                raise GroundingError("UNWITNESSED_DOMAIN_PREDICATE")
            continue
        if (table, column) not in chosen or constraint.get("operator") not in ("=", "!=", ">", ">=", "<", "<="):
            raise GroundingError("INVALID_TYPED_CONSTRAINT")
        type_name = schema[table][column]["duckdb_type"]
        if kind == "numeric_threshold":
            if not type_name.startswith(("BIGINT", "INTEGER", "DOUBLE", "DECIMAL")) or isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
                raise GroundingError("WRONG_CONSTRAINT_TYPE")
        elif kind == "time_threshold":
            source_type = schema[table][column].get("sqlite_type", "").upper()
            if not isinstance(value, str) or not (type_name.startswith(("TIMESTAMP", "DATE")) or source_type in ("DATE", "TIME", "DATETIME", "TIMESTAMP")):
                raise GroundingError("WRONG_CONSTRAINT_TYPE")
            try:
                time.fromisoformat(value) if source_type == "TIME" else datetime.fromisoformat(value)
            except ValueError as error:
                raise GroundingError("WRONG_CONSTRAINT_TYPE") from error
        else:
            raise GroundingError("UNSUPPORTED_CONSTRAINT_KIND")
    return {**submitted_link, "grounded_values": grounded, "database_id": context.database_id,
            "snapshot_identity": context.identity["logical_sha256"]}
