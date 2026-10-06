"""Pre-inference qualification from Spider's supplied structured SQL AST.

Difficulty here is a VinSOC rubric, not the official Spider difficulty metric.
Family counts describe dependence; question counts must never be presented as
independent observations merely because wording or constants differ.
"""
from __future__ import annotations

import hashlib
import json
from collections import Counter, defaultdict
from copy import deepcopy
from typing import Any

from .data import RegistryError


DIFFICULTY_RUBRIC = {
    "advanced": "nested SELECT, set operation, or at least three FROM table units",
    "medium": "otherwise JOIN, GROUP/HAVING, ORDER/LIMIT, aggregate or DISTINCT",
    "basic": "otherwise a single-table SELECT with optional predicates",
}


def _walk(value: Any):
    yield value
    if isinstance(value, dict):
        for item in value.values():
            yield from _walk(item)
    elif isinstance(value, list):
        for item in value:
            yield from _walk(item)


def classify_query(sql: dict[str, Any]) -> dict[str, Any]:
    nested = any(isinstance(node, dict) and "select" in node for key in ("where", "having", "from") for node in _walk(sql[key]))
    set_operation = any(sql[key] for key in ("intersect", "union", "except"))
    table_count = len(sql["from"]["table_units"])
    features = []
    if table_count > 1:
        features.append("join")
    if nested or set_operation:
        features.append("nested")
    if sql["select"][0] or any(
        isinstance(node, list) and len(node) == 3 and node[-1] is True
        for node in _walk(sql)
    ):
        features.append("distinct")
    if sql["groupBy"] or sql["having"]:
        features.append("group_having")
    if sql["orderBy"] or sql["limit"] is not None:
        features.append("order_limit")
    aggregate = any(unit[0] for unit in sql["select"][1])
    if nested or set_operation or table_count >= 3:
        difficulty = "advanced"
    elif table_count >= 2 or aggregate or features:
        difficulty = "medium"
    else:
        difficulty = "basic"
    return {"difficulty": difficulty, "features": features}


def _predicate_value(value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, dict) and "select" in value:
        return _canonical_ast(value)
    # Spider col_unit = (aggregate ID, column ID, DISTINCT bool).
    if isinstance(value, list) and len(value) == 3 and isinstance(value[-1], bool):
        return value
    return "<constant>"


def _canonical_ast(sql: dict[str, Any]) -> dict[str, Any]:
    result = deepcopy(sql)
    for conditions in (result["where"], result["having"], result["from"]["conds"]):
        for condition in conditions:
            if isinstance(condition, list):
                condition[3] = _predicate_value(condition[3])
                condition[4] = _predicate_value(condition[4])
    for unit in result["from"]["table_units"]:
        if unit[0] == "sql":
            unit[1] = _canonical_ast(unit[1])
    for key in ("intersect", "union", "except"):
        if result[key] is not None:
            result[key] = _canonical_ast(result[key])
    if result["limit"] is not None:
        result["limit"] = "<limit>"
    return result


def sql_family(sql: dict[str, Any]) -> str:
    encoded = json.dumps(_canonical_ast(sql), sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(encoded).hexdigest()


def qualification_report(cases: list[dict[str, Any]]) -> dict[str, Any]:
    groups = defaultdict(list)
    for case in cases:
        groups[case["db_id"]].append(case)
    databases = {}
    for database_id, members in sorted(groups.items()):
        counts = Counter(classify_query(case["sql"])["difficulty"] for case in members)
        families = {sql_family(case["sql"]) for case in members}
        databases[database_id] = {
            "source_question_count": len(members),
            "difficulty_counts": dict(counts),
            "unique_family_count": len(families),
            "evaluation_quota_eligible": all(counts[level] >= n for level, n in (("basic", 2), ("medium", 4), ("advanced", 2))),
        }
    return {
        "difficulty_rubric": DIFFICULTY_RUBRIC,
        "family_independence_assumed": False,
        "databases": databases,
        "sufficient_for_8_external_evaluation_databases": sum(entry["evaluation_quota_eligible"] for entry in databases.values()) >= 8,
    }


def select_external_candidates(cases: list[dict[str, Any]], entries: list[dict[str, Any]], *, seed: int) -> dict[str, Any]:
    """Select source question candidates before gold/parity qualification and inference.

Prefer different families, record shared families when a difficulty bucket has
fewer families than questions required. These are correlated question-level
measurements and do not increase the independent family count.
"""
    groups = defaultdict(list)
    for case in cases:
        identity = json.dumps({"db_id": case["db_id"], "question": " ".join(case["question"].split()), "sql": case["sql"]}, sort_keys=True)
        case_id = "external_" + case["db_id"] + "_" + hashlib.sha256(identity.encode()).hexdigest()[:16]
        groups[case["db_id"]].append({
            "case_id": case_id, "database_id": case["db_id"], "question": case["question"],
            "family_id": sql_family(case["sql"]), **classify_query(case["sql"]),
        })
    result = {"calibration": [], "evaluation": []}
    for entry in sorted(entries, key=lambda item: item["database_id"]):
        candidates = {case["case_id"]: case for case in groups[entry["database_id"]]}
        ordered = sorted(candidates.values(), key=lambda case: hashlib.sha256(f"{seed}:{case['case_id']}".encode()).hexdigest())
        chosen = []
        families = set()

        def take(pool, count):
            for _ in range(count):
                remaining = [case for case in pool if case not in chosen]
                if not remaining:
                    raise RegistryError(f"SOURCE_CASE_QUOTA_UNMET: {entry['database_id']}")
                pick = next((case for case in remaining if case["family_id"] not in families), remaining[0])
                chosen.append(pick)
                families.add(pick["family_id"])

        if entry["split"] == "calibration":
            take(ordered, 4)
            split = "calibration"
        else:
            take([case for case in ordered if case["difficulty"] == "basic"], 2)
            medium = [case for case in ordered if case["difficulty"] == "medium"]
            joined = [case for case in medium if "join" in case["features"]]
            take(joined, min(2, len(joined)))
            take(medium, 4 - sum(case["difficulty"] == "medium" for case in chosen))
            advanced = [case for case in ordered if case["difficulty"] == "advanced"]
            nested = [case for case in advanced if "nested" in case["features"]]
            if nested:
                take(nested, 1)
            take(advanced, 2 - sum(case["difficulty"] == "advanced" for case in chosen))
            split = "evaluation"
        multiplicity = Counter(case["family_id"] for case in chosen)
        result[split].extend({**case, "selected_family_multiplicity": multiplicity[case["family_id"]]} for case in chosen)
    if len(result["calibration"]) != 16 or len(result["evaluation"]) != 64:
        raise RegistryError("EXTERNAL_SPLIT_COUNT_MISMATCH")
    features = Counter(feature for case in result["evaluation"] for feature in case["features"])
    if features["join"] < 16 or features["nested"] < 8:
        raise RegistryError(f"EXTERNAL_FEATURE_QUOTA_UNMET: {dict(features)}")
    return {
        **result, "evaluation_feature_counts": dict(features), "independence_assumed": False,
        "unique_evaluation_families": len({(case["database_id"], case["family_id"]) for case in result["evaluation"]}),
        "status": "CANDIDATES_NOT_BENCHMARK_LOCKED_GOLD_PARITY_PENDING",
        "selection_seed": seed,
        "selection_policy": "SHA-256 order within rubric buckets, prefer distinct families; prefer two medium JOINs and one advanced nested per database when available",
    }
