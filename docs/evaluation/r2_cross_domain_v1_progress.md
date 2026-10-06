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
- [ ] Push and exact-SHA CI Python 3.11/3.12. Check completion against Actions.

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

Task 2 generic tools/controller, Task 3 benchmark/gold/semantic lock, and Task 4
statistics/telemetry/release are pending. Paid Tasks 5/6 need expansion-specific
budget/release authorization; the old $0.75 authorization is not reused.
Model calls: **0**. New inference cost: **$0**. S1/S4 remain consumed/closed.
