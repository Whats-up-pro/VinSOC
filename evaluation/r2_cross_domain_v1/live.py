"""Authentic release transport with durable, no-retry accounting.

The historical synthetic controller is preserved byte-for-byte. This versioned
live adapter uses the same pinned prompts, tools, grounding and SQL validators;
it never labels a real SDK call as synthetic to bypass that controller's guard.
Actual benchmark release needs new private paid authorization. No default live
authority is granted by importing this module or by the demo authorization.
"""
from __future__ import annotations

from copy import deepcopy
import hashlib
import json
import math
import os
from pathlib import Path
import subprocess
from time import monotonic

from .release import CONDITIONS, REQUEST_CONTRACT, WINDOW_ID, canonical_hash, preflight_release


def canonical_release_root():
    return Path.home()/".vinsoc"/"live-windows"/WINDOW_ID


def _atomic_write(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix+".tmp")
    with temporary.open("w", encoding="utf-8") as handle:
        json.dump(value, handle, indent=2, sort_keys=True, ensure_ascii=False)
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(temporary, path)


class RequestJournal:
    @classmethod
    def claim(cls, path, *, max_requests, budget_usd, prior_usd, reserve_usd, implementation_sha):
        path = Path(path)
        if path.resolve() != (canonical_release_root()/"ledger.json").resolve():
            raise ValueError("NONCANONICAL_RELEASE_LEDGER")
        if (type(max_requests) is not int or not 0 < max_requests <= 672
            or any(type(v) not in (int, float) or not math.isfinite(v) or v < 0 for v in (budget_usd, prior_usd, reserve_usd))
            or prior_usd+max_requests*reserve_usd > budget_usd):
            raise ValueError("FULL_RUN_BUDGET_INSUFFICIENT")
        if path.exists():
            raise ValueError("RELEASE_WINDOW_CONSUMED")
        path.parent.mkdir(parents=True, exist_ok=True)
        try:
            with (path.parent/"claim.json").open("x", encoding="utf-8") as handle:
                json.dump({"implementation_sha": implementation_sha, "window_id": WINDOW_ID}, handle)
                handle.flush()
                os.fsync(handle.fileno())
        except FileExistsError:
            raise ValueError("RELEASE_WINDOW_CONSUMED") from None
        self = cls()
        self.path, self.max_requests, self.budget, self.reserve = path, max_requests, budget_usd, reserve_usd
        self.data = {"window_id": WINDOW_ID, "implementation_sha": implementation_sha, "consumed": True,
                     "attempted": 0, "received": 0, "valid_usage": 0, "known_usd": prior_usd,
                     "prior_usd": prior_usd, "pending_exposure_usd": 0.0, "cost_unknown": False,
                     "terminal": False, "events": []}
        self.persist()
        return self

    def persist(self):
        _atomic_write(self.path, self.data)

    def begin(self, payload):
        if self.data["terminal"]:
            raise ValueError("TERMINAL_RELEASE")
        if (self.data["attempted"] >= self.max_requests or self.data["cost_unknown"]
            or self.data["known_usd"]+self.data["pending_exposure_usd"]+self.reserve > self.budget):
            raise ValueError("REQUEST_BUDGET_OR_CALL_CAP")
        event = {"request_sha256": canonical_hash(payload), "received": False, "usage": None,
                 "cost_usd": None, "reserved_usd": self.reserve}
        self.data["events"].append(event)
        self.data["attempted"] += 1
        self.data["pending_exposure_usd"] += self.reserve
        # A crash after this point is paid exposure, never a free retry.
        self.data["cost_unknown"] = True
        self.persist()
        return event


