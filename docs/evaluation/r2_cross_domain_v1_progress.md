# Cross-domain v1 execution ledger

Scope: approved cross-domain plan dated 2026-10-05. This ledger describes offline
implementation evidence, not new model accuracy. Initial master/remote SHA:
`95cc81d3c751df881e914075d72cde715bbb9717`.

Task 1 works in `D:\VINUNI_AI2026\VinSOC-finalization-clean-95cc81d`.
The original checkout at `aa6ee22854ee65f21e0aa20308774c0af4bac4c0` retains its
endpoint work and untracked files. No original-checkout files or index entries
were changed in this continuation.

- [x] Fetch and compare origin/master; remote remained at the initial SHA.
- [x] Official source acquired and archive/member identities checked.
- [x] Read-only SQLite conversion and two independent builds for 12 databases.
- [x] Reopen DuckDB read-only; actual content and duplicate multiplicities match SQLite.
- [x] Deterministic external candidate selection: 16 calibration / 64 evaluation.
- [x] Source-AST rubric: 2 basic / 4 medium / 2 advanced per evaluation database.
- [x] Candidate features: 23 JOIN and 14 nested; 61 evaluation SQL families.
- [x] Preservation inventory: 245 historical tracked files and locks unchanged.
- [x] Focused tests: 18 passed; full repository tests: 848 passed, 1654 warnings.
- [x] Compile checks and staged diff/allowlist verification.
- [x] Push Task 1 `516a02dda409a9ef7ebaf63dd47d42ba294ca4b8`; exact-SHA CI
  Python 3.11/3.12 successful: https://github.com/Whats-up-pro/VinSOC/actions/runs/37402308323.

Artifacts live under `evaluation/r2_cross_domain_v1`: manifest, registry,
source/member receipts, 12 two-build receipts, qualification/exclusion report,
external candidate inventory, execution receipt and preservation receipt.
Raw ZIP, SQLite and DuckDB stay under ignored `data/r2_cross_domain_v1/` paths.

The new source archive hash was computed from the official download, not supplied
independently by the publisher. `wta_1` is excluded for SQLite UTF-8 decoding
failure; no source bytes are repaired. `real_estate_properties` lacks eight
questions; `museum_visit` lacks the basic quota under the recorded VinSOC rubric.
Other unselected databases are recorded as excluded by hash order.

Ruling: SQL families disclose correlated questions; they do not imply that every
question is independent. Selection prefers distinct families and records repeated
families. Imposing eight independent families per database would change the
approved question-level design; no such extra quota is imposed.

Ruling: this registry gate validates SQLite/DuckDB **data content** parity.
Original/adapted gold SQL parity, final domain annotations, CTU calibration/new
cases, semantic instances and the 96-case benchmark lock remain Task 3 gates.
The candidate inventory is not an evaluation lock and cannot authorize inference.

## Task 2: generic pipeline (base `516a02d`)

- [x] Watch regression failures before implementation: typed constraints, derived
  time predicates, forged catalog metadata, safe CASE/EXISTS, COUNT(*) without
  invented columns, invalid tool arguments, SQLite connection closure and domain witnesses.
- [x] Independent multi-table AST policy; read-only DuckDB tools with timeout,
  row/payload caps, twelve executed DB calls and qualified catalog witnesses.
- [x] Typed numeric/time thresholds, LIMIT and derived expressions do not require
  catalog-value existence probes. Truncated domains cannot prove absence.
- [x] Generic linker/controller; three model turns per role. Runtime DTO has no gold.
  Live transport remains closed until the release gate; synthetic results are ineligible.
- [x] Synthetic integration trace uses actual fixture DuckDB rows, four fake
  responses and one DB tool call; zero external model calls.
- [x] Targeted tests: 64 passed. SQLite cleanup regression reproduced and fixed
  through explicit connection closure, preserving the initial negative receipt.
- [x] Final full suite: 894 passed, 1654 warnings (106.70 seconds).
- [x] Compile checks, staged diff/allowlist and preservation receipt: 245 older
  protected files and all 21 Task 1 artifact JSON files retain their exact bytes.
