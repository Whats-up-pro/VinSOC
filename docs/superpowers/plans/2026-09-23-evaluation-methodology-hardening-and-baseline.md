# VinSOC Evaluation Methodology Hardening + Official Baseline Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Harden VinSOC's Tool Calling (R1) and Text-to-SQL (R2) evaluation so mentor-facing metrics are methodologically defensible, reproducible, and directly aligned with the project objective: measure real Tool Calling Accuracy and Text-to-SQL Accuracy before controlled improvement experiments.

**Architecture:** Extend the existing evaluation paths on `master`; do not replace them. R1 remains a BFCL-inspired, native-function-calling benchmark over production tool schemas. R2 remains a BIRD-style execution-accuracy benchmark over one frozen, read-only DuckDB snapshot, with explicit snapshot identity verification and semantic-trap tests. A final integration gate freezes configuration before any official holdout run.

**Tech Stack:** Python 3.11/3.12, pytest, OpenAI-compatible native tool calling, JSON Schema, DuckDB, SHA-256, GitHub Actions.

**Spec:** `docs/superpowers/specs/2026-09-23-r1-r2-evaluation-hardening-design.md`

## Methodology References

- OpenAI Function Calling: native tool calls; strict mode; strict schemas require `additionalProperties: false` for objects and every property to be required, with optional values represented as nullable.
- Berkeley Function Calling Leaderboard (BFCL) V4: deterministic function-call evaluation, relevance/no-tool/hallucination coverage, multi-call categories; VinSOC intentionally implements the subset relevant to its three SOC tools rather than reproducing the full BFCL agentic benchmark.
- BIRD Text-to-SQL: Execution Accuracy is the primary correctness metric.
- Zhong, Yu & Klein (EMNLP 2020): one database instance can hide semantic SQL errors; VinSOC uses targeted semantic-trap fixtures rather than implementing the full distilled test-suite benchmark.
- DuckDB: official file connections support `read_only=True`; VinSOC keeps SQL evaluation inside the existing read-only safety boundary.

## Global Constraints

- Source code on current `master` is the implementation ground truth.
- Extend existing implementation; no rewrite of the orchestrator, provider layer, evaluator, or DuckDB data layer.
- No model fine-tuning.
- No new agent framework.
- R1 must use production tool schemas and native `LLMResponse.tool_calls`.
- R2 stays offline; do not expose raw SQL execution to the production LLM orchestrator.
- R2 headline correctness metric is Execution Accuracy, not SQL string Exact Match.
- R1 headline reporting must distinguish tool selection, exact calls, argument correctness, no-tool behavior, and case-level success.
- Frozen holdouts are never used for prompt/schema tuning.
- No synthetic/mutated/training rows may enter the official frozen DuckDB snapshot.
- Every production behavior change follows TDD: RED -> GREEN -> full-suite verification -> commit.
- Do not silently fall back to another provider/model during evaluation.
- Do not fabricate an official benchmark score if credentials, source data, or the frozen snapshot are unavailable.
- Direct implementation target remains `master`, per the existing project working agreement.

## Review Focus

1. Strict schemas that cause nullable optional fields to break existing production skill validation.
2. R1 no-tool accuracy that is reported but cannot be tuned because dev has no meaningful relevance/no-tool coverage.
3. R1 "trajectory" wording being mistaken for BFCL V4 multi-turn/agentic evaluation when current A1 is single-turn decision evaluation.
4. R2 runs that accept a different DuckDB file from the benchmark's declared frozen snapshot.
5. Execution Accuracy false positives caused by one snapshot accidentally making semantically different queries return the same result.

---

# Team Topology

## Agent A — R1 Tool Calling Methodology Engineer

**ROLE:** Tool/function-calling evaluation specialist.

**MISSION:** Make R1 strict-schema compatible, relevance-aware, and mentor-facing without changing the intended three-tool SOC architecture.

**OWNERSHIP:**
- `agent/tools.py`
- minimal execution-argument sanitation in `agent/orchestrator.py` if required by strict nullable schemas
- `evaluation/tool_calling/*`
- `evaluation/tool_calling/benchmarks/dev/*`
- R1-specific tests and docs

**NON-GOALS:**
- Do not edit Text-to-SQL code.
- Do not add new SOC tools.
- Do not implement BFCL web search, memory, or full multi-turn agentic evaluation.
- Do not tune on frozen cases.

**DEPENDENCIES:** None.

**DELIVERABLE:** strict-compatible production schemas, safe execution semantics, dev no-tool coverage, clear mentor-facing metric mapping, tests, verification evidence.

---

## Agent B — R2 Text-to-SQL Evaluation Engineer

**ROLE:** Text-to-SQL evaluation and reproducibility specialist.

**MISSION:** Make R2's Execution Accuracy runs cryptographically bound to the intended frozen snapshot and improve benchmark diagnostics without changing the offline-only safety architecture.

