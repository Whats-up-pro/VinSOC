"""
R1 Tool Calling Evaluation - Call Matching

One-to-one matching between predicted and expected calls.
"""
from __future__ import annotations

from collections import Counter
from typing import Any, Dict, List, Optional, Tuple

from evaluation.tool_calling.models import (
    CallMatch,
    ExpectedCall,
    MatchType,
    OrderingConstraint,
    PredictedCall,
    ToolCallCase,
)
from evaluation.tool_calling.arguments import compare_values


def is_tool_compatible(predicted_tool: str, expected_tool: str) -> bool:
    """
    Check if predicted tool matches expected tool.
    """
    return predicted_tool == expected_tool


def check_critical_args(
    predicted_args: Dict[str, Any],
    expected_call: ExpectedCall,
) -> Tuple[bool, List[str], List[str]]:
    """
    Check if critical arguments match.

    Returns:
        (all_match, matched_args, mismatched_args)
    """
    matched = []
    mismatched = []

    for arg_name in expected_call.critical_arguments:
        expected_value = expected_call.required_arguments.get(arg_name)
        predicted_value = predicted_args.get(arg_name)

        if compare_values(expected_value, predicted_value, is_critical=True):
            matched.append(arg_name)
        else:
            mismatched.append(arg_name)

    return len(mismatched) == 0, matched, mismatched


def check_required_args(
    predicted_args: Dict[str, Any],
    expected_call: ExpectedCall,
) -> Tuple[bool, List[str], List[str]]:
    """Check that every required argument is present and value-correct.

    Returns:
        (all_match, matched_args, mismatched_or_missing_args)
    """
    matched = []
    mismatched = []

    for arg_name, expected_value in expected_call.required_arguments.items():
        if arg_name not in predicted_args:
            mismatched.append(arg_name)
            continue

        predicted_value = predicted_args[arg_name]
        if compare_values(expected_value, predicted_value):
            matched.append(arg_name)
        else:
            mismatched.append(arg_name)

    return len(mismatched) == 0, matched, mismatched


def match_single_call(
    predicted_call: PredictedCall,
    expected_call: ExpectedCall,
) -> CallMatch:
    """
    Match a single predicted call against a single expected call.

    Returns a CallMatch with the match type.
    """
    # Check tool compatibility
    if not is_tool_compatible(predicted_call.tool, expected_call.tool):
        return CallMatch(
            predicted_call=predicted_call,
            expected_call=expected_call,
            match_type=MatchType.NO_MATCH,
            critical_arg_match=False,
            required_arg_match=False,
        )

    # Check critical arguments
    crit_match, crit_matched, crit_mismatched = check_critical_args(
        predicted_call.arguments, expected_call
    )

    # Check required arguments
    req_match, req_present, req_missing = check_required_args(
        predicted_call.arguments, expected_call
    )

    # Determine match type
    # EXACT requires: tool matches + critical args match + required args match
    if crit_match and req_match:
        match_type = MatchType.EXACT
    # PARTIAL requires: tool matches but args differ
    elif is_tool_compatible(predicted_call.tool, expected_call.tool):
        match_type = MatchType.PARTIAL
    else:
        match_type = MatchType.NO_MATCH

    return CallMatch(
        predicted_call=predicted_call,
        expected_call=expected_call,
        match_type=match_type,
        critical_arg_match=crit_match,
        required_arg_match=req_match,
        matched_critical_args=crit_matched,
        mismatched_critical_args=crit_mismatched,
    )


