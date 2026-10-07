"""Synthetic, hand-counted statistical fixtures; not experimental results."""
import pytest


def rows(condition="E3"):
    return [{"case_id": str(i), "database_id": "a" if i < 2 else "b", "domain": "school" if i < 2 else "music",
             "family_id": "same" if i < 2 else str(i), "difficulty": "basic", "features": ["join"],
             "execution_accurate": i < 2, "present": True, "condition": condition, "planned_case_count": 4,
             "provenance_valid": True, "usage_valid": True, "snapshot_identity": "a"*64,
             "scorer_identity": "b"*64, "benchmark_identity": "c"*64} for i in range(4)]


def test_micro_macro_breakdowns_and_seed_are_reproducible():
    from evaluation.r2_cross_domain_v1.statistics import summarize_statistics
    first = summarize_statistics(rows(), bootstrap_replicates=200)
    assert first == summarize_statistics(list(reversed(rows())), bootstrap_replicates=200)
    e3 = first["conditions"]["E3"]
    assert e3["micro"] == {"correct": 2, "n": 4, "rate": .5}
    assert e3["macro_database"] == .5
    assert e3["database"]["a"] == {"correct": 2, "n": 2, "rate": 1.0}
    assert e3["features"]["join"]["n"] == 4
    assert e3["cluster_intervals"]["family"]["clusters"] == 3
    assert e3["wilson_case_diagnostic"]["independence_assumed"] is True
    assert first["limitations"]["case_independence_established"] is False


def test_missing_cases_never_shrink_denominator_or_emit_full_run_interval():
    from evaluation.r2_cross_domain_v1.statistics import summarize_statistics
    partial = summarize_statistics(rows()[:2], bootstrap_replicates=20)["conditions"]["E3"]
    assert partial["micro"] == {"correct": 2, "n": 4, "rate": .5}
    assert partial["coverage"] == {"planned": 4, "present": 2, "missing": 2}
    assert partial["cluster_intervals"]["database"]["interval"] is None
    assert partial["cluster_intervals"]["database"]["reason"] == "INCOMPLETE_CASES"


def test_no_output_is_false_in_matched_pair_and_identity_mismatch_blocks_release():
    from evaluation.r2_cross_domain_v1.statistics import summarize_statistics
    e0, e3 = rows("E0"), rows("E3")
    e3[2].update(execution_accurate=True)
    e0[3].update(final_sql=None, error_category="TOOL_LIMIT", execution_accurate=False)
    result = summarize_statistics(e0 + e3, bootstrap_replicates=50)
    assert result["paired"]["complete"] is True
    assert result["paired"]["wins"] == 1
    assert result["paired"]["losses"] == 0
    assert result["paired"]["ties"] == 3
    assert result["paired"]["delta"] == .25
    e3[1]["snapshot_identity"] = "d"*64
    bad = summarize_statistics(e0 + e3, bootstrap_replicates=20)
    assert bad["paired"]["complete"] is False
    assert bad["paired"]["delta"] is None
    assert "PAIR_IDENTITY_MISMATCH" in bad["paired"]["reasons"]


@pytest.mark.parametrize("key", ["usage_valid", "provenance_valid"])
def test_invalid_telemetry_or_provenance_is_not_dropped_from_pair(key):
    from evaluation.r2_cross_domain_v1.statistics import summarize_statistics
    e0, e3 = rows("E0"), rows("E3")
    e3[0][key] = False
    out = summarize_statistics(e0 + e3, bootstrap_replicates=20)
    assert out["paired"]["planned"] == 4
    assert out["paired"]["complete"] is False
    assert out["conditions"]["E3"]["micro"]["n"] == 4


def test_one_cluster_cannot_estimate_and_extreme_intervals_are_valid():
    from evaluation.r2_cross_domain_v1.statistics import summarize_statistics
    data = rows()
    for row in data:
        row.update(database_id="only", family_id="only", execution_accurate=True)
    out = summarize_statistics(data, bootstrap_replicates=20)["conditions"]["E3"]
    assert out["cluster_intervals"]["database"]["interval"] is None
    assert out["cluster_intervals"]["database"]["reason"] == "INSUFFICIENT_CLUSTERS"
    assert out["wilson_case_diagnostic"]["interval"][1] == pytest.approx(1.0)
    for row in data:
        row["execution_accurate"] = False
    zero = summarize_statistics(data, bootstrap_replicates=20)["conditions"]["E3"]
    assert zero["wilson_case_diagnostic"]["interval"][0] == pytest.approx(0.0)


def test_duplicate_case_is_rejected_instead_of_double_weighting():
    from evaluation.r2_cross_domain_v1.statistics import summarize_statistics
    with pytest.raises(ValueError, match="DUPLICATE"):
        summarize_statistics(rows() + [rows()[0]], bootstrap_replicates=20)
