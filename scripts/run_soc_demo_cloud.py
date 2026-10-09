"""Run one authentic SOC alert-to-report demonstration in GitHub Actions."""

import hashlib
import json
import os
from pathlib import Path
import re
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from agent.orchestrator import InvestigationOrchestrator
from agent.soc_provider import SocProvider
from evaluation.finalization.cloud_window import GitHubAPI, REPOSITORY
from evaluation.soc_traces_v1.accounting import atomic_json
from evaluation.soc_traces_v1.demo import (
    DEMO_CASE_ID,
    DEMO_CONDITION,
    DEMO_WINDOW,
    SocDemoCloudStore,
    SocDemoJournal,
    build_demo_release,
)
from evaluation.soc_traces_v1.release import ROOT, runtime_hashes
from evaluation.soc_traces_v1.reporting import render_case, technical_valid
from evaluation.soc_traces_v1.runner import bound, checkpoint_case, scan_visible, _verify_account
from scripts.run_soc_traces_cloud import prepare_cloud_corpus
from skills.soc_corpus_skill import SocCorpusContext
from vinsoc_data.soc_corpus import SocCorpusRepository

REQUIRED = ("OPENAI_API_KEY", "GITHUB_TOKEN", "GITHUB_SHA", "GITHUB_RUN_ID")


def _identities(source, database, receipt, implementation_sha):
    import duckdb
    import httpx
    import openai

    artifacts = ROOT / "results/evaluation_v1/soc_traces_v1"
    return {
        "implementation_sha": implementation_sha,
        "runtime": runtime_hashes(),
        "environment": {
            "python": ".".join(map(str, sys.version_info[:3])),
            "duckdb": duckdb.__version__,
            "openai": openai.__version__,
            "httpx": httpx.__version__,
        },
        "source_revision": receipt["source_revision"],
        "source_dir": str(source.resolve()),
        "corpus_path": str(database.resolve()),
        "corpus_receipt": bound(database.parent / "corpus_receipt.json"),
        "inventory": bound(artifacts / "inventory.json"),
        "gold": bound(artifacts / "gold.json"),
        "demo_selection": bound(artifacts / "demo_selection.json"),
    }