- [x] Commit/push `4390c47fa5dde552b2027d6f32ee46039e9d076c`; exact-SHA CI
  Python 3.11/3.12 successful: https://github.com/Whats-up-pro/VinSOC/actions/runs/37408302569.

Ruling: complete domains of at most eight values expose controller-issued
`domain_witnesses` so the linker can cite observed values without another search.
Search matches remain distinct from domain witnesses; larger/truncated domains
are not treated as complete witness lists. This is a generic bounded interface,
not a CTU mapping or a call-cap increase.

## Task 3: evaluator/gold audit checkpoint (not complete)

- [x] Reference DTO separates gold from runtime; real execution scoring preserves
  pipeline failure, Decimal values, select-list positions and duplicate multiplicities.
- [x] RED/GREEN for incorrect SQL after generation OK, SQLite quoted strings,
  declared-key GROUP BY dependencies, Boolean safety and incomplete ORDER/LIMIT ties.
- [x] Immutable initial candidate audit: 69/80 base parity, 3 mismatches, 8 blocked.
- [x] Full registered-source audit: 768 unique IDs; initial conservative policy
  704 base-parity verified, 59 blocked, 5 mismatches.
- [x] Stricter ordered-tie audit: 694 base-parity verified, 71 blocked, 3 mismatches.
  All twelve database question/difficulty quotas remain available in this pool.
- [x] Checkpoint tests: 76 targeted and 906 full tests pass (1654 existing warnings);
  compile, diff and preservation checks pass. 245 older protected files and 24
  earlier cross-domain artifact JSON files retain their exact bytes.
- [x] Checkpoint commit/push `193a04fe455e4f1ca7e4047097055f251a067b3c`; exact-SHA
  CI Python 3.11/3.12 successful: https://github.com/Whats-up-pro/VinSOC/actions/runs/37410505249.
- [ ] Materialize 24 calibration + 96 evaluation cases, annotations and oracle subset.
- [ ] Two adversarial instances per case, executable mutants and equivalent controls.
- [ ] Benchmark validation and lock. No benchmark lock has been created.

The audit command deliberately exits 2 when any audited source case is blocked or
mismatched. This is preserved negative data evidence, not a passing whole-source
gold gate. Future selection may use only qualified cases in seeded order and must
publish exclusions before inference; Task 1 candidate artifacts remain unchanged.

Ruling: add dependent GROUP BY columns only when declared primary keys are verified
non-null/unique and unconditional inner-join equalities establish the dependency.
Reject arbitrary bare group columns; do not use ANY_VALUE to force gold to execute.
Mixed numeric/text IN conversion remains unsupported: blind TRY_CAST can introduce
NULL and change NOT IN semantics. Incomplete ORDER ties are rejected even when
both engines accidentally choose the same rows. No gold SQL is rewritten to resolve
ties or rescue parity. Base-instance parity does not prove universal semantic correctness.

Case preparation continuation:
- [x] Three annotation tests and two materialization tests observed RED then GREEN.
- [x] Materialize 16 external calibration and 64 external evaluation candidates;
  replay original/adapted gold parity on all eighty, with zero errors. Runtime
  JSON contains only ID/database/question. Direct annotations remain incomplete
  for derived/pattern predicates; this is not a benchmark lock.
- [x] New CTU inventory test observed RED then GREEN: 8 calibration plus 32
  evaluation questions with 8/16/8 difficulty allocation.
- [x] Initial CTU gold audit: 39/40 execute; one listing exceeds the fixed 10,000
  evaluator-row cap. Negative receipt and original question/SQL are preserved.
- [x] Revised CTU gold audit: 40/40 execute; combined inventory is 24 calibration
  and 96 evaluation candidates. Original rejected candidate receipt is unchanged.
- [x] Checkpoint verification: 82 targeted / 912 full tests pass; compile and
  preservation checks pass (245 protected files and 28 earlier artifact JSONs).
- [x] Candidate checkpoint commit/push `62da30100cac9375691a2d82587fde48f23f7a51`;
  exact-SHA Python 3.11/3.12 CI successful:
  https://github.com/Whats-up-pro/VinSOC/actions/runs/37423537492.
