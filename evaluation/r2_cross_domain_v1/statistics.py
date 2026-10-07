"""Reproducible offline intervals; correlated cases are not independent trials.

Input is a scored/normalized record per planned case and condition. A partial
list must retain planned_case_count (default 96 for this release). Pending cases
stay in the descriptive denominator; intervals require a complete case list.
Paired inference additionally requires matched identities and valid telemetry.
"""
from __future__ import annotations

import math
import random
from collections import defaultdict
from statistics import NormalDist

VERSION = "cross_domain_statistics_v1"


def _metric(rows, n=None):
    n = len(rows) if n is None else n
    correct = sum(row.get("execution_accurate") is True and row.get("present", True) is True for row in rows)
    return {"correct": correct, "n": n, "rate": correct/n if n else None}


def _wilson(correct, n):
    if not n:
        return None
    z = NormalDist().inv_cdf(.975)
    p = correct/n
    denominator = 1 + z*z/n
    center = (p + z*z/(2*n))/denominator
    half = z*math.sqrt(p*(1-p)/n + z*z/(4*n*n))/denominator
    return [max(0.0, center-half), min(1.0, center+half)]


def _quantile(values, p):
    values = sorted(values)
    at = (len(values)-1)*p
    lo = int(at)
    hi = min(lo+1, len(values)-1)
    return values[lo] + (values[hi]-values[lo])*(at-lo)


def _cluster_interval(rows, cluster, *, seed, replicates, complete, value):
    groups = defaultdict(list)
    for row in rows:
        key = row.get("database_id") if cluster == "database" else (row.get("database_id"), row.get("family_id"))
        groups[key].append(row)
    result = {"interval": None, "clusters": len(groups), "replicates": replicates,
              "seed": seed, "method": "cluster_resampling_case_weighted_mean", "reason": None}
    if not complete:
        result["reason"] = "INCOMPLETE_CASES"
    elif any(not row.get("database_id") or (cluster == "family" and not row.get("family_id")) for row in rows):
        result["reason"] = "MISSING_CLUSTER_IDENTITY"
    elif len(groups) < 2:
        result["reason"] = "INSUFFICIENT_CLUSTERS"
    else:
        randomizer = random.Random(seed)
        keys = sorted(groups)
        draws = []
        for _ in range(replicates):
            sample = [row for key in randomizer.choices(keys, k=len(keys)) for row in groups[key]]
            draws.append(sum(value(row) for row in sample)/len(sample))
        result["interval"] = [_quantile(draws, .025), _quantile(draws, .975)]
    return result


def _breakdown(rows, key, feature=False):
    groups = defaultdict(list)
    for row in rows:
        values = row.get(key, []) if feature else [row.get(key) or "unknown"]
        for value in sorted(set(values)):
            groups[value].append(row)
    return {name: _metric(group) for name, group in sorted(groups.items())}