**OWNERSHIP:**
- `evaluation/text_to_sql.py`
- new snapshot verification helper if needed
- `schemas/text_to_sql_case.json`
- `evaluation/text_to_sql_benchmarks/*` except raw benchmark database contents
- R2 evaluator tests and docs

**NON-GOALS:**
- Do not expose SQL as a production agent tool.
- Do not download/build public datasets.
- Do not replace Execution Accuracy with Exact Match.
- Do not implement full EMNLP distilled test suites.

**DEPENDENCIES:** Defines the snapshot manifest contract consumed by Agent C.

**DELIVERABLE:** snapshot identity/hash verification, benchmark metadata/reporting, semantic-trap coverage, tests, verification evidence.

---

## Agent C — Frozen Snapshot / Data Provenance Engineer

**ROLE:** Benchmark data and reproducibility specialist.

**MISSION:** Produce a reproducible `vinsoc_public_v1.duckdb` from approved public sources, preserving provenance and creating the actual manifest values required by R2.

**OWNERSHIP:**
- snapshot-building scripts under `scripts/` or `vinsoc_data/`
- `docs/duckdb_data_layer.md`
- local `data/snapshots/vinsoc_public_v1.duckdb` build artifact
- dataset provenance records
- actual snapshot SHA-256 value inserted into the manifest contract defined by Agent B

**NON-GOALS:**
- Do not fabricate rows.
- Do not use private/company telemetry.
- Do not modify R1.
- Do not commit large source datasets or the DuckDB binary unless repository policy explicitly permits it.
- Do not invent license notes; record source-provided terms or report a blocker.

**DEPENDENCIES:** Can prepare source mapping in parallel; final manifest update depends on Agent B's contract.

**DELIVERABLE:** reproducible build command/script, provenance records, row-count/coverage validation, actual snapshot SHA-256, blocker report if any source cannot be legally/reliably obtained.

---

## Agent D — Integration Reviewer + Baseline Orchestrator

**ROLE:** Independent evaluator/reviewer.

**MISSION:** Review artifacts from Agents A/B/C directly, integrate only compatible changes, run full verification, then execute official dev baselines and freeze the configuration for controlled experiments.

**OWNERSHIP:**
- cross-subsystem review
- full test/CI verification
- benchmark run artifacts under `results/`
- final evaluation methodology/status docs
- no production feature ownership unless fixing a review finding with a regression test

**NON-GOALS:**
- Do not trust agent summaries without reading diffs/tests.
- Do not tune on frozen results.
- Do not silently waive failed tests or missing snapshot/credentials.
- Do not report historical A2 MockProvider results as the R1 LLM baseline.

**DEPENDENCIES:** Agents A + B complete; R2 baseline additionally requires Agent C snapshot.

**DELIVERABLE:** reviewed integrated state, fresh test evidence, official dev baseline artifacts when prerequisites exist, exact blockers otherwise.

---

# Execution Graph

```text
T0  Capture HEAD + freeze plan
 |
 +--------------------------+--------------------------+
 |                          |                          |
 v                          v                          v
T1 R1 strict schemas     T4 R2 manifest contract   T7 snapshot source mapping
 |                          |                          |
T2 R1 null sanitation       T5 R2 semantic traps      T8 reproducible builder
 |                          |                          |
T3 R1 no-tool/dev metric    T6 R2 report metadata     T9 build + hash/provenance
 |                          |                          |
 +--------------------------+-------------+------------+
                                            |
                                            v
                                    T10 independent review
                                            |
                                            v
                                    T11 full verification
                                            |
                            +---------------+---------------+
                            |                               |
                            v                               v
                     T12 R1 dev baseline             T13 R2 dev baseline
                            |                               |
                            +---------------+---------------+
                                            |
                                            v
                                   T14 error analysis
                                            |
                                            v
                                   T15 controlled experiments
                                            |
                                            v
                                   T16 freeze best config
                                            |
                                            v
                                   T17 frozen holdout ONCE
```

Parallel rule:
- T1-T3 = Agent A sequential internally.
- T4-T6 = Agent B sequential internally.
- T7-T8 may run in parallel with Agents A/B.
- T9 waits for Agent B's manifest contract.
- T10 onward is sequential.

---

### Task 0: Capture Reproducibility Envelope

**Owner:** Agent D / orchestrator before dispatch.

**Files:**
- No production code.
- Record in execution log.

**Produces:** immutable execution context for all agents.

- [ ] **Step 1: Capture current HEAD**

Run:
```bash
git rev-parse HEAD
git status --short
```

Expected: exact HEAD recorded; working tree state documented.

- [ ] **Step 2: Record current CI baseline**

Run:
```bash
python -m pytest -q
```

Expected: current full suite passes before any new work. If it fails, record each pre-existing failure and stop treating later failures as regressions until classified.

- [ ] **Step 3: Freeze evaluation principles**

Record these exact decisions in the execution log:
- R1 official path = A1 real provider, not A2 MockProvider.
- R1 frozen split is holdout only.
- R2 primary metric = Execution Accuracy.
- R2 frozen split is holdout only.
- R2 official run requires verified snapshot identity/hash.
- No fallback provider/model in official runs.

