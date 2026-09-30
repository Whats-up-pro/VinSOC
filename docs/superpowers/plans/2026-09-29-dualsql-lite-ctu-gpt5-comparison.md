# DualSQL-Lite CTU GPT-5 Comparison Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Mark each checkbox only after its verification command has actually passed.

**Goal:** Keep the locked GPT-5 Mini E0 one-shot run as the R2 baseline, implement DualSQL-Lite as an additional E1/E2/E3 comparison on the same CTU S5/S7 development contract, select the winner by Execution Accuracy, and stop before any frozen model call.

**Architecture:** First close the unfinished offline CTU S1/S4 frozen preparation required by Task 5. Then create a new versioned `dualsql_lite_ctu_gpt5_v1` package that reuses the locked CTU S5/S7 benchmark and scorer, adds three bounded database tools, and runs E1/E2/E3 without modifying historical DualSQL evidence. E0 is reused only after strict report and request compatibility checks.

**Tech Stack:** Python 3.11/3.12, DuckDB, OpenAI Python SDK, pytest, GitHub Actions.

**Spec:** `docs/superpowers/specs/2026-09-28-vinsoc-r1-r2-finalization-design.md`

**Supersedes:** This plan replaces the unfinished implementation details of Tasks 5-8 and clarifies the Task 12 gate in `docs/superpowers/plans/2026-09-29-vinsoc-r1-r2-finalization.md`. Other tasks in that plan remain binding.

## Global Constraints

- Work directly on `master`. Do not create a branch or pull request.
- Before editing, run `git fetch origin`, fast-forward to `origin/master`, record the full initial SHA, and run `git status --short`.
- Preserve `.env`, all pre-existing untracked files, historical result JSON, and historical locks.
- Never use `git clean`, `git reset --hard`, broad `git add .`, or overwrite an evidence path.
- Stage only named task files.
- Historical `evaluation/dualsql_lite/`, its `SELECTED_CONFIG.lock`, and `results/evaluation_v1/public_pilot/dualsql_lite/` are immutable.
- E0 run `36520685612` is immutable and must not be rerun.
- Do not change benchmark questions, gold SQL, comparator semantics, scorer code, source bytes, or the locked S5/S7 snapshot contract.
- Do not inspect S1/S4 frozen model outputs because none should exist. Offline source, schema, gold SQL, and deterministic result validation are allowed.
- Do not use frozen data, values, questions, or gold to tune E1/E2/E3 prompts or tools.
- Provider is OpenAI. Model is `gpt-5-mini-2025-08-07`. `reasoning_effort=low`, `max_completion_tokens=1000`, SDK retries `0`, and the API request must omit `temperature`.
- Do not use `OPENAI_BASE_URL`, fallback providers, routers, model aliases, or silent substitutions.
- All paid workflows are manual-only and reject GitHub Actions reruns.
- No paid call occurs before offline tests, full CI on the exact implementation SHA, snapshot verification, account/credit check, and conservative budget preflight.
- The conservative E1+E2+E3 ceiling must be below USD 0.75. Do not buy credit or change account limits.
- One incorrect SQL is scored evidence. Do not retry it.
- Any identity, provider, model, source, CI, or budget failure stops the task. Preserve safe partial evidence and do not dispatch again.
- Do not run R1, a demo, ThreatFox, OTRF, or any model/snapshot outside this task.

## Fixed Evidence

- E0 Actions run: `36520685612`
- E0 report: `results/evaluation_v1/ctu_network_public/gpt5_e0/36520685612/ctu-r2-result.json`
- E0 report SHA-256: `33b35678171309c1a8958c1d9818499915986942e6936a03428df8fa0544bc15`
- E0 result: Execution Accuracy `0/8`, Syntax Validity `8/8`, Execution Success `8/8`
- Dev version: `ctu_network_public_dev_v1`
- Dev logical snapshot SHA-256: `42c8e0a62441295cc5d95329a65dc22409c37de5b26a1e37dd56fbf0164a758c`
- Dev split SHA-256: `96362f80e9e6bf01f18f1023c75066c553ddd9c105d2545f98af808d24f736fb`
- Dev sources: `ctu13_s5` and `ctu13_s7`, exactly 243,906 normalized flows
- Frozen sources: `ctu13_s1` and `ctu13_s4`, with hashes already pinned in `evaluation/ctu_network_frozen/dataset_manifest.json`

