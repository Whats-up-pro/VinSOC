"""Execution-based Text-to-SQL evaluation over a frozen DuckDB snapshot."""

from __future__ import annotations

from collections import Counter
from collections.abc import Sequence
from dataclasses import dataclass
from decimal import Decimal
from typing import Any, Literal

from vinsoc_data.duckdb_store import DuckDBSnapshot, QuerySafetyError

ComparatorName = Literal["unordered_rows", "multiset_rows", "scalar", "boolean"]


@dataclass(frozen=True)
class SQLBenchmarkCase:
    """One frozen-snapshot question with one or more accepted gold queries."""

    case_id: str
    question: str
    database_snapshot: str
    gold_sql: tuple[str, ...]
    result_comparator: ComparatorName = "unordered_rows"

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> SQLBenchmarkCase:
        gold = payload.get("gold_sql", [])
        if isinstance(gold, str):
            gold = [gold]
        if not payload.get("case_id") or not payload.get("question") or not gold:
            raise ValueError("SQL benchmark case requires case_id, question, and gold_sql")
        return cls(
            case_id=payload["case_id"],
            question=payload["question"],
            database_snapshot=payload.get("database_snapshot", ""),
            gold_sql=tuple(gold),
            result_comparator=payload.get("result_comparator", "unordered_rows"),
        )


@dataclass(frozen=True)
class SQLEvaluationResult:
    case_id: str
    syntax_valid: bool
    execution_success: bool
    execution_accurate: bool
    safety_rejected: bool
    error: str | None = None


def evaluate_sql_case(
    case: SQLBenchmarkCase,
    predicted_sql: str,
    snapshot: DuckDBSnapshot,
) -> SQLEvaluationResult:
    """Compare model SQL with gold SQL by executing both on one snapshot."""
    syntax_valid = _has_valid_syntax(predicted_sql)
    if not syntax_valid:
        return SQLEvaluationResult(
            case.case_id,
            False,
            False,
            False,
            False,
            "DuckDB parser rejected SQL",
        )
    try:
        predicted = snapshot.query(predicted_sql)
    except QuerySafetyError as exc:
        return SQLEvaluationResult(case.case_id, True, False, False, True, str(exc))
    except RuntimeError as exc:
        return SQLEvaluationResult(
            case.case_id,
            True,
            False,
            False,
            False,
            str(exc),
        )

    gold_results = []
    for gold_sql in case.gold_sql:
        # Gold SQL is validated by the same policy. A broken gold case is a
        # benchmark authoring error, not a model failure.
        gold_results.append(snapshot.query(gold_sql))

    accurate = any(
        _equivalent(predicted.rows, gold.rows, case.result_comparator) for gold in gold_results
    )
    return SQLEvaluationResult(case.case_id, True, True, accurate, False)


def aggregate_sql_metrics(results: Sequence[SQLEvaluationResult]) -> dict[str, float]:
    """Return the three headline rates plus the hard safety rejection rate."""
    total = len(results)
    if not total:
        return {
            "syntax_validity_rate": 0.0,
            "execution_success_rate": 0.0,
            "execution_accuracy": 0.0,
            "safety_rejection_rate": 0.0,
        }
    return {
        "syntax_validity_rate": sum(item.syntax_valid for item in results) / total,
        "execution_success_rate": sum(item.execution_success for item in results) / total,
        "execution_accuracy": sum(item.execution_accurate for item in results) / total,
        "safety_rejection_rate": sum(item.safety_rejected for item in results) / total,
    }


def _canonical_value(value: Any) -> Any:
    if isinstance(value, float):
        return ("float", round(value, 9))
    if isinstance(value, Decimal):
        return ("decimal", str(value.normalize()))
    if isinstance(value, dict):
        return tuple(sorted((key, _canonical_value(item)) for key, item in value.items()))
    if isinstance(value, (list, tuple)):
        return tuple(_canonical_value(item) for item in value)
    return value


def _canonical_rows(rows: list[dict[str, Any]]) -> list[tuple[Any, ...]]:
    # SQL aliases are presentation details. Keep select-list order but compare
    # values only, so ``COUNT(*) AS total`` and ``COUNT(*) AS n`` are equal.
    return [tuple(_canonical_value(value) for value in row.values()) for row in rows]


def _equivalent(
    predicted: list[dict[str, Any]], gold: list[dict[str, Any]], comparator: ComparatorName
) -> bool:
    pred_rows = _canonical_rows(predicted)
    gold_rows = _canonical_rows(gold)
    if comparator in {"scalar", "boolean"}:
        return pred_rows == gold_rows
    if comparator == "multiset_rows":
        return Counter(pred_rows) == Counter(gold_rows)
    if comparator == "unordered_rows":
        return set(pred_rows) == set(gold_rows)
    raise ValueError(f"Unsupported result comparator: {comparator}")


def _has_valid_syntax(sql: str) -> bool:
    """Use DuckDB's parser without executing the model query."""
    try:
        import duckdb

        return len(duckdb.extract_statements(sql)) == 1
    except duckdb.ParserException:
        return False