**Acceptance Criteria:**
- HEAD, dirty state, test baseline, and evaluation rules are recorded before edits.

---

### Task 1: Make Production Tool Schemas Strict-Compatible

**Owner:** Agent A.

**Files:**
- Modify: `agent/tools.py`
- Test: create `tests/test_tool_schema_strictness.py`
- Possibly modify existing provider tests only if needed.

**Interfaces:**
- Consumes: current `get_tool_schemas() -> List[Dict[str, Any]]`.
- Produces: same public function name and outer OpenAI tool format; each function becomes strict-compatible.

- [ ] **Step 1: Write a failing schema-contract test**

The test must recursively assert:
- every function contains `"strict": true`;
- every object schema has `"additionalProperties": false`;
- every property name appears in that object's `required`;
- formerly optional top-level fields accept `null`;
- required business identifiers such as `indicator` and `host` remain non-null strings.

Example assertion helper:

```python
def assert_strict_object(schema):
    assert schema["type"] == "object" or (
        isinstance(schema["type"], list) and "object" in schema["type"]
    )
    assert schema["additionalProperties"] is False
    assert set(schema.get("properties", {})) == set(schema.get("required", []))
```

- [ ] **Step 2: Verify RED**

Run:
```bash
python -m pytest tests/test_tool_schema_strictness.py -q
```

Expected: FAIL because current schemas omit `strict` and `additionalProperties`.

- [ ] **Step 3: Implement strict schemas with nullable optional values**

Required behavior:
- `indicator` / `host`: non-null required string.
- `indicator_type`: required by JSON Schema but nullable to preserve business-level optional semantics.
- `time_range`: required by JSON Schema but may be `null`; if object, it must contain non-null `start` and `end` strings and reject extra keys.
- all object levels use `additionalProperties: false`.

Do not create a second evaluation-only schema; A1 must evaluate the production contract.

- [ ] **Step 4: Verify GREEN**

Run:
```bash
python -m pytest tests/test_tool_schema_strictness.py -q
python -m pytest tests/test_tool_calling_decision_runner.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add agent/tools.py tests/test_tool_schema_strictness.py
git commit -m "feat(r1): make production tool schemas strict-compatible"
```

**Acceptance Criteria:**
- Strict contract tests pass.
- Existing A1 decision-runner tests still use `get_tool_schemas()`.
- No evaluation-only divergence from production schemas.

---

### Task 2: Preserve Existing Runtime Semantics Under Nullable Strict Arguments

**Owner:** Agent A.

**Files:**
- Modify: `agent/tools.py` or add one narrowly-scoped helper module.
- Modify: `agent/orchestrator.py`.
- Test: create/update orchestrator/tool argument tests.

**Interfaces:**
- Produces: `sanitize_tool_arguments_for_execution(tool_name: str, arguments: dict[str, Any]) -> dict[str, Any]`.

- [ ] **Step 1: Write failing runtime regression tests**

Required cases:
1. `{"indicator": "1.2.3.4", "indicator_type": null}` dispatches as if `indicator_type` was omitted.
2. `{"indicator": "1.2.3.4", "time_range": null}` does not fail `NetworkSkill.validate_input`.
3. `{"host": "WS-01", "time_range": null}` does not fail endpoint validation.
4. Unknown non-null keys are impossible through schema but must not be silently invented by sanitation.

- [ ] **Step 2: Verify RED**

Run the targeted tests and confirm failures arise from passing `None` into current validators.

- [ ] **Step 3: Implement minimal sanitation**

Rules:
- drop top-level keys whose value is `None`;
- do not rewrite non-null values;
- do not coerce types;
- do not silently repair partially invalid `time_range` objects;
- call sanitation exactly once immediately before skill dispatch.

- [ ] **Step 4: Verify GREEN + regression**

Run:
```bash
python -m pytest tests/test_tool_schema_strictness.py -q
python -m pytest tests/test_tool_calling_decision_runner.py -q
python -m pytest -q
```

- [ ] **Step 5: Commit**

```bash
git add agent/tools.py agent/orchestrator.py tests/
git commit -m "fix(r1): preserve optional tool semantics under strict schemas"
```

**Acceptance Criteria:**
- Strict schema output cannot break the pre-existing optional-field behavior.
- No general coercion layer is introduced.

---

### Task 3: Add R1 Relevance/No-Tool Development Coverage and Clarify Headline Metrics

**Owner:** Agent A.

**Files:**
- Add: at least 4 reviewed `evaluation/tool_calling/benchmarks/dev/case_0xx.json` no-tool/relevance cases.
- Modify: `tests/test_tool_calling_benchmark_contract.py`.
- Modify: `evaluation/tool_calling/README.md`.
- Modify metric/report model only if a `case_success_rate` alias is added.