## Review Focus

1. The S1/S4 builder must prove the database's real distinct row identity count; it cannot copy the expected total into the report.
2. Every E1/E2/E3 Actions run must reconstruct and validate the exact S5/S7 dev snapshot before any client is created.
3. E0 compatibility checks serialized request objects for an absent `temperature` key; `config.temperature=null` is valid report metadata and is not an API parameter.
4. E1, E2, and E3 must run on one identical implementation SHA. No evidence commit may occur between the three paid runs.
5. Charged usage, response ID, actual model, and latency must be saved before tool-argument or final-output parsing can fail.

## File Map

### Modify

- `scripts/build_ctu_network_frozen_snapshot.py`: explicit staging CSV/COPY contract and measured row-identity evidence.
- `tests/test_ctu_network_frozen_builder.py`: builder regressions for commas, NULLs, COPY options, and distinct identity.

### Create for offline frozen completion

- `evaluation/ctu_network_frozen/contract.py`: build and validate the S1/S4 frozen contract.
- `evaluation/ctu_network_frozen/VERSION.lock`: immutable source, snapshot, case, gold, and scorer identity.
- `evaluation/ctu_network_frozen/frozen/frozen_001.json` through `frozen_008.json`: offline-authored holdout cases.
- `tests/test_ctu_network_frozen.py`: frozen contract and gold-isolation tests.

### Create for the new comparison series

- `evaluation/dualsql_lite_ctu_gpt5/__init__.py`: package identity.
- `evaluation/dualsql_lite_ctu_gpt5/contract.py`: E0 compatibility and series identity.
- `evaluation/dualsql_lite_ctu_gpt5/SERIES.lock`: E0/dev/model/pricing contract.
- `evaluation/dualsql_lite_ctu_gpt5/tools.py`: CTU-only database tools and catalog.
- `evaluation/dualsql_lite_ctu_gpt5/prompts.py`: versioned linker and generator prompts.
- `evaluation/dualsql_lite_ctu_gpt5/agents.py`: bounded GPT-5 controller.
- `evaluation/dualsql_lite_ctu_gpt5/runner.py`: one-condition runner, budget gate, and partial evidence.
- `evaluation/dualsql_lite_ctu_gpt5/selection.py`: identity validation and deterministic winner selection.
- `evaluation/dualsql_lite_ctu_gpt5/SELECTED_CONFIG.lock`: created only after all three dev runs complete.
- `tests/test_dualsql_ctu_gpt5.py`: core contract, tools, agents, runner, and selection tests.
- `tests/test_dualsql_ctu_gpt5_workflow.py`: workflow shape and snapshot-provisioning tests.
- `.github/workflows/r2-dualsql-ctu-gpt5.yml`: manual E1/E2/E3 workflow.
- `docs/evaluation/r2_dualsql_ctu_gpt5_dev.md`: final dev comparison and error analysis.

### Append after all paid runs, never between them

- `results/evaluation_v1/ctu_network_public/dualsql_lite_ctu_gpt5_v1/<run-id>/<condition>.json`
- `results/evaluation_v1/ctu_network_public/dualsql_lite_ctu_gpt5_v1/<run-id>/receipt.json`

---

### Task 1: Harden and prove the S1/S4 snapshot builder

**Files:**
- Modify: `scripts/build_ctu_network_frozen_snapshot.py`
- Modify: `tests/test_ctu_network_frozen_builder.py`

**Interfaces:**
- Consumes: pinned S1/S4 manifest and source receipt.
- Produces: `build_ctu_network_frozen_snapshot(...) -> dict[str, Any]` with measured counts and a deterministic logical hash.

- [x] **Step 1: Add failing staging/load regression tests**

