"""Offline planned status/checkpoint contracts, not fabricated predictions."""

import json
from pathlib import Path
import pytest
from tests.soc_support import feature, sources, corpus

ROOT = Path(__file__).resolve().parents[1]


def test_preflight_zero_calls(sources, corpus, tmp_path):
    m = feature("evaluation.soc_traces_v1.runner")
    result = m.preflight(
        source_dir=sources,
        corpus=corpus[0].database,
        inventory=ROOT / "results/evaluation_v1/soc_traces_v1/inventory.json",
        reviews=tmp_path / "missing.json",
        private_dir=tmp_path,
    )
    assert (
        result["status"] == "blocked"
        and result["attempted_calls"] == 0
        and result["client_created"] is False
    )


def test_inventory_or_source_mutation_blocks(sources, corpus, tmp_path):
    m = feature("evaluation.soc_traces_v1.runner")
    p = tmp_path / "inventory.json"
    p.write_text('{"inventory_sha256":"changed","cases":[]}')
    r = m.preflight(
        source_dir=sources,
        corpus=corpus[0].database,
        inventory=p,
        reviews=tmp_path / "missing.json",
        private_dir=tmp_path,
    )
    assert r["status"] == "blocked" and "SOC_INVENTORY_CHANGED" in r["blockers"]


def test_records_preserve_planned_ids(corpus):
    m = feature("evaluation.soc_traces_v1.runner")
    inv = json.loads((ROOT / "results/evaluation_v1/soc_traces_v1/inventory.json").read_text())
    records = m.planned_records(inv, corpus[0])
    assert len(records) == 128 and all(
        r["status"] == "not_run" and not r.get("report") for r in records
    )
    assert {r["scenario_id"] for r in records} == {c["scenario_id"] for c in inv["cases"]}


def test_partial_after_failure_persists(tmp_path):
    m = feature("evaluation.soc_traces_v1.runner")
    receipt = {
        "scenario_id": "unit",
        "condition": "S1",
        "status": "partial",
        "unit_boundary_only": True,
    }
    p = m.checkpoint_case(case_id="unit", condition="S1", receipt=receipt, output_dir=tmp_path)
    assert json.loads(p.read_text())["status"] == "partial"
    changed = {**receipt, "status": "failed"}
    m.checkpoint_case(case_id="unit", condition="S1", receipt=changed, output_dir=tmp_path)
    with pytest.raises(ValueError):
        m.checkpoint_case(case_id="unit", condition="S1", receipt=receipt, output_dir=tmp_path)


def test_output_change_cannot_reopen_scope():
    m = feature("evaluation.soc_traces_v1.runner")
    import inspect

    assert "private_directory()" in inspect.getsource(m.run_live)
    assert "SocRunJournal.claim" in inspect.getsource(m.run_live)
