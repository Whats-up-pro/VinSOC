"""Independent multi-table AST boundary; no archived single-table policy import."""
from sqlglot import ErrorLevel, exp, parse

from .data import DatabaseContext


class SafetyError(ValueError):
    pass


PURE_FUNCTIONS = frozenset({
    "COUNT", "SUM", "AVG", "MIN", "MAX", "ABS", "ROUND", "LOWER", "UPPER", "LENGTH",
    "COALESCE", "NULLIF", "CAST", "TRY_CAST", "EXTRACT", "DATE_DIFF", "DATEDIFF", "DATE_TRUNC",
    "STRFTIME", "STRPTIME", "SUBSTRING", "TRIM", "CONCAT", "CONCAT_WS", "REPLACE", "YEAR", "MONTH",
    "DAY", "ROW_NUMBER", "RANK", "DENSE_RANK", "LAG", "LEAD", "FIRST_VALUE", "LAST_VALUE",
    "CASE", "IF", "EXISTS", "STARTS_WITH", "ENDS_WITH", "CONTAINS", "AND", "OR", "TRANSLATE",
})
FORBIDDEN_NODES = frozenset({
    "Insert", "Update", "Delete", "Drop", "Create", "Alter", "Attach", "Detach", "Copy", "Install",
    "Load", "Command", "Into", "Use", "Pragma", "Transaction", "Execute", "Export", "Import", "Lock",
})


def validate_sql(query: str, context: DatabaseContext) -> None:
    if not isinstance(query, str) or not query.strip() or len(query.encode("utf-8")) > 16384:
        raise SafetyError("INVALID_SQL_PAYLOAD")
    try:
        statements = parse(query, read="duckdb", error_level=ErrorLevel.RAISE)
    except Exception as error:
        raise SafetyError("SQL_PARSE_REJECTED") from error
    if len(statements) != 1 or not isinstance(statements[0], exp.Query):
        raise SafetyError("SINGLE_READ_ONLY_QUERY_REQUIRED")
    tree = statements[0]
    allowed_tables = {table["name"].casefold() for table in context.identity["schema"]}
    cte_names = {cte.alias.casefold() for cte in tree.find_all(exp.CTE)}
    for node in tree.walk():
        if type(node).__name__ in FORBIDDEN_NODES:
            raise SafetyError("WRITE_OR_SYSTEM_OPERATION_REJECTED")
        if isinstance(node, exp.Func):
            name = node.name.upper() if isinstance(node, exp.Anonymous) else node.sql_name().upper()
            if name not in PURE_FUNCTIONS:
                raise SafetyError("FUNCTION_NOT_ALLOWLISTED")
        if isinstance(node, exp.Table):
            if not isinstance(node.this, exp.Identifier) or node.db or node.catalog:
                raise SafetyError("EXTERNAL_OR_QUALIFIED_DATABASE_REJECTED")
            if node.name.casefold() not in allowed_tables | cte_names:
                raise SafetyError("TABLE_NOT_REGISTERED")