Add tests named:

```python
def test_internal_csv_copy_preserves_comma_null_and_types(tmp_path): ...
def test_copy_contract_disables_auto_detect(tmp_path, monkeypatch): ...
def test_distinct_source_row_id_is_measured_from_database(tmp_path): ...
```

The fixture must include a VARCHAR containing a comma, a nullable port/value, a numeric-looking `source_row_id` retained as text, valid integer fields, and nullable/valid timestamps. Query DuckDB after loading and assert exact values and types.

- [x] **Step 2: Run the focused tests and confirm failure**

Run:

```bash
python -m pytest tests/test_ctu_network_frozen_builder.py -q
```

Expected: the new tests fail because the CSV dialect, COPY contract, or measured distinct count is absent.

- [x] **Step 3: Make the staging dialect explicit**

In `_write_normalized_csv()` configure `csv.DictWriter` with:

```text
delimiter=","
quotechar='"'
doublequote=True
quoting=csv.QUOTE_MINIMAL
lineterminator="\n"
```

- [x] **Step 4: Make DuckDB COPY explicit**

Use typed table schema and all of:

```text
FORMAT CSV
HEADER TRUE
AUTO_DETECT FALSE
DELIMITER ','
QUOTE '"'
ESCAPE '"'
NULL ''
```

Do not add a second parser or change `iter_ctu_rows()`.

- [x] **Step 5: Measure row identity from DuckDB**

Query:

```sql
SELECT count(DISTINCT source_dataset || ':' || source_row_id)
FROM network_flows
```

Compare the result with total rows and fail on mismatch. Store the measured result in `distinct_source_row_id`.

- [x] **Step 6: Run focused verification**

Run:

```bash
python -m pytest tests/test_ctu_network_frozen_builder.py -q
python -m py_compile scripts/build_ctu_network_frozen_snapshot.py
git diff --check
```

Expected: PASS with no provider/model call.

- [x] **Step 7: Commit only the builder change**

```bash
git add scripts/build_ctu_network_frozen_snapshot.py tests/test_ctu_network_frozen_builder.py
git commit -m "fix(eval): lock CTU frozen staging contract"
git push origin master
```

### Task 2: Complete Task 5 and seal the offline S1/S4 frozen contract

**Files:**
- Create: `evaluation/ctu_network_frozen/contract.py`
- Create: `evaluation/ctu_network_frozen/VERSION.lock`
- Create: `evaluation/ctu_network_frozen/frozen/frozen_001.json` through `frozen_008.json`
- Create: `tests/test_ctu_network_frozen.py`

**Interfaces:**
- Produces: `build_frozen_lock(snapshot: Path, cases_dir: Path) -> dict[str, Any]`.
- Produces: `validate_frozen_contract(snapshot: Path, lock_path: Path, cases_dir: Path) -> dict[str, Any]`.
- Consumes later: Task 10 frozen gate only. DualSQL dev prompts and tools must never consume these files.

- [x] **Step 1: Write failing contract tests**

Cover:

- source URL/hash mismatch;
- logical snapshot mismatch;
- measured distinct row mismatch;
- changed case file;
- duplicate/missing case ID;
- gold result mismatch;
- comparator mismatch;
- semantic counterexample that differs from gold;
- provider creation forbidden during all offline validation.

- [x] **Step 2: Build the full snapshot twice from the same pinned bytes**

Use separate output/work directories. Record real S1/S4 normalized counts, schema, source hashes, logical hashes, and measured distinct identity. Require both logical hashes to match.

If either pinned source file is unavailable or either full build fails, STOP. Do not download replacement bytes or silently rebuild from another source.

- [x] **Step 3: Author eight source-separated frozen cases offline**

Use S1/S4 only. Collectively cover:

- scalar count/filter;
- DISTINCT;
- Boolean precedence;
- bounded time interval;
- aggregation/GROUP BY;
- ORDER BY/LIMIT;
- stored-value grounding;
- multi-row comparison.

