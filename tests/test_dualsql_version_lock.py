"""The new evidence series has its own scorer lock; historical locks remain intact."""

import json
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
