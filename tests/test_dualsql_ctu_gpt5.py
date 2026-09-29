"""Identity regressions for the immutable CTU GPT-5 Mini E0 baseline."""

from __future__ import annotations

import copy
import hashlib
import importlib
import json
from pathlib import Path

import pytest


REPORT = Path("results/evaluation_v1/ctu_network_public/gpt5_e0/36520685612/ctu-r2-result.json")
DEV_LOCK = Path("evaluation/ctu_network_public/VERSION.lock")
REPORT_SHA256 = "33b35678171309c1a8958c1d9818499915986942e6936a03428df8fa0544bc15"


def _contract():
    try:
        return importlib.import_module("evaluation.dualsql_lite_ctu_gpt5.contract")
    except ModuleNotFoundError:
        pytest.fail("E0 compatibility contract is missing")


def _lock_payload():
    report = json.loads(REPORT.read_text(encoding="utf-8"))
    dev = json.loads(DEV_LOCK.read_text(encoding="utf-8"))
    return {
        "version": "dualsql_lite_ctu_gpt5_v1",
        "e0_report_sha256": REPORT_SHA256,
        "e0_run_id": "36520685612",
        "dev_version": "ctu_network_public_dev_v1",
        "case_ids": dev["case_ids"],
        "split_sha256": dev["split_sha256"],
        "logical_snapshot_sha256": dev["logical_snapshot_sha256"],
        "source_file_sha256": dev["source_file_sha256"],
        "builder_scorer_sha256": dev["builder_scorer_sha256"],
        "system_prompt_sha256": report["provenance"]["system_prompt_sha256"],
        "schema_context_sha256": report["provenance"]["schema_context_sha256"],
        "model_config_sha256": report["model_config_sha256"],
        "model": "gpt-5-mini-2025-08-07",
        "reasoning_effort": "low",
        "max_completion_tokens": 1000,
        "max_retries": 0,
        "pricing": {
            "input_usd_per_million": 0.25,
            "output_usd_per_million": 2.0,
            "source": "https://developers.openai.com/api/docs/models/gpt-5-mini",
            "verified_utc": "2026-09-29T10:33:37Z",
            "stop_if_current_official_price_differs": True,
        },
    }


def _write_variant(tmp_path, payload, lock, *, update_report_sha=True):
    report_path = tmp_path / "e0.json"
    report_path.write_text(json.dumps(payload, sort_keys=True) + "\n", encoding="utf-8")
    if update_report_sha:
        lock["e0_report_sha256"] = hashlib.sha256(report_path.read_bytes()).hexdigest()
    lock_path = tmp_path / "SERIES.lock"
    lock_path.write_text(json.dumps(lock) + "\n", encoding="utf-8")
    return report_path, lock_path


def test_exact_e0_report_is_accepted_without_provider(monkeypatch, tmp_path):
    monkeypatch.setattr("agent.provider.create_provider", lambda *a, **kw: pytest.fail("provider called"))
    contract = _contract()
    lock_path = tmp_path / "SERIES.lock"
    lock_path.write_text(json.dumps(_lock_payload()) + "\n", encoding="utf-8")
    result = contract.verify_e0_baseline(REPORT, lock_path)
    assert result.run_id == "36520685612"
    assert result.case_ids == tuple(f"ctu_sql_{index:03d}" for index in range(1, 9))
    assert result.execution_accurate == 0
    assert result.known_cost_usd == pytest.approx(0.00384725)
    assert result.report_sha256 == REPORT_SHA256