Use no model output. If eight cases cannot satisfy coverage, stop for human review before writing a smaller lock.

- [x] **Step 4: Implement and write the frozen lock**

The lock must include source URLs/hashes, normalized source counts, schema, logical hash, measured distinct row identity, case IDs/file hashes/directory hash, gold-result hashes, comparator contract, semantic counterexamples, and builder/scorer hashes.

- [x] **Step 5: Run offline verification**

```bash
python -m pytest tests/test_ctu_network_frozen_builder.py tests/test_ctu_network_frozen.py -q
python -m evaluation.ctu_network_frozen.contract --snapshot <first-full-snapshot>
python -m evaluation.ctu_network_frozen.contract --snapshot <second-full-snapshot>
python -m py_compile evaluation/ctu_network_frozen/contract.py
git diff --check
```

Expected: two matching logical hashes, no model calls, no paid cost.

- [x] **Step 6: Commit the complete Task 5 lock**

Stage only the named frozen files and tests. Commit and push. Do not create a frozen model workflow.

### Task 3: Lock E0 compatibility for the new dev series

**Files:**
- Create: `evaluation/dualsql_lite_ctu_gpt5/__init__.py`
- Create: `evaluation/dualsql_lite_ctu_gpt5/contract.py`
- Create: `evaluation/dualsql_lite_ctu_gpt5/SERIES.lock`
- Create: `tests/test_dualsql_ctu_gpt5.py`

**Interfaces:**

```python
def verify_e0_baseline(
    report_path: Path,
    series_lock_path: Path,
) -> BaselineEvidence: ...
```

- [x] **Step 1: Write parameterized failing tests for every identity field**

Require exactly eight distinct `ctu_sql_001` through `ctu_sql_008` cases, complete run status, eight valid usage records, requested/actual model, reasoning effort, cap, retries, split hash, logical snapshot hash, source hashes, scorer/builder hashes, system prompt hash, schema hash, and fixed report SHA.

- [x] **Step 2: Pin the API request semantics correctly**

For every item in `serialized_requests` assert:

- `model == "gpt-5-mini-2025-08-07"`;
- `reasoning_effort == "low"`;
- `max_completion_tokens == 1000`;
- the `temperature` key is absent.

Accept `report["config"]["temperature"] is None` as descriptive metadata.

- [x] **Step 3: Pin pricing provenance**

`SERIES.lock` must record the rates used by the E0 report, official pricing URL, verification timestamp, and a rule that paid execution stops if current official pricing differs before E1.

- [x] **Step 4: Implement the compatibility gate and run it offline**

The gate reads the immutable E0 report and `evaluation/ctu_network_public/VERSION.lock`. It never creates a provider.

- [x] **Step 5: Run focused tests and commit**

```bash
python -m pytest tests/test_dualsql_ctu_gpt5.py -q
python -m py_compile evaluation/dualsql_lite_ctu_gpt5/__init__.py evaluation/dualsql_lite_ctu_gpt5/contract.py
git diff --check
```

Commit only after the exact E0 report passes.

### Task 4: Implement CTU-only database tools

**Files:**
- Create: `evaluation/dualsql_lite_ctu_gpt5/tools.py`
- Modify: `tests/test_dualsql_ctu_gpt5.py`

**Interfaces:**

```python
class CTUDatabaseTools:
    def database_profiler(self, arguments: dict[str, Any]) -> dict[str, Any]: ...
    def value_search(self, arguments: dict[str, Any]) -> dict[str, Any]: ...
    def sql_probe(self, arguments: dict[str, Any]) -> dict[str, Any]: ...
    def invoke(self, name: str, arguments: Any) -> dict[str, Any]: ...
```

- [x] **Step 1: Write failing tests**

Test real S5/S7 snapshot values for `source_dataset`, `label`, and `protocol`; deterministic catalog hash; unique controller-owned `evidence_id`; 20-row probe cap; response byte cap; read-only SQL; external access rejection; internal/provenance table rejection; and raw DuckDB exception suppression.

- [x] **Step 2: Implement only three tools**

Expose exactly:

