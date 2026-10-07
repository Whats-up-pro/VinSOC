"""Offline module diagnostics. Missing/failed cases remain in the denominator.

Consumes scored records plus evaluator-only inventory. No SQL, provider, raw SDK
response or gold is exposed by this report. Diagnostic attribution follows the
observable failure order; it is not a causal claim about model reasoning.
"""
from __future__ import annotations

import math
from collections import Counter
from .module_metrics import aggregate_module_metrics

VERSION = "cross_domain_report_v1"


def rate(correct, total):
    return {"correct": correct, "total": total, "rate": correct / total if total else None}


def _nonnegative(value):
    return type(value) in (int, float) and math.isfinite(value) and value >= 0


def primary_error(record, modules):
    if record is None:
        return "MISSING_CASE", []
    observed = []
    pipeline = record.get("pipeline_error_category", record.get("error_category"))
    scoring = record.get("scoring_error_category")
    if pipeline in {"TRANSPORT_OR_PARSE_FAILURE", "PROVIDER_ERROR", "QUOTA_ERROR", "MODEL_MISMATCH", "MISSING_USAGE"}:
        observed.append(pipeline)
    if not isinstance(record.get("final_sql"), str) or not record["final_sql"].strip():
        observed.append("NO_FINAL_SQL")
    if pipeline and pipeline != "OK":
        observed.append(pipeline)
    if modules.get("schema_linker") is not None and modules["schema_linker"].get("case_success") is False:
        observed.append("SCHEMA_LINKING_MISMATCH")
    if modules.get("value_grounding") is not None:
        grounding = modules["value_grounding"]
        witness = grounding.get("witness_precision")
        if witness and witness["correct"] < witness["total"]:
            observed.append("UNSUPPORTED_WITNESS")
        if grounding.get("case_success") is False:
            observed.append("GROUNDING_MISMATCH")
    if record.get("safety_rejected") is True:
        observed.append("SAFETY_REJECTION")
    if record.get("syntax_valid") is False and record.get("final_sql"):
        observed.append("INVALID_SQL_SYNTAX")
    if record.get("execution_success") is False and record.get("syntax_valid") is True and record.get("safety_rejected") is not True:
        observed.append("EXECUTION_ERROR")
    if scoring == "RESULT_MISMATCH" or (record.get("execution_success") is True and record.get("execution_accurate") is False):
        observed.append("SEMANTIC_MISMATCH")
    if record.get("semantic_test_accuracy") is False and record.get("execution_accurate") is True:
        observed.append("SEMANTIC_COUNTEREXAMPLE_FAILED")
    observed = list(dict.fromkeys(observed))
    return (observed[0] if observed else ("OK" if record.get("execution_accurate") is True else "SCORING_UNAVAILABLE")), observed[1:]


def _accounting(record):
    attempts = record.get("attempted_calls", 0)
    received = record.get("response_count", 0)
    if type(attempts) is not int or type(received) is not int or not 0 <= received <= attempts:
        raise ValueError("INVALID_REQUEST_COUNTS")
    events = record.get("responses", [])
    if not isinstance(events, list):
        raise ValueError("INVALID_RESPONSE_RECORDS")
    cost, valid, inputs, outputs = 0.0, 0, 0, 0
    for event in events:
        response = event.get("response", {})
        usage = response.get("usage")
        known = response.get("cost_usd", event.get("cost_usd"))
        if _nonnegative(known):
            cost += known
        if (isinstance(usage, dict) and all(type(usage.get(key)) is int and usage[key] >= 0
                                          for key in ("input_tokens", "output_tokens"))):
            inputs += usage["input_tokens"]
            outputs += usage["output_tokens"]
            valid += 1
    complete = (record.get("cost_unknown") is not True and len(events) == received == attempts == valid
                and all(_nonnegative(item.get("response", {}).get("cost_usd", item.get("cost_usd"))) for item in events))
    return {"attempted": attempts, "received": received, "valid_usage": valid,
            "known_usd": cost, "complete": complete, "input_tokens": inputs, "output_tokens": outputs}


