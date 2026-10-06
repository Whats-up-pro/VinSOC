"""Versioned result-bag semantics for the new benchmark, never archived scoring."""
from collections import Counter
from decimal import Decimal, InvalidOperation, localcontext
from copy import deepcopy
import hashlib
import json

import duckdb


COMPARATORS = frozenset({"ordered_rows", "unordered_multiset", "unordered_set", "scalar"})


def _value(value):
    if isinstance(value, (int, float, Decimal)) and not isinstance(value, bool):
        number = Decimal(str(value))
        if not number.is_finite():
            raise ValueError("NONFINITE_RESULT")
        try:
            with localcontext() as context:
                context.prec = max(64, len(number.as_tuple().digits) + abs(number.as_tuple().exponent) + 12)
                rounded = number.quantize(Decimal("0.000000001"))
                return ("number", "0" if rounded == 0 else str(rounded.normalize()))
        except InvalidOperation as error:
            raise ValueError("NUMERIC_PRECISION_UNSUPPORTED") from error
    if isinstance(value, bytes):
        return ("bytes", value.hex())
    if value is None:
        return ("null",)
    return (type(value).__name__, value.isoformat() if hasattr(value, "isoformat") else value)


def canonical_rows(rows):
    return [tuple(_value(value) for value in (row.values() if isinstance(row, dict) else row)) for row in rows]


def compare_results(predicted, expected, comparator):
    if comparator not in COMPARATORS:
        raise ValueError("UNKNOWN_COMPARATOR")
    pred, gold = canonical_rows(predicted), canonical_rows(expected)
    if comparator == "scalar":
        return len(pred) == len(gold) == 1 and len(pred[0]) == len(gold[0]) == 1 and pred == gold
    if comparator == "ordered_rows":
        return pred == gold
    if comparator == "unordered_set":
        return set(pred) == set(gold)
    return Counter(pred) == Counter(gold)


def score_case(reference_case, record, snapshot_instances):
    """Score saved SQL on one verified base plus explicitly tagged fixtures.

    This never creates a model client, never overwrites generation errors and
    never treats invalid gold/infrastructure as a model failure.
    """
    from .benchmark import BenchmarkError
    from .safety import SafetyError, validate_sql
    from .tools import DatabaseTools, ToolError, _json_value
    result = deepcopy(record)
    if not snapshot_instances or snapshot_instances[0]["fixture_only"]:
        raise BenchmarkError("VERIFIED_BASE_INSTANCE_REQUIRED")
    ids = [item["instance_id"] for item in snapshot_instances]
    if len(ids) != len(set(ids)) or any(item["context"].database_id != reference_case.database_id for item in snapshot_instances):
        raise BenchmarkError("INVALID_SCORING_INSTANCES")
    result.update({"pipeline_error_category": record.get("error_category"), "syntax_valid": False,
                   "execution_success": False, "execution_accurate": False, "safety_rejected": False,
                   "scoring_error_category": "NO_FINAL_SQL", "instance_results": [],
                   "semantic_instances_correct": 0, "semantic_instances_total": len(snapshot_instances)})
    sql = record.get("final_sql")
    if not isinstance(sql, str) or not sql.strip():
        return result
    try:
        result["syntax_valid"] = len(duckdb.extract_statements(sql)) == 1
    except duckdb.Error:
        result["scoring_error_category"] = "INVALID_SQL_SYNTAX"
        return result
    if not result["syntax_valid"]:
        result["scoring_error_category"] = "INVALID_SQL_SYNTAX"
        return result
    for i, instance in enumerate(snapshot_instances):
        tools = DatabaseTools(instance["context"], row_cap=10000, payload_bytes=4_000_000)
        def execute(query):
            validate_sql(query, instance["context"])
            columns, rows, truncated = tools._execute(query)
            return {"columns": columns, "rows": rows, "truncated": truncated}
        try:
            gold = execute(reference_case.gold_sql)
            if gold["truncated"]:
                raise BenchmarkError("GOLD_RESULT_LIMIT")
        except (SafetyError, ToolError) as error:
            raise BenchmarkError("GOLD_INFRASTRUCTURE_FAILURE:" + str(error)) from error
        scored = {"instance_id": instance["instance_id"], "fixture_only": instance["fixture_only"],
                  "snapshot_identity": instance["context"].identity["logical_sha256"], "execution_accurate": False}
        try:
            predicted = execute(sql)
            if predicted["truncated"]:
                scored["error_category"] = "PREDICTION_RESULT_LIMIT"
            else:
                correct = compare_results(predicted["rows"], gold["rows"], reference_case.comparator)
                scored.update({"execution_accurate": correct, "execution_success": True,
                               "error_category": "OK" if correct else "RESULT_MISMATCH",
                               "gold_row_count": len(gold["rows"]), "predicted_row_count": len(predicted["rows"]),
                               "gold_columns": gold["columns"], "predicted_columns": predicted["columns"],
                               "sample_gold_rows": [[_json_value(value) for value in row] for row in gold["rows"][:3]],
                               "sample_predicted_rows": [[_json_value(value) for value in row] for row in predicted["rows"][:3]],
                               "gold_result_sha256": hashlib.sha256(json.dumps(canonical_rows(gold["rows"]), sort_keys=True).encode()).hexdigest(),
                               "predicted_result_sha256": hashlib.sha256(json.dumps(canonical_rows(predicted["rows"]), sort_keys=True).encode()).hexdigest()})
        except SafetyError as error:
            scored.update({"error_category": "SAFETY_REJECTION", "failure_code": str(error), "safety_rejected": True})
        except ToolError as error:
            scored.update({"error_category": "EXECUTION_ERROR", "failure_code": str(error)})
        result["instance_results"].append(scored)
        result["semantic_instances_correct"] += int(scored["execution_accurate"])
        if i == 0:
            result.update({"execution_accurate": scored["execution_accurate"],
                           "execution_success": scored.get("execution_success", False),
                           "safety_rejected": scored.get("safety_rejected", False),
                           "scoring_error_category": scored["error_category"]})
    result["semantic_test_accuracy"] = result["semantic_instances_correct"] == len(snapshot_instances)
    return result