def summarize_statistics(case_records: list[dict], *, seed: int = 20261007, bootstrap_replicates: int = 10000) -> dict:
    if type(seed) is not int or type(bootstrap_replicates) is not int or bootstrap_replicates <= 0:
        raise ValueError("INVALID_BOOTSTRAP_CONFIGURATION")
    groups, seen = defaultdict(list), set()
    for row in case_records:
        key = (row.get("condition"), row.get("case_id"))
        if key[0] not in ("E0", "E3") or not isinstance(key[1], str) or not key[1]:
            raise ValueError("INVALID_CASE_IDENTITY")
        if key in seen:
            raise ValueError("DUPLICATE_CASE_CONDITION")
        seen.add(key)
        groups[key[0]].append(row)
    summaries, plans = {}, {}
    for condition, rows in sorted(groups.items()):
        rows.sort(key=lambda row: row["case_id"])
        planned = {row.get("planned_case_count", 96) for row in rows}
        if len(planned) != 1 or type(next(iter(planned))) is not int or next(iter(planned)) < len(rows):
            raise ValueError("INVALID_PLANNED_DENOMINATOR")
        n = plans[condition] = next(iter(planned))
        present = sum(row.get("present", True) is True for row in rows)
        complete = present == len(rows) == n
        micro = _metric(rows, n)
        breakdowns = {key: _breakdown(rows, key) for key in ("database_id", "domain", "difficulty")}
        summary = {"micro": micro, "coverage": {"planned": n, "present": present, "missing": n-present},
                   "database": breakdowns["database_id"], "domain": breakdowns["domain"],
                   "difficulty": breakdowns["difficulty"], "features": _breakdown(rows, "features", True),
                   "family_count": len({(r.get("database_id"), r.get("family_id")) for r in rows}),
                   "wilson_case_diagnostic": {"interval": _wilson(micro["correct"], n) if complete else None,
                       "independence_assumed": True, "reason": "DIAGNOSTIC_ONLY_CORRELATED_CASES" if complete else "INCOMPLETE_CASES"}}
        for label, key in (("macro_database", "database_id"), ("macro_domain", "domain")):
            values = list(breakdowns[key].values())
            summary[label] = sum(v["rate"] for v in values)/len(values) if complete and values else None
        summary["cluster_intervals"] = {cluster: _cluster_interval(rows, cluster, seed=seed,
            replicates=bootstrap_replicates, complete=complete, value=lambda r: int(r.get("execution_accurate") is True))
            for cluster in ("database", "family")}
        summaries[condition] = summary
    paired = {"complete": False, "reasons": [], "planned": max(plans.values(), default=96),
              "matched": 0, "wins": None, "losses": None, "ties": None, "delta": None, "cluster_intervals": None}
    if set(groups) != {"E0", "E3"}:
        paired["reasons"].append("CONDITION_MISSING")
    else:
        first = {r["case_id"]: r for r in groups["E0"]}
        second = {r["case_id"]: r for r in groups["E3"]}
        common = sorted(first.keys() & second.keys())
        paired["matched"] = len(common)
        if plans["E0"] != plans["E3"] or first.keys() != second.keys() or len(common) != paired["planned"]:
            paired["reasons"].append("INCOMPLETE_MATCHED_CASES")
        for case_id in common:
            a, b = first[case_id], second[case_id]
            if a.get("present", True) is not True or b.get("present", True) is not True:
                paired["reasons"].append("MISSING_CASE")
            if any(r.get("provenance_valid") is not True or r.get("usage_valid") is not True for r in (a, b)):
                paired["reasons"].append("INVALID_PROVENANCE_OR_TELEMETRY")
            if any(not a.get(k) or a[k] != b.get(k) for k in (
                "database_id", "family_id", "domain", "difficulty", "snapshot_identity", "scorer_identity", "benchmark_identity")):
                paired["reasons"].append("PAIR_IDENTITY_MISMATCH")
        for identity in ("scorer_identity", "benchmark_identity"):
            if len({r.get(identity) for rows in groups.values() for r in rows}) != 1:
                paired["reasons"].append("MIXED_RUN_IDENTITIES")
        paired["reasons"] = list(dict.fromkeys(paired["reasons"]))
        if not paired["reasons"]:
            differences = [{**first[key], "difference": int(second[key].get("execution_accurate") is True)
                            - int(first[key].get("execution_accurate") is True)} for key in common]
            wins = sum(r["difference"] == 1 for r in differences)
            losses = sum(r["difference"] == -1 for r in differences)
            paired.update({"complete": True, "wins": wins, "losses": losses,
                           "ties": len(common)-wins-losses, "delta": (wins-losses)/len(common),
                           "cluster_intervals": {cluster: _cluster_interval(differences, cluster, seed=seed,
                               replicates=bootstrap_replicates, complete=True, value=lambda row: row["difference"])
                               for cluster in ("database", "family")}})
    return {"version": VERSION, "seed": seed, "bootstrap_replicates": bootstrap_replicates,
            "conditions": summaries, "paired": paired, "scope": "offline_statistics_not_new_model_run",
            "limitations": {"case_independence_established": False,
                "intervals_are_descriptive_not_holdout_generalization": True,
                "database_clusters_may_be_few": True, "family_clusters_nested_in_database": True,
                "no_new_inference": True}}