**Interfaces:**
- Existing frozen cases remain untouched.
- Existing `no_tool_accuracy` remains the no-tool metric.

- [ ] **Step 1: Add failing benchmark-contract test**

Require:
- dev contains at least 4 `category == "no_tool"` cases;
- every no-tool case has `expected_calls == []`;
- every no-tool case forbids all three production investigation tools;
- dev/frozen case IDs remain disjoint.

- [ ] **Step 2: Verify RED**

Expected: current dev benchmark does not satisfy the no-tool coverage threshold.

- [ ] **Step 3: Author four non-overlapping dev cases**

Required intents:
1. conceptual explanation request;
2. tool-capability/documentation question;
3. explicit "do not query investigation data" request;
4. unrelated/non-investigation informational request.

Do not copy `frozen_005` wording or leak its exact prompt.

- [ ] **Step 4: Clarify mentor-facing metric hierarchy**

Document:
- **Tool Selection Accuracy:** `tool_set_exact_match_rate`.
- **Exact Call Correctness:** `exact_call_precision/recall/f1`.
- **Required Argument Accuracy:** `argument_field_accuracy`.
- **No-Tool Accuracy:** `no_tool_accuracy`.
- **Case Success:** current `trajectory_success_rate`, explicitly described as single-turn case success and **not** BFCL V4 multi-turn trajectory evaluation.

If adding `case_success_rate` as an alias, preserve `trajectory_success_rate` for backward compatibility and test equality.

- [ ] **Step 5: Verify**

Run:
```bash
python -m pytest tests/test_tool_calling_benchmark_contract.py -q
python -m pytest tests/test_tool_calling_evaluator.py -q
python -m pytest -q
```

- [ ] **Step 6: Commit**

```bash
git add evaluation/tool_calling tests/
git commit -m "test(r1): add relevance and no-tool dev coverage"
```

**Acceptance Criteria:**
- R1 can measure and improve abstention behavior on dev without inspecting frozen.
- Documentation does not claim full BFCL V4 multi-turn equivalence.

---

### Task 4: Add R2 Snapshot Manifest Contract

**Owner:** Agent B.

**Files:**
- Create: `evaluation/text_to_sql_snapshot.py`
- Modify: `evaluation/text_to_sql.py`
- Create: `evaluation/text_to_sql_benchmarks/snapshot_manifest.schema.json`
- Test: extend `tests/test_text_to_sql_runner.py` or create `tests/test_text_to_sql_snapshot.py`.

**Interfaces:**
- Produces:
  - `SnapshotManifest`
  - `sha256_file(path: Path) -> str`
  - `load_snapshot_manifest(path: Path) -> SnapshotManifest`
  - `verify_snapshot(path: Path, manifest: SnapshotManifest) -> None`
- `run_text_to_sql_benchmark(...)` must verify before provider generation.

- [ ] **Step 1: Write failing tests**

Required cases:
1. correct file SHA passes;
2. same filename with changed bytes fails;
3. wrong path/snapshot ID fails;
4. verification happens before any provider call;
5. report contains `snapshot_id` and actual `snapshot_sha256`.

- [ ] **Step 2: Verify RED**

Expected: current R2 accepts any CLI `--snapshot` path and has no cryptographic identity check.

- [ ] **Step 3: Implement manifest validation**

Manifest contract:

```json
{
  "snapshot_id": "vinsoc_public_v1",
  "path": "data/snapshots/vinsoc_public_v1.duckdb",
  "sha256": "64-lowercase-hex-characters",
  "schema_version": "1"
}
```

Do not commit a fake SHA. Tests use temporary files and test manifests.

- [ ] **Step 4: Wire CLI/runner**

Add:
```text
--manifest evaluation/text_to_sql_benchmarks/snapshot_manifest.json
```

Official R2 execution order:
1. load manifest;
2. verify snapshot path + SHA;
3. load benchmark cases;
4. confirm each case references the manifest's canonical snapshot path/ID contract;
5. only then call the provider.

- [ ] **Step 5: Verify GREEN**

Run:
```bash
python -m pytest tests/test_text_to_sql_snapshot.py -q
python -m pytest tests/test_text_to_sql_runner.py -q
```

- [ ] **Step 6: Commit**

```bash
git add evaluation/text_to_sql.py evaluation/text_to_sql_snapshot.py evaluation/text_to_sql_benchmarks tests/
git commit -m "feat(r2): bind evaluation runs to a verified snapshot manifest"
```

**Acceptance Criteria:**
- R2 refuses to score against a different file even if its schema looks compatible.
- Provider is not called after manifest verification fails.

---

### Task 5: Strengthen R2 Benchmark Metadata + Semantic Trap Tests

**Owner:** Agent B.

**Files:**
- Modify: `schemas/text_to_sql_case.json`.
- Modify all current R2 dev/frozen JSON case definitions.
- Modify: `evaluation/text_to_sql.py`.
- Test: `tests/test_text_to_sql_runner.py`.

