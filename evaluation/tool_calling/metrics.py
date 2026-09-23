"""
R1 Tool Calling Evaluation - Metrics Engine

Aggregates per-case results into aggregate metrics.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List

from evaluation.tool_calling.models import (
    AggregateResult,
    CaseResult,
    CaseCategory,
    ExpectedCall,
    MatchType,
    PredictedCall,
)
from evaluation.tool_calling.matching import compute_case_metrics


def compute_tool_prf(tp: int, fp: int, fn: int) -> tuple[float, float, float]:
    """Compute precision, recall, F1."""
    precision = tp / (tp + fp) if (tp + fp) > 0 else 0.0
    recall = tp / (tp + fn) if (tp + fn) > 0 else 0.0
    f1 = 2 * precision * recall / (precision + recall) if (precision + recall) > 0 else 0.0
    return precision, recall, f1


def compute_exact_call_prf(case_results: List[CaseResult]) -> tuple[float, float, float]:
    """Compute exact-call precision/recall/F1 independently of tool-name PRF.

    A prediction is an exact TP only when the tool and all required argument
    values match. A partial tool match therefore contributes one exact FP and,
    for a required expected call, one exact FN.
    """
    total_tp = 0
    total_fp = 0
    total_fn = 0

    for result in case_results:
        exact_matches = [
            match
            for match in result.matches
            if match.expected_call is not None and match.match_type == MatchType.EXACT
        ]
        exact_required = sum(
            1 for match in exact_matches if match.expected_call and not match.expected_call.optional
        )
        required_expected = sum(1 for call in result.expected_calls if not call.optional)

        total_tp += len(exact_matches)
        total_fp += max(0, len(result.predicted_calls) - len(exact_matches))
        total_fn += max(0, required_expected - exact_required)

    return compute_tool_prf(total_tp, total_fp, total_fn)


def compute_tool_prf_from_results(case_results: List[CaseResult]) -> tuple[float, float, float]:
    """
    Compute tool-level precision/recall/F1.

    A tool is correct if:
    - tool name matches expected
    - (optional: critical args match)
    """
    total_tp = sum(r.true_positives for r in case_results)
    total_fp = sum(r.false_positives for r in case_results)
    total_fn = sum(r.false_negatives for r in case_results)

    return compute_tool_prf(total_tp, total_fp, total_fn)


def compute_argument_accuracy(case_results: List[CaseResult]) -> tuple[float, float]:
    """
    Compute argument field accuracy and critical argument accuracy.
    """
    total_correct = 0
    total_fields = 0
    total_crit_correct = 0
    total_crit_fields = 0

    for result in case_results:
        for match in result.matches:
            if match.expected_call is None:
                continue

            # Count required argument fields by value, not merely presence.
            for arg_name, expected_value in match.expected_call.required_arguments.items():
                total_fields += 1
                predicted_value = match.predicted_call.arguments.get(arg_name)
                from evaluation.tool_calling.arguments import compare_values
                if compare_values(expected_value, predicted_value):
                    total_correct += 1

            # Count critical argument fields
            for arg_name in match.expected_call.critical_arguments:
                total_crit_fields += 1
                if arg_name in match.matched_critical_args:
                    total_crit_correct += 1

    arg_accuracy = total_correct / total_fields if total_fields > 0 else 0.0
    crit_accuracy = total_crit_correct / total_crit_fields if total_crit_fields > 0 else 0.0

    return arg_accuracy, crit_accuracy


def compute_tool_set_em(case_results: List[CaseResult]) -> float:
    """
    Compute tool set exact match rate.

    A case has exact match if:
    - predicted tool multiset == expected tool multiset
    """
    exact_matches = 0

    for result in case_results:
        expected_tools = {c.tool for c in result.expected_calls}
        predicted_tools = {c.tool for c in result.predicted_calls}

        if expected_tools == predicted_tools:
            exact_matches += 1

    return exact_matches / len(case_results) if case_results else 0.0


def compute_no_tool_accuracy(case_results: List[CaseResult]) -> float | None:
    """Compute no-tool accuracy, preserving the distinction between N/A and 0%."""
    no_tool_cases = [r for r in case_results if len(r.expected_calls) == 0]

    if not no_tool_cases:
        return None

    correct = sum(1 for r in no_tool_cases if len(r.predicted_calls) == 0)
    return correct / len(no_tool_cases)


def compute_forbidden_rate(case_results: List[CaseResult]) -> float:
    """
    Compute forbidden tool rate.

    Lower is better.
    """
    total_cases = len(case_results)
    if total_cases == 0:
        return 0.0

    violations = sum(1 for r in case_results if len(r.forbidden_tool_violations) > 0)
    return violations / total_cases


def compute_trajectory_success_rate(case_results: List[CaseResult]) -> float:
    """
    Compute trajectory success rate.

    Trajectory is successful if:
    - all required calls matched
    - no forbidden calls
    - critical args correct
    - ordering constraints satisfied
    """
    if not case_results:
        return 0.0

    successes = sum(1 for r in case_results if r.trajectory_success)
    return successes / len(case_results)


def compute_latency_stats(case_results: List[CaseResult]) -> tuple[float, float, float]:
    """
    Compute latency statistics.

    Returns: (mean, p50, p95)
    """
    if not case_results:
        return 0.0, 0.0, 0.0

    latencies = sorted([r.latency_ms for r in case_results])

    mean = sum(latencies) / len(latencies)

    # P50
    idx_50 = int(len(latencies) * 0.5)
    p50 = latencies[idx_50] if latencies else 0.0

    # P95
    idx_95 = int(len(latencies) * 0.95)
    p95 = latencies[idx_95] if latencies else 0.0

    return mean, p50, p95


def aggregate_case_results(
    run_id: str,
    case_results: List[CaseResult],
) -> AggregateResult:
    """
    Aggregate per-case results into aggregate metrics.
    """
    if not case_results:
        return AggregateResult(run_id=run_id, case_count=0)

    # Tool-level P/R/F1
    tool_prec, tool_rec, tool_f1 = compute_tool_prf_from_results(case_results)

    # Exact call P/R/F1
    exact_prec, exact_rec, exact_f1 = compute_exact_call_prf(case_results)

    # Argument accuracies
    arg_acc, crit_acc = compute_argument_accuracy(case_results)

    # Tool set EM
    tool_set_em = compute_tool_set_em(case_results)

    # No-tool accuracy
    no_tool_acc = compute_no_tool_accuracy(case_results)

    # Forbidden rate
    forbidden_rate = compute_forbidden_rate(case_results)

    # Trajectory success
    traj_success = compute_trajectory_success_rate(case_results)

    # Latency
    mean_lat, p50_lat, p95_lat = compute_latency_stats(case_results)

    return AggregateResult(
        run_id=run_id,
        case_count=len(case_results),
        tool_precision=tool_prec,
        tool_recall=tool_rec,
        tool_f1=tool_f1,
        exact_call_precision=exact_prec,
        exact_call_recall=exact_rec,
        exact_call_f1=exact_f1,
        argument_field_accuracy=arg_acc,
        critical_argument_accuracy=crit_acc,
        tool_set_exact_match_rate=tool_set_em,
        no_tool_accuracy=no_tool_acc,
        forbidden_tool_rate=forbidden_rate,
        trajectory_success_rate=traj_success,
        mean_latency_ms=mean_lat,
        p50_latency_ms=p50_lat,
        p95_latency_ms=p95_lat,
        case_results=case_results,
    )


def generate_error_summary(case_results: List[CaseResult]) -> Dict[str, int]:
    """
    Generate error category summary.
    """
    error_counts: Dict[str, int] = {}

    for result in case_results:
        for error in result.errors:
            error_counts[error] = error_counts.get(error, 0) + 1

    # Sort by count
    return dict(sorted(error_counts.items(), key=lambda x: -x[1]))


def generate_report(
    aggregate: AggregateResult,
    error_summary: Dict[str, int],
) -> str:
    """
    Generate markdown report.
    """
    lines = [
        "# Tool Calling Evaluation Report",
        f"",
        f"**Run ID:** `{aggregate.run_id}`",
        f"**Cases:** {aggregate.case_count}",
        f"",
        f"## Tool-Level Metrics",
        f"",
        f"| Metric | Value |",
        f"|--------|-------|",
        f"| Precision | {aggregate.tool_precision:.2%} |",
        f"| Recall | {aggregate.tool_recall:.2%} |",
        f"| F1 | {aggregate.tool_f1:.2%} |",
        f"",
        f"## Exact Call Metrics",
        f"",
        f"| Metric | Value |",
        f"|--------|-------|",
        f"| Precision | {aggregate.exact_call_precision:.2%} |",
        f"| Recall | {aggregate.exact_call_recall:.2%} |",
        f"| F1 | {aggregate.exact_call_f1:.2%} |",
        f"",
        f"## Argument Metrics",
        f"",
        f"| Metric | Value |",
        f"|--------|-------|",
        f"| Argument Field Accuracy | {aggregate.argument_field_accuracy:.2%} |",
        f"| Critical Argument Accuracy | {aggregate.critical_argument_accuracy:.2%} |",
        f"",
        f"## Other Metrics",
        f"",
        f"| Metric | Value |",
        f"|--------|-------|",
        f"| Tool Set Exact Match | {aggregate.tool_set_exact_match_rate:.2%} |",
        f"| Forbidden Tool Rate | {aggregate.forbidden_tool_rate:.2%} |",
        f"| Trajectory Success | {aggregate.trajectory_success_rate:.2%} |",
    ]

    if aggregate.no_tool_accuracy is not None:
        lines.extend([
            f"| No-Tool Accuracy | {aggregate.no_tool_accuracy:.2%} |",
        ])

    lines.extend([
        f"",
        f"## Latency",
        f"",
        f"| Metric | Value |",
        f"|--------|-------|",
        f"| Mean | {aggregate.mean_latency_ms:.0f}ms |",
        f"| P95 | {aggregate.p95_latency_ms:.0f}ms |",
    ])

    if error_summary:
        lines.extend([
            f"",
            f"## Error Summary",
            f"",
            f"| Error Type | Count |",
            f"|------------|-------|",
        ])
        for error_type, count in error_summary.items():
            lines.append(f"| {error_type} | {count} |")

    return "\n".join(lines)
