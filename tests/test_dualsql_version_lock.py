"""The new evidence series has its own scorer lock; historical locks remain intact."""

import json
import hashlib
from pathlib import Path

from evaluation.text_to_sql_snapshot import sha256_file


def test_dualsql_lock_pins_current_scorer_without_rewriting_pilot_history():
    new = json.loads(Path("evaluation/dualsql_lite/BASE.lock").read_text())
    old = json.loads(Path("evaluation/public_pilot/VERSION.lock").read_text())
    source = "vinsoc_data/duckdb_store.py"
    assert new["scorer_file_sha256"][source] == sha256_file(Path(source))
    assert new["scorer_file_sha256"][source] != old["scorer_file_sha256"][source]
    assert new["r2_split_sha256"] == old["r2_split_sha256"]
    assert new["snapshot_content_sha256"] == old["snapshot_content_sha256"]


def test_selected_public_dev_configuration_is_locked_to_preserved_v4_artifacts():
    lock = json.loads(Path("evaluation/dualsql_lite/SELECTED_CONFIG.lock").read_text())
    directory = Path(
        "results/evaluation_v1/public_pilot/dualsql_lite/dualsql-lite-36122033957-1"
    )
    assert lock["series_version"] == "dualsql_lite_public_dev_v4"
    assert lock["selected_experiment"] == "E0"
    assert lock["results"]["E0"]["correct"] == 5
    assert lock["results"]["E2"]["correct"] == 5
    assert lock["results"]["E0"]["cost_usd"] < lock["results"]["E2"]["cost_usd"]
    for experiment, expected in lock["artifact_sha256"].items():
        actual = hashlib.sha256((directory / f"{experiment}.json").read_bytes()).hexdigest()
        assert actual == expected
