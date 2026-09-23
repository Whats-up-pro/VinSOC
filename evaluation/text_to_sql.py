"""Execution-based Text-to-SQL evaluation over a frozen DuckDB snapshot."""

from __future__ import annotations

from collections import Counter
from collections.abc import Sequence
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
from typing import Any, Literal

from agent.provider import LLMProvider, ProviderError, create_provider
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



@dataclass(frozen=True)
class SQLGenerationConfig:
    """Pinned provider settings for one Text-to-SQL benchmark run."""

    provider: str = "openai"
    model: str = "gpt-4o"
    temperature: float = 0.0


@dataclass(frozen=True)
class SQLCaseRun:
    """One model generation plus its deterministic execution evaluation."""

    case_id: str
    generated_sql: str | None
    evaluation: SQLEvaluationResult
    error_category: str
    latency_ms: float = 0.0
    input_tokens: int = 0
    output_tokens: int = 0
    provider_error: str | None = None


class TextToSQLRunner:
    """Generate SQL with a pinned model and evaluate it on a frozen snapshot."""

    def __init__(
        self,
        snapshot: DuckDBSnapshot,
        config: SQLGenerationConfig | None = None,
        provider: LLMProvider | None = None,
        benchmarks_dir: Path | None = None,
    ):
        self.snapshot = snapshot
        self.config = config or SQLGenerationConfig()
        self.benchmarks_dir = benchmarks_dir or Path("evaluation/text_to_sql_benchmarks")
        if provider is not None:
            self.provider = provider
        else:
            provider_kwargs: dict[str, Any] = {}
            if self.config.provider == "routed":
                provider_kwargs["mode"] = "evaluation"
            self.provider = create_provider(
                provider_type=self.config.provider,
                model=self.config.model,
                **provider_kwargs,
            )

    def schema_context(self) -> str:
        """Return deterministic schema-only context; no telemetry rows are exposed."""
        result = self.snapshot.query(
            """
            SELECT table_name, column_name, data_type
            FROM information_schema.columns
            WHERE table_schema = 'main'
              AND table_name <> 'dataset_provenance'
            ORDER BY table_name, ordinal_position
            """
        )
        grouped: dict[str, list[str]] = {}
        for row in result.rows:
            grouped.setdefault(str(row["table_name"]), []).append(
                f'{row["column_name"]} {row["data_type"]}'
            )
        return "\n".join(
            f"{table}({', '.join(columns)})" for table, columns in grouped.items()
        )

    def run_case(self, case: SQLBenchmarkCase) -> SQLCaseRun:
        """Generate one SQL statement and score it through the existing safety gate."""
        system_prompt = (
            "You generate DuckDB SQL for the VinSOC SOC benchmark. "
            "Return exactly one read-only SELECT statement (WITH ... SELECT is allowed). "
            "Do not write data, attach databases, install extensions, or emit prose.\n\n"
            "Database schema:\n"
            + self.schema_context()
        )
        try:
            response = self.provider.generate(
                messages=[{"role": "user", "content": case.question}],
                tools=None,
                system_prompt=system_prompt,
                temperature=self.config.temperature,
            )
        except ProviderError as exc:
            evaluation = SQLEvaluationResult(
                case_id=case.case_id,
                syntax_valid=False,
                execution_success=False,
                execution_accurate=False,
                safety_rejected=False,
                error=str(exc),
            )
            return SQLCaseRun(
                case_id=case.case_id,
                generated_sql=None,
                evaluation=evaluation,
                error_category="PROVIDER_ERROR",
                provider_error=str(exc),
            )

        generated_sql = _extract_sql(response.content)
        evaluation = evaluate_sql_case(case, generated_sql, self.snapshot)
        metadata = response.metadata or {}
        return SQLCaseRun(
            case_id=case.case_id,
            generated_sql=generated_sql,
            evaluation=evaluation,
            error_category=_sql_error_category(evaluation),
            latency_ms=float(metadata.get("latency_ms", 0.0) or 0.0),
            input_tokens=int(metadata.get("input_tokens", 0) or 0),
            output_tokens=int(metadata.get("output_tokens", 0) or 0),
        )

    def load_cases(self, split: str = "dev") -> list[SQLBenchmarkCase]:
        split_dir = self.benchmarks_dir / split
        if not split_dir.exists():
            return []
        import json

        cases: list[SQLBenchmarkCase] = []
        for path in sorted(split_dir.glob("*.json")):
            cases.append(SQLBenchmarkCase.from_dict(json.loads(path.read_text(encoding="utf-8"))))
        return cases

    def run_suite(self, split: str = "dev") -> list[SQLCaseRun]:
        return [self.run_case(case) for case in self.load_cases(split)]


def _extract_sql(content: str) -> str:
    """Accept raw SQL or a single fenced SQL block without changing semantics."""
    text = (content or "").strip()
    if text.startswith("```") and text.endswith("```"):
        lines = text.splitlines()
        if len(lines) >= 3:
            return "\n".join(lines[1:-1]).strip()
    return text


def _sql_error_category(result: SQLEvaluationResult) -> str:
    if result.safety_rejected:
        return "SAFETY_REJECTION"
    if not result.syntax_valid:
        return "SYNTAX_ERROR"
    if not result.execution_success:
        return "EXECUTION_ERROR"
    if not result.execution_accurate:
        return "RESULT_MISMATCH"
    return "OK"

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
