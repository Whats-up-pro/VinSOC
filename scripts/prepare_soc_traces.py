"""Prepare pinned corpus offline; this command never creates a model client."""

import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from vinsoc_data.soc_corpus import (
    SOURCE_MANIFEST,
    fetch_sources,
    verify_sources,
    import_corpus,
    file_digest,
    require_corpus_paths,
)


def main(argv=None):
    p = argparse.ArgumentParser()
    p.add_argument("--source-dir", type=Path, required=True)
    p.add_argument("--output-dir", type=Path)
    p.add_argument("--fetch", action="store_true")
    p.add_argument("--verify-only", action="store_true")
    args = p.parse_args(argv)
    if args.fetch:
        fetch_sources(args.source_dir)
    verify_sources(args.source_dir, SOURCE_MANIFEST)
    if args.verify_only:
        print(json.dumps({"status": "source_verified", "new_model_calls": 0}))
        return 0
    if args.output_dir is None:
        p.error("--output-dir required for import")
    args.output_dir.mkdir(parents=True, exist_ok=True)
    database = args.output_dir / "corpus.duckdb"
    receipt_path = args.output_dir / "corpus_receipt.json"
    if database.exists():
        if not receipt_path.is_file() or json.loads(receipt_path.read_text())[
            "database_sha256"
        ] != file_digest(database):
            raise ValueError("SOC_EXISTING_CORPUS_UNVERIFIED")
        require_corpus_paths(args.source_dir, database, required=True)
        print(json.dumps({"status": "existing_corpus_verified", "new_model_calls": 0}))
        return 0
    receipt = import_corpus(args.source_dir, database, manifest=SOURCE_MANIFEST)
    receipt.update(
        new_model_calls=0, attribution="alirezaaminzadeh/soc-agent-traces-100k; Apache-2.0"
    )
    receipt_path.write_text(json.dumps(receipt, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({k: v for k, v in receipt.items() if k != "quarantine"}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
