"""Fetch exactly the three manifest-pinned public source files, no credentials."""

from __future__ import annotations

import argparse
import hashlib
import os
from pathlib import Path
from urllib.parse import urlparse
from urllib.request import Request, urlopen

from evaluation.text_to_sql_snapshot import sha256_file
from scripts.build_vinsoc_public_snapshot import _load_dataset_manifest


def fetch_sources(manifest: Path) -> dict[str, str]:
    sources = _load_dataset_manifest(manifest)
    if {source["dataset_id"] for source in sources} != {"ctu13_s5", "ctu13_s7", "otrf_apt29_day1"}:
        raise ValueError("Pilot manifest must name exactly the two CTU scenarios and OTRF")
    verified = {}
    for source in sources:
        url = source["source_url"]
        if urlparse(url).hostname not in {"mcfp.felk.cvut.cz", "raw.githubusercontent.com"}:
            raise ValueError("Source URL host is outside the public pilot allowlist")
        path = Path(source["path"])
        expected = source["file_sha256"]
        if path.exists():
            if sha256_file(path) != expected:
                raise ValueError(f"Existing source checksum mismatch: {source['dataset_id']}")
        else:
            path.parent.mkdir(parents=True, exist_ok=True)
            temporary = path.with_suffix(path.suffix + ".partial")
            digest = hashlib.sha256()
            try:
                with urlopen(Request(url, headers={"User-Agent": "VinSOC-public-evaluation/1.0"}), timeout=90) as response, temporary.open("wb") as out:
                    while chunk := response.read(1024 * 1024):
                        out.write(chunk)
                        digest.update(chunk)
                if digest.hexdigest() != expected:
                    raise ValueError(f"Downloaded source checksum mismatch: {source['dataset_id']}")
                os.replace(temporary, path)
            finally:
                temporary.unlink(missing_ok=True)
        verified[source["dataset_id"]] = expected
    return verified


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, default=Path("evaluation/public_pilot/dataset_manifest.json"))
    args = parser.parse_args()
    for name, digest in fetch_sources(args.manifest).items():
        print(f"{name}: SHA-256 {digest}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