class GuardedTransport:
    transport_kind = "openai"

    def __init__(self, sdk, journal, contract, pricing):
        self.sdk, self.journal, self.contract, self.pricing = sdk, journal, contract, pricing

    def counters(self):
        return {k: self.journal.data[k] for k in ("attempted", "received", "valid_usage", "terminal")}

    def request(self, payload):
        if self.journal.data["terminal"]:
            raise ValueError("TERMINAL_RELEASE")
        if (any(payload.get(k) != self.contract[k] for k in ("model", "reasoning_effort", "max_completion_tokens", "service_tier"))
            or "temperature" in payload or not isinstance(payload.get("messages"), list)
            or len(payload["messages"]) > self.contract["max_messages"]
            or len(json.dumps(payload, ensure_ascii=False).encode()) > self.contract["max_request_bytes"]):
            self.journal.data.update(terminal=True, terminal_reason="REQUEST_CONTRACT_MISMATCH")
            self.journal.persist()
            raise ValueError("REQUEST_CONTRACT_MISMATCH")
        event = self.journal.begin(payload)
        started = monotonic()
        try:
            response = self.sdk.chat.completions.create(**payload)
        except Exception as error:
            from evaluation.finalization.live_window import _provider_error_details
            event["provider_error"] = _provider_error_details(error)
            event["latency_seconds"] = monotonic()-started
            self.journal.data["terminal"] = True
            self.journal.persist()
            raise ValueError("PROVIDER_ERROR") from None
        from evaluation.finalization.live_window import _safe_request_id
        event.update(received=True, actual_provider="openai", actual_model=getattr(response, "model", None),
                     request_id=_safe_request_id(getattr(response, "_request_id", None)), latency_seconds=monotonic()-started)
        self.journal.data["received"] += 1
        usage = getattr(response, "usage", None)
        inputs, outputs = getattr(usage, "prompt_tokens", None), getattr(usage, "completion_tokens", None)
        cached = getattr(getattr(usage, "prompt_tokens_details", None), "cached_tokens", None)
        failure = None
        if type(inputs) is not int or type(outputs) is not int or min(inputs, outputs) < 0:
            failure = "MISSING_USAGE"
        elif type(cached) is not int or not 0 <= cached <= inputs:
            failure = "CACHED_USAGE_UNVERIFIED"
        else:
            event["usage"] = {"input_tokens": inputs, "output_tokens": outputs, "cached_tokens": cached}
            self.journal.data["valid_usage"] += 1
            cached_rate = self.pricing.get("cached_input_usd_per_million")
            if cached and (type(cached_rate) not in (int, float) or not math.isfinite(cached_rate)
                           or not 0 <= cached_rate <= self.pricing["input_usd_per_million"]):
                failure = "CACHED_PRICE_UNVERIFIED"
            else:
                cost = ((inputs-cached)*self.pricing["input_usd_per_million"] + cached*(cached_rate or 0)
                        + outputs*self.pricing["output_usd_per_million"])/1_000_000
                event["cost_usd"] = cost
                self.journal.data["known_usd"] += cost
                self.journal.data["pending_exposure_usd"] -= self.journal.reserve
                self.journal.data["cost_unknown"] = False
                if outputs > self.contract["max_completion_tokens"] or inputs > self.contract["max_request_bytes"]+self.contract["frame_reserve_tokens"]:
                    failure = "USAGE_BOUND_EXCEEDED"
                if self.journal.data["known_usd"] > self.journal.budget:
                    failure = "BUDGET_EXCEEDED"
        if event["actual_model"] != self.contract["model"]:
            failure = "MODEL_MISMATCH"
        self.journal.data["terminal"] = failure is not None
        event["error_category"] = failure
        self.journal.persist()  # before model JSON/tool-argument parsing
        if failure:
            raise ValueError(failure)
        try:
            choice = response.choices[0]
            finish = choice.finish_reason
            if finish not in ("stop", "tool_calls"):
                raise ValueError("INVALID_FINISH_REASON")
            calls = [{"id": call.id, "type": "function", "function": {
                "name": call.function.name, "arguments": call.function.arguments}}
                for call in (choice.message.tool_calls or [])]
            return {"content": choice.message.content, "tool_calls": calls, "actual_model": event["actual_model"],
                    "model": event["actual_model"], "finish_reason": finish, "usage": event["usage"],
                    "cost_usd": event["cost_usd"], "request_sha256": event["request_sha256"]}
        except Exception:
            self.journal.data["terminal"] = True
            event["error_category"] = "INVALID_PROVIDER_RESPONSE"
            self.journal.persist()
            raise ValueError("INVALID_PROVIDER_RESPONSE") from None


def run_live_case(runtime_case, condition, tools, transport, telemetry_sink):
    """Benchmark DTO adapter; gold remains outside the shared runtime."""
    from .models import RuntimeCase
    from vinsoc_text2sql.service import QueryRequest, _generate
    if type(runtime_case) is not RuntimeCase or not isinstance(transport, GuardedTransport):
        raise ValueError("GUARDED_OPENAI_TRANSPORT_REQUIRED")
    return _generate(QueryRequest(runtime_case.case_id, runtime_case.database_id, runtime_case.question),
                     condition, tools, transport, telemetry_sink)