def run(output_dir, env):
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=False)
    result = {
        "scope": DEMO_WINDOW,
        "status": "blocked",
        "case_id": DEMO_CASE_ID,
        "condition": DEMO_CONDITION,
        "attempted_calls": 0,
        "responses_received": 0,
        "client_created": False,
        "window_claimed": False,
        "cost_unknown": False,
        "new_inference_cost_usd": 0,
        "source_review_status": "deferred_after_demo",
        "human_review_status": "awaiting_human",
    }
    client = repository = journal = store = None
    receipt_path = None
    try:
        missing = [name for name in REQUIRED if not env.get(name)]
        if missing:
            result["missing_inputs"] = missing
            raise ValueError("SOC_DEMO_CLOUD_INPUTS_MISSING")
        if (
            env.get("GITHUB_REPOSITORY") != REPOSITORY
            or env.get("GITHUB_REF") != "refs/heads/master"
            or env.get("OPENAI_BASE_URL")
            or not re.fullmatch(r"[0-9a-f]{40}", env["GITHUB_SHA"])
        ):
            raise ValueError("SOC_DEMO_CLOUD_CONTEXT_INVALID")
        private = Path(env.get("RUNNER_TEMP", "/tmp")) / "vinsoc-soc-demo-private"
        private.mkdir(parents=True, exist_ok=False, mode=0o700)
        source = private / "source"
        database = prepare_cloud_corpus(source, private / "corpus")
        corpus_receipt = json.loads((database.parent / "corpus_receipt.json").read_text())
        identities = _identities(source, database, corpus_receipt, env["GITHUB_SHA"])
        release = build_demo_release(
            identities=identities,
            implementation_sha=env["GITHUB_SHA"],
            api_key_sha256=hashlib.sha256(env["OPENAI_API_KEY"].encode()).hexdigest(),
            operator="Thiên Vũ Hiếu",
            authorization_statement=(
                "User instructed on 2026-10-09 to continue until an authentic E2E result exists; "
                "this authorizes one locked demonstration with a USD 1 hard cap."
            ),
        )
        atomic_json(private / "release.json", release)
        checked = __import__(
            "evaluation.soc_traces_v1.demo", fromlist=["validate_demo_release"]
        ).validate_demo_release(release)
        _verify_account(checked)
        api = GitHubAPI(env["GITHUB_TOKEN"])
        store = SocDemoCloudStore(api, env["GITHUB_SHA"], env["GITHUB_RUN_ID"])
        if store.exists():
            raise ValueError("SOC_DEMO_SCOPE_ALREADY_CONSUMED")
        journal = SocDemoJournal.claim(
            release, ledger_path=private / "ledger.json", remote_store=store
        )
        repository = SocCorpusRepository(database, expected_sha256=corpus_receipt["database_sha256"])
        scan_visible(repository)
        context = SocCorpusContext(
            repository,
            DEMO_CASE_ID,
            DEMO_CONDITION,
            corpus_receipt["source_revision"],
            corpus_receipt["database_sha256"],
        )
        import openai

        client = openai.OpenAI(
            api_key=env["OPENAI_API_KEY"],
            base_url="https://api.openai.com/v1",
            max_retries=0,
            http_client=openai.DefaultHttpxClient(trust_env=False),
            timeout=60,
        )
        journal.mark_client_created()
        provider = SocProvider(client, journal=journal, context=context)
        record = {
            "scenario_id": DEMO_CASE_ID,
            "condition": DEMO_CONDITION,
            "status": "not_run",
            "review_status": "awaiting_human",
            "data_origin": "synthetic",
            "input": {"kind": "alert", "alert": repository.input_for(DEMO_CASE_ID)},
            "model_outputs": [],
            "report": None,
            "cost_unknown": False,
        }
        receipt_path = checkpoint_case(
            case_id=DEMO_CASE_ID,
            condition=DEMO_CONDITION,
            receipt=record,
            output_dir=output / "live",
        )

        def response_checkpoint(raw, metadata):
            partial = {
                **record,
                "status": "partial",
                "model_outputs": [
                    {
                        "id": raw.get("id"),
                        "model": raw.get("model"),
                        "message": (raw.get("choices") or [{}])[0].get("message"),
                        "usage": raw.get("usage"),
                        "metadata": metadata,
                    }
                ],
                "provider": provider.get_run_metadata(),
            }
            checkpoint_case(
                case_id=DEMO_CASE_ID,
                condition=DEMO_CONDITION,
                receipt=partial,
                output_dir=output / "live",
            )

        provider.response_checkpoint = response_checkpoint
        case = InvestigationOrchestrator(provider=provider).investigate_alert(
            record["input"], soc_context=context
        )
        meta = case.metadata
        final = {
            **record,
            "status": meta["technical_status"],
            "case": case.to_dict(),
            "report": meta["soc_report"],
            "model_outputs": meta["model_outputs"],
            "provider": meta["provider"],
            "cost_unknown": meta["cost_unknown"],
            "release_sha256": release["release_sha256"],
            "implementation_sha": env["GITHUB_SHA"],
        }
        receipt_path = checkpoint_case(
            case_id=DEMO_CASE_ID,
            condition=DEMO_CONDITION,
            receipt=final,
            output_dir=output / "live",
        )
        rendered = render_case(receipt_path, output / "report")
        state = journal.snapshot()
        result.update(
            status="completed" if technical_valid(json.loads(receipt_path.read_text())) else "failed",
            technical_valid=technical_valid(json.loads(receipt_path.read_text())),
            client_created=state.get("client_created", False),
            attempted_calls=len(state["reservations"]),
            responses_received=sum("response_sha256" in row for row in state["reservations"]),
            cost_unknown=state["unknown_cost"],
            new_inference_cost_usd=(None if state["unknown_cost"] else state["estimated_cost_usd"]),
            report_files={key: str(Path(value).relative_to(output)) for key, value in rendered.items() if key in ("json", "html", "markdown")},
        )
    except Exception as error:
        reason = str(error) if isinstance(error, (ValueError, RuntimeError)) else ""
        result["failure_category"] = (
            reason if re.fullmatch(r"SOC_[A-Z0-9_:,]+", reason) else "SOC_DEMO_RUNTIME_FAILURE"
        )
        if journal:
            state = journal.snapshot()
            result.update(
                status="partial" if state["reservations"] else "blocked",
                client_created=state.get("client_created", False),
                attempted_calls=len(state["reservations"]),
                responses_received=sum("response_sha256" in row for row in state["reservations"]),
                cost_unknown=state["unknown_cost"],
                new_inference_cost_usd=(None if state["unknown_cost"] else state["estimated_cost_usd"]),
            )
        if receipt_path and receipt_path.is_file():
            try:
                render_case(receipt_path, output / "report")
            except Exception:
                pass
    finally:
        if store:
            result["window_claimed"] = store.claimed
        if journal:
            journal.finish()
        if client:
            client.close()
        if repository:
            repository.close()
        atomic_json(output / "cloud_run.json", result)
    return result


def main():
    if len(sys.argv) != 2:
        raise SystemExit("usage: run_soc_demo_cloud.py OUTPUT_DIR")
    result = run(Path(sys.argv[1]), os.environ)
    print(json.dumps(result, ensure_ascii=False))
    return 0 if result["status"] == "completed" else 2


if __name__ == "__main__":
    raise SystemExit(main())
