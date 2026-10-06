# Cross-domain Text-to-SQL: source and registry

This namespace implements the offline source/registry and generic pipeline stages of the approved
`r2_cross_domain_v1` protocol. It contains no external model client and no live evaluation
results. CTU Phase 2 remains a separate historical benchmark (verified dev EX 7/8).

The manifest pins the official Spider 1.0 archive acquired on 2026-10-05. Its
SHA-256 is an identity computed from downloaded bytes; it is **not** a checksum
independently published by the Spider authors. Every parsed archive member is
checked against those bytes before SQLite is opened read-only.

Run from the repository root:

```powershell
python -m scripts.prepare_r2_cross_domain --source spider-dev --output data/r2_cross_domain_v1 --metadata evaluation/r2_cross_domain_v1
python -m pytest -q tests/test_r2_cross_domain_data.py
```

If the archive is absent, the prepare command downloads only the URL in the
manifest and validates its hash before extracting individual members. Existing
source files with mismatched hashes are preserved and rejected. Each invocation
builds a fresh snapshot namespace; existing DuckDB files are never overwritten.
Raw ZIP/SQLite/DuckDB files are ignored and must remain outside Git.

The registry selects 12 multi-table databases with foreign-key metadata and at
least eight original development questions and sufficient source-AST difficulty
buckets, in SHA-256 order using seed
20261005. The first four are calibration databases and the remaining eight are
evaluation candidates. `selection_exclusions.json` records exclusions before
inference. `external_candidate_inventory.json` contains 16 calibration and 64
evaluation question candidates with source-AST difficulty/features and families.
The VinSOC rubric is saved in `source_qualification.json`; it is not official
Spider hardness. Family dependence is recorded, including when the same family
occurs in multiple selected questions. Exact normalized-question/AST duplicates
have the same case ID. Task 3 must verify gold parity, final annotations, domain
quotas and semantic coverage before benchmark locking. No selected case may be
excluded based on future model output.

Two independent builds are reopened read-only. Typed row multisets, including
NULL and duplicate multiplicities, must match SQLite content and each other.
Conversion that loses values is rejected. Logical identity includes schema,
types, declared PK/FK metadata and rows. Binary hashes identify each physical
build. Declared keys are metadata; they are not a claim of verified uniqueness
or referential integrity. Gold SQL dialect parity remains a separate gate.

