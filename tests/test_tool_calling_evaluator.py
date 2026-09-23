"""
R1 Tool Calling Evaluator - Unit Tests

Tests the argument normalization, call matching, and metrics engine.
"""
import pytest
from evaluation.tool_calling.arguments import (
    normalize_ip,
    normalize_domain,
    normalize_hash,
    normalize_hostname,
    normalize_indicator,
    compare_values,
    normalize_arguments,
)
from evaluation.tool_calling.matching import (
    match_single_call,
    find_best_match,
    detect_duplicates,
    check_forbidden_tools,
    compute_case_metrics,
)
from evaluation.tool_calling.models import (
    ExpectedCall,
    PredictedCall,
    ToolCallCase,
    CaseCategory,
    CaseDifficulty,
    MatchType,
)


class TestArgumentNormalization:
    """Tests for argument normalization."""

    def test_normalize_ip_strips_leading_zeros(self):
        assert normalize_ip("001.002.003.004") == "1.2.3.4"

    def test_normalize_ip_preserves_canonical(self):
        assert normalize_ip("1.2.3.4") == "1.2.3.4"

    def test_normalize_ip_invalid_returns_none(self):
        assert normalize_ip("not.an.ip") is None
        assert normalize_ip("999.999.999.999") is None
        assert normalize_ip(123) is None

    def test_normalize_domain_lowercase(self):
        assert normalize_domain("Example.COM") == "example.com"

    def test_normalize_domain_strips_trailing_dot(self):
        assert normalize_domain("example.com.") == "example.com"

    def test_normalize_domain_strips_protocol(self):
        assert normalize_domain("https://Example.COM/") == "example.com"
        assert normalize_domain("http://test.org") == "test.org"

    def test_normalize_hash_lowercase(self):
        # MD5 is 32 chars
        md5 = "da8b8be96d7c4a1f2c3b4d5e6f7a8b9c"
        assert normalize_hash(md5) == md5
        assert normalize_hash(md5.upper()) == md5

    def test_normalize_hash_validates_length(self):
        assert normalize_hash("a" * 32) is not None  # MD5
        assert normalize_hash("a" * 40) is not None  # SHA1
        assert normalize_hash("a" * 64) is not None  # SHA256
        assert normalize_hash("a" * 16) is None  # Invalid

    def test_normalize_hostname(self):
        assert normalize_hostname("WS001") == "ws001"
        assert normalize_hostname("SERVER-01") == "server-01"

    def test_compare_values_exact_match(self):
        assert compare_values("1.2.3.4", "1.2.3.4") is True
        assert compare_values("aabbcc", "aabbcc") is True

    def test_compare_values_normalized_match(self):
        assert compare_values("001.002.003.004", "1.2.3.4") is True
        assert compare_values("Example.COM", "example.com") is True
        assert compare_values("AABBCC", "aabbcc") is True

    def test_compare_values_mismatch(self):
        assert compare_values("1.2.3.4", "5.6.7.8") is False
        assert compare_values("ws001", "ws002") is False

    def test_normalize_arguments_cti(self):
        args = {
            "indicator": "1.2.3.4",
            "indicator_type": "ipv4"
        }
        normalized = normalize_arguments("cti_enrichment", args)
        assert normalized["indicator"] == "1.2.3.4"
        assert normalized["indicator_type"] == "ipv4"