- `database_profiler`;
- `value_search`;
- `sql_probe`.

Only `network_flows` is visible. Build the value catalog directly from the verified snapshot. Do not create case-ID rules, `scenario 5 -> ctu13_s5` aliases, benchmark literal maps, or hand-written answer hints.

- [x] **Step 3: Enforce safe errors**

Tool failure output contains a safe category such as `INVALID_ARGUMENTS`, `SAFETY_REJECTION`, `OUTPUT_LIMIT`, or `EXECUTION_ERROR`. Never serialize `str(original_exception)`.

- [x] **Step 4: Run focused and historical safety tests**

```bash
python -m pytest tests/test_dualsql_ctu_gpt5.py tests/test_dualsql_tools.py -q
```

Expected: new tests pass and historical DualSQL safety behavior remains intact.

- [x] **Step 5: Commit the tool boundary**

Stage only `tools.py` and the named tests.

### Task 5: Implement the GPT-5 linker and generator controller

**Files:**
- Create: `evaluation/dualsql_lite_ctu_gpt5/prompts.py`
- Create: `evaluation/dualsql_lite_ctu_gpt5/agents.py`
- Modify: `tests/test_dualsql_ctu_gpt5.py`

**Interfaces:**

```python
def run_role(
    *,
    role: Literal["linker", "generator"],
    question: str,
    system_prompt: str,
    tools: CTUDatabaseTools | None,
    client: Any,
    telemetry_sink: Callable[[ProviderCall], None],
) -> RoleResult: ...
```

- [x] **Step 1: Write failing controller tests**

Cover two valid native tool calls in one turn, sixth tool call blocked, sixth model turn blocked, question literal accepted without DB provenance, DB-derived value carrying `evidence_id`, invented DB value rejected, usage saved before malformed arguments, and no gold sentinel in any inference input.

- [x] **Step 2: Implement request construction**

Every call uses the fixed GPT-5 contract. Do not include a `temperature` key. Omit `tools` entirely for a no-tool role rather than sending `null`.

- [x] **Step 3: Implement role limits**

Each role allows at most five model turns, five total DB tool calls, and one final submission. Multiple tool calls in one turn are valid while the total remains within five.

- [x] **Step 4: Make grounding controller-owned**

The linker final answer contains only selected table and column names. The controller attaches bounded values returned by tools together with their `evidence_id`. Question literals remain a separate evidence class and need no database trace.

- [x] **Step 5: Save charged telemetry before parsing**

Immediately after a response, validate and persist response ID, actual model, usage, cost, and latency. Only then parse tool arguments or final content.

- [x] **Step 6: Run tests and commit**

```bash
python -m pytest tests/test_dualsql_ctu_gpt5.py tests/test_dualsql_agents.py -q
python -m py_compile evaluation/dualsql_lite_ctu_gpt5/prompts.py evaluation/dualsql_lite_ctu_gpt5/agents.py
```

### Task 6: Implement one-condition runner and bounded evidence

**Files:**
- Create: `evaluation/dualsql_lite_ctu_gpt5/runner.py`
- Modify: `tests/test_dualsql_ctu_gpt5.py`

**Interfaces:**

```python
def run_condition(
    condition: Literal["E1", "E2", "E3"],
    snapshot_path: Path,
    output_path: Path,
    client: Any,
    series_lock: SeriesLock,
) -> ConditionReport: ...
```

- [x] **Step 1: Write failing runner tests**

Test invalid condition rejection, E1/E2/E3 call limits, provider creation after preflight only, partial evidence after a charged parse failure, actual-model mismatch, usage mismatch, output-path immutability, and report identity completeness.

- [x] **Step 2: Implement condition semantics**

- E1: linker has DB tools; generator is one-shot and has no DB tools.
- E2: no linker; generator has DB tools.
- E3: linker and generator both have DB tools.

- [x] **Step 3: Implement conservative preflight**

Reserve at most:

- E1: 48 model calls across eight cases;
- E2: 40 model calls;
- E3: 80 model calls.

