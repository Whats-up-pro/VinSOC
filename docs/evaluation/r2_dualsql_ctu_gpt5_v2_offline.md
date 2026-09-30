# CTU GPT-5 Mini DualSQL-Lite v2: offline gate

This is a new development series beside the immutable v1 comparison. No v1
artifact, lock, benchmark case, gold SQL, comparator, scorer, or S5/S7 snapshot
was changed. The v1 E0–E3 result remains 0/8 in every condition and is not
rerun.

## Review rulings

- The paid v1 workflow used `runner.py → run_role()`. Its older
  `DualSQLCaseRunner`/`validate_linked_schema` path remains in the historical
  package but is not the v2 controller. V2 has one validated linker path.
- The five nonempty value-search calls in v1 were not all false positives.
  `Normal` searched in `label` returned stored Normal labels. The 27 calls are
  replayed as diagnostic evidence, without requiring every old miss to turn
  into a match; wrong-column lookups should stay unresolved.
- Source aliases come from the pinned source manifest's `source_name` and
  `dataset_id`, checked against the snapshot catalog. This replaces numeric
  token guessing and supplies provenance for `scenario 5 → ctu13_s5`.
- A grounded value can still express the wrong intent. Case 002's
  `line:10007` really appeared among the linker observations. V2 checks the
  selected source column against source references before generator dispatch.
- SQL literal checks are diagnostic only. They do not alter the locked scorer
  and report `unknown` where the catalog is capped rather than treating an
  absent catalog entry as proof the snapshot lacks that value.

## Gate and evidence

The offline gate validates the locked dev snapshot and all eight case identities,
then resolves the seven explicit scenario references using source metadata. Case
008 correctly has no concrete source reference. Two negative controls reject a
single-digit high-cardinality row-ID lookup and return an unresolved domain for
an unknown source. The gate also records replay results for all 27 v1
`value_search` calls.

| Check | Observed |
| --- | --- |
| Locked logical snapshot SHA-256 | `42c8e0a62441295cc5d95329a65dc22409c37de5b26a1e37dd56fbf0164a758c` |
| Dev split SHA-256 | `96362f80e9e6bf01f18f1023c75066c553ddd9c105d2545f98af808d24f736fb` |
| Explicit source references | 7/7 resolved |
| No-reference case | `ctu_sql_008` |
| Negative controls | 2/2 passed |
| Historical calls replayed | 27 |
| Model calls / API cost | 0 / $0 |

Full case and replay detail: [offline gate JSON](../../results/evaluation_v1/ctu_network_public/dualsql_lite_ctu_gpt5_v2/offline_gate_2026-09-30.json).
This gate proves retrieval behavior only. The v2 model condition, E0′ baseline,
selection and frozen evaluation remain separate gates.
