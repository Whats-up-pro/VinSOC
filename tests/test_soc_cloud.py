"""Cloud safety boundaries only; no fabricated provider responses or approvals."""

import importlib.util
import json
from pathlib import Path
import pytest
import subprocess
import tarfile
from tests.soc_support import sources, corpus


def cloud():
    assert (
        importlib.util.find_spec("scripts.run_soc_traces_cloud") is not None
    ), "SOC cloud runner missing"
    from scripts import run_soc_traces_cloud

    return run_soc_traces_cloud


def test_cloud_missing_inputs_has_no_client_or_claim(tmp_path):
    result = cloud().run("live", tmp_path / "outputs", {})
    assert result["status"] == "blocked"
    assert result["attempted_calls"] == 0
    assert result["client_created"] is False
    assert result["window_claimed"] is False
    assert result["missing_inputs"] == ["OPENAI_API_KEY", "GITHUB_TOKEN", "SOC_E2E_GATES_JSON"]


def test_cloud_bundle_cannot_write_without_source_reviews(tmp_path):
    with pytest.raises(ValueError, match="SOC_CLOUD_GATE_BUNDLE_INVALID"):
        cloud().validate_bundle({"account": {"operator": "unit parser only"}})
    assert list(tmp_path.iterdir()) == []


def test_cloud_state_requires_previous_hosts_sealed():
    m = cloud()
    with pytest.raises(ValueError, match="SOC_CLOUD_PRIOR_STATE_UNVERIFIED"):
        m.validate_host_state(
            {
                "window": "soc-traces-20261008-v1",
                "prior_hosts_sealed": False,
                "claimed": False,
                "attempted_calls": 0,
            }
        )


def test_cloud_secret_documents_reject_path_traversal():
    with pytest.raises(ValueError, match="SOC_CLOUD_DOCUMENT_NAME_INVALID"):
        cloud().validate_documents({"../runtime.py": "unit source proof only"})


def test_journal_remote_claim_required_before_native_claim(tmp_path):
    from evaluation.soc_traces_v1.accounting import SocRunJournal
    import inspect

    signature = inspect.signature(SocRunJournal.claim)
    assert "remote_store" in signature.parameters


def test_cloud_run_mode_is_explicit():
    with pytest.raises(ValueError, match="SOC_CLOUD_MODE_INVALID"):
        cloud().run("auto", Path("unused"), {})


def test_cloud_preparation_imports_actual_pinned_sources(sources, tmp_path):
    m = cloud()
    assert hasattr(m, "prepare_cloud_corpus")
    database = m.prepare_cloud_corpus(sources, tmp_path / "corpus")
    receipt = json.loads((database.parent / "corpus_receipt.json").read_text())
    assert receipt["cases"] == {"test": 5031, "validation": 4984}
    assert receipt["imported_records"] == 87028


def test_cloud_render_preserves_not_run_instead_of_fabricating_reports(corpus, tmp_path):
    m = cloud()
    assert hasattr(m, "render_cloud_outputs")
    from evaluation.soc_traces_v1.runner import planned_records, checkpoint_case

    inventory = (
        Path(__file__).resolve().parents[1] / "results/evaluation_v1/soc_traces_v1/inventory.json"
    )
    for record in planned_records(json.loads(inventory.read_text()), corpus[0]):
        checkpoint_case(
            case_id=record["scenario_id"],
            condition=record["condition"],
            receipt=record,
            output_dir=tmp_path / "live",
        )
    summary = m.render_cloud_outputs(tmp_path / "live", tmp_path / "views", inventory)
    assert summary["status"] == "not_run"
    assert summary["conditions"]["S1"]["agreement"] is None
    assert (tmp_path / "views/index.html").is_file()


def test_private_archive_uses_real_encryption_and_round_trip(tmp_path):
    m = cloud()
    root = tmp_path / "private"
    root.mkdir()
    key = tmp_path / "unit_key.pem"
    cert = root / "archive_certificate.pem"
    subprocess.run(
        [
            "openssl",
            "req",
            "-x509",
            "-newkey",
            "rsa:2048",
            "-nodes",
            "-keyout",
            str(key),
            "-out",
            str(cert),
            "-days",
            "1",
            "-subj",
            "/CN=VinSOC unit archive only",
        ],
        capture_output=True,
        check=True,
    )
    plaintext = b"Unit archive boundary input; no operator approval or SDK response."
    (root / "unit.txt").write_bytes(plaintext)
    output = tmp_path / "public"
    output.mkdir()
    receipt = m.encrypt_private_archive(output, private_root=root)
    assert receipt["recovery_requires_operator_private_key"] is True
    sealed = output / "private_journal.cms"
    assert plaintext not in sealed.read_bytes()
    restored = tmp_path / "restored.tar.gz"
    subprocess.run(
        [
            "openssl",
            "cms",
            "-decrypt",
            "-binary",
            "-inform",
            "DER",
            "-in",
            str(sealed),
            "-recip",
            str(cert),
            "-inkey",
            str(key),
            "-out",
            str(restored),
        ],
        capture_output=True,
        check=True,
    )
    with tarfile.open(restored) as archive:
        assert archive.extractfile("unit.txt").read() == plaintext