Bounds use serialized initial requests plus the maximum bounded tool/assistant context for later turns. Compute all three condition ceilings before provider creation and require their sum to be below USD 0.75.

- [x] **Step 4: Enforce per-call budget**

Before each call require:

```text
known_spend + conservative_remaining_bound < condition_budget
```

Save a credential-free partial JSON before and after every charged response. A final path must never overwrite an existing file.

- [x] **Step 5: Record complete provenance**

Include git SHA, condition, case IDs, split hash, logical snapshot hash, source hashes, scorer hashes, model config hash, prompt hashes, tool schema/implementation hashes, catalog hash, pricing rates/source/check time, requested/actual model, response IDs, calls, tokens, cost, latency, SQL, trajectory, and score.

- [x] **Step 6: Run tests and commit**

```bash
python -m pytest tests/test_dualsql_ctu_gpt5.py tests/test_dualsql_experiments.py -q
python -m py_compile evaluation/dualsql_lite_ctu_gpt5/runner.py
```

### Task 7: Implement selection and the manual workflow

**Files:**
- Create: `evaluation/dualsql_lite_ctu_gpt5/selection.py`
- Create: `.github/workflows/r2-dualsql-ctu-gpt5.yml`
- Create: `tests/test_dualsql_ctu_gpt5_workflow.py`
- Modify: `tests/test_dualsql_ctu_gpt5.py`

**Interfaces:**

```python
def build_selection(
    e0: BaselineEvidence,
    e1: ConditionReport,
    e2: ConditionReport,
    e3: ConditionReport,
) -> SelectionResult: ...
```

- [x] **Step 1: Test every selection tie-break and identity mismatch**

Order:

1. higher Execution Accuracy;
2. lower cost;
3. fewer model calls;
4. lower latency;
5. simpler E0, E1, E2, E3.

Reject partial reports, different splits, logical snapshots, sources, scorer identities, model contracts, implementation SHAs among E1-E3, or prompt/tool/catalog drift.

- [x] **Step 2: Test workflow shape**

Require:

- only `workflow_dispatch`;
- one choice input limited to E1/E2/E3;
- `contents: read` permission;
- `GITHUB_RUN_ATTEMPT == 1` before paid work;
- no `push` trigger;
- no E0 dispatch;
- no artifact upload containing source bytes or DuckDB files.

- [x] **Step 3: Reconstruct the exact dev snapshot in every run**

The workflow must:

1. read `evaluation/ctu_network_public/dataset_manifest.json`;
2. download only S5/S7 official URLs;
3. verify both pinned source SHA-256 values;
4. build two separate snapshots with `scripts.build_ctu_network_public_snapshot`;
5. validate both using `evaluation.ctu_network_public.contract` and `VERSION.lock`;
6. require equal logical hashes and the fixed 243,906 count;
7. use the first validated snapshot for inference;
8. clean source bytes and DuckDB files in an `if: always()` step;
9. upload only credential-free JSON evidence.

- [x] **Step 4: Enforce checkout and paid gates**

The workflow runs only on `refs/heads/master`, validates `GITHUB_SHA` against local HEAD, requires the pinned model secret/value, and creates the OpenAI client only after snapshot, E0, price, budget, and account gates pass.

- [x] **Step 5: Run all offline verification**

```bash
python -m pytest tests/test_dualsql_ctu_gpt5.py tests/test_dualsql_ctu_gpt5_workflow.py tests/test_dualsql_tools.py tests/test_dualsql_agents.py tests/test_dualsql_experiments.py -q
python -m pytest -q
python -m py_compile evaluation/dualsql_lite_ctu_gpt5/*.py
git diff --check
```

If a dependency is missing, report the exact command and error. Do not call an unrun test passed.

- [x] **Step 6: Commit the final implementation SHA**

Stage named code, tests, lock, and workflow only. Push `master`. Record this full SHA as `IMPLEMENTATION_SHA`.

- [x] **Step 7: Wait for exact-SHA CI**

