"""Recovery contract checks; no model calls or fabricated database predictions."""

import hashlib
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/recover_vinsoc_spider_bundle.py"


def run(*args):
    return subprocess.run(
        [sys.executable, str(SCRIPT), "--repo", str(ROOT), *args],
        capture_output=True, text=True, check=False,
    )


def test_preflight_reports_missing_archive_without_creating_outputs(tmp_path):
    result = run("--check-only", "--archive", str(tmp_path / "missing.zip"))
    assert result.returncode == 1
    report = json.loads(result.stdout)
    assert report["status"] == "BLOCKED_SOURCE_ARCHIVE_MISSING"
    assert report["external_model_calls"] == 0
    assert not list(tmp_path.iterdir())


def test_recovery_refuses_historical_output_before_any_download():
    registry = ROOT / "evaluation/r2_cross_domain_v1/runtime_registry.json"
    before = hashlib.sha256(registry.read_bytes()).hexdigest()
    result = run("--output", "evaluation/r2_cross_domain_v1")
    assert result.returncode == 1
    assert json.loads(result.stdout)["status"] == "BLOCKED_OUTPUT_OUTSIDE_RECOVERY_ROOT"
    assert hashlib.sha256(registry.read_bytes()).hexdigest() == before


def test_recovery_contract_rejects_changed_source_identity():
    import pytest

    from evaluation.r2_cross_domain_v1.data import RegistryError
    from scripts.recover_vinsoc_spider_bundle import assert_recovered_identity

    metadata = ROOT / "evaluation/r2_cross_domain_v1"
    entry = json.loads((metadata / "runtime_registry.json").read_text())["databases"][0]
    observed = json.loads((metadata / "build_receipts" / f"{entry['database_id']}.json").read_text())["build_1"]
    observed.update({key: entry[key] for key in ("schema", "relationships", "row_counts", "primary_keys")})
    assert_recovered_identity(entry, observed)
    observed["source_sha256"] = "0" * 64
    with pytest.raises(RegistryError, match="RECOVERY_IDENTITY_MISMATCH:source_sha256"):
        assert_recovered_identity(entry, observed)


def test_bundle_rejects_live_wal_before_accepting_snapshot(tmp_path):
    import pytest

    from evaluation.r2_cross_domain_v1.data import RegistryError
    from scripts.recover_vinsoc_spider_bundle import verify_closed_snapshot

    snapshot = tmp_path / "db.duckdb"
    Path(str(snapshot) + ".wal").touch()
    with pytest.raises(RegistryError, match="RECOVERY_WAL_PRESENT"):
        verify_closed_snapshot(snapshot, "0" * 64)
