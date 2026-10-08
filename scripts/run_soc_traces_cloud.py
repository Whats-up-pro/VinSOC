"""Run the native SOC pipeline where the existing Actions credential lives.

No gate is manufactured. A single private bundle supplies real reviews and
authority. Raw journals are encrypted to the operator's certificate, never
uploaded in plaintext. The remote immutable claim prevents runner replacement
from resetting the paid window.
"""

import argparse
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tarfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from evaluation.soc_traces_v1.release import GATES, WINDOW, ROOT, private_directory
from evaluation.soc_traces_v1.accounting import atomic_json, atomic_bytes
from evaluation.soc_traces_v1.runner import preflight, run_live
from evaluation.soc_traces_v1.reporting import render_suite, render_case, build_suite_report
from evaluation.soc_traces_v1.cloud import SocCloudStore
from evaluation.finalization.cloud_window import GitHubAPI, REPOSITORY, CloudError
from vinsoc_data.soc_corpus import fetch_sources, import_corpus, file_digest, SOURCE_MANIFEST

REQUIRED = ("OPENAI_API_KEY", "GITHUB_TOKEN", "SOC_E2E_GATES_JSON")


def validate_host_state(state):
    if (
        not isinstance(state, dict)
        or state.get("window") != WINDOW
        or state.get("prior_hosts_sealed") is not True
        or state.get("claimed") is not False
        or type(state.get("attempted_calls")) is not int
        or state["attempted_calls"] != 0
        or state.get("cost_unknown") is not False
    ):
        raise ValueError("SOC_CLOUD_PRIOR_STATE_UNVERIFIED")


def validate_documents(documents):
    if not isinstance(documents, dict) or not documents:
        raise ValueError("SOC_CLOUD_DOCUMENTS_REQUIRED")
    for name, text in documents.items():
        if not isinstance(name, str) or not re.fullmatch("[A-Za-z0-9][A-Za-z0-9_.-]{0,99}", name):
            raise ValueError("SOC_CLOUD_DOCUMENT_NAME_INVALID")
        if not isinstance(text, str) or len(text.encode()) > 200000:
            raise ValueError("SOC_CLOUD_DOCUMENT_INVALID")


def validate_bundle(bundle):
    if (
        not isinstance(bundle, dict)
        or set(bundle) != set(GATES) | {"documents", "host_state"}
        or not isinstance(bundle.get("source_reviews"), list)
        or any(not isinstance(bundle.get(k), dict) for k in GATES if k != "source_reviews")
    ):
        raise ValueError("SOC_CLOUD_GATE_BUNDLE_INVALID")
    validate_host_state(bundle["host_state"])
    validate_documents(bundle["documents"])
    if "archive_certificate.pem" not in bundle["documents"]:
        raise ValueError("SOC_CLOUD_ARCHIVE_CERTIFICATE_REQUIRED")
    return bundle


def materialize(bundle):
    root = private_directory()
    if root.exists():
        raise ValueError("SOC_CLOUD_EXISTING_PRIVATE_STATE")
    root.mkdir(parents=True, mode=0o700)
    for name, text in bundle["documents"].items():
        atomic_bytes(root / name, text.encode())
    for name in GATES:
        value = bundle[name]
        if name in ("pricing", "request_bound"):
            value = dict(value)
            field = "source_evidence_path" if name == "pricing" else "verification_evidence_path"
            document = value.get(field)
            if document not in bundle["documents"]:
                raise ValueError("SOC_CLOUD_SUPPORTING_DOCUMENT_MISSING")
            value[field] = str(root / document)
        atomic_json(root / (name + ".json"), value)
    # Inspect the certificate locally, without a model client or transmission.
    checked = subprocess.run(
        ["openssl", "x509", "-in", str(root / "archive_certificate.pem"), "-noout"],
        capture_output=True,
        env={"PATH": os.environ.get("PATH", "")},
    )
    if checked.returncode:
        raise ValueError("SOC_CLOUD_ARCHIVE_CERTIFICATE_INVALID")
    return root


def encrypt_private_archive(output, *, private_root):
    root = Path(private_root)
    plaintext = root / "private_journal.tar.gz"
    with tarfile.open(plaintext, "w:gz") as archive:
        for path in sorted(root.rglob("*")):
            if path.is_file() and path != plaintext:
                archive.add(path, arcname=str(path.relative_to(root)), recursive=False)
    sealed = Path(output) / "private_journal.cms"
    process = subprocess.run(
        [
            "openssl",
            "cms",
            "-encrypt",
            "-binary",
            "-aes-256-cbc",
            "-in",
            str(plaintext),
            "-outform",
            "DER",
            "-out",
            str(sealed),
            str(root / "archive_certificate.pem"),
        ],
        capture_output=True,
        env={"PATH": os.environ.get("PATH", "")},
    )
    plaintext.unlink()
    if process.returncode or not sealed.is_file():
        raise ValueError("SOC_CLOUD_ARCHIVE_ENCRYPTION_FAILED")
    return {
        "format": "OpenSSL CMS DER",
        "sha256": file_digest(sealed),
        "recovery_requires_operator_private_key": True,
    }