def case_usage_valid(record):
    """Live eligibility requires at least one complete, pinned API response."""
    attempts, received = record.get("attempted_calls"), record.get("response_count")
    events = record.get("responses")
    if (type(attempts) is not int or attempts < 1 or type(received) is not int
        or not isinstance(events, list) or attempts != received or received != len(events)):
        return False
    for event in events:
        response = event.get("response", {})
        usage = response.get("usage")
        cost = response.get("cost_usd")
        if (response.get("actual_model") != REQUEST_CONTRACT["model"]
            or response.get("finish_reason") not in ("stop", "tool_calls")
            or not isinstance(usage, dict)
            or any(type(usage.get(k)) is not int or usage[k] < 0
                   for k in ("input_tokens", "output_tokens", "cached_tokens"))
            or usage["cached_tokens"] > usage["input_tokens"]
            or type(cost) not in (int, float) or not math.isfinite(cost) or cost < 0):
            return False
    return True


def runtime_revalidate(release, case_ids, conditions, ledger_path):
    """Flag alone is insufficient: recompute authorization plus actual files/DBs."""
    from .benchmark_lock import file_hash, validate_benchmark
    if not isinstance(release, dict) or "gate_inputs" not in release:
        raise ValueError("RELEASE_RECORD_INVALID")
    inputs = release["gate_inputs"]
    current = preflight_release(**inputs)
    if (not current["authorized"] or current != release or conditions != CONDITIONS
        or len(case_ids) != 96 or len(set(case_ids)) != 96 or sorted(case_ids) != current["case_ids"]):
        raise ValueError("RELEASE_GATE_OR_FULL_CASE_IDENTITY_INVALID")
    canonical = Path(__file__).resolve().parents[2]/"evaluation/r2_cross_domain_v1"
    inventory = inputs["inventory"]
    expected = {"registry_path": canonical/"runtime_registry.json", "benchmark_dir": canonical/"benchmarks",
                "benchmark_lock_path": canonical/"benchmark.lock.json"}
    if any(Path(inventory[key]).resolve() != path.resolve() for key, path in expected.items()):
        raise ValueError("NONCANONICAL_BENCHMARK_INPUT")
    if Path(ledger_path).resolve() != (canonical_release_root()/"ledger.json").resolve():
        raise ValueError("NONCANONICAL_RELEASE_LEDGER")
    if Path(ledger_path).exists() or (Path(ledger_path).parent/"claim.json").exists():
        raise ValueError("RELEASE_WINDOW_CONSUMED")
    def git(*args):
        return subprocess.check_output(["git", *args], text=True, stderr=subprocess.DEVNULL).strip()
    sha = inputs["identities"]["implementation_sha"]
    if (git("branch", "--show-current") != "master" or git("rev-parse", "HEAD") != sha
        or git("rev-parse", "origin/master") != sha or git("status", "--porcelain")):
        raise ValueError("GIT_NOT_EXACT_CLEAN_MASTER")
    inv, identities = inputs["inventory"], inputs["identities"]
    registry, lock = Path(inv["registry_path"]), Path(inv["benchmark_lock_path"])
    if file_hash(registry) != identities["registry_sha256"] or file_hash(lock) != identities["benchmark_lock_sha256"]:
        raise ValueError("REGISTRY_OR_BENCHMARK_IDENTITY_MISMATCH")
    expected_sources = identities.get("runtime_source_sha256")
    required = ("evaluation/r2_cross_domain_v1/live.py", "evaluation/r2_cross_domain_v1/release.py",
                "evaluation/r2_cross_domain_v1/reporting.py", "evaluation/r2_cross_domain_v1/statistics.py",
                "scripts/run_r2_cross_domain.py")
    if not isinstance(expected_sources, dict) or set(expected_sources) != set(required):
        raise ValueError("RUNTIME_SOURCE_BINDINGS_MISSING")
    if any(file_hash(path, portable=True) != expected_sources[path] for path in required):
        raise ValueError("RUNTIME_SOURCE_IDENTITY_MISMATCH")
    validated = validate_benchmark(registry, Path(inv["benchmark_dir"]), lock)
    runtime = json.loads((Path(inv["benchmark_dir"])/"evaluation_runtime.json").read_text(encoding="utf-8"))
    if sorted(row["case_id"] for row in runtime) != current["case_ids"] or validated["inventory"]["counts"]["evaluation"] != 96:
        raise ValueError("RUNTIME_CASE_IDENTITY_MISMATCH")
    return runtime