- [ ] Full semantic instances and complete annotations.

Ruling: reject the unbounded UDP IP-pair listing candidate before any inference
because its gold exceeds the evaluator row cap. Replace it with a new count-of-
distinct-pairs question/ID and retain the rejected candidate in the pre-lock
exclusion evidence. No historical question/gold or locked benchmark is changed;
the evaluator/tool caps stay fixed. Both conditions will use the same final IDs.

Task 3 benchmark/semantic lock and Task 4 statistics/telemetry/release remain
pending. Paid Tasks 5/6 need expansion-specific
budget/release authorization; the old $0.75 authorization is not reused.
Model calls: **0**. New inference cost: **$0**. S1/S4 remain consumed/closed.

### Task 3 semantic continuation (not complete)

- [x] Four new annotation regressions RED/GREEN: patterns/escape, NULL/IN/BETWEEN,
  reversed and aggregate thresholds, timestamp casts/correlation, Boolean functions.
- [x] Module item metrics retain exact numerator/denominator, one consistent
  reference alternative, NA empty sets/stage absence and conditional coverage.
  Provenance verifies actual values; a self-consistent fabricated witness fails.
- [x] Controller regression RED/GREEN: completed linker output survives generator
  TOOL_LIMIT, so downstream failure does not erase module coverage.
- [x] Synthetic engine builds verified PK/FK/NULL fixtures, executes intentional
  wrong queries and equivalent controls. Syntax errors are not semantic kills.
- [x] Initial 120-case semantic audit: 90 pass, 30 blocked; receipt preserved.
  This is fixture validation, not model accuracy or an accepted benchmark gate.
- [x] SQLite LIKE ASCII/mixed-case/Unicode/escape regressions: two RED, then all
  three GREEN after the generic adapter correction.
- [x] Candidate v2 materialization: 80 external base gold parity checks pass;
  producer hashes recorded before execution, original candidates unchanged.
- [x] Semantic v2 audit stops after 42 saved records on Decimal serialization.
  RED/GREEN writer regression fixes this offline failure. Partial evidence is
  retained; no provider call or cost was involved.
- [ ] Final semantic audit, full verification, commit/push and exact-SHA CI.
- [ ] Resolve per-case semantic/dialect/order exclusions and quotas before lock.

Semantic checkpoint verification:
- [x] Audits v3/v4/v5/v6 retain respectively 105/109/119/119 PASS out of 120.
  v6 has one unresolved source ORDER tie; it is not an accepted benchmark gate.
- [x] Source-order failures are excluded only with executed fixture evidence;
  generator failures and undistinguished mutants are retained and repaired, never
  used to remove questions. All selection is before inference.
- [x] Final focused command: `python -m pytest -q tests/test_r2_cross_domain_*.py`:
  119 passed. Full `python -m pytest -q`: 949 passed, 1654 existing warnings.
- [ ] Semantic checkpoint commit/push and exact-SHA CI.

The final benchmark, runtime CTU registry, oracle subset and release remain pending.
Module metrics currently verify schema items and typed mappings, not every possible
equivalent predicate representation. No lock or new model accuracy is claimed.

Ruling: SQLite default LIKE requires ASCII-only folding, not DuckDB ILIKE/Unicode
LOWER. The new-version adapter uses explicit TRANSLATE on both operands; non-ASCII
letters and safe escape characters retain their semantics. Unproved operand types
and ASCII-letter escape characters are rejected. This changes only pre-inference
adapted candidate gold, never original source SQL or historical benchmark/gold.

Ruling: source gold with unresolved ORDER/LIMIT ties is blocked even if two engines
happen to produce the same base rows. Fixtures must preserve the ambiguity as a
data/semantic exclusion; do not add a tie breaker to the source gold to rescue it.

Ruling: a synthetic generator is not a coverage certificate. NOT_DISTINGUISHED
mutants and failed parity remain explicit failures; they cannot be counted as
semantic kills or silently omitted from the data gate.