Attribution: [Spider project](https://yale-lily.github.io/spider),
[official repository](https://github.com/taoyds/spider), Yu et al.,
*Spider: A Large-Scale Human-Labeled Dataset for Complex and Cross-Domain
Semantic Parsing and Text-to-SQL Task* (EMNLP 2018).
Source data and adapted database metadata follow
[CC BY-SA 4.0](https://creativecommons.org/licenses/by-sa/4.0/).
This subset will not be presented as an official Spider score or an independent
model-pretraining holdout.

## Generic pipeline (offline)

`DatabaseTools` executes bounded read-only queries on a verified multi-table
catalog. Its SQLGlot AST policy is independent of the archived single-table
policy. Tool witnesses identify database, snapshot, table, column, type and value;
the controller validates those identities before accepting linked values.
Numeric/time thresholds and LIMIT quantities are typed constraints. Small complete
string domains expose citable witnesses; truncated searches are never closed domains.

`run_case` accepts only the three-field `RuntimeCase` and synthetic transport
until the release adapter is implemented and authorized. E0 has one decision;
E3 has at most three linker and three generator requests, with twelve DB calls.
Responses are journaled before parsing. Generation `OK` is not execution accuracy.
The 32 KiB request safety cap is not a proof of the proposed 6,144-token billing bound.

```powershell
python -m pytest -q tests/test_r2_cross_domain_pipeline.py tests/test_r2_cross_domain_data.py tests/test_r2_cross_domain_selection.py
```

`offline_task2/integration_trace.json` is a scripted fake-client trace over a
synthetic DuckDB fixture, not a model benchmark. It preserves its trace-time
fixture code hash; the execution receipt records the final tested source bundle
separately. Gold SQL parity, 96-case locking, semantic stress tests, module metrics
and any expansion-specific paid authorization remain later gates.

## Gold audit checkpoint (Task 3 in progress)

```powershell
python -m scripts.audit_r2_cross_domain_gold --all-registered --output evaluation/r2_cross_domain_v1/offline_task3/NEW_AUDIT.json
```

Choose a new output filename: receipts are never overwritten. Exit 2 reports that
some source questions are blocked or mismatched; inspect the per-case records.
It does not mean those questions were run on a model. The initial selected-candidate
audit and subsequent all-registered audits are retained as separate policy-stage
evidence. The strict audit checks 768 unique source IDs; 694 have verified base
parity, 71 are blocked, three mismatch, and all twelve DB quotas remain available.
This is source qualification, not 694 correct model predictions.

The adapter preserves original SQL in the receipt, translates SQLite double-quoted
strings, and extends GROUP BY only through verified declared-key dependencies.
Unproved bare group columns, ambiguous ordering/ties and unproved mixed numeric/text
IN conversions are rejected. Source questions rejected before inference must stay
in the published exclusion inventory. Neither archived candidate bytes nor source
gold are edited to fix a mismatch. Base parity is separate from the pending
per-case adversarial semantic checks and the pending 96-case benchmark lock.

The candidate materializer is implemented:

```powershell
python -m scripts.prepare_r2_cross_domain_cases --qualification evaluation/r2_cross_domain_v1/offline_task3/registered_gold_qualification_strict.json --output evaluation/r2_cross_domain_v1/offline_task3/NEW_CANDIDATES
python -m scripts.audit_r2_cross_domain_ctu_cases --snapshot data/ctu_network_public/snapshots/ctu_dev.duckdb --output evaluation/r2_cross_domain_v1/offline_task3/NEW_CTU_AUDIT.json
```

The saved candidate receipts contain 80 verified external gold queries and 40
new CTU queries (24 calibration / 96 evaluation in total). The CTU initial
39/40 negative audit is preserved beside the revised 40/40 audit. These are
offline gold executions, not model scores. Complete predicate annotations,
two adversarial instances per case, the oracle subset and benchmark lock remain
pending. The external materialization did not record its producer source hash;
the checkpoint receipt records tested source hashes without assigning retrospective
producer provenance.

## Verified benchmark (Task 3)

The append-only qualification/audit versions retain all negative findings. The
final semantic audit `offline_task3/semantic_candidates_v7/receipt.json` verifies
120/120 calibration/evaluation candidates with two constraint-checked synthetic
instances and executed mutants/equivalent controls. This is **not model accuracy**.
`benchmarks/semantic_coverage.json` lists killed families per case; generated
nonexecutable/undistinguished mutants remain visible in the underlying audit and
are not counted as kills. Two finite fixtures cannot prove correctness on every DB.

`benchmark.lock.json` locks 24 calibration and 96 evaluation questions, including
64 external evaluation questions across eight databases/seven domains and 32
in-domain CTU questions. Evaluation difficulty is 24 basic / 48 medium / 24 advanced.
There are 93 evaluation families (61 external); correlated families remain disclosed.
The twelve oracle IDs are a subset of the 96, not twelve extra primary observations.
Eight historical CTU anchors are replayed separately; their saved Phase2 predictions
remain 7/8, including case006 TOOL_LIMIT. Nothing is inferred from new model output.

`runtime_registry.json` preserves the original twelve-database registry and adds a
read-only adapter for the verified CTU bytes. Its generic logical hash uses a new
typed-row/schema policy and is explicitly separate from the historical CTU logical
hash `42c8e0a62441295cc5d95329a65dc22409c37de5b26a1e37dd56fbf0164a758c`.
No CTU data was rebuilt or old lock rewritten.

```powershell
python -m scripts.validate_r2_cross_domain --registry evaluation/r2_cross_domain_v1/runtime_registry.json --benchmarks evaluation/r2_cross_domain_v1/benchmarks --lock evaluation/r2_cross_domain_v1/benchmark.lock.json
python -m pytest -q (Get-ChildItem tests -Filter 'test_r2_cross_domain_*.py' | ForEach-Object FullName)
```

The validator checks source archive/members, snapshot/catalog hashes, reference
and runtime identity, oracle membership, semantic audit bytes and all 120 base
gold queries. Runtime files contain only case ID/database ID/question. Module
annotations describe typed mappings and parsed structure, not a unique acceptable
SQL AST. End-to-end scoring uses actual query results and preserves duplicates,
ordering, NULL and locked numeric tolerance. Benchmark locking grants **no paid
or frozen authorization**. Live release/preflight is Task 4; expansion funding
and model availability remain separate gates.