def prepare_cloud_corpus(source, corpus_dir):
    corpus_dir = Path(corpus_dir)
    corpus_dir.mkdir(parents=True, exist_ok=False)
    fetch_sources(source)
    database = corpus_dir / "corpus.duckdb"
    receipt = import_corpus(source, database, manifest=SOURCE_MANIFEST)
    atomic_json(corpus_dir / "corpus_receipt.json", receipt)
    return database


def render_cloud_outputs(live, output, inventory):
    live, output, inventory = Path(live), Path(output), Path(inventory)
    inv = json.loads(inventory.read_text())
    records = [json.loads(path.read_text()) for path in sorted((live / "cases").glob("*.json"))]
    summary = build_suite_report(inv, records, [])
    selection = json.loads((inventory.parent / "demo_selection.json").read_text())
    if selection["inventory_sha256"] != inv["inventory_sha256"]:
        raise ValueError("SOC_DEMO_SELECTION_CHANGED")
    for path in sorted((live / "cases").glob("*.json")):
        render_case(path, output)
    render_suite(summary, demo_ids=selection["ids"], output_dir=output)
    return summary


def run(mode, output_dir, env):
    if mode not in ("preflight", "live"):
        raise ValueError("SOC_CLOUD_MODE_INVALID")
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=False)
    result = {
        "scope": WINDOW,
        "mode": mode,
        "status": "blocked",
        "attempted_calls": 0,
        "responses_received": 0,
        "client_created": False,
        "window_claimed": False,
        "cost_unknown": False,
        "new_inference_cost_usd": 0,
        "human_approval": False,
    }
    store = None
    root = None
    try:
        missing = [name for name in REQUIRED if not env.get(name)]
        if missing:
            result["missing_inputs"] = missing
            raise ValueError("SOC_CLOUD_PRIVATE_INPUTS_MISSING")
        if (
            env.get("GITHUB_REPOSITORY") != REPOSITORY
            or env.get("GITHUB_REF") != "refs/heads/master"
            or env.get("OPENAI_BASE_URL")
        ):
            raise ValueError("SOC_CLOUD_CONTEXT_INVALID")
        bundle = validate_bundle(json.loads(env["SOC_E2E_GATES_JSON"]))
        api = GitHubAPI(env["GITHUB_TOKEN"])
        implementation = bundle["ci"].get("implementation_sha", "")
        store = SocCloudStore(api, implementation, env.get("GITHUB_RUN_ID", ""))
        if store.exists():
            raise ValueError("SOC_SCOPE_ALREADY_CONSUMED")
        root = materialize(bundle)
        source = ROOT / "data/soc_traces_v1/cloud-source"
        corpus_dir = ROOT / "data/soc_traces_v1/cloud-corpus"
        database = prepare_cloud_corpus(source, corpus_dir)
        inventory = ROOT / "results/evaluation_v1/soc_traces_v1/inventory.json"
        check = preflight(
            source_dir=source,
            corpus=database,
            inventory=inventory,
            reviews=root / "source_reviews.json",
            private_dir=root,
        )
        public_check = {k: v for k, v in check.items() if k != "release"}
        atomic_json(output / "preflight.json", public_check)
        result["preflight_status"] = check["status"]
        result["blockers"] = check["blockers"]
        if check["status"] != "ready_to_live":
            raise ValueError("SOC_CLOUD_PREFLIGHT_BLOCKED")
        if mode == "preflight":
            result["status"] = "ready_to_live"
            return result
        atomic_json(root / "release.json", check["release"])
        result.update(
            run_live(
                release_path=root / "release.json",
                output_dir=output / "live",
                private_dir=root,
                remote_store=store,
            )
        )
        render_cloud_outputs(output / "live", output / "views", inventory)
        return result
    except Exception as error:
        reason = str(error) if isinstance(error, (ValueError, CloudError)) else ""
        result["failure_category"] = (
            reason if re.fullmatch("SOC_[A-Z_:,]+", reason) else "SOC_CLOUD_RUNTIME_FAILURE"
        )
        return result
    finally:
        if store:
            result["window_claimed"] = store.claimed
        ledger = private_directory() / "ledger.json"
        if root and ledger.is_file():
            state = json.loads(ledger.read_text())
            result.update(
                client_created=state.get("client_created", False),
                attempted_calls=len(state.get("reservations", [])),
                responses_received=sum(
                    "response_sha256" in r for r in state.get("reservations", [])
                ),
                cost_unknown=state["unknown_cost"],
                new_inference_cost_usd=(
                    None if state["unknown_cost"] else state["estimated_cost_usd"]
                ),
            )
            if result.get("failure_category"):
                result["status"] = "partial"
            try:
                result["encrypted_private_archive"] = encrypt_private_archive(
                    output, private_root=root
                )
            except Exception:
                result.update(status="partial", private_archive_status="failed")
        atomic_json(output / "cloud_run.json", result)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", required=True, choices=["preflight", "live"])
    parser.add_argument("--output-dir", required=True, type=Path)
    args = parser.parse_args(argv)
    result = run(args.mode, args.output_dir, os.environ)
    print(json.dumps(result, ensure_ascii=False))
    return 0 if result["status"] in ("ready_to_live", "completed") else 2


if __name__ == "__main__":
    raise SystemExit(main())