def find_best_match(
    predicted_call: PredictedCall,
    expected_calls: List[ExpectedCall],
    used_expected: set[str],
) -> CallMatch:
    """
    Find the best matching expected call for a predicted call.

    Considers:
    1. Tool name match
    2. Critical arguments
    3. Required arguments
    """
    best_match: Optional[CallMatch] = None
    best_score = -1

    for expected_call in expected_calls:
        if expected_call.call_id in used_expected:
            continue

        match = match_single_call(predicted_call, expected_call)

        if not match.is_match:
            continue

        # Score: EXACT > PARTIAL > TOOL_ONLY
        score = 0
        if match.match_type == MatchType.EXACT:
            score = 3
        elif match.match_type == MatchType.PARTIAL:
            score = 2
        else:
            score = 1

        # Bonus for critical args matching
        if match.critical_arg_match:
            score += 0.5

        if score > best_score:
            best_score = score
            best_match = match

    if best_match:
        used_expected.add(best_match.expected_call.call_id)
        return best_match

    # No match found
    return CallMatch(
        predicted_call=predicted_call,
        expected_call=None,
        match_type=MatchType.NO_MATCH,
        critical_arg_match=False,
        required_arg_match=False,
    )


def detect_duplicates(
    predicted_calls: List[PredictedCall],
    expected_calls: List[ExpectedCall],
) -> List[Tuple[int, str]]:
    """
    Detect duplicate calls that don't correspond to multiple expected calls.

    Returns:
        List of (index, tool) for duplicate calls
    """
    # Count expected calls per tool
    expected_counts: Dict[str, int] = {}
    for ec in expected_calls:
        expected_counts[ec.tool] = expected_counts.get(ec.tool, 0) + 1

    # Track which predictions have been matched
    used_count: Dict[str, int] = {tool: 0 for tool in expected_counts}

    # Find duplicates
    duplicates = []
    for i, pc in enumerate(predicted_calls):
        tool = pc.tool
        if tool in expected_counts:
            used_count[tool] += 1
            if used_count[tool] > expected_counts[tool]:
                duplicates.append((i, tool))
        # If tool not in expected at all, it's not a duplicate, it's an extra

    return duplicates


def tool_multiset_matches(
    expected_calls: List[ExpectedCall],
    predicted_calls: List[PredictedCall],
) -> bool:
    """Match required tool multiplicity while allowing omission of optional calls."""
    required_tools = Counter(call.tool for call in expected_calls if not call.optional)
    optional_tools = Counter(call.tool for call in expected_calls if call.optional)
    predicted_tools = Counter(call.tool for call in predicted_calls)
    allowed_tools = required_tools + optional_tools

    if any(predicted_tools[tool] < count for tool, count in required_tools.items()):
        return False
    if any(tool not in allowed_tools for tool in predicted_tools):
        return False
    if any(predicted_tools[tool] > allowed_tools[tool] for tool in predicted_tools):
        return False
    return True


def check_forbidden_tools(
    predicted_calls: List[PredictedCall],
    forbidden_tools: List[str],
) -> List[str]:
    """
    Check for forbidden tool calls.

    Returns:
        List of forbidden tools that were called
    """
    violations = []
    for pc in predicted_calls:
        if pc.tool in forbidden_tools:
            violations.append(pc.tool)
    return violations


def check_ordering_constraints(
    predicted_calls: List[PredictedCall],
    ordering_constraints: List[OrderingConstraint],
) -> List[str]:
    """
    Check if ordering constraints are satisfied.

    Returns:
        List of violated constraint descriptions
    """
    if not ordering_constraints:
        return []

    violations = []

    # Build call index map
    call_indices: Dict[str, int] = {}
    for i, pc in enumerate(predicted_calls):
        call_indices[pc.tool] = i  # Simplified - just tool name

    # More detailed: track by call_id in matched context
    # For now, use tool name as proxy
    for constraint in ordering_constraints:
        before_tool = None
        after_tool = None

        # Find tools matching before/after call_ids
        for pc in predicted_calls:
            if constraint.before_call.startswith(pc.tool.split("_")[0]):
                before_tool = pc.tool
            if constraint.after_call.startswith(pc.tool.split("_")[0]):
                after_tool = pc.tool

        if before_tool and after_tool:
            idx_before = call_indices.get(before_tool, -1)
            idx_after = call_indices.get(after_tool, -1)

            if idx_before >= idx_after:
                violations.append(f"{constraint.before_call} should be before {constraint.after_call}: {constraint.reason}")

    return violations