**Interfaces:**
- Add case metadata used for stratified reporting:
  - `category`: one of `filter`, `time_range`, `aggregation`, `distinct`, `ordering_limit`, `cti`, `network`, `endpoint`, or another explicitly documented fixed enum.
  - `difficulty`: `basic|intermediate|advanced`.

- [ ] **Step 1: Write failing schema/loader tests**

Require every R2 benchmark case to contain valid `category` and `difficulty`.

- [ ] **Step 2: Verify RED**

Current cases lack this metadata.

- [ ] **Step 3: Annotate all existing R2 cases**

Use the case's actual SQL semantics; do not infer difficulty from filename.

- [ ] **Step 4: Add semantic-trap unit tests**

At minimum pin these semantic differences:
- `COUNT(*)` vs `COUNT(DISTINCT x)`;
- `>` vs `>=`;
- `AND` vs `OR`;
- `ORDER BY ... ASC` vs `DESC`;
- top-k with correct rows but wrong order.

Use test fixtures only; do not place synthetic rows in official benchmark snapshot data.

- [ ] **Step 5: Add stratified report counts**

Report per category:
- cases;
- syntax validity;
- execution success;
- execution accuracy.

Do not introduce LLM-as-judge semantic scoring.

- [ ] **Step 6: Verify**

Run:
```bash
python -m pytest tests/test_text_to_sql_runner.py -q
python -m pytest -q
```

- [ ] **Step 7: Commit**

```bash
git add schemas/text_to_sql_case.json evaluation/text_to_sql.py evaluation/text_to_sql_benchmarks tests/
git commit -m "feat(r2): add stratified benchmark metadata and semantic traps"
```

**Acceptance Criteria:**
- R2 remains execution-based.
- Semantic traps prove the evaluator catches common one-snapshot mistakes when the fixture contains a counterexample.
- No claim is made that VinSOC implements the full EMNLP distilled test-suite method.

---

### Task 6: Produce the Reproducible Public DuckDB Snapshot

**Owner:** Agent C.

**Files:**
- Create: `scripts/build_vinsoc_public_snapshot.py` or equivalent focused builder.
- Modify: `docs/duckdb_data_layer.md`.
- Local output: `data/snapshots/vinsoc_public_v1.duckdb`.
- Final manifest value: `evaluation/text_to_sql_benchmarks/snapshot_manifest.json`.

**Interfaces:**
- Consumes `SocSnapshotBuilder` and the normalized table schemas already in `vinsoc_data/duckdb_store.py`.
- Must produce rows compatible with current `cti_indicators`, `network_flows`, and `sysmon_process_events` contracts.

- [ ] **Step 1: Select exact public input files**

Allowed source families:
- ThreatFox for CTI;
- CTU-13 and/or CICIDS2017 for network telemetry;
- a public Sysmon event-log corpus for endpoint telemetry.

For every chosen file record before ingestion:
- source URL;
- retrieval UTC timestamp;
- source-file SHA-256;
- license/usage note from source;
- dataset ID.

If the terms cannot be established, stop that source and report the blocker; do not invent metadata.

- [ ] **Step 2: Write ingestion tests on tiny extracted source samples**

Tests must verify mapping for:
- event timestamps;
- IP/port/protocol/action/byte fields;
- process parent/child/host fields;
- `source_dataset`;
- `source_row_id`;
- null/invalid-row handling.

Fixtures may be minimal source-format excerpts but must not be passed off as benchmark data.

- [ ] **Step 3: Verify RED then implement adapters**

Use existing normalized schemas. Do not change table meaning merely to accommodate one source file.

- [ ] **Step 4: Build snapshot locally**

The builder must:
1. create empty schema;
2. register provenance before row insertion;
3. ingest normalized rows;
4. close cleanly;
5. reopen through `DuckDBSnapshot(...)` in read-only mode.

- [ ] **Step 5: Validate coverage**

Run SQL checks proving:
- provenance table has one row per source dataset;
- all benchmark-relevant normalized tables exist;
- every ingested row has `source_dataset` and `source_row_id`;
- row counts are non-zero for every table referenced by official R2 cases;
- gold queries for all dev cases execute successfully.

- [ ] **Step 6: Compute official snapshot hash**

Run:
```bash
sha256sum data/snapshots/vinsoc_public_v1.duckdb
```

Write the exact resulting lowercase SHA-256 into `snapshot_manifest.json`. Never use a placeholder.

- [ ] **Step 7: Verify manifest through Agent B's code**

Run a manifest verification command/test before any LLM call.

- [ ] **Step 8: Commit reproducibility code/docs/manifest**

Do not commit raw downloaded datasets. Do not commit the DuckDB file if repository size/license policy disallows it; the manifest + builder + provenance instructions must be sufficient to reproduce it.

**Acceptance Criteria:**
- Snapshot can be rebuilt from recorded public sources.
- Actual snapshot hash matches the committed manifest.
- All official R2 gold queries execute on that snapshot.
- No synthetic benchmark rows.

---

