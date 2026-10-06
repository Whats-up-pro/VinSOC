# Network E2E Completion Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:executing-plans` to implement this plan task by task. Agent A is the sole writer on the user's local laptop. Steps use checkbox (`- [ ]`) syntax; mark them only after the stated verification really passes. Work directly on `master`; do not create a branch, worktree or PR.

**Goal:** Complete a real, verifiable CLI investigation for both CTU Botnet and Normal scenarios, including triage, model-generated native tool arguments, production network execution, source-backed evidence, model-generated assessment, factual verification and human review; then complete the pending controlled R2 comparison and artifact presentation without changing historical results.

**Architecture:** Reuse `InvestigationOrchestrator.investigate()` and its existing production skills, EvidenceStore and HITL interfaces. Add an optional network investigation policy and a guarded live window rather than a separate scripted investigation loop. The network demo, R1 accuracy benchmark, R2 SQL benchmark and cross-domain expansion remain separately identified evidence streams.

**Tech Stack:** Python >=3.11, OpenAI Python SDK / Chat Completions, DuckDB read-only snapshots, existing native JSON tool schemas, pytest, existing CLI/Rich and a standalone HTML artifact reader.

**Spec:** The updated user requirements in this conversation; `docs/VinSOC_Verified_Demo_Runbook_2026-10-05.md`, especially sections 4–8; and `docs/superpowers/plans/2026-10-05-vinsoc-finalization-fix.md`, Tasks 3–6. The older `docs/superpowers/specs/2026-09-28-vinsoc-r1-r2-finalization-design.md` remains a methodological reference where it does not conflict with the user's subsequent instructions about consumed holdout, demo scope or execution order.

## Global constraints and authority

- This document is a complete implementation handoff. Its creation does not claim that implementation, a live request or a demo has already succeeded.
- The user has requested live E2E execution after verification, not an offline-only replacement. Live calls are part of Tasks 7 and 10; they are permitted only after their explicit CI, identity, account and budget checks pass.
- Demo comes before the new matched E0/E3 pair. This changes the old Task 4 → Task 5 order; it does not cancel either deliverable. The pair is not a prerequisite for demonstrating the production network workflow.
- Keep both Botnet and Normal. Keep all investigation stages. Never replace model arguments, assessment or human decisions with script-authored successes.
- Do not silently shorten tool outputs, evidence, final assessment or the acceptance criteria. Existing data/transport limits must be disclosed. An oversized payload blocks the request; it does not permit hidden slicing to obtain a green demo.
- Preserve `.env`, all pre-existing untracked/user files, source bytes, snapshots, historical predictions/reports and historical locks. Do not print, copy, overwrite, hash, stage or commit `.env` or credentials.
- Use existing CTU S5/S7 bytes and the locked development snapshot. No ThreatFox/OTRF download or execution; no R1 run; no frozen read, inference or reopening. S1/S4 remains consumed and protocol-ineligible. R1 frozen remains sealed.
- Do not change benchmark questions, gold SQL, existing comparators, historical prompts or historical result JSON to make a run pass. No per-case tuning or prediction splicing.
- No model fallback, SDK retry, automatic retry, extra smoke, case retry or second suite attempt in this window. A failed attempted run remains evidence.
- The demo keeps the already specified envelope: `gpt-4.1-mini-2025-04-14`, `temperature=0`, `max_completion_tokens=1000`, SDK retries 0, two scenarios, at most two model responses per scenario / four attempted requests total. Native tool selection uses `tool_choice=auto`; this is a bounded network investigation, not a claim of evaluated multi-domain orchestration.
- The R2 pair keeps `gpt-5-mini-2025-08-07`, `reasoning_effort=low`, cap 1000, omitted temperature, SDK retries 0, one E0 and one E3 on the same implementation SHA. Retain existing role/tool limits; the 80-call E3 bound is a cost envelope, not permission to expand controller limits.
- Demo implementation SHA A may differ from the later corrected R2 implementation SHA B. Both R2 conditions must use B. Both use the same cost allocation and durable window; a code commit does not reset that window.
- Account/pricing confirmations must be real and current. Do not invent receipts, purchase credit or increase spend limits. A deprecated label is not proof that a pinned model is unavailable; an unavailable model/parameter error stops the pinned run without migration or fallback.
- This plan reuses the previously specified USD 0.75 new-window ceiling, subject to fresh confirmation of its remaining allocation. Do not reset spent/unknown costs, add a new allocation yourself, or reuse it for cross-domain paid evaluation.
- Only code/test/doc files belonging to the current task may be staged. No `git add .`, reset, clean, forced push or overwrite of historical artifacts. Push atomic commits directly to `origin/master`.
- API errors/logs/reports may contain only validated safe status/code/type/request_id/retry_after/category. No raw error body/message, prompt dump, credentials or raw traceback in public output.

## Verified starting point