def match_case(
    expected_case: ToolCallCase,
    predicted_calls: List[PredictedCall],
) -> Tuple[List[CallMatch], int, int, int, int, int]:
    """
    Match all predicted calls against expected calls for a case.

    Returns:
        (matches, tool_tp, exact_tp, false_positives, false_negatives, partial_tp)
    """
    matches: List[CallMatch] = []
    used_expected: set[str] = set()

    # Match each predicted call
    for predicted_call in predicted_calls:
        match = find_best_match(
            predicted_call,
            expected_case.expected_calls,
            used_expected
        )
        matches.append(match)

    # Tool-level TP: any tool match (EXACT or PARTIAL)
    tool_tp = sum(1 for m in matches if m.is_match)

    # Exact call TP: EXACT match only
    exact_tp = sum(1 for m in matches if m.is_match and m.match_type == MatchType.EXACT)

    # Partial TP
    partial_tp = sum(1 for m in matches if m.is_match and m.match_type == MatchType.PARTIAL)

    # FP: no match or tool-only
    false_positives = sum(1 for m in matches if not m.is_match)

    # Tool-level FN: expected calls with no tool-name-compatible prediction.
    required_expected = [c for c in expected_case.expected_calls if not c.optional]
    matched_expected = sum(
        1 for m in matches if m.is_match and m.expected_call and not m.expected_call.optional
    )
    false_negatives = len(required_expected) - matched_expected

    return matches, tool_tp, exact_tp, false_positives, false_negatives, partial_tp


def compute_case_metrics(
    expected_case: ToolCallCase,
    predicted_calls: List[PredictedCall],
) -> Dict[str, Any]:
    """
    Compute all metrics for a single case.
    """
    matches, tool_tp, exact_tp, fp, fn, partial_tp = match_case(expected_case, predicted_calls)

    # Forbidden tools
    forbidden_violations = check_forbidden_tools(
        predicted_calls,
        expected_case.forbidden_tools
    )

    # Duplicates
    duplicates = detect_duplicates(predicted_calls, expected_case.expected_calls)

    # Ordering
    ordering_violations = check_ordering_constraints(
        predicted_calls,
        expected_case.ordering_constraints
    )

    # Critical arg errors
    crit_errors = sum(
        1 for m in matches
        if m.expected_call and not m.critical_arg_match
    )

    # Per-case exact-call success: every required call is exact and every
    # prediction is exact. Optional expected calls may be omitted.
    required_calls = [c for c in expected_case.expected_calls if not c.optional]
    exact_required_ids = {
        m.expected_call.call_id
        for m in matches
        if (
            m.match_type == MatchType.EXACT
            and m.expected_call is not None
            and not m.expected_call.optional
        )
    }
    exact_call_match = (
        len(exact_required_ids) == len(required_calls)
        and all(m.match_type == MatchType.EXACT for m in matches)
    )

    tool_set_match = tool_multiset_matches(expected_case.expected_calls, predicted_calls)

    trajectory_success = (
        exact_call_match
        and len(forbidden_violations) == 0
        and crit_errors == 0
        and len(ordering_violations) == 0
    )

    return {
        "matches": matches,
        "tp": tool_tp,      # Tool-level TP (EXACT + PARTIAL)
        "exact_tp": exact_tp,  # Exact call TP
        "partial_tp": partial_tp,  # Partial TP
        "fp": fp,
        "fn": fn,
        "exact_call_match": exact_call_match,
        "tool_set_match": tool_set_match,
        "forbidden_violations": forbidden_violations,
        "duplicates": duplicates,
        "ordering_violations": ordering_violations,
        "critical_arg_errors": crit_errors,
        "trajectory_success": trajectory_success,
    }
