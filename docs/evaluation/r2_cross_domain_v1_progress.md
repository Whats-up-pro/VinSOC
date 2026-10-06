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
- [ ] Commit/push and exact-SHA CI Python 3.11/3.12.

Ruling: complete domains of at most eight values expose controller-issued
`domain_witnesses` so the linker can cite observed values without another search.
Search matches remain distinct from domain witnesses; larger/truncated domains
are not treated as complete witness lists. This is a generic bounded interface,
not a CTU mapping or a call-cap increase.

Task 3 benchmark/gold/semantic lock and Task 4 statistics/telemetry/release remain
pending. Paid Tasks 5/6 need expansion-specific
budget/release authorization; the old $0.75 authorization is not reused.
Model calls: **0**. New inference cost: **$0**. S1/S4 remain consumed/closed.