def build_locked_instances(reference, metadata, base_context, destination):
    """Evaluator-only fixtures, never added to the model catalog/prompt."""
    from .semantic_instances import build_fixture
    from .semantic_scoring import score_case
    audit_path = Path(metadata["semantic_audit_path"])
    audit = json.loads(audit_path.read_text(encoding="utf-8"))
    expected = audit["fixture_identities"]
    if len(expected) != 2:
        raise ValueError("TWO_LOCKED_SEMANTIC_INSTANCES_REQUIRED")
    instances = [{"instance_id": "base_"+base_context.database_id, "context": base_context, "fixture_only": False}]
    for index in range(2):
        spec = json.loads((audit_path.parent/f'{reference.case_id}_{index}.fixture.json').read_text(encoding="utf-8"))
        fixture = build_fixture(spec, Path(destination)/f'{reference.case_id}_{index}.duckdb')
        if (fixture["instance_id"] != expected[index]["instance_id"]
            or fixture["context"].identity["logical_sha256"] != expected[index]["logical_sha256"]):
            raise ValueError("SEMANTIC_FIXTURE_IDENTITY_MISMATCH")
        instances.append(fixture)
    gold = score_case(reference, {"final_sql": reference.gold_sql, "error_category": "OK"}, instances)
    if gold.get("semantic_test_accuracy") is not True:
        raise ValueError("GOLD_SEMANTIC_REPLAY_FAILED")
    return instances


