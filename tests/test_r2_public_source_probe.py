"""Offline checks for the three named, public pilot source downloads."""

from __future__ import annotations

import io
from hashlib import sha256

from scripts.probe_r2_public_sources import SOURCES, copy_and_hash, label_group


def test_probe_downloads_only_scenario_5_7_and_otrf_day1():
    assert [source["dataset_id"] for source in SOURCES] == ["ctu13_s5", "ctu13_s7", "otrf_apt29_day1"]
    assert "Botnet-46/detailed-bidirectional-flow-labels/capture20110815-2.binetflow" in SOURCES[0]["source_url"]
    assert "Botnet-48/detailed-bidirectional-flow-labels/capture20110816-2.binetflow" in SOURCES[1]["source_url"]
    assert SOURCES[2]["source_url"].endswith("apt29_evals_day1_manual.zip")


def test_hash_covers_full_downloaded_bytes():
    payload = b"abc" * 500000
    target = io.BytesIO()
    length, digest = copy_and_hash(io.BytesIO(payload), target)
    assert length == len(payload)
    assert digest == sha256(payload).hexdigest()
    assert target.getvalue() == payload


def test_ctu_flow_prefix_is_removed_before_evidence_sampling():
    assert label_group("flow=From-Botnet-V42-TCP") == "From"
    assert label_group("flow=To-Botnet-V42-TCP") == "To"
    assert label_group("flow=Background") == "Background"