class TestCallMatching:
    """Tests for call matching."""

    def test_exact_match_cti(self):
        """CTI call with correct indicator matches exactly."""
        expected = ExpectedCall(
            call_id="cti_1",
            tool="cti_enrichment",
            required_arguments={"indicator": "1.2.3.4", "indicator_type": "ipv4"},
            critical_arguments=["indicator"],
        )
        predicted = PredictedCall(
            tool="cti_enrichment",
            arguments={"indicator": "1.2.3.4", "indicator_type": "ipv4"},
        )

        match = match_single_call(predicted, expected)
        assert match.match_type == MatchType.EXACT
        assert match.critical_arg_match is True

    def test_tool_mismatch(self):
        """Different tool does not match."""
        expected = ExpectedCall(
            call_id="net_1",
            tool="network_investigation",
            required_arguments={"indicator": "1.2.3.4"},
            critical_arguments=["indicator"],
        )
        predicted = PredictedCall(
            tool="cti_enrichment",
            arguments={"indicator": "1.2.3.4"},
        )

        match = match_single_call(predicted, expected)
        assert match.match_type == MatchType.NO_MATCH

    def test_wrong_indicator_is_partial_match(self):
        """Correct tool but wrong indicator is partial match."""
        expected = ExpectedCall(
            call_id="cti_1",
            tool="cti_enrichment",
            required_arguments={"indicator": "1.2.3.4"},
            critical_arguments=["indicator"],
        )
        predicted = PredictedCall(
            tool="cti_enrichment",
            arguments={"indicator": "5.6.7.8"},
        )

        match = match_single_call(predicted, expected)
        assert match.match_type == MatchType.PARTIAL
        assert match.critical_arg_match is False
        assert "indicator" in match.mismatched_critical_args

    def test_find_best_match_skips_used(self):
        """Already matched expected calls are skipped."""
        expected_calls = [
            ExpectedCall(
                call_id="cti_1",
                tool="cti_enrichment",
                required_arguments={"indicator": "1.2.3.4"},
                critical_arguments=["indicator"],
            ),
            ExpectedCall(
                call_id="cti_2",
                tool="cti_enrichment",
                required_arguments={"indicator": "8.8.8.8"},
                critical_arguments=["indicator"],
            ),
        ]
        used_expected = {"cti_1"}

        predicted = PredictedCall(
            tool="cti_enrichment",
            arguments={"indicator": "1.2.3.4"},
        )

        match = find_best_match(predicted, expected_calls, used_expected)
        # Should match cti_2, not cti_1 (already used)
        assert match.expected_call.call_id == "cti_2"

    def test_detect_duplicates(self):
        """Duplicate calls are detected."""
        predicted = [
            PredictedCall(tool="cti_enrichment", arguments={"indicator": "1.2.3.4"}),
            PredictedCall(tool="cti_enrichment", arguments={"indicator": "1.2.3.4"}),
        ]
        expected = [
            ExpectedCall(
                call_id="cti_1",
                tool="cti_enrichment",
                required_arguments={"indicator": "1.2.3.4"},
                critical_arguments=["indicator"],
            ),
        ]

        duplicates = detect_duplicates(predicted, expected)
        # First CTI matches expected, second is duplicate
        assert len(duplicates) == 1
        assert duplicates[0][1] == "cti_enrichment"

    def test_check_forbidden_tools(self):
        """Forbidden tool violations are detected."""
        predicted = [
            PredictedCall(tool="cti_enrichment", arguments={}),
            PredictedCall(tool="network_investigation", arguments={}),
        ]
        forbidden = ["endpoint_investigation"]

        violations = check_forbidden_tools(predicted, forbidden)
        assert len(violations) == 0

    def test_check_forbidden_tools_violation(self):
        """Forbidden tool is detected."""
        predicted = [
            PredictedCall(tool="endpoint_investigation", arguments={}),
        ]
        forbidden = ["endpoint_investigation"]

        violations = check_forbidden_tools(predicted, forbidden)
        assert len(violations) == 1
        assert violations[0] == "endpoint_investigation"


class TestMetricsComputation:
    """Tests for metrics computation."""

    def test_tp_fp_fn_counts(self):
        """True positives, false positives, false negatives are counted correctly."""
        expected_calls = [
            ExpectedCall(
                call_id="cti_1",
                tool="cti_enrichment",
                required_arguments={"indicator": "1.2.3.4"},
                critical_arguments=["indicator"],
            ),
            ExpectedCall(
                call_id="net_1",
                tool="network_investigation",
                required_arguments={"indicator": "1.2.3.4"},
                critical_arguments=["indicator"],
            ),
        ]

        predicted_calls = [
            PredictedCall(
                tool="cti_enrichment",
                arguments={"indicator": "1.2.3.4"},
            ),
            # Missing: network_investigation
            PredictedCall(
                tool="endpoint_investigation",  # Wrong tool
                arguments={"host": "WS001"},
            ),
        ]

        case = ToolCallCase(
            case_id="test_001",
            category=CaseCategory.CTI_NETWORK,
            difficulty=CaseDifficulty.INTERMEDIATE,
            request="Test request",
            reference_time="2026-09-22T00:00:00Z",
            expected_calls=expected_calls,
        )

        metrics = compute_case_metrics(case, predicted_calls)
        assert metrics["tp"] == 1  # CTI matched
        assert metrics["fp"] >= 1  # endpoint is extra
        assert metrics["fn"] >= 1  # network is missing

    def test_trajectory_success_requires_all(self):
        """Trajectory success requires all conditions."""
        expected_calls = [
            ExpectedCall(
                call_id="cti_1",
                tool="cti_enrichment",
                required_arguments={"indicator": "1.2.3.4"},
                critical_arguments=["indicator"],
            ),
        ]

        # Perfect prediction
        predicted_calls = [
            PredictedCall(
                tool="cti_enrichment",
                arguments={"indicator": "1.2.3.4"},
            ),
        ]

        case = ToolCallCase(
            case_id="test_002",
            category=CaseCategory.CTI_ONLY,
            difficulty=CaseDifficulty.BASIC,
            request="Test",
            reference_time="2026-09-22T00:00:00Z",
            expected_calls=expected_calls,
        )

        metrics = compute_case_metrics(case, predicted_calls)
        assert metrics["trajectory_success"] is True