def run_authorized_release(release: dict, *, case_ids: list[str], conditions: tuple[str, ...], output_dir: Path,
                           ledger_path: Path, env_file: Path) -> dict:
    output_dir = Path(output_dir)
    if output_dir.exists():
        raise FileExistsError("Refusing to overwrite a release output directory")
    report = {"scope": "r2_cross_domain_v1_matched_E0_E3", "status": "blocked", "client_created": False,
              "attempted_calls": 0, "responses_received": 0, "valid_usage_records": 0, "case_records": []}
    try:
        runtime = runtime_revalidate(release, case_ids, conditions, ledger_path)
        from scripts.check_env import load_env, resolve_openai_key
        env = load_env(Path(env_file))
        key = resolve_openai_key(os.environ, env)
        if key.key is None or key.source == "conflicting_key_sources" or os.environ.get("OPENAI_BASE_URL") or env.get("OPENAI_BASE_URL"):
            raise ValueError("KEY_UNAVAILABLE_CONFLICTING_OR_CUSTOM_ENDPOINT")
        inputs = release["gate_inputs"]
        report.update(implementation_sha=inputs["identities"]["implementation_sha"],
                      benchmark_lock_sha256=inputs["identities"]["benchmark_lock_sha256"],
                      registry_sha256=inputs["identities"]["registry_sha256"],
                      release_sha256=release["release_sha256"], request_config=release["request_contract"],
                      runtime_source_sha256=inputs["identities"]["runtime_source_sha256"],
                      pricing={k: inputs["pricing"].get(k) for k in ("model", "source_url", "checked_utc", "input_usd_per_million", "cached_input_usd_per_million", "output_usd_per_million")})
        from .models import RuntimeCase
        from .data import DatabaseContext
        from .tools import DatabaseTools
        from .module_metrics import score_modules
        from .benchmark import ReferenceCase
        from .semantic_scoring import score_case
        from .reporting import build_evaluation_report
        from .statistics import summarize_statistics
        import tempfile
        benchmark_dir = Path(inputs["inventory"]["benchmark_dir"])
        registry = Path(inputs["inventory"]["registry_path"])
        references = {row["case_id"]: row for row in (json.loads(p.read_text(encoding="utf-8"))
                      for p in sorted((benchmark_dir/"references/evaluation").glob("*.json")))}
        fixture_workspace = tempfile.TemporaryDirectory(prefix="vinsoc-cross-domain-scoring-")
        contexts, instances = {}, {}
        for row in runtime:
            if row["database_id"] not in contexts:
                contexts[row["database_id"]] = DatabaseContext.from_manifest(registry, row["database_id"])
            context = contexts[row["database_id"]]
            metadata = references[row["case_id"]]
            reference = ReferenceCase(**{k: metadata[k] for k in ReferenceCase.__dataclass_fields__})
            instances[row["case_id"]] = build_locked_instances(reference, metadata, context, Path(fixture_workspace.name))
        # All base/fixture gold and identities have passed BEFORE claim/client.
        journal = RequestJournal.claim(ledger_path, max_requests=release["max_requests"], budget_usd=release["budget_usd"],
            prior_usd=inputs["account"]["known_prior_cost_usd"], reserve_usd=release["per_request_reserve_usd"],
            implementation_sha=inputs["identities"]["implementation_sha"])
        output_dir.mkdir(parents=True, exist_ok=False)
        _atomic_write(output_dir/"report.json", report)
        import openai
        sdk = openai.OpenAI(api_key=key.key, max_retries=0, base_url="https://api.openai.com/v1", timeout=60)
        report["client_created"] = True
        transport = GuardedTransport(sdk, journal, release["request_contract"], inputs["pricing"])
        for condition in CONDITIONS:
            for row in sorted(runtime, key=lambda row: row["case_id"]):
                context = contexts[row["database_id"]]
                tools = DatabaseTools(context)
                def checkpoint(partial):
                    _atomic_write(output_dir/f'{condition}_{row["case_id"]}.json', partial)
                record = run_live_case(RuntimeCase(**row), condition, tools, transport, checkpoint)
                reference = ReferenceCase(**{k: references[row["case_id"]][k] for k in ReferenceCase.__dataclass_fields__})
                record["modules"] = score_modules(reference, record, context)
                record = score_case(reference, record, instances[row["case_id"]])
                record.update(planned_case_count=96, present=True,
                    **{k: references[row["case_id"]][k] for k in ("domain", "family_id", "difficulty", "features")},
                    snapshot_identity=context.identity["logical_sha256"],
                    scorer_identity=canonical_hash({k: v for k, v in json.loads(Path(inputs["inventory"]["benchmark_lock_path"]).read_text())["source_files"].items()
                                                    if k.endswith(("semantic_scoring.py", "module_metrics.py", "safety.py"))}),
                    benchmark_identity=inputs["identities"]["benchmark_lock_sha256"],
                    provenance_valid=True,
                    usage_valid=case_usage_valid(record))
                checkpoint(record)
                report["case_records"].append(record)
                report.update(attempted_calls=journal.data["attempted"], responses_received=journal.data["received"],
                              valid_usage_records=journal.data["valid_usage"], cost_summary={
                                  "known_cost_usd": journal.data["known_usd"], "cost_unknown": journal.data["cost_unknown"],
                                  "pending_exposure_usd": journal.data["pending_exposure_usd"]},
                              requests=deepcopy(journal.data["events"]))
                report["status"] = "partial"
                _atomic_write(output_dir/"report.json", report)
                if journal.data["terminal"]:
                    return report
        inv = {"conditions": list(CONDITIONS), "cases": [references[key] for key in sorted(references)]}
        report["metrics"] = build_evaluation_report(report["case_records"], inv)
        report["statistics"] = summarize_statistics(report["case_records"])
        complete = (len(report["case_records"]) == 192 and not journal.data["cost_unknown"]
                    and report["statistics"]["paired"]["complete"] is True)
        report["status"] = "completed" if complete else "partial"
        report["official_eligible"] = complete
        report["ineligible_reasons"] = [] if complete else ["INCOMPLETE_PAIRED_RELEASE"]
    except Exception as error:
        # Do not return arbitrary exception text/provider bodies/private paths.
        safe_categories = {
            "RELEASE_RECORD_INVALID", "RELEASE_GATE_OR_FULL_CASE_IDENTITY_INVALID",
            "NONCANONICAL_BENCHMARK_INPUT", "NONCANONICAL_RELEASE_LEDGER", "RELEASE_WINDOW_CONSUMED",
            "GIT_NOT_EXACT_CLEAN_MASTER", "REGISTRY_OR_BENCHMARK_IDENTITY_MISMATCH",
            "RUNTIME_SOURCE_BINDINGS_MISSING", "RUNTIME_SOURCE_IDENTITY_MISMATCH", "RUNTIME_CASE_IDENTITY_MISMATCH",
            "KEY_UNAVAILABLE_CONFLICTING_OR_CUSTOM_ENDPOINT", "TWO_LOCKED_SEMANTIC_INSTANCES_REQUIRED",
            "SEMANTIC_FIXTURE_IDENTITY_MISMATCH", "GOLD_SEMANTIC_REPLAY_FAILED", "FULL_RUN_BUDGET_INSUFFICIENT",
        }
        category = error.args[0] if len(error.args) == 1 and isinstance(error.args[0], str) else None
        report["failure_category"] = category if category in safe_categories else type(error).__name__
        if "journal" in locals():
            report.update(status="partial", attempted_calls=journal.data["attempted"], responses_received=journal.data["received"],
                          valid_usage_records=journal.data["valid_usage"], cost_summary={"known_cost_usd": journal.data["known_usd"],
                              "cost_unknown": journal.data["cost_unknown"], "pending_exposure_usd": journal.data["pending_exposure_usd"]},
                          requests=deepcopy(journal.data["events"]))
    finally:
        if "sdk" in locals():
            try:
                sdk.close()
            except Exception:
                pass  # cleanup must not discard charged partial evidence
        if "fixture_workspace" in locals():
            fixture_workspace.cleanup()
    if not output_dir.exists():
        output_dir.mkdir(parents=True, exist_ok=False)
    _atomic_write(output_dir/"report.json", report)
    return report
