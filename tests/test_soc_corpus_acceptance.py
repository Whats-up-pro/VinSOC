"""Required acceptance runs actual pinned source/DB queries, never fake observations."""

from datetime import timedelta
import json
import os
from pathlib import Path
import duckdb
import pytest
from tests.soc_support import feature, sources, corpus

ROOT = Path(__file__).resolve().parents[1]


def test_required_corpus_absence_fails(tmp_path):
    m = feature("vinsoc_data.soc_corpus")
    assert hasattr(m, "require_corpus_paths")
    with pytest.raises(ValueError, match="SOC_REQUIRED_CORPUS_ABSENT"):
        m.require_corpus_paths(tmp_path, tmp_path / "missing.duckdb", required=True)


def test_prepare_rejects_stale_importer_receipt(sources, corpus, tmp_path):
    from scripts.prepare_soc_traces import main

    repository, receipt = corpus
    (tmp_path / "corpus.duckdb").symlink_to(repository.database.resolve())
    stale = dict(receipt, importer_sha256="0" * 64)
    (tmp_path / "corpus_receipt.json").write_text(json.dumps(stale))
    with pytest.raises(ValueError, match="SOC_REQUIRED_CORPUS_IDENTITY_CHANGED"):
        main(["--source-dir", str(sources), "--output-dir", str(tmp_path)])


def required_paths(sources, corpus):
    if os.environ.get("VINSOC_SOC_REQUIRED") == "1":
        feature("vinsoc_data.soc_corpus").require_corpus_paths(
            Path(os.environ.get("VINSOC_SOC_SOURCE_DIR", "missing")),
            Path(os.environ.get("VINSOC_SOC_CORPUS_PATH", "missing")),
            required=True,
        )
    return sources, corpus[0]


def resolve(row, pointer):
    value = row
    for part in pointer.lstrip("/").split("/"):
        if isinstance(value, str):
            value = json.loads(value)
        value = value[int(part)] if isinstance(value, list) else value[part]
    return json.loads(value) if isinstance(value, str) else value


def test_source_pointer_and_digest_acceptance(sources, corpus):
    source, r = required_paths(sources, corpus)
    m = feature("vinsoc_data.soc_corpus")
    inv = json.loads((ROOT / "results/evaluation_v1/soc_traces_v1/inventory.json").read_text())
    ids = [c["scenario_id"] for c in inv["cases"]]
    with duckdb.connect() as c:
        query = c.execute(
            "SELECT scenario_id,alert,trace FROM read_parquet(?) WHERE scenario_id IN (SELECT unnest(?))",
            [str(source / "test.parquet"), ids],
        )
        rows = {
            values[0]: dict(zip([col[0] for col in query.description], values))
            for values in query.fetchall()
        }
    total = 0
    for scenario in ids:
        inp = r.input_provenance_for(scenario)
        assert m.digest(resolve(rows[scenario], inp["json_pointer"])) == inp["raw_record_sha256"]
        for resource in ("events", "asset", "process_tree", "related_alerts"):
            for record in r.records(scenario, resource):
                p = record["provenance"]
                assert p["file_sha256"] == m.SOURCE_MANIFEST["files"]["test.parquet"]
                assert (
                    m.digest(resolve(rows[scenario], p["json_pointer"])) == p["raw_record_sha256"]
                )
                assert not {"decisive", "ground_truth", "verdict", "confidence"} & set(
                    record["data"]
                )
                total += 1
    assert total > 64


def test_real_scoped_tool_queries(sources, corpus):
    _, r = required_paths(sources, corpus)
    m = feature("skills.soc_corpus_skill")
    scenario = r.scenario_ids("test")[0]
    before = feature("vinsoc_data.soc_corpus").file_digest(r.database)
    skill = m.SocCorpusSkill(
        m.SocCorpusContext(r, scenario, "S1", r.metadata()["source_revision"], r.sha256)
    )
    result = skill.search_events()
    assert result["rows"]
    row = next(x for x in result["rows"] if x["observed_at"])
    t = m._utc(row["observed_at"])
    start = t.isoformat()
    end = (t + timedelta(seconds=1)).isoformat()
    assert row["source_record_id"] in {
        x["source_record_id"] for x in skill.search_events(start=start, end=end)["rows"]
    }
    assert row["source_record_id"] not in {
        x["source_record_id"]
        for x in skill.search_events(start=(t - timedelta(seconds=1)).isoformat(), end=start)[
            "rows"
        ]
    }
    assert all(x["provenance"]["scenario_id"] == scenario for x in result["rows"])
    assert len(feature("vinsoc_data.soc_corpus").canonical(result).encode()) <= 20000
    tree = skill.get_context(resource="process_tree")
    assert all(x["observed_at"] is None for x in tree["rows"])
    assert before == feature("vinsoc_data.soc_corpus").file_digest(r.database)
