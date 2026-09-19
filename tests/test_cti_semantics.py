"""Contract tests for CTI source and validation semantics."""

import json

import pytest

from skills.cti_skill import CTISkill


def test_invalid_ioc_returns_controlled_failure() -> None:
    # Use non-empty mock to test validation, not source failure
    result = CTISkill(mock_data={"192.0.2.10": {}}).execute(indicator="not-an-ioc")

    assert not result.success
    assert result.data is None
    assert "validation" in (result.error or "").lower()


def test_unsupported_hostname_type_returns_controlled_failure() -> None:
    # Use non-empty mock to test validation, not source failure
    result = CTISkill(mock_data={"192.0.2.10": {}}).execute(
        indicator="host.example.com", indicator_type="hostname"
    )

    assert not result.success
    assert result.data is None
    assert "validation" in (result.error or "").lower()


def test_valid_ioc_without_source_fails_closed() -> None:
    # Empty mock_data {} is treated as no source configured
    result = CTISkill(mock_data={}).execute(indicator="192.0.2.10")

    assert not result.success
    assert result.data is None
    assert "no cti data source" in (result.error or "").lower()


def test_valid_ioc_with_executable_source_and_no_match_returns_unknown() -> None:
    result = CTISkill(mock_data={"198.51.100.1": {}}).execute(
        indicator="192.0.2.10"
    )

    assert result.success
    assert result.data is not None
    assert result.data["reputation"] == "unknown"
    assert result.data["observed_evidence"][0]["value"] == "not_found"


def test_valid_ioc_with_source_match_returns_result() -> None:
    result = CTISkill(
        mock_data={"192.0.2.10": {"reputation": "malicious", "confidence": "high"}}
    ).execute(indicator="192.0.2.10")

    assert result.success
    assert result.data is not None
    assert result.data["reputation"] == "malicious"
    assert result.data["confidence"] == "high"


@pytest.mark.parametrize("source_kwargs", [{"threatfox_data": {}}])
def test_explicit_empty_threatfox_source_is_executable(source_kwargs) -> None:
    """Empty ThreatFox file {} is a valid source that returns unknown for unmatched IOCs."""
    result = CTISkill(**source_kwargs).execute(indicator="192.0.2.10")

    assert result.success
    assert result.data is not None
    assert result.data["reputation"] == "unknown"


@pytest.mark.parametrize("path_kind", ["missing", "invalid_json", "unreadable"])
def test_unusable_threatfox_path_fails_closed(tmp_path, path_kind) -> None:
    if path_kind == "missing":
        path = tmp_path / "missing.json"
    elif path_kind == "invalid_json":
        path = tmp_path / "invalid.json"
        path.write_text("{not valid json", encoding="utf-8")
    else:
        path = tmp_path / "directory"
        path.mkdir()

    result = CTISkill(threatfox_path=str(path)).execute(indicator="192.0.2.10")

    assert not result.success
    assert result.data is None
    assert "no cti data source" in (result.error or "").lower()


def test_non_string_indicator_returns_controlled_failure() -> None:
    # Use non-empty mock to test validation, not source failure
    result = CTISkill(mock_data={"192.0.2.10": {}}).execute(indicator=12345)

    assert not result.success
    assert result.data is None
    assert "validation" in (result.error or "").lower()


def test_valid_empty_threatfox_file_is_executable(tmp_path) -> None:
    path = tmp_path / "empty.json"
    path.write_text(json.dumps({}), encoding="utf-8")

    result = CTISkill(threatfox_path=str(path)).execute(indicator="192.0.2.10")

    assert result.success
    assert result.data is not None
    assert result.data["reputation"] == "unknown"


def test_invalid_utf8_threatfox_file_fails_closed(tmp_path) -> None:
    path = tmp_path / "invalid_utf8.json"
    path.write_bytes(b"{\xff}")

    result = CTISkill(threatfox_path=str(path)).execute(indicator="192.0.2.10")

    assert not result.success
    assert result.data is None
    assert "no cti data source" in (result.error or "").lower()


def test_non_mapping_threatfox_json_fails_closed(tmp_path) -> None:
    path = tmp_path / "list.json"
    path.write_text(json.dumps([]), encoding="utf-8")

    result = CTISkill(threatfox_path=str(path)).execute(indicator="192.0.2.10")

    assert not result.success
    assert result.data is None
    assert "no cti data source" in (result.error or "").lower()


def test_explicit_mock_source_takes_priority_over_threatfox_source() -> None:
    # mock_data={} is no source, so ThreatFox should be used
    result = CTISkill(
        threatfox_data={"192.0.2.10": {"reputation": "malicious"}},
    ).execute(indicator="192.0.2.10")

    assert result.success
    assert result.data is not None
    assert result.data["reputation"] == "malicious"


@pytest.mark.parametrize("record", ["malicious", None, []])
def test_malformed_threatfox_record_fails_closed(tmp_path, record) -> None:
    path = tmp_path / "malformed_record.json"
    path.write_text(json.dumps({"192.0.2.10": record}), encoding="utf-8")

    result = CTISkill(threatfox_path=str(path)).execute(indicator="192.0.2.10")

    assert not result.success
    assert result.data is None
    assert "no cti data source" in (result.error or "").lower()


@pytest.mark.parametrize("record", ["malicious", None, []])
def test_malformed_constructor_threatfox_record_fails_closed(record) -> None:
    result = CTISkill(threatfox_data={"192.0.2.10": record}).execute(
        indicator="192.0.2.10"
    )

    assert not result.success
    assert result.data is None
    assert "no cti data source" in (result.error or "").lower()


def test_valid_threatfox_match_returns_result() -> None:
    result = CTISkill(
        threatfox_data={
            "192.0.2.10": {
                "reputation": "malicious",
                "confidence": "high",
                "related_actors": [],
                "related_malware": ["Example Malware"],
                "mitre_techniques": [],
                "sources": [],
                "observed_evidence": [],
            }
        }
    ).execute(indicator="192.0.2.10")

    assert result.success
    assert result.data is not None
    assert result.data["reputation"] == "malicious"
    assert result.data["related_malware"] == ["Example Malware"]
