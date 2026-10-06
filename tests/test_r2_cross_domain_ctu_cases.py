"""New in-domain questions are evaluator data, not runtime mappings."""
from collections import Counter


def test_ctu_new_inventory_has_required_counts_and_distinct_features():
    from evaluation.r2_cross_domain_v1.ctu_cases import new_ctu_cases
    cases = new_ctu_cases()
    evaluation = [case for case in cases if case["split"] == "evaluation"]
    assert len(cases) == 40 and len(evaluation) == 32
    assert len({case["case_id"] for case in cases}) == 40
    assert Counter(case["difficulty"] for case in evaluation) == {"basic": 8, "medium": 16, "advanced": 8}
    assert sum("distinct" in case["features"] for case in evaluation) >= 7
    assert all("ctu13_s1" not in case["gold_sql"] and "ctu13_s4" not in case["gold_sql"] for case in cases)
    assert all(case["benchmark_locked"] is False for case in cases)