### Task 7: Independent Review Gate

**Owner:** Agent D.

**Depends on:** Tasks 1-6.

**Review directly:**
- all changed production files;
- all new/changed tests;
- all benchmark cases;
- snapshot manifest;
- snapshot builder;
- methodology docs.

- [ ] **Step 1: Review R1**

Check:
- strict schema conforms to OpenAI strict requirements;
- optional-null sanitation cannot hide real invalid arguments;
- production and A1 use the same schemas;
- no-tool dev cases do not leak frozen prompts;
- metric labels do not overclaim BFCL multi-turn support.

- [ ] **Step 2: Review R2**

Check:
- hash verification precedes provider generation;
- failed verification cannot produce a score;
- Execution Accuracy remains primary;
- comparator semantics remain correct;
- semantic traps are tests only;
- snapshot data provenance is complete.

- [ ] **Step 3: Search for scope creep**

Search changed files for:
```text
TODO
FIXME
NotImplementedError
temporary
mock baseline
fallback
```

Every occurrence on the critical path must be resolved or explicitly classified.

- [ ] **Step 4: Classify findings**

Use:
- Critical: invalidates benchmark score or leaks holdout.
- Important: can materially bias metric/reproducibility.
- Minor: documentation/maintainability only.

No Critical or Important finding may remain before official baseline.

---

### Task 8: Full Verification Gate

**Owner:** Agent D.

- [ ] **Step 1: Full tests**

Run:
```bash
python -m pytest -q
```

Then verify GitHub Actions on both Python 3.11 and 3.12.

Expected: zero failures.

- [ ] **Step 2: R1 smoke**

Use injected/fake provider tests to prove:
- native tool calls only;
- production schema passed;
- no fallback;
- strict nullable fields safe.

- [ ] **Step 3: R2 smoke**

Use temporary test snapshot to prove:
- correct hash passes;
- wrong hash fails before provider call;
- read-only safety still rejects writes;
- execution accuracy remains deterministic.

- [ ] **Step 4: Benchmark contract checks**

Verify:
- R1 dev/frozen disjoint;
- R2 dev/frozen disjoint;
- R1 dev includes no-tool coverage;
- all R2 cases reference the official snapshot contract;
- frozen files were not modified in response to model performance.

**Acceptance Criteria:**
- Fresh local full suite green.
- Fresh CI green on 3.11 + 3.12.
- Zero unresolved Critical/Important review findings.

---

### Task 9: Run Official R1 Development Baseline

**Owner:** Agent D.

**Prerequisite:** valid provider credentials.

Before running, export the exact evaluation configuration once and reuse it unchanged:
```bash
export VINSOC_EVAL_PROVIDER=openai
test -n "$VINSOC_EVAL_MODEL" || { echo "Set VINSOC_EVAL_MODEL to the exact project-selected model ID"; exit 2; }
```
If `VINSOC_EVAL_MODEL` has not already been selected by the project, baseline execution is blocked; the agent must report that blocker rather than choose a model implicitly. The resolved value must be recorded in the run artifact.

Pin:
- provider;
- exact model ID;
- temperature = 0;
- git commit SHA;
- system prompt;
- production tool schema hash;
- dev benchmark hash.

Run:
```bash
python -m evaluation.tool_calling benchmarks dev \
  --mode decision \
  --provider $VINSOC_EVAL_PROVIDER \
  --model $VINSOC_EVAL_MODEL \
  --temperature 0
```

For robustness, run dev 3 times if cost permits. Do not tune between repetitions.

Report:
- Tool Selection Accuracy = tool-set exact match;
- Exact Call P/R/F1;
- Required Argument Accuracy;
- Critical Argument Accuracy;
- No-Tool Accuracy;
- Case Success / legacy trajectory success;
- forbidden-tool rate;
- mean/p50/p95 latency;
- token/cost metadata;
- run-to-run variation when repeated.

Do not call the historical A2/MockProvider score the official baseline.

**Acceptance Criteria:**
- Result artifact contains actual provider/model metadata.
- No provider errors are silently counted as ordinary wrong calls without separate reporting.
- Baseline is tied to one git commit + benchmark version.

---

### Task 10: Run Official R2 Development Baseline

**Owner:** Agent D.

**Prerequisites:** verified `vinsoc_public_v1.duckdb`, matching manifest, provider credentials.

Run:
```bash
python -m evaluation.text_to_sql evaluate \
  --snapshot data/snapshots/vinsoc_public_v1.duckdb \
  --manifest evaluation/text_to_sql_benchmarks/snapshot_manifest.json \
  --split dev \
  --provider $VINSOC_EVAL_PROVIDER \
  --model $VINSOC_EVAL_MODEL \
  --temperature 0 \
  --output results/text_to_sql/r2_dev_baseline.json
```

Run dev 3 times if cost permits; do not alter prompt/schema between repetitions.

Headline:
- **Execution Accuracy**