class TestGoldenEvaluatorTests:
    """
    Golden tests from R1 spec section 44.

    These are the canonical test cases that define expected behavior.
    """

    def test_gold_cti_network_prediction_cti_cti_network(self):
        """
        Gold: CTI(A), Network(A)
        Prediction: CTI(A), CTI(A), Network(A)
        Expected: TP=2, FP=1, FN=0
        """
        expected_calls = [
            ExpectedCall(
                call_id="cti_1",
                tool="cti_enrichment",
                required_arguments={"indicator": "1.2.3.4"},
                critical_arguments=["indicator"],
            ),
            ExpectedCall(
                call_id="net_1",
                tool="network_investigation",
                required_arguments={"indicator": "1.2.3.4"},
                critical_arguments=["indicator"],
            ),
        ]

        predicted_calls = [
            PredictedCall(tool="cti_enrichment", arguments={"indicator": "1.2.3.4"}),
            PredictedCall(tool="cti_enrichment", arguments={"indicator": "1.2.3.4"}),
            PredictedCall(tool="network_investigation", arguments={"indicator": "1.2.3.4"}),
        ]

        case = ToolCallCase(
            case_id="golden_001",
            category=CaseCategory.CTI_NETWORK,
            difficulty=CaseDifficulty.BASIC,
            request="Test",
            reference_time="2026-09-22T00:00:00Z",
            expected_calls=expected_calls,
        )

        metrics = compute_case_metrics(case, predicted_calls)
        # 2 correct (CTI + Network), 1 duplicate (extra CTI)
        assert metrics["tp"] == 2
        assert len(metrics["duplicates"]) >= 1

    def test_gold_endpoint_prediction_cti_endpoint(self):
        """
        Gold: Endpoint(host=WS001)
        Prediction: CTI(indicator=WS001), Endpoint(host=WS001)
        Expected: Tool TP=1, Tool FP=1, Forbidden tool=1, Trajectory success=false
        """
        expected_calls = [
            ExpectedCall(
                call_id="ep_1",
                tool="endpoint_investigation",
                required_arguments={"host": "WS001"},
                critical_arguments=["host"],
            ),
        ]

        forbidden_tools = ["cti_enrichment"]

        predicted_calls = [
            PredictedCall(tool="cti_enrichment", arguments={"indicator": "WS001"}),
            PredictedCall(tool="endpoint_investigation", arguments={"host": "WS001"}),
        ]

        case = ToolCallCase(
            case_id="golden_002",
            category=CaseCategory.HOSTNAME_LED,
            difficulty=CaseDifficulty.INTERMEDIATE,
            request="Test hostname investigation",
            reference_time="2026-09-22T00:00:00Z",
            expected_calls=expected_calls,
            forbidden_tools=forbidden_tools,
        )

        metrics = compute_case_metrics(case, predicted_calls)

        # Tool TP = 1 (endpoint matched)
        assert metrics["tp"] == 1
        # Tool FP = 1 (cti is extra)
        assert metrics["fp"] >= 1
        # Forbidden tool violation
        assert "cti_enrichment" in metrics["forbidden_violations"]
        # Trajectory should fail
        assert metrics["trajectory_success"] is False

    def test_gold_cti_wrong_indicator(self):
        """
        Gold: CTI(indicator=1.2.3.4)
        Prediction: CTI(indicator=8.8.8.8)
        Expected: tool-name match=yes, exact-call match=no, critical arg accuracy=0

        With new behavior:
        - Tool matches: tp=1 (PARTIAL)
        - But critical args wrong: critical_arg_errors=1
        - Exact match: exact_tp=0
        - Trajectory fails due to wrong arg
        """
        expected_calls = [
            ExpectedCall(
                call_id="cti_1",
                tool="cti_enrichment",
                required_arguments={"indicator": "1.2.3.4"},
                critical_arguments=["indicator"],
            ),
        ]

        predicted_calls = [
            PredictedCall(tool="cti_enrichment", arguments={"indicator": "8.8.8.8"}),
        ]

        case = ToolCallCase(
            case_id="golden_003",
            category=CaseCategory.CTI_ONLY,
            difficulty=CaseDifficulty.BASIC,
            request="Test CTI",
            reference_time="2026-09-22T00:00:00Z",
            expected_calls=expected_calls,
        )

        metrics = compute_case_metrics(case, predicted_calls)

        # Tool matches (PARTIAL)
        assert metrics["tp"] == 1
        # Exact match fails
        assert metrics["exact_tp"] == 0
        # But critical args wrong
        assert metrics["critical_arg_errors"] == 1
        # Trajectory fails due to wrong arg
        assert metrics["trajectory_success"] is False