Read-only audit on 06/10 found `master@193a04fe455e4f1ca7e4047097055f251a067b3c`. Its [CI 37410505249](https://github.com/Whats-up-pro/VinSOC/actions/runs/37410505249) passed on Python 3.11 and 3.12: **905 passed, 1 skipped** on each. The skipped test requires the ignored local CTU snapshot; CI alone does not prove the local snapshot/release gate.

| Area | Already present | Remaining work for this plan |
|---|---|---|
| R1 | GPT-4.1 Mini dev v2: 22/24; exact-call F1 0.9508; no-tool 5/5 | Preserve the result; demo does not update R1 accuracy |
| R2 | Verified complete Phase2 dev suite: 7/8; case006 remains TOOL_LIMIT / NO_FINAL_SQL | New matched E0/E3 on corrected release inputs after demo |
| Network data | CTU S5/S7: 129831 + 114075 = 243906 flows | Verify the existing snapshot locally; do not rebuild/download by default |
| Demo | Safe 429/key-source diagnosis, model arguments and assessment script, production network dispatch | Public lifecycle integration, factual claims, complete receipts and real HITL |
| Evidence V2 | OBSERVED flow aggregates and DERIVED analytics with parent IDs | Preserve both classes in model input; prove aggregates and parent links |
| Release v4 | Contract, CI/account/budget gates and R2 CLI exist | Fix scoring-policy wiring, unscored eligibility, cleanup/attempt/ledger boundaries |
| Cross-domain | Spider registry/builds, generic offline controller and gold-parity audit exist at HEAD | Preserve these commits. Benchmark/semantic lock, release and paid runs are unfinished and continue under their separate plan |

Snapshot identities to verify, not recreate:

```text
path: data/ctu_network_public/snapshots/ctu_dev.duckdb
logical SHA-256: 42c8e0a62441295cc5d95329a65dc22409c37de5b26a1e37dd56fbf0164a758c
binary SHA-256: 0b29765b9a175d00e0a193039a1b058691406e28a434e10030ae78265cfa67b9
source datasets: ctu13_s5, ctu13_s7
```

Concrete code observations behind the tasks:

1. `scripts/demo_ctu_network_public_model_driven.py::_network_tool_request()` forces `network_investigation`; `_execute_network()` manually initializes the orchestrator and calls private `_execute_tool_call()`. It is not the complete public lifecycle.
2. `_assessment_evidence()` keeps only 12 observed records and 20 source references; `_checked_assessment()` verifies JSON/citation structure, not factual values. `_execute_network()` filters out DERIVED items with no direct source_records.
3. `InvestigationOrchestrator._run_investigation_loop()` advertises all three tools. Its system prompt still says CTI usually first; `_execute_tool_call()` sends `result_text[:4000]` without a transport completeness contract or assigned evidence-ID payload.
4. `_generate_case()` clips assistant content to 2000 characters. `_verify_case_quality()` principally appends limitations/flags; it does not prevent a failed case from being presented as complete. `_analyze_evidence()` reads legacy patterns_detected rather than the granular V2 candidate types.
5. Existing aggregate demo flags are set during execution. The current second-scenario-failure test can fail at the first assessment because it supplies invented evidence IDs; it does not prove the intended second-scenario boundary.
6. `run_vinsoc_finalization_dev.py` gives a snapshot Path to `score_prediction()`, which constructs archived `Phase2Snapshot`; the current tools use `Phase2V4Snapshot`. It also aggregates nullable unscored flags through bool(), and does not require every case to be scored for official eligibility. An exception from client.close() can bypass final report/ledger writes.

## Chosen approach and sequencing

The quickest complete approach is to add a small optional policy to the existing public orchestrator. Extending only the standalone forced-tool script would leave triage, normal conversation correlation and HITL unproven. Replacing the production pipeline with the new cross-domain SQL controller would introduce a new product interface and delay this deliverable. Neither alternative is selected.

The sequence is **Task 0 → 1 → 2 → 3 → 4 → 5 → 6 → 7 → 8 → 9 → 10 → 11**. Tasks 0–8 produce the real network E2E and its reader first. Tasks 9–11 finish the controlled R2 comparison and evidence package. Cross-domain work is retained under its own protocol; it must not interrupt or be silently marked complete by this delivery.

Allow roughly 4–6 hours for the demo path if the local snapshot/account is ready; the estimate is scheduling guidance, not permission to skip gates. Report a specific blocker immediately instead of spending the day polishing docs while live integration remains incomplete.

## File responsibilities

| File | Responsibility |
|---|---|
| `agent/investigation_policy.py` (new) | Optional policy interface, typed validated assessment and stable validation error |
| `agent/network_investigation_policy.py` (new) | Network-only tool scope, complete evidence conversation payload and structured assessment checks |
| `agent/orchestrator.py` | Policy integration through public investigate; stage/termination status; verification before review |
| `agent/provider.py` | Optional injected client for guarded native SDK transport; preserve existing default behavior |
| `evaluation/finalization/live_window.py` (new) | Fixed window identity, durable attempts/cost journal, model/request/usage gates and safe failures |
| `evaluation/finalization/network_contract.py` (new) | Snapshot and deterministic demo scenario qualification, portable source identities |
| `scripts/demo_ctu_network_public_model_driven.py` | CLI/preflight and public orchestrator runner; keep legacy diagnostic mode explicitly separate |
| `scripts/render_network_e2e_report.py` (new) | Standalone HTML generated only from saved receipt JSON |
| `scripts/run_vinsoc_finalization_dev.py` | Correct R2 scoring, eligibility, shared live window and safe finalization |
| `evaluation/finalization/R2_MATCHED_v1.lock.json` (new, Task 9) | New immutable matched-release source/prompt/tool/scoring identities |
| `evaluation/finalization/NETWORK_E2E_v1.lock.json` (new, Task 6) | New immutable network release/scenario/request/policy identity |
| `tests/test_network_e2e_policy.py`, `tests/test_network_e2e_lifecycle.py`, `tests/test_finalization_live_window.py`, `tests/test_network_e2e_report.py` (new) | Real local DB + synthetic transport/HITL tests, no API requests |
| Existing demo, provider, HITL and finalization tests | Regressions for changed interfaces and safe failure semantics |
| `docs/evaluation/network_e2e_results_2026-10-06.md` (new after actual run) and existing runbook | Artifact-derived delivery evidence and exact commands |

Conditional modifications in Task 3 only: `vinsoc_data/network_source.py`, `vinsoc_data/domain_queries.py`, `skills/network_skill.py` if tests reproduce lost query coverage/truncation metadata. No change to telemetry interpretation or analytic thresholds merely to obtain a desired Botnet verdict.

## Review focus

1. First scenario passes, second fails: preserve the first result; aggregate E2E=false, exact charged calls retained. Task 5 tests must actually reach the second assessment.
2. Valid evidence ID with wrong number/endpoint/time: reject the factual claim despite valid citation. Task 3 pins this with real DB aggregates.
3. Missing/truncated telemetry and truncated source references: absence is not benign; a source sample is not proof of a full-population count. Task 3 tests both boundaries.
4. Malformed completion or client cleanup failure after a charged response: keep known usage/cost and partial receipt; prevent further calls. Tasks 1 and 5 test this.
5. Changing output paths, two processes or an interruption after attempt persistence: cannot reset budget/one-attempt identity. Task 1 tests this; Task 9 reuses it for R2.

---

### Task 0: Sync, protect evidence and establish the actual baseline

**Files:** Create `results/evaluation_v1/network_e2e_v1/<window_id>/setup_receipt.json`; read existing manifests/locks/results. Do not edit historical files.

**Interfaces:** Produces an append-only setup receipt with initial SHA, remote SHA, protected tracked-file hashes excluding secrets, snapshot identities and the existing result-source paths. Later tasks consume that receipt's window_id and preservation inventory.

- [ ] **Step 1: Record initial state, then sync safely.** Run separately: `git status --short`, `git branch --show-current`, `git rev-parse HEAD`, `git fetch origin master`, `git rev-parse origin/master`, `git rev-list --left-right --count HEAD...origin/master`. If behind and no conflicting user edits, `git merge --ff-only origin/master`; otherwise report the specific conflict without reset/stash/clean. Preserve every existing untracked file. Agent A must avoid concurrent writes from another local agent.
- [ ] **Step 2: Read this plan, the runbook, older finalization plan, live/demo code and the latest cross-domain progress ledger.** Compare HEAD to the audited 193a04f. Record actual differences; do not repeat completed cross-domain tasks or revert them.
- [ ] **Step 3: Verify the local development snapshot.** Run `python -m evaluation.ctu_network_public.contract --snapshot data/ctu_network_public/snapshots/ctu_dev.duckdb`. Expected: existing lock PASS, source row counts 129831/114075, logical SHA above and semantic counterexamples pass. Separately compute its binary SHA with Python hashlib. Do not use `--write-lock`. Missing or changed bytes are a blocker before client creation.
- [ ] **Step 4: Run the starting focused tests.** `python -m pytest tests/test_demo_ctu_network_public_model_driven.py tests/test_demo_ctu_network_public.py tests/test_hitl.py tests/test_cli_context_contract.py tests/test_vinsoc_finalization_contract.py tests/test_vinsoc_finalization_live.py -q`. Record actual commands/counts/skips. Missing dependencies are not a pass.
- [ ] **Step 5: Save the protected inventory and setup receipt, inspect its diff, stage only the new safe receipt and commit.** No `.env`, raw data, raw exceptions or account-identifying values. Expected: remote historical report/case/lock bytes unchanged.

### Task 1: One guarded live window with durable attempts, costs and safe errors

**Files:** Create `evaluation/finalization/live_window.py`, `tests/test_finalization_live_window.py`. Read/reuse algorithms from `evaluation/finalization/contract.py` and current safe 429 helpers; do not mutate archived runner helpers.

**Interfaces:**

```python
class LiveWindow:
    @classmethod
    def open(cls, root: Path, window_id: str, gates: dict) -> "LiveWindow": ...
    def claim(self, condition: str, implementation_sha: str, output: Path) -> dict: ...
    def guarded_client(self, client: Any, condition: str, contract: dict) -> Any: ...
    def record_terminal(self, condition: str, receipt: dict) -> None: ...
    def state(self) -> dict: ...
```

Return a Chat Completions-compatible client. Fixed conditions: `NETWORK_DEMO`, `R2_E0`, `R2_E3`. Journal attempts/usage before parsing model output. Separate immutable terminal receipt from the append-only ledger. The authoritative registry/ledger lives at one fixed `.vinsoc/live-windows/network-finalization-20261006/` root, regardless of output directory; public copies omit sensitive account details. No alternate root/window ID may silently start another attempt.

- [ ] **Step 1: Add failing tests:** duplicate claim after output-path change; concurrent exclusive claim; interrupted attempt without terminal receipt; unknown-cost latch; corrupted/non-finite/negative ledger costs; missing/stale/false account/pricing/CI fields specified in Task 7; malformed tool JSON after known charged usage; missing model/usage; valid structured 429; close() failure; no raw sentinel `SENSITIVE_RAW_ERROR`/test key in JSON/stdout/formatted traceback. Never use the real `.env`.
- [ ] **Step 2: Run `python -m pytest tests/test_finalization_live_window.py -q`; capture RED from the new missing/incorrect interfaces.** Existing behavior already passing is recorded as passing rather than manufactured RED.
- [ ] **Step 3: Implement exclusive claims and fsynced attempt/response journal.** Claim before first SDK call. A provider exception creates an unresolved/unknown cost state, even when known_cost=0. A parsed/model validation failure with valid usage retains known charged cost. Gate failures before transmission have attempted=0 and cost_unknown=false. Preserve original failures if client.close() also fails; cleanup must not prevent report/ledger persistence.
- [ ] **Step 4: Validate the exact model/parameters, official endpoint, SDK retries=0, finish_reason, usage ints/nonnegative totals/cached<=input, service tier and request size before/after transport.** Missing usage or identity does not become zero usage or requested-model fallback. Finish_reason=length/content_filter/refusal stops the scenario; valid usage is still charged. Reject bool/NaN/Infinity in numeric budget fields.
- [ ] **Step 5: Reuse key-source resolution and safe error extraction from current demo/check_env.** Differing process/.env key sources fail before creating the SDK client. Only source labels are emitted; no prefix/length/hash/fingerprint. Safe provider failures are raised with suppressed raw exception chains.
- [ ] **Step 6: Run GREEN and existing safe diagnostic regressions.** `python -m pytest tests/test_finalization_live_window.py tests/test_check_env.py tests/test_demo_ctu_network_public_model_driven.py -q`; then py_compile on the new module and `git diff --check`. Stage only these task files and commit.

### Task 2: Integrate a network policy into the public orchestrator lifecycle

**Files:** Create `agent/investigation_policy.py`, `agent/network_investigation_policy.py`, `tests/test_network_e2e_lifecycle.py`; modify `agent/orchestrator.py`, `agent/provider.py` and relevant existing tests.

**Interfaces:**

```python
@dataclass(frozen=True)
class ValidatedAssessment:
    assessment: str
    hypotheses: tuple[dict, ...]
    risk_level: str
    confidence: str
    evidence_ids: tuple[str, ...]
    observations: tuple[dict, ...]
    limitations: tuple[str, ...]

class InvestigationPolicy(Protocol):
    def tool_schemas(self) -> list[dict]: ...
    def system_prompt(self) -> str: ...
    def validate_tool_call(self, call: dict) -> dict: ...
    def tool_response(self, call: dict, result: Any, store: EvidenceStore) -> str: ...
    def parse_final_response(self, content: str, store: EvidenceStore) -> ValidatedAssessment: ...
    def validate_case(self, case: InvestigationCase) -> dict: ...

NetworkInvestigationPolicy(indicator: str, time_range: dict[str, str])
InvestigationOrchestrator(..., investigation_policy: InvestigationPolicy | None = None)
OpenAIProvider(..., client: Any | None = None)
```

`None` preserves existing default orchestration. The policy supplies only the unchanged native network schema, not a rewritten schema. OpenAIProvider consumes the preflighted guarded client when supplied and does not create a second client or hide its retries.

- [ ] **Step 1: Write RED lifecycle tests:** public investigate called once per scenario; triage before transport; allowed schemas network-only; tool_choice auto; native arguments reach the production NetworkSkill unchanged except existing null sanitization; out-of-scope arguments/unknown tool rejected before execution; original native tool-call ID retained in the role=tool message; assigned EvidenceStore IDs reach the next model request; final verification before final HITL; provider failure never treated as a successful no-tool decision.
- [ ] **Step 2: Run `python -m pytest tests/test_network_e2e_lifecycle.py -q`; record the failing boundary.** Test real production NetworkSkill + fixture DuckDB, synthetic SDK only.
- [ ] **Step 3: Add the optional policy injection at schema/prompt/tool execution/conversation/final response/verification boundaries.** Use `investigate()`, not fixed_pipeline or manual private dispatch. First request has analyst IPv4/history interval and neutral question, no Botnet/Normal label, seed row, gold SQL or expected verdict. Keep CTI-first legacy prompt outside this profile; the network profile is evidence-relevance based.
- [ ] **Step 4: Track explicit termination:** final assessment, no required tool, tool limit, model turn limit, invalid arguments, provider failure, validation failure. Exhausting two model turns after another tool call means `NO_FINAL_ASSESSMENT`; never promote an earlier planning message or synthesize an answer. First-response prose without a required network execution is `REQUIRED_TOOL_NOT_EXECUTED` for these two scenarios.
- [ ] **Step 5: Keep full validated model assessment separately from its narrative.** Put the validated `assessment` prose in case.final_assessment and the complete observations/hypotheses/validation metadata in case metadata/receipt before case schema validation. No truncation of raw JSON to 2000 chars, no lost fields and no script-authored threat/risk success. Retain hypothesis-to-evidence relationships and distinguish model claims from deterministic analytic candidates.
- [ ] **Step 6: Run GREEN plus existing provider/HITL/schema/CLI tests.** `python -m pytest tests/test_network_e2e_lifecycle.py tests/test_provider_routing.py tests/test_hitl.py tests/test_schema_contracts.py tests/test_cli_context_contract.py -q`; py_compile modified files, diff check, allowlisted commit.

### Task 3: Preserve and independently verify complete network evidence and factual observations

**Files:** Modify `agent/network_investigation_policy.py`, `agent/orchestrator.py`; create `evaluation/finalization/network_contract.py`, `tests/test_network_e2e_policy.py`. Apply the conditional data-source/NetworkSkill fixes listed above only after RED reproduces a lost coverage boundary.

**Interfaces:** `verify_network_evidence(snapshot: DuckDBSnapshot, arguments: dict, evidence: list[dict]) -> dict` belongs to `evaluation/finalization/network_contract.py`. Policy `parse_final_response()` validates observations against the exact evidence sent; DB verifier validates that evidence against source rows. The two checks must not be conflated.

Structured final JSON has exactly these required top-level fields: `assessment`, `hypotheses`, `risk_level`, `confidence`, `evidence_ids`, `observations`, `limitations`. Observation shape: `{"evidence_id": str, "field": str, "value": JSON scalar}`. Allowed fields are explicitly present scalar facts: connection_count, src_ip, dst_ip, dst_port, protocol, first_seen, last_seen, bytes_src_to_dst and bytes_dst_to_src. Hypotheses contain description, supporting_evidence IDs and confidence. Validate all types/lengths/enums; extra fields cannot become commands or additional unverified facts.

- [ ] **Step 1: Add real-DuckDB RED tests:** valid ID/wrong connection_count; wrong IP/port/protocol/time; mixed source datasets sharing source_row_id; verified ID but wrong aggregate; DERIVED item with missing/wrong parent; duplicate observation; Boolean masquerading as int; null value invented where field absent; source-reference truncation; repository/skill event truncation; Unicode/newlines in JSON; an instruction injected into tool text; no-evidence assessment must retain uncertainty. Gold counts are hand checked in synthetic fixture rows.
- [ ] **Step 2: Run `python -m pytest tests/test_network_e2e_policy.py -q`; record RED.** Do not use real source rows or model calls in these tests.
- [ ] **Step 3: Send valid complete JSON tool results with assigned evidence IDs and coverage metadata, preserving OBSERVED and DERIVED records and parent links.** Replace the profile's naked 4000-character cut and 12/20 slicing. Keep all actual tool/evidence objects in the receipt. Size-check the entire next request before API transmission; oversize becomes PAYLOAD_BOUND_EXCEEDED, not silent evidence selection. Default legacy transport outside the profile may retain its behavior.
- [ ] **Step 4: Verify every source pair is unique and belongs to the executed IP/time predicate.** For complete groups, recompute count, endpoints, protocol, time extrema and directional bytes from the DB using the same declared predicate/group. For truncated retrieval, verify the actual returned source set and label claims as retrieved-subset facts. Do not compare a truncated provenance sample as though it were the full aggregate. Propagate snapshot/repository/skill truncation separately; never claim full coverage when it is unknown.
- [ ] **Step 5: Validate every structured observation's field/value against the exact delivered evidence.** Require at least one count and one endpoint/port/protocol fact for each nonempty scenario. Timestamp equality uses the same instant/precision; require explicit consistent naive historical-time policy. Failed citations/facts invalidate the scenario. Check risk/confidence enums and cited hypotheses; do not force a Botnet→malicious or Normal→benign answer.
- [ ] **Step 6: Account for V2 risk synthesis.** Add a regression proving scan/periodicity candidates are not lost just because patterns_detected is absent in individual evidence.data. Include candidate type/confidence/parents in the case; a periodicity candidate or large transfer is not proof of C2/exfiltration. Preserve existing legacy aggregate behavior unless a reproduced integration defect requires a separate explained correction.
- [ ] **Step 7: Run GREEN:** `python -m pytest tests/test_network_e2e_policy.py tests/test_network_e2e_lifecycle.py tests/test_network_skill_v2.py tests/test_network_analytics.py tests/test_evidence_v2.py -q`; py_compile and diff checks; commit only verified changed code/tests.

The validator certifies structured facts and references, not arbitrary free prose. Human review explicitly covers hypothesis language, causal claims, verdict and calibration. The receipt must state `prose_semantics_machine_verified=false`; do not convert this limitation into a reason to omit the assessment.

### Task 4: Qualify scenarios and add the usable CLI with real HITL

**Files:** Extend `evaluation/finalization/network_contract.py`; modify `scripts/demo_ctu_network_public_model_driven.py`, policy tests and lifecycle tests. Reuse `cli.main.ConsoleHumanReviewGate`/`agent.hitl` through their existing interfaces.

**Interfaces:**

```python
qualify_demo(snapshot: Path) -> dict
run_network_e2e(snapshot: Path, output: Path, *, window: LiveWindow,
                provider: LLMProvider, review_gate: HumanReviewGate | None) -> dict
```

CLI additions: `--e2e`, `--preflight-only`, `--gates PATH`, `--window-id network-finalization-20261006`, `--review-mode interactive|deferred`, alongside existing `--snapshot`/`--output`. Retain `--diagnostic-first-request` semantics as an explicitly different mode; it must not be combined with `--e2e`. No raw --api-key argument. Existing historical script modes remain labelled legacy and cannot issue another live call to bypass the window.

- [ ] **Step 1: Add RED qualification/CLI tests:** changed/missing snapshot, lost source identity, dataset label leaked into either API request, same output exists, mutually exclusive modes, custom endpoint, conflicting key sources, deferred review status and interactive actual decisions. Qualify scenarios with the existing deterministic earliest-source-row selection; no cherry-picking a new easier IP/window after model output.
- [ ] **Step 2: Implement data-only qualification.** Verify source manifest hashes, schema, source counts, binary/logical snapshot identity and deterministic scenario IP/time/seed provenance. Store label/seed only in evaluator-side scenario receipt; model input contains neutral request and historical interval. Do not make demo qualification depend on running gold SQL or completing the cross-domain lock.
- [ ] **Step 3: Use public investigate with max_steps=2 per scenario and max_review_cycles=0 within this already bounded four-request window.** A human request for more evidence is retained/escalated and requires a separately authorized next window; it never silently dispatches a fifth request. Capture triage, investigation, verify and review lifecycle in each case.
- [ ] **Step 4: Verification gates the review.** An invalid case is retained with safe failure status and does not reach an approval UI as verified. For valid cases, display complete assessment/observations/evidence trace for real human inspection; no ScriptedHumanReviewGate in live mode. In interactive mode record real APPROVE/REJECT/ESCALATE decisions. In deferred mode record technical_complete / awaiting_human, not E2E COMPLETE. An authentic reject/escalate closes the review workflow with accepted=false; do not demand APPROVE to cosmetically green a run.
- [ ] **Step 5: Add offline review finalization:** `--review-receipt PATH` reads an immutable technical receipt, rechecks its identity/validation and writes a new review receipt linked by input SHA; no API calls, no overwriting the technical artifact. Stop if review input is missing/invalid. Human interaction cannot be manufactured by Agent A.
- [ ] **Step 6: Run GREEN:** `python -m pytest tests/test_network_e2e_lifecycle.py tests/test_network_e2e_policy.py tests/test_demo_ctu_network_public_model_driven.py tests/test_hitl.py tests/test_check_env.py -q`; `python -m scripts.demo_ctu_network_public_model_driven --help`; compile/diff/staged checks; commit. Expose the new E2E runner through this CLI and document it as the real public-orchestrator entrypoint; do not present an unchanged legacy `soc-investigate` invocation as this gated demo.

### Task 5: Receipts that preserve partial runs and cannot claim false completion

**Files:** Modify new live-window/policy/runner files and corresponding tests.

**Interfaces:** Every receipt has schema_version, window/condition, implementation_SHA, request/policy/schema/scenario/manifest/snapshot hashes, CI identity, timestamps, stage, status, attempts/responses, usage/cost, per-scenario flags, case/evidence/tool trace and safe errors. IDs/digests must be factual; a local run has run_url/artifact_id=null with `execution_environment=local`, never invented Actions provenance.

- [ ] **Step 1: Add RED tests with actual progression:** first scenario gets real fixture evidence and valid assessment, then the second assessment fails. Assert four attempts/responses, one completed scenario, second tool trace retained, all charged usage retained and aggregate E2E=false. Also test failure at first request, first tool, factual verification and human cancellation. Do not use invented IDs that fail before the tested stage.
- [ ] **Step 2: Implement per-scenario flags:** triage_completed, model_tool_call_received, model_arguments_valid, production_tool_executed, evidence_source_verified, model_assessment_received, citations_valid, structured_facts_valid, case_schema_valid, human_review_completed and accepted. Aggregate flags are conjunctions over both required scenarios; never set them optimistically after the first scenario.
- [ ] **Step 3: Terminal status semantics:** complete only if both scenarios pass technical verification and have real valid final human decisions; technical_complete if technical checks pass and review awaits the user; partial on any attempted failure; blocked on pre-call failure. completed_scenarios is separate from retained partial scenario objects. Cost_unknown tracks missing/rejected usage/provider uncertainty, not simply model-answer correctness.
- [ ] **Step 4: Save receipt atomically after every boundary; append terminal ledger even if parsing, verification, rendering or close fails.** Never overwrite an older output; prevent path traversal/out-of-namespace writes. Failure text uses safe categories. Keep any completed first scenario intact and stop further provider calls on infrastructure/cost uncertainty. No retry for invalid assessment or wrong arguments.
- [ ] **Step 5: Run GREEN:** `python -m pytest tests/test_finalization_live_window.py tests/test_network_e2e_lifecycle.py tests/test_network_e2e_policy.py tests/test_demo_ctu_network_public_model_driven.py -q`; compile/diff; commit.

### Task 6: Freeze the demo implementation and pass local + exact-SHA CI gates

**Files:** Create `evaluation/finalization/NETWORK_E2E_v1.lock.json`; modify `tests/test_vinsoc_finalization_contract.py` or new network contract tests; update this plan's execution ledger only with actual verification.

**Interfaces:** Lock binds complete source/policy/provider/entrypoint/transport hashes, unchanged production tool schema hash, scenario qualification hash, snapshot logical/binary/manifest IDs, actual request contract and budget profile. Use portable LF text hashes for tracked code; use exact byte hashes for datasets/binary artifacts. No circular commit-SHA hash: implementation SHA belongs to the run receipt.

- [ ] **Step 1: Write RED lock tests:** changed policy/tool schema/entrypoint/scenario/snapshot -> fail before SDK creation; request temperature/cap/model mismatch -> fail; cap error never caught as a successful no-tool result.
- [ ] **Step 2: Generate the new network lock from verified bytes.** Preserve existing CTU/R1/R2/historical locks. Pin `parallel_tool_calls=false`, `tool_choice=auto`, service_tier=default, JSON response mode and instructions for the structured final answer. Native tools remain the unchanged production schema.
- [ ] **Step 3: Run focused and full suites:**

```bash
python -m pytest tests/test_finalization_live_window.py tests/test_network_e2e_policy.py tests/test_network_e2e_lifecycle.py tests/test_demo_ctu_network_public_model_driven.py tests/test_provider_routing.py tests/test_hitl.py -q
python -m pytest -q
```

Compile every changed Python file explicitly; run `git diff --check`. Run snapshot-required tests locally against the real verified snapshot; a CI skip is not enough. Add a local-only lifecycle integration test that consumes `VINSOC_LOCAL_SNAPSHOT=data/ctu_network_public/snapshots/ctu_dev.duckdb`, actual production NetworkSkill and synthetic model/reviewer transports. It must verify complete payload size/coverage/facts for the two deterministic scenarios before paid execution; its receipt is labelled OFFLINE_REHEARSAL and cannot stand in for Task 7. Run it with that environment variable set; missing input skips only in CI and blocks this local acceptance. Record real counts and errors; do not assert 906 or another old count as the current run.

- [ ] **Step 4: Inspect `git diff --cached --name-only` and `git diff --cached`.** Only allowlisted task code/tests/new lock/safe receipts. Verify protected artifacts and source/snapshot hashes remain equal. Commit, `git push origin master`, capture implementation SHA.
- [ ] **Step 5: Wait for Python 3.11 and 3.12 CI success on that exact implementation SHA, inspect both job logs and save actual run/job URLs.** No API before success. No editing/commit between CI acceptance and the two-scenario demo. New remote code or source mismatch invalidates this preflight; re-verify before any attempt rather than trusting a stale CI badge.

### Task 7: Execute one real two-scenario network E2E window

**Files:** New append-only local artifacts under `results/evaluation_v1/network_e2e_v1/network-finalization-20261006/`; live gates under ignored `.vinsoc/`. Do not modify code during the run.

**Interfaces:** Consumes Task 6 implementation/lock and Task 1 window. Produces technical receipt plus actual human-review receipt, complete or partial, with full per-request usage and safe failure categories.

- [ ] **Step 1: Confirm key/account/pricing without another API probe.** Resolve key source; verify expected project access, usable credit, remaining project/organization spend allowance and applicable model rate/token limits. Owner confirmation is valid only when actually obtained and recorded with time; if unavailable, list exactly what cannot be verified. Keep private account details out of repo. Do not increase limits/buy credit.
- [ ] **Step 1a: Write a private gate receipt using actual checked values.** Required fields: schema_version, window_id, new_live_budget_usd, prior-allocation reconciliation; implementation_sha; ci.headSha, ci.run_url, ci.conclusion and both jobs with exact name/conclusion/job_url; account.source=`owner_confirmation`, confirmed_utc, project_verified, available credit/remaining spend amounts; and per-model pricing url/checked_utc/source_sha256/input/cached_input/output. Require CI head=local HEAD=origin/master, tracked implementation clean, both jobs success and account/pricing checks at most 21600 seconds old. Preserve unrelated untracked files. Private identifiers/credentials are not part of the public receipt; validated booleans, times and amounts suffice. Unit tests must prove missing/stale/false checks fail before client creation.
- [ ] **Step 2: Reconcile window ledger.** Import known prior costs from actual receipts and retain any unresolved cost_unknown from earlier attempts. The hard-coded historical PRIOR_TASK_COST_USD is not the new authoritative ledger. If unknown earlier cost belongs to this allocation, stop until reconciled; do not call it zero. Show previous known cost, remaining allocation and pending reservations separately.
- [ ] **Step 3: Calculate preflight with no cache discount:** demo <= `4 * ((50000 * 0.40 + 1000 * 1.60) / 1e6) = USD 0.0864000`. The full pending allocation reserves R2 E0 <=0.0570240 and E3 <=0.5702400, total new-call envelope <= **0.7136640**. Prior charged costs sharing the allocation must fit within 0.75 as well. Recheck published prices; changed prices require recomputation, not stale acceptance. Count serialized request tokens using the available tokenizer plus declared conservative framing reserve, and retain the existing request-byte bound; no heuristic-only unlimited input.
- [ ] **Step 4: Run preflight-only first:**

```bash
python -m scripts.demo_ctu_network_public_model_driven --e2e --preflight-only --snapshot data/ctu_network_public/snapshots/ctu_dev.duckdb --output results/evaluation_v1/network_e2e_v1/network-finalization-20261006/demo --gates .vinsoc/live-windows/network-finalization-20261006/gates.json --window-id network-finalization-20261006 --review-mode deferred
```

Expected: actual key/account/CI/lock/snapshot/scenario/window/budget PASS, attempted=0. The command is not an API smoke. Request 2 evidence size is checked after actual tool execution; if too large, preserve request 1 cost and stop.

- [ ] **Step 5: Execute exactly once, same command without `--preflight-only`.** Use `--review-mode interactive` when the user is present; otherwise use deferred and obtain review through Task 4's offline review-receipt command. Exactly two successful native conversation turns per scenario can complete the technical path. Model-generated wrong arguments, wrong facts, refusal, length termination or another tool request after the limit stays partial. No fallback, smoke, prompt change or retry.
- [ ] **Step 6: Verify saved JSON independently:** both actual model identities, four attempts/responses when fully successful, valid total/cached usage, cost sum, executed native arguments, tool_call_id/evidence linkage, source facts, full assessment/hypotheses/limitations, each lifecycle stage and real review status. Report latency per call/tool/scenario/total. Do not turn a single successful diagnostic response into a completed demo.
- [ ] **Step 7: On failure save evidence and report the exact blocker, then stop this live condition.** Account/transport/unknown-cost failures stop the remaining paid window. A technically valid model-answer failure permits offline diagnosis; it does not permit a second demo attempt. Checkboxes representing failed acceptance remain unchecked.
- [ ] **Step 8: After human review, commit only safe aggregate receipts/results and artifact hashes; keep raw data/credentials out.** CI of this evidence commit is separate from the implementation CI and does not retroactively change run provenance.

### Task 8: Render the saved E2E evidence as a complete standalone reader

**Files:** Create `scripts/render_network_e2e_report.py`, `tests/test_network_e2e_report.py`; update runbook section 8 only from saved evidence.

**Interfaces:** `render_report(receipt_path: Path, output_path: Path) -> dict`; CLI `python -m scripts.render_network_e2e_report --receipt PATH --output PATH`. No SDK/provider creation, source rebuild, DB query or inference.

- [ ] **Step 1: Write RED reader tests:** complete/partial/awaiting-human status; wrong schema or missing receipt; HTML injection in assessment/field values; locally missing files; overwrite prevention; attempts/usage/cost fields exactly equal JSON; model/scenario labels never disguised as benchmark scores.
- [ ] **Step 2: Build one self-contained HTML file showing request summary, triage, native tool trace, arguments, OBSERVED/DERIVED evidence and parent/source references, structured observation checks, complete assessment/hypotheses/risk/confidence/limitations, human decisions and usage/cost/latency/identity.** Escape all text. No network/CDN dependency or API button. Long content is collapsible but preserved, not deleted or clipped. Partial runs show the failure stage and retained prior evidence.
- [ ] **Step 3: Run `python -m pytest tests/test_network_e2e_report.py -q`, compile/diff and render the actual receipt.** Expected: exact counts/costs/status match JSON; opening/re-rendering has zero model calls. If live demo is blocked, render its real partial result and label the block; do not fabricate a successful example.
- [ ] **Step 4: Update runbook with the exact live/review/render commands and distinctions among LIVE, REPLAY and OFFLINE REHEARSAL.** Preserve the CLI path and its full receipts; HTML is a presentation of that evidence. Commit allowed script/tests/doc/result references.

### Task 9: Close the remaining R2 release defects without changing archived scores

**Files:** Modify `scripts/run_vinsoc_finalization_dev.py`, `tests/test_vinsoc_finalization_live.py`, `tests/test_vinsoc_finalization_contract.py`; create `evaluation/finalization/R2_MATCHED_v1.lock.json`. Reuse `live_window.py`. Leave archived `evaluation/r2_phase2/scoring.py`, safety.py and existing locks byte-for-byte unchanged.

**Interfaces:** New matched series identity `r2_finalization_matched_v1`; new lock explicitly binds current prompt_v4/tool_v4/runner/grounding/safety_v4, actual E0 request builder, archived evaluator/comparator and entrypoint/live-window code. `score_prediction(case, record, tools.snapshot)` receives the verified `Phase2V4Snapshot` rather than a Path.

- [ ] **Step 1: Add RED tests:** a native LIKE/ILIKE ESCAPE/Unicode query passes the same V4 policy in tools and scoring; missing/broken/truncated gold remains unscored; eight retained unscored records cannot be complete/official_eligible; cleanup failure preserves scored records and costs; changing output cannot rerun E0/E3; provider failure/unknown cost prevents the next condition.
- [ ] **Step 2: Correct scoring wiring and aggregation.** Track expected, attempted, retained, scored and unscored case counts separately. Unscored flags stay null, do not become false/zero accuracy. Official eligibility requires all eight unique expected IDs scored, validation_passed, correct implementation/request/snapshot/split/scorer and complete actual usage. Wrong SQL or NO_FINAL_SQL remains a scored model failure inside the 8-case denominator; it does not become an infrastructure exclusion.
- [ ] **Step 3: Make report/ledger persistence survive close() and local exceptions; reuse the fixed Task 1 claims/cost state.** Keep pipeline_error_category distinct from scoring_error_category. Old run helpers remain retired, no historical replay edits and no case006 special rerun.
- [ ] **Step 4: Produce the new matched lock and allow its explicit identity/path in the release verifier/CLI.** Preserve CONTRACT_v4.lock.json; add version support without weakening its old hash checks. If a verifier source file bound by the old v4 lock changes, document that old lock still verifies only old source bytes; do not rewrite it. Default the new matched CLI to its new lock/series, not the historical identity.
- [ ] **Step 5: Verify focused/full suites, local actual snapshot contract, compile and diff; protect all historical hashes.** Run `python -m pytest tests/test_vinsoc_finalization_live.py tests/test_vinsoc_finalization_contract.py tests/test_finalization_live_window.py tests/test_r2_phase2_semantics.py tests/test_r2_phase2_safety.py tests/test_r2_phase2_grounding.py -q`, followed by `python -m pytest -q`. Commit/push implementation, wait for both exact-SHA CI jobs. Do not call either condition before CI.

### Task 10: Run the complete new controlled E0/E3 development comparison

**Files:** New `results/evaluation_v1/finalization_matched_v1/network-finalization-20261006/E0/` and `E3/` artifacts; new safe matched-series results doc. Same authoritative window as the demo.

**Interfaces:** Existing R2 CLI adds explicit `--lock`, `--series-id` and `--window-id` options. E0 is the actual one-shot baseline with no tools; E3 is the supplemental linker+generator framework with existing profiler/value-search/SQL-probe capabilities. The experiment does not replace the production network tool with raw model SQL.

- [ ] **Step 1: Verify actual remaining allocation after the demo, current account/pricing and Task 9 exact-SHA CI.** Same dev split/snapshot/model/scorer between E0/E3; request architecture is the deliberate difference. Preflight each condition and reserve its partner before transmission. No extra paid smoke/model listing probe.
- [ ] **Step 2: Record the implementation SHA and freeze code across the pair.** Do not commit or change any code/lock/prompt/benchmark between E0 and E3. Each condition has exactly one claimed suite attempt; already-consumed conditions are not rerun.
- [ ] **Step 3: Run E0 once, 8 IDs; verify report/ledger.** If infrastructure/cost uncertainty occurs, stop E3. Model wrong answers with valid provider telemetry are valid measured failures and do not trigger a retry.
- [ ] **Step 4: Run E3 once, same 8 IDs on the same SHA, after its gate.** Do not retry case006 or any failed case. Do not enlarge tool/turn/token limits to obtain a final SQL.

Exact commands after Task 9 adds the named options (preflight each first; these are not commands to run on the current unmodified HEAD):

```bash
python -m scripts.run_vinsoc_finalization_dev --condition E0 --preflight-only --snapshot data/ctu_network_public/snapshots/ctu_dev.duckdb --lock evaluation/finalization/R2_MATCHED_v1.lock.json --series-id r2_finalization_matched_v1 --window-id network-finalization-20261006 --gates .vinsoc/live-windows/network-finalization-20261006/gates.json --output results/evaluation_v1/finalization_matched_v1/network-finalization-20261006/E0
python -m scripts.run_vinsoc_finalization_dev --condition E0 --snapshot data/ctu_network_public/snapshots/ctu_dev.duckdb --lock evaluation/finalization/R2_MATCHED_v1.lock.json --series-id r2_finalization_matched_v1 --window-id network-finalization-20261006 --gates .vinsoc/live-windows/network-finalization-20261006/gates.json --output results/evaluation_v1/finalization_matched_v1/network-finalization-20261006/E0
python -m scripts.run_vinsoc_finalization_dev --condition E3 --preflight-only --snapshot data/ctu_network_public/snapshots/ctu_dev.duckdb --lock evaluation/finalization/R2_MATCHED_v1.lock.json --series-id r2_finalization_matched_v1 --window-id network-finalization-20261006 --gates .vinsoc/live-windows/network-finalization-20261006/gates.json --output results/evaluation_v1/finalization_matched_v1/network-finalization-20261006/E3
python -m scripts.run_vinsoc_finalization_dev --condition E3 --snapshot data/ctu_network_public/snapshots/ctu_dev.duckdb --lock evaluation/finalization/R2_MATCHED_v1.lock.json --series-id r2_finalization_matched_v1 --window-id network-finalization-20261006 --gates .vinsoc/live-windows/network-finalization-20261006/gates.json --output results/evaluation_v1/finalization_matched_v1/network-finalization-20261006/E3
```
- [ ] **Step 5: Independently sum per-case flags and per-response usage/cost; publish EX, syntax validity, execution success, safety rejection and pipeline/scoring error classes for each ID.** EX is matching non-truncated gold result under the locked comparator on this development snapshot. Pipeline OK is not EX. Neither EX nor demo success proves a clean holdout or full SQL semantic equivalence.
- [ ] **Step 6: Compare paired cases and cost/calls, preserving both complete suites.** Identify common-correct, E0-only, E3-only and common-wrong IDs; report small-n limitations. Baseline stays available even if E3 is better. Cross-domain and module diagnostics remain separate; do not rename this 8-case pair as the 96-case benchmark.
- [ ] **Step 7: Commit evidence only after both conditions terminate, with their real implementation SHA, fresh receipt identities and separate evidence-commit CI.** On a failed gate/partial suite publish the actual partial state and leave completion unchecked. No score merging with historical 7/8.

### Task 11: Final reproducible handoff, preservation check and completion decision

**Files:** Create `docs/evaluation/network_e2e_results_2026-10-06.md`, a new matched R2 results doc if executed, and `results/evaluation_v1/network_e2e_v1/network-finalization-20261006/delivery_receipt.json`. Update current runbook/README result references only where actually changed.

**Interfaces:** The delivery receipt links setup → implementation/CI → live attempts → technical/review receipt → HTML → R2 paired receipts → artifact digests. Status is scoped per deliverable, never one ambiguous COMPLETE flag for the entire research project.

- [ ] **Step 1: Verify protected hashes from Task 0 against the final tree and the local source/snapshot bytes.** Explain authorized new files/code changes separately; no historical result/benchmark/lock rewrite.
- [ ] **Step 2: Include exact initial/implementation/final SHA, files changed, tests really run, focused/full counts/skips, both CI URLs/jobs, safe key-source label, account checks, per-condition attempts/responses/usage/cost/unknown state, source identities and hashes.** For local runs use a committed safe receipt + SHA as evidence; artifact ID is N/A unless there really is an uploaded artifact.
- [ ] **Step 3: Report each required stage for each demo scenario and its actual review decision.** Include a concrete request → native argument → tool fact → structured model observation → validated assessment example from the saved run. Show why the numeric fact was verified. Ground-truth dataset label stays contextual, not a forced threat conclusion.
- [ ] **Step 4: Keep historical headlines until replaced by a complete newly scored suite.** R1 remains 22/24, R2 historical Phase2 remains 7/8. Add a separately named new paired result if Task 10 completed; code/tests/replay do not raise model accuracy.
- [ ] **Step 5: Record cross-domain progress honestly:** registry/controller/gold-audit checkpoint implemented; calibration/evaluation materialization, adversarial instances, semantic benchmark lock, telemetry/statistics release and paid experiments still use their own gates. Do not discard or re-label this work as merely a proposal, and do not run it with this allocation.
- [ ] **Step 6: Run final doc/result-reference checks, compile/diff where code changed, push allowed delivery files, verify the final commit CI.** Then STOP with the complete evidence or exact remaining blockers. No frozen, R1, additional demo, ThreatFox, OTRF or unapproved cross-domain inference after this task.

## Acceptance matrix — all original work is accounted for

| Deliverable | Required evidence | Completion condition |
|---|---|---|
| Real network E2E | Two native model/tool conversations using production public investigate on verified S5/S7 | Both scenarios pass technical checks; real final human decisions recorded |
| Triage / tool / evidence / assessment / review | Ordered lifecycle and provenance-linked case JSON | No stage skipped or script-fabricated |
| Factual assessment | Structured claims checked against delivered evidence; evidence checked against DB; prose reviewed by human | Wrong numbers/IDs/coverage fail; uncertainty retained |
| Safe partial behavior | Charged failures, unknown-cost latch, durable claim/ledger tests and actual receipts | Failure cannot become no-tool accuracy or E2E success |
| Usable presentation | CLI + standalone HTML sourced from the same receipt | Complete content preserved; no new calls when rendering |
| R2 controlled comparison | One new matched E0/E3 pair, same SHA/model/data/scorer and 8 unique IDs | Both complete scored reports, actual usage/cost and paired error analysis |
| Existing metrics | Immutable R1 22/24 and historical R2 7/8 sources | No unearned headline change or denominator reduction |
| Expanded benchmark | Existing cross-domain commits and explicit pending gates preserved | No accidental cancellation, fake completion or mixing with demo |
| Holdout integrity | R1 sealed; consumed S1/S4 never called clean | Independent holdout remains a separately authorized future task |

## Exact local handoff

> Sync `origin/master`, record initial SHA/status and preserve `.env`, user files and all historical artifacts. Read this entire plan and its referenced runbook. Use `superpowers:executing-plans`; execute Tasks 0–11 in order and mark a checkbox only after its stated verification really passes. Finish the public-orchestrator Botnet + Normal CLI E2E first, including factual verification and real/deferred human review, then render its full receipt and complete the controlled R2 E0/E3 pair. Do not use forced arguments, replay, scripted assessment or scripted approval to call live E2E complete. After exact-SHA Python 3.11/3.12 CI and real account/identity/budget gates, live calls are required within the fixed window; no additional smoke or retry. Preserve baseline, cross-domain work and frozen restrictions. Report exact evidence or the precise failed gate, not another vague plan-only checkpoint.

## Primary technical references

1. [OpenAI function calling](https://developers.openai.com/api/docs/guides/function-calling): native call → application execution → correlated tool result → final model response.
2. [OpenAI structured outputs / JSON mode](https://developers.openai.com/api/docs/guides/structured-outputs): valid JSON alone does not guarantee the application schema; validate content and termination.
3. [GPT-4.1 Mini model/pricing](https://developers.openai.com/api/docs/models/gpt-4.1-mini): pinned demo model and standard input/cached/output rates; recheck at live preflight.
4. [GPT-5 Mini model/pricing](https://developers.openai.com/api/docs/models/gpt-5-mini): pinned R2 model/rates; record current availability/deprecation information without automatic fallback.

## Planner self-review

- Design uses existing public lifecycle, production native schema, NetworkSkill, EvidenceStore and HITL. No replacement model framework or undeclared SQL production tool.
- Every known demo gap above maps to Tasks 1–6 and a concrete offline test; each review-focus failure maps to its owning task.
- Both scenarios, assessment/hypotheses, factual checks, real review, usage/cost/provenance, reader and pending R2 pair have explicit acceptance. Speed comes from reusing implementation and ordering, not removing requirements.
- Historical scores/locks/data and cross-domain work are preserved; no claimed new model result during plan authoring.
- Paid attempts are bounded, durable and scoped; successful offline tests do not substitute for Tasks 7/10. A failed gate cannot be checked as complete.
