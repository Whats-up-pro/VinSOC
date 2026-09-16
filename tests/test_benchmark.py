"""Benchmark and QA gate tests."""
from tests.benchmark_runner import run_benchmark_suite


def test_benchmark_suite_returns_comparison_metrics():
    summary = run_benchmark_suite(limit=3)
    assert summary["scenarios"] == 3
    assert 0.0 <= summary["evidence_driven_match_rate"] <= 1.0
    assert 0.0 <= summary["fixed_pipeline_match_rate"] <= 1.0
    assert summary["evidence_driven_avg_tools"] >= 0.0
    assert summary["fixed_pipeline_avg_tools"] >= 0.0