Diagnostics:
- Syntax Validity;
- Execution Success;
- Safety Rejection Rate;
- category-level Execution Accuracy;
- provider errors;
- latency/tokens/cost.

**Acceptance Criteria:**
- report includes snapshot ID + SHA;
- actual SHA equals manifest;
- every gold query executed on the same snapshot as the generated query;
- no Exact SQL Match headline is introduced.

---

### Task 11: Error Analysis Before Any Optimization

**Owner:** Agent D with read-only input from A/B specialists.

Create one normalized failure table per track.

R1 labels:
- WRONG_TOOL
- MISSING_TOOL
- EXTRA_TOOL
- NO_TOOL_HALLUCINATION
- REQUIRED_ARG_MISSING
- REQUIRED_ARG_WRONG_VALUE
- CRITICAL_ARG_WRONG
- FORBIDDEN_TOOL
- DUPLICATE_CALL
- PROVIDER_ERROR

R2 labels:
- PROVIDER_ERROR
- SYNTAX_ERROR
- SAFETY_REJECTION
- EXECUTION_ERROR
- RESULT_MISMATCH

For R2 `RESULT_MISMATCH`, manually annotate the dominant semantic cause for analysis only:
- filter;
- time range;
- aggregation;
- distinct;
- ordering/limit;
- schema/table/column selection;
- other.

Do not use manual labels as the correctness scorer.

Rank improvement candidates by:
```text
priority = frequency x impact
```

**Acceptance Criteria:**
- Every failed dev case has an inspectable reason.
- No optimization is selected before this analysis exists.

---

### Task 12: Controlled Improvement Experiments

**Owner:** Agent A for R1; Agent B for R2; Agent D controls experiment protocol.

## R1 experiments

Only one variable changes per experiment:

- TC-E0: official baseline.
- TC-E1: tool descriptions — explicit "when to use / when NOT to use".
- TC-E2: system routing prompt wording.
- TC-E3: schema descriptions/enums only if error analysis shows argument ambiguity remains after strict mode.

Keep fixed:
- model;
- provider;
- temperature;
- dev set;
- evaluator;
- schema structure except when schema is the one explicit independent variable.

## R2 experiments

Only run experiments justified by baseline errors:

- SQL-E0: official baseline.
- SQL-E1: improved schema serialization.
- SQL-E2: schema-linking hints.
- SQL-E3: few-shot examples selected from dev-only cases.
- SQL-E4: validation/repair pass only if syntax/execution errors are material.

Keep fixed:
- model;
- provider;
- temperature;
- snapshot SHA;
- dev set;
- evaluator.

For every experiment store:
```text
experiment_id
hypothesis
single modification
git commit
model/provider/temp
benchmark hashes
snapshot hash (R2)
metric_before
metric_after
absolute_delta_pp
error_class_delta
latency/cost delta
```

**Acceptance Criteria:**
- No experiment changes two independent variables.
- No frozen data is consulted.
- Improvement claim includes metric delta and error-class evidence.

---

### Task 13: Freeze Best Configuration and Run Frozen Holdout Once

**Owner:** Agent D.

Before frozen execution record:
- winning R1 configuration;
- winning R2 configuration;
- exact commit SHA;
- provider/model/temp;
- tool schema hash;
- benchmark directory hashes;
- snapshot SHA;
- prompts.

Then run each frozen split once.

R1:
```bash
python -m evaluation.tool_calling benchmarks frozen --mode decision ...
```

R2:
```bash
python -m evaluation.text_to_sql evaluate --split frozen ...
```

Do not modify prompts, schemas, cases, snapshot, or evaluator after seeing frozen scores. Any change after frozen invalidates that holdout result and requires a new holdout dataset version.

**Acceptance Criteria:**
- Frozen run artifacts are immutable and tied to exact config/version identifiers.
- Report clearly separates dev optimization results from final holdout results.

---

# Definition of Done

The evaluation system is complete for this internship stage only when all conditions below are evidenced:

1. R1 official evaluation uses native real-model function calling against the same strict-compatible production schemas used by runtime.
2. R1 dev includes relevance/no-tool cases; frozen is untouched during optimization.
3. R1 reports tool-set accuracy, exact-call correctness, argument accuracy, no-tool accuracy, and case success without claiming full BFCL V4 agentic equivalence.
4. R2 uses Execution Accuracy as the headline metric.
5. R2 refuses to run when snapshot path/hash differs from the official manifest.
6. R2 semantic-trap tests cover at least DISTINCT, boundary operator, Boolean predicate, and ordering mistakes.
7. Official snapshot has public-source provenance and an actual SHA-256.
8. Full pytest and CI 3.11/3.12 are green after integration.
9. Official dev baselines exist for both R1 and R2, or the exact external prerequisite blocker is documented.
10. Controlled experiments modify one variable at a time.
11. Frozen holdouts are executed only after configuration freeze.
12. Final report contains baseline vs improved metrics, absolute percentage-point deltas, error breakdown, and reproducibility identifiers.

---

# Agent Dispatch Prompts