class TestMetricRegressionCoverage:
    """Regression tests for mentor-facing Tool Calling accuracy semantics."""

    def test_wrong_required_value_is_partial_not_exact(self):
        """A required field with the wrong value must invalidate exact-call correctness."""
        expected = ExpectedCall(
            call_id="cti_1",
            tool="cti_enrichment",
            required_arguments={"indicator": "1.2.3.4", "indicator_type": "ipv4"},
            critical_arguments=["indicator"],
        )
        predicted = PredictedCall(
            tool="cti_enrichment",
            arguments={"indicator": "1.2.3.4", "indicator_type": "domain"},
        )

        match = match_single_call(predicted, expected)

        assert match.match_type == MatchType.PARTIAL
        assert match.required_arg_match is False

    def test_exact_call_prf_and_argument_accuracy_are_value_sensitive(self):
        """Tool-name accuracy may be perfect while exact-call and argument accuracy are not."""
        from evaluation.tool_calling.metrics import aggregate_case_results
        from evaluation.tool_calling.models import CaseResult

        expected = ExpectedCall(
            call_id="cti_1",
            tool="cti_enrichment",
            required_arguments={"indicator": "1.2.3.4", "indicator_type": "ipv4"},
            critical_arguments=["indicator"],
        )
        predicted = PredictedCall(
            tool="cti_enrichment",
            arguments={"indicator": "1.2.3.4", "indicator_type": "domain"},
        )
        case = ToolCallCase(
            case_id="regression_metric_001",
            category=CaseCategory.CTI_ONLY,
            difficulty=CaseDifficulty.BASIC,
            request="Investigate 1.2.3.4",
            reference_time="2026-09-23T00:00:00Z",
            expected_calls=[expected],
        )
        metrics = compute_case_metrics(case, [predicted])
        result = CaseResult(
            case_id=case.case_id,
            expected_calls=case.expected_calls,
            predicted_calls=[predicted],
            matches=metrics["matches"],
            true_positives=metrics["tp"],
            false_positives=metrics["fp"],
            false_negatives=metrics["fn"],
        )

        aggregate = aggregate_case_results("regression", [result])

        assert aggregate.tool_precision == 1.0
        assert aggregate.tool_recall == 1.0
        assert aggregate.exact_call_precision == 0.0
        assert aggregate.exact_call_recall == 0.0
        assert aggregate.argument_field_accuracy == 0.5


def test_zero_no_tool_accuracy_is_serialized_as_zero_not_null():
    from evaluation.tool_calling.metrics import aggregate_case_results
    from evaluation.tool_calling.models import CaseResult

    result = CaseResult(
        case_id="no_tool_wrong_001",
        expected_calls=[],
        predicted_calls=[PredictedCall(tool="cti_enrichment", arguments={"indicator": "1.2.3.4"})],
    )

    aggregate = aggregate_case_results("no-tool-zero", [result])

    assert aggregate.no_tool_accuracy == 0.0
    assert aggregate.to_dict()["no_tool_accuracy"] == 0.0


def test_tool_set_exact_match_is_multiset_aware():
    from evaluation.tool_calling.metrics import compute_tool_set_em
    from evaluation.tool_calling.models import CaseResult

    expected = [
        ExpectedCall(call_id="net_1", tool="network_investigation"),
        ExpectedCall(call_id="net_2", tool="network_investigation"),
    ]
    result = CaseResult(
        case_id="duplicate_required_001",
        expected_calls=expected,
        predicted_calls=[PredictedCall(tool="network_investigation", arguments={})],
    )

    assert compute_tool_set_em([result]) == 0.0


def test_tool_set_exact_match_allows_omitting_optional_calls():
    from evaluation.tool_calling.metrics import compute_tool_set_em
    from evaluation.tool_calling.models import CaseResult

    expected = [
        ExpectedCall(call_id="cti_1", tool="cti_enrichment"),
        ExpectedCall(call_id="net_optional", tool="network_investigation", optional=True),
    ]
    result = CaseResult(
        case_id="optional_001",
        expected_calls=expected,
        predicted_calls=[PredictedCall(tool="cti_enrichment", arguments={})],
    )

    assert compute_tool_set_em([result]) == 1.0
