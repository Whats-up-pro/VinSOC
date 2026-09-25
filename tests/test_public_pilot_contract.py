"""The public pilot lock changes when evidence, scorer or cases change."""

import json

import pytest

from evaluation.public_pilot.contract import canonical_sha256, verify_locked_files


def test_canonical_hash_ignores_json_key_and_file_read_order():
    assert canonical_sha256({"a.json": {"x": 1, "y": 2}, "b.json": [1, 2]}) == canonical_sha256(
        {"b.json": [1, 2], "a.json": {"y": 2, "x": 1}}
    )


def test_verification_fails_on_changed_case_bytes(tmp_path):
    cases = tmp_path / "cases"
    cases.mkdir()
    case = cases / "case.json"
    case.write_text('{"case_id":"case_1","request":"A"}')
    expected = canonical_sha256({case.name: json.loads(case.read_text())})
    verify_locked_files(cases, expected)
    case.write_text('{"case_id":"case_1","request":"B"}')
    with pytest.raises(ValueError, match="split hash mismatch"):
        verify_locked_files(cases, expected)
