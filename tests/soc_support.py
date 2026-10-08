"""Pinned public corpus inputs for SOC tests; never model predictions."""

import hashlib
import importlib
import importlib.util
import json
import os
from pathlib import Path
import urllib.request

import pytest

REV = "fe94a95dadbd188c2bf137a9785b82cb5f7865c2"
DIGESTS = {
    "test": "9ef309da7ad04f173d89a5f8da238f20db4051b92514531667b30c042da7bd1a",
    "validation": "94cd7987fe3064cd0933d8fabed75d517e955f8faa8723ac07c9b01446cdfcf7",
}


def feature(name):
    assert importlib.util.find_spec(name) is not None, f"Missing SOC feature: {name}"
    return importlib.import_module(name)


@pytest.fixture(scope="session")
def sources():
    root = Path(os.environ.get("VINSOC_SOC_SOURCE_DIR", "data/soc_traces_v1/source"))
    root.mkdir(parents=True, exist_ok=True)
    for split, digest in DIGESTS.items():
        p = root / (split + ".parquet")
        if not p.exists():
            url = f"https://huggingface.co/datasets/alirezaaminzadeh/soc-agent-traces-100k/resolve/{REV}/data/{split}-00000-of-00001.parquet"
            with urllib.request.urlopen(url, timeout=90) as response:
                p.write_bytes(response.read())
        assert hashlib.sha256(p.read_bytes()).hexdigest() == digest
    return root


@pytest.fixture(scope="session")
def corpus(sources, tmp_path_factory):
    m = feature("vinsoc_data.soc_corpus")
    configured = os.environ.get("VINSOC_SOC_CORPUS_PATH")
    if configured:
        path = Path(configured)
        receipt = json.loads((path.parent / "corpus_receipt.json").read_text())
        m.verify_sources(sources, m.SOURCE_MANIFEST)
    else:
        path = tmp_path_factory.mktemp("soc-real") / "corpus.duckdb"
        receipt = m.import_corpus(sources, path, manifest=m.SOURCE_MANIFEST)
    return m.SocCorpusRepository(path, expected_sha256=receipt["database_sha256"]), receipt


def raw_case(sources):
    import duckdb

    with duckdb.connect() as con:
        cursor = con.execute(
            "SELECT * FROM read_parquet(?) LIMIT 1", [str(sources / "test.parquet")]
        )
        return dict(zip([d[0] for d in cursor.description], cursor.fetchone()))