## Prompt — Agent A

**ROLE:** R1 Tool Calling Methodology Engineer.

**CURRENT SYSTEM CONTEXT:** VinSOC already has A1 real-provider decision evaluation, deterministic matching, exact-call/argument metrics, 20 dev cases, and 8 frozen cases. A1 uses `get_tool_schemas()` and native `LLMResponse.tool_calls`. Current production tool schemas are not OpenAI strict-compatible, and dev relevance/no-tool coverage is insufficient.

**MISSION:** Implement Tasks 1-3 from `docs/superpowers/plans/2026-09-23-evaluation-methodology-hardening-and-baseline.md` using TDD.

**OWNERSHIP:** `agent/tools.py`, minimal nullable sanitation in `agent/orchestrator.py`, `evaluation/tool_calling/*`, R1 dev cases, R1 tests/docs.

**NON-GOALS:** Do not edit R2, do not add tools, do not modify frozen prompts for tuning, do not implement full BFCL V4 multi-turn.

**REQUIREMENTS:** production and A1 share schemas; strict mode compatibility; nullable optionals must preserve existing runtime semantics; add >=4 dev no-tool cases; keep metric claims precise.

**ACCEPTANCE CRITERIA:** targeted RED/GREEN evidence, full pytest green, no R1 frozen leakage, concise change summary with assumptions/unresolved issues.

**DELIVERABLE:** implementation commits, tests/results, findings, assumptions, unresolved issues.

## Prompt — Agent B

**ROLE:** R2 Text-to-SQL Evaluation Engineer.

**CURRENT SYSTEM CONTEXT:** VinSOC already generates SQL with a pinned provider, exposes schema-only context, executes through `DuckDBSnapshot` read-only safety, compares predicted/gold results, and reports Execution Accuracy. Cases declare `data/snapshots/vinsoc_public_v1.duckdb`, but the runner does not cryptographically verify snapshot identity.

**MISSION:** Implement Tasks 4-5 using TDD.

**OWNERSHIP:** `evaluation/text_to_sql.py`, new snapshot-verification helper, R2 schemas/cases/tests/docs.

**NON-GOALS:** Do not build/download the actual public snapshot; do not expose SQL to production; do not implement LLM-as-judge or full distilled test suites.

**REQUIREMENTS:** SHA verification before provider call; report snapshot identity; add benchmark category/difficulty; semantic traps remain test fixtures; Execution Accuracy remains headline.

**ACCEPTANCE CRITERIA:** wrong SHA fails before provider call; targeted + full tests green; existing read-only safety unchanged.

**DELIVERABLE:** implementation commits, manifest contract, tests/results, findings, assumptions, unresolved issues.

## Prompt — Agent C

**ROLE:** Frozen Snapshot / Data Provenance Engineer.

**CURRENT SYSTEM CONTEXT:** `SocSnapshotBuilder` and normalized DuckDB tables already exist. Repo intentionally contains no official snapshot. Approved source families are ThreatFox, CTU-13/CICIDS2017, and public Sysmon event logs.

**MISSION:** Implement Task 6 and produce a reproducible local `vinsoc_public_v1.duckdb` if public sources and license/provenance information are available.

**OWNERSHIP:** snapshot ingestion/build scripts, provenance documentation, local snapshot build, final actual SHA value.

**NON-GOALS:** No fabricated/synthetic benchmark rows; no private telemetry; no R1 edits; do not invent licensing terms.

**DEPENDENCY:** Use Agent B's manifest format for final SHA registration.

**REQUIREMENTS:** provenance before insertion, stable source_row_id, source hashes, read-only reopen, non-zero coverage for official cases.

**ACCEPTANCE CRITERIA:** build is reproducible; all dev gold SQL executes; manifest SHA equals file SHA; otherwise report exact source/licensing blocker instead of fabricating completion.

**DELIVERABLE:** builder implementation, source/provenance record, verification output, snapshot hash or blocker.

## Prompt — Agent D

**ROLE:** Independent Integration Reviewer + Baseline Orchestrator.

**CURRENT SYSTEM CONTEXT:** Agents A/B/C may report success independently; their claims are not trusted until direct review and full verification.

**MISSION:** Implement Tasks 7-13 after upstream artifacts are available.

**OWNERSHIP:** review, conflict resolution, verification, benchmark artifacts, error analysis, experiment protocol, final holdout execution.

**NON-GOALS:** Do not tune against frozen; do not silently ignore failures; do not substitute A2/mock scores for A1 real-model baseline.

**REQUIREMENTS:** read diffs/tests directly; zero Critical/Important findings before baseline; full pytest and CI evidence; pin every evaluation input; one-variable experiments.

**ACCEPTANCE CRITERIA:** trustworthy dev baselines or exact external blockers, reproducibility metadata, error analysis, controlled experiments, frozen holdout only after configuration freeze.

**DELIVERABLE:** review findings, verification logs, baseline/experiment artifacts, final status with unresolved blockers.
