# Cross-domain Text-to-SQL: source and registry

This namespace implements the offline source/registry stage of the approved
`r2_cross_domain_v1` protocol. It contains no model client and no live evaluation
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