def build_evaluation_report(case_records: list[dict], inventory: dict) -> dict:
    cases = inventory.get("cases", [])
    if not cases or any(not isinstance(row, dict) or not row.get("case_id") for row in cases):
        raise ValueError("PLANNED_CASE_INVENTORY_REQUIRED")
    ids = [row["case_id"] for row in cases]
    if len(set(ids)) != len(ids):
        raise ValueError("DUPLICATE_PLANNED_CASE")
    conditions = inventory.get("conditions", ["E0", "E3"])
    if not conditions or len(set(conditions)) != len(conditions) or any(c not in ("E0", "E3") for c in conditions):
        raise ValueError("INVALID_CONDITIONS")
    indexed = {}
    for record in case_records:
        key = (record.get("condition"), record.get("case_id"))
        if key[0] not in conditions or key[1] not in ids or key in indexed:
            raise ValueError("DUPLICATE_OR_FOREIGN_CASE_RECORD")
        indexed[key] = record
    summaries = {}
    for condition in conditions:
        normalized, module_records, account = [], [], []
        witnesses = {"correct": 0, "total": 0, "unavailable_cases": 0}
        benign = rejected_benign = 0
        for meta in cases:
            record = indexed.get((condition, meta["case_id"]))
            modules = (record or {}).get("modules") or {"schema_linker": None, "value_grounding": None}
            module_records.append(modules)
            error, secondary = primary_error(record, modules)
            row = {key: meta.get(key) for key in ("case_id", "database_id", "domain", "family_id", "difficulty", "features")}
            row.update({"condition": condition, "present": record is not None, "primary_error": error,
                        "secondary_errors": secondary, "missing_stages": {}, "modules": modules})
            for stage in ("schema_linker", "value_grounding"):
                if modules.get(stage) is None:
                    row["missing_stages"][stage] = "NOT_APPLICABLE_E0" if condition == "E0" else "STAGE_NOT_RECORDED"
            for metric in ("syntax_valid", "execution_success", "execution_accurate", "semantic_test_accuracy", "safety_rejected"):
                row[metric] = (record or {}).get(metric) is True
            grounding = modules.get("value_grounding") or {}
            witness = grounding.get("witness_precision")
            if witness is None:
                witnesses["unavailable_cases"] += 1
            else:
                witnesses["correct"] += witness["correct"]
                witnesses["total"] += witness["total"]
            if record is not None:
                counts = _accounting(record)
                account.append(counts)
                row.update({"accounting": counts, "db_calls": record.get("db_calls"),
                            "latency_seconds": record.get("wall_seconds"), "evidence_kind": record.get("evidence_kind")})
                for check in record.get("safety_checks", []):
                    if check.get("benign") is True:
                        benign += 1
                        rejected_benign += int(check.get("rejected") is True)
            normalized.append(row)
        n = len(cases)
        missing = [row["case_id"] for row in normalized if not row["present"]]
        complete = not missing and all(item["complete"] for item in account)
        costs = sum(item["known_usd"] for item in account)
        summary = {"cases": normalized, "coverage": {"received": n-len(missing), "planned": n, "missing_case_ids": missing},
                   "module_metrics": aggregate_module_metrics(module_records),
                   "primary_errors": dict(Counter(row["primary_error"] for row in normalized)),
                   "attribution_policy": "observable_failure_order_not_causal_diagnosis",
                   "cost": {"known_usd": costs, "complete": complete, "total_usd": costs if complete else None},
                   "requests": {key: sum(item[key] for item in account) for key in ("attempted", "received", "valid_usage", "input_tokens", "output_tokens")},
                   "safety_false_rejection_rate": rate(rejected_benign, benign),
                   "witness_precision": {**witnesses, "rate": witnesses["correct"]/witnesses["total"] if witnesses["total"] else None},
                   "synthetic_records": sum(row.get("evidence_kind") == "synthetic_transport" for row in normalized)}
        for stage, kinds in (("schema_linker", ("tables", "columns", "relationships")),
                             ("value_grounding", ("predicates",))):
            for kind in kinds:
                counts = summary["module_metrics"][stage][kind]
                counts.update(tp=counts["correct"], fp=counts["predicted"]-counts["correct"],
                              fn=counts["required"]-counts["correct"])
        present_records = [indexed[(condition, meta["case_id"])] for meta in cases if (condition, meta["case_id"]) in indexed]
        latencies = [r["wall_seconds"] for r in present_records if _nonnegative(r.get("wall_seconds"))]
        summary["sql_generation"] = {
            "final_sql_coverage": rate(sum(isinstance(r.get("final_sql"), str) and bool(r["final_sql"].strip()) for r in present_records), n),
            "no_final_sql": sum(row["primary_error"] == "NO_FINAL_SQL" for row in normalized),
            "db_calls_known": sum(r.get("db_calls", 0) for r in present_records if type(r.get("db_calls")) is int and r["db_calls"] >= 0),
            "latency_seconds": {"available": len(latencies), "planned": n,
                                "total": sum(latencies), "mean": sum(latencies)/len(latencies) if latencies else None},
        }
        for label, metric in (("execution_accuracy", "execution_accurate"), ("syntax_validity", "syntax_valid"),
                              ("execution_success", "execution_success"), ("semantic_test_accuracy", "semantic_test_accuracy"),
                              ("safety_rejection_rate", "safety_rejected")):
            summary[label] = rate(sum(row[metric] for row in normalized), n)
        summaries[condition] = summary
    return {"version": VERSION, "scope": "offline_scored_record_report", "conditions": summaries,
            "planned_case_count": len(cases), "official_model_score": False,
            "status": "complete_records" if all(s["coverage"]["received"] == len(cases) and s["cost"]["complete"] for s in summaries.values()) else "incomplete"}
