"""Focused regression tests for runtime-only SQL semantic findings."""

from vinsoc_text2sql.service import _semantic_findings


def test_singular_conjunctive_count_rejects_union_all_of_per_scope_counts():
    question = (
        "Count distinct destination IPs receiving TCP flows after 2011-08-15 17:00:00 "
        "in CTU scenario 5 and after 2011-08-16 14:00:00 in scenario 7; use strict time boundaries."
    )
    sql = """SELECT 'ctu13_s5' AS scenario, COUNT(DISTINCT dst_ip) AS distinct_dst_ips
FROM network_flows
WHERE source_dataset = 'ctu13_s5' AND protocol = 'TCP'
UNION ALL
SELECT 'ctu13_s7' AS scenario, COUNT(DISTINCT dst_ip) AS distinct_dst_ips
FROM network_flows
WHERE source_dataset = 'ctu13_s7' AND protocol = 'TCP'"""

    findings = _semantic_findings(question, sql)

    assert any("SINGULAR_COUNT_MULTIPLE_ROWS" in finding for finding in findings)
    assert any("CONJUNCTIVE_SCOPES_SEPARATED" in finding for finding in findings)


def test_explicit_per_scope_count_allows_union_all_shape():
    question = "Count distinct destination IPs for each scenario."
    sql = """SELECT scenario, COUNT(DISTINCT dst_ip) FROM flows WHERE scenario = 'a' GROUP BY scenario
UNION ALL
SELECT scenario, COUNT(DISTINCT dst_ip) FROM flows WHERE scenario = 'b' GROUP BY scenario"""

    assert _semantic_findings(question, sql) == []