Both Python 3.11 and 3.12 must pass on `IMPLEMENTATION_SHA`. Do not use CI from an earlier or later SHA.

### Task 8: Run E1, E2, and E3 once on the same SHA

**Files:** No tracked file changes until all three runs finish.

- [ ] **Step 1: Confirm account and cumulative budget**

Verify usable OpenAI project/organization, credit or billing state, spend limits, and model rate limits. Do not infer available balance from a previous successful call.

- [ ] **Step 2: Freeze the implementation checkout**

Before every dispatch confirm `origin/master == IMPLEMENTATION_SHA`. Do not commit documentation, receipts, result JSON, or any other file between E1, E2, and E3.

- [ ] **Step 3: Dispatch E1 once**

Run preflight, then one manual E1 suite. On any failure, preserve the partial artifact and STOP. Do not rerun.

- [ ] **Step 4: Dispatch E2 once**

Only after E1 completes validly, with the same `IMPLEMENTATION_SHA` and no repository commit. On failure, STOP.

- [ ] **Step 5: Dispatch E3 once**

Only after E2 completes validly, with the same `IMPLEMENTATION_SHA` and no repository commit. On failure, STOP.

- [ ] **Step 6: Verify all three artifacts before committing anything**

For each run verify artifact ID/digest, condition, eight unique cases, run complete, actual model, valid usage, snapshot/split/source/scorer identity, prompt/tool/catalog hashes, and evaluator SHA. Require all E1-E3 evaluator SHAs to equal `IMPLEMENTATION_SHA`.

### Task 9: Preserve results, select the winner, and stop

**Files:**
- Append: three immutable result directories and receipts.
- Create: `evaluation/dualsql_lite_ctu_gpt5/SELECTED_CONFIG.lock`
- Create: `docs/evaluation/r2_dualsql_ctu_gpt5_dev.md`

- [ ] **Step 1: Copy verified artifacts into new immutable paths**

Never overwrite. Record original Actions URLs, artifact IDs/digests, and report SHA-256 values in receipts.

- [ ] **Step 2: Run deterministic selection**

Compare E0/E1/E2/E3 with `build_selection()`. Headline metric:

```text
Execution Accuracy = correct execution results / 8
```

Also report raw correct count, Syntax Validity, Execution Success, Safety Rejection, linker completion, model calls, DB calls, tokens, cost, latency, and per-case error class.

- [ ] **Step 3: Apply claim discipline**

Each case equals 12.5 percentage points. Claim a `strong pilot signal` only if the winner exceeds E0 by at least 2/8. Do not claim statistical significance.

- [ ] **Step 4: Write and verify the selection lock**

The lock contains all four report hashes, winner, exact deployable config, prompt/tool/catalog hashes, pricing identity, selection inputs, and tie-break trace.

- [ ] **Step 5: Commit evidence only after selection passes**

Commit the three result directories, receipts, selection lock, and dev report. Run full CI on this evidence commit.

- [ ] **Step 6: STOP FOR HUMAN REVIEW**

Do not run frozen.

If E0 wins, the later frozen task may run E0 once after its lock and exact-SHA CI.

If E1, E2, or E3 wins, first update the spec and plan to choose one protocol:

1. selected-only frozen; or
2. paired E0/winner frozen in one atomic workflow with no intermediate result exposure.

No frozen workflow may be dispatched until that protocol is written, reviewed, and locked.

## Required Final Report to the Reviewer

Report:

- initial SHA;
- `IMPLEMENTATION_SHA`;
- final evidence SHA;
- exact files changed;
- local commands actually run;
- CI URLs for implementation and evidence SHAs;
- E1/E2/E3 Actions URLs;
- artifact IDs/digests and report hashes;
- E0/E1/E2/E3 EX, syntax, execution success, and safety;
- per-condition model/DB calls, tokens, cost, and latency;
- total known task cost and `cost_unknown` state;
- selected configuration and full tie-break trace;
- any blocker or deviation;
- explicit confirmation that no result commit occurred between E1/E2/E3;
- explicit confirmation that no frozen model call occurred.