@pytest.mark.parametrize("field", [
    "report_sha", "run_status", "case_ids", "case_result_ids", "usage_records",
    "actual_model", "requested_model", "reasoning_effort", "token_cap",
    "sdk_retries", "split_hash", "snapshot_hash", "source_hash",
    "scorer_hash", "system_prompt_hash", "schema_hash", "model_config_hash",
    "request_model", "request_reasoning", "request_cap", "request_temperature",
    "request_question", "pricing_rate",
])
def test_e0_identity_mutation_is_rejected(tmp_path, field):
    contract = _contract()
    payload = copy.deepcopy(json.loads(REPORT.read_text(encoding="utf-8")))
    lock = _lock_payload()
    if field == "report_sha":
        lock["e0_report_sha256"] = "0" * 64
    elif field == "run_status":
        payload["run_status"] = "partial"
    elif field == "case_ids":
        payload["case_ids"][7] = "ctu_sql_007"
    elif field == "case_result_ids":
        payload["case_results"][7]["case_id"] = "ctu_sql_007"
    elif field == "usage_records":
        payload["case_results"][0]["input_tokens"] = 0
    elif field == "actual_model":
        payload["case_results"][0]["actual_model"] = "different-model"
    elif field == "requested_model":
        payload["config"]["model"] = "different-model"
    elif field == "reasoning_effort":
        payload["config"]["reasoning_effort"] = "high"
    elif field == "token_cap":
        payload["config"]["max_completion_tokens"] = 999
    elif field == "sdk_retries":
        payload["config"]["max_retries"] = 1
    elif field == "split_hash":
        payload["provenance"]["split_sha256"] = "0" * 64
    elif field == "snapshot_hash":
        payload["provenance"]["logical_snapshot_sha256"] = "0" * 64
    elif field == "source_hash":
        payload["provenance"]["source_file_sha256"]["ctu13_s5"] = "0" * 64
    elif field == "scorer_hash":
        payload["provenance"]["builder_scorer_sha256"]["evaluation/text_to_sql.py"] = "0" * 64
    elif field == "system_prompt_hash":
        payload["provenance"]["system_prompt_sha256"] = "0" * 64
    elif field == "schema_hash":
        payload["provenance"]["schema_context_sha256"] = "0" * 64
    elif field == "model_config_hash":
        payload["model_config_sha256"] = "0" * 64
    elif field == "request_model":
        payload["serialized_requests"][0]["model"] = "different-model"
    elif field == "request_reasoning":
        payload["serialized_requests"][0]["reasoning_effort"] = "high"
    elif field == "request_cap":
        payload["serialized_requests"][0]["max_completion_tokens"] = 999
    elif field == "request_temperature":
        payload["serialized_requests"][0]["temperature"] = 0
    elif field == "request_question":
        payload["serialized_requests"][0]["messages"][1]["content"] = "changed"
    elif field == "pricing_rate":
        payload["pricing"]["input_usd_per_million"] = 0.15
    report_path, lock_path = _write_variant(
        tmp_path, payload, lock, update_report_sha=field != "report_sha"
    )
    expected_error = {
        "report_sha": "fixed report SHA-256",
        "run_status": "run status",
        "case_ids": "case IDs",
        "case_result_ids": "case result IDs",
        "usage_records": "case 1 usage",
        "actual_model": "case 1 response identity",
        "requested_model": "config model",
        "reasoning_effort": "config reasoning_effort",
        "token_cap": "config max_completion_tokens",
        "sdk_retries": "config max_retries",
        "split_hash": "split_sha256",
        "snapshot_hash": "logical_snapshot_sha256",
        "source_hash": "source_file_sha256",
        "scorer_hash": "builder_scorer_sha256",
        "system_prompt_hash": "system_prompt_sha256",
        "schema_hash": "schema_context_sha256",
        "model_config_hash": "model_config_sha256",
        "request_model": "request 1 model",
        "request_reasoning": "request 1 reasoning_effort",
        "request_cap": "request 1 max_completion_tokens",
        "request_temperature": "request 1 forbidden keys",
        "request_question": "request 1 question",
        "pricing_rate": "pricing rates",
    }[field]
    with pytest.raises(ValueError, match=expected_error):
        contract.verify_e0_baseline(report_path, lock_path)


def test_e0_descriptive_null_temperature_is_allowed(tmp_path):
    contract = _contract()
    payload = json.loads(REPORT.read_text(encoding="utf-8"))
    assert payload["config"]["temperature"] is None
    assert all("temperature" not in request for request in payload["serialized_requests"])
    lock_path = tmp_path / "SERIES.lock"
    lock_path.write_text(json.dumps(_lock_payload()), encoding="utf-8")
    assert contract.verify_e0_baseline(REPORT, lock_path).report_sha256 == REPORT_SHA256
