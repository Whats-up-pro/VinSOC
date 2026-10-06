"""Source-AST selection tests; synthetic fixtures are not model results."""
from copy import deepcopy


def _query(column=1, value=5, operator=2):
    return {
        "select": [False, [[0, [0, [0, column, False], None]]]],
        "from": {"table_units": [["table_unit", 0]], "conds": []},
        "where": [[False, operator, [0, [0, column, False], None], value, None]],
        "groupBy": [], "having": [], "orderBy": [], "limit": None,
        "intersect": None, "union": None, "except": None,
    }


def test_family_ignores_constants_but_preserves_columns_and_operator():
    from evaluation.r2_cross_domain_v1.selection import sql_family

    assert sql_family(_query(value=5)) == sql_family(_query(value=999))
    assert sql_family(_query(column=1)) != sql_family(_query(column=2))
    assert sql_family(_query(operator=2)) != sql_family(_query(operator=3))


def test_difficulty_and_nested_join_features_come_from_source_ast():
    from evaluation.r2_cross_domain_v1.selection import classify_query

    basic = _query()
    assert classify_query(basic)["difficulty"] == "basic"
    joined = deepcopy(basic)
    joined["from"]["table_units"].append(["table_unit", 1])
    assert classify_query(joined)["difficulty"] == "medium"
    assert "join" in classify_query(joined)["features"]
    nested = deepcopy(basic)
    nested["where"][0][3] = basic
    assert classify_query(nested)["difficulty"] == "advanced"
    assert "nested" in classify_query(nested)["features"]


def test_paraphrase_or_changed_constant_does_not_fill_independent_family_quota():
    from evaluation.r2_cross_domain_v1.selection import qualification_report

    cases = [{"db_id": "fixture", "question": f"paraphrase {n}", "sql": _query(value=n)} for n in range(20)]
    report = qualification_report(cases)
    assert report["databases"]["fixture"]["source_question_count"] == 20
    assert report["databases"]["fixture"]["unique_family_count"] == 1
    assert report["databases"]["fixture"]["evaluation_quota_eligible"] is False
    assert report["sufficient_for_8_external_evaluation_databases"] is False


def test_candidate_selection_is_stable_and_reports_dependence():
    from evaluation.r2_cross_domain_v1.selection import select_external_candidates

    cases, entries = [], []
    for db in range(12):
        db_id = f"fixture_{db}"
        entries.append({"database_id": db_id, "split": "calibration" if db < 4 else "evaluation_locked_candidate"})
        for n in range(8):
            sql = _query(column=n + 1)
            if 2 <= n < 6:
                sql["from"]["table_units"].append(["table_unit", 1])
            if n >= 6:
                sql["where"][0][3] = _query()
            cases.append({"db_id": db_id, "question": f"fixture question {n}", "sql": sql})
    first = select_external_candidates(cases, entries, seed=20261005)
    second = select_external_candidates(list(reversed(cases)), list(reversed(entries)), seed=20261005)
    assert first == second
    assert len(first["calibration"]) == 16
    assert len(first["evaluation"]) == 64
    assert first["evaluation_feature_counts"]["join"] >= 16
    assert first["evaluation_feature_counts"]["nested"] >= 8
    assert first["independence_assumed"] is False
    assert all("gold_sql" not in case and "sql" not in case for case in first["evaluation"])
