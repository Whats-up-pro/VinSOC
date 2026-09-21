# PLAN 02 — Evidence V2 Schema Contract

**Save as:** `docs/superpowers/plans/2026-09-21-02-evidence-v2-schema.md`

## Goal

Làm cho JSON Schema của `InvestigationCase` enforce chính xác Evidence V2 mà runtime đã sử dụng.

## Precondition

Evidence runtime fields already exist in:
- agent/evidence.py

## Input

Runtime model:
```
evidence_class
source_name
observed_at
confidence
provenance
references
related_evidence_ids
```

Current stale schema:
- schemas/investigation_case.json

## Output

A generated `InvestigationCase` cannot validate while silently dropping Evidence V2 semantics.

---

## Task 2.1 — Pin schema failure first

Create/update:
- tests/test_schema_contracts.py

Test invalid evidence:
```python
evidence = {
    "evidence_id": "EV1",
    "source_tool": "network_investigation",
    ...
    # evidence_class intentionally absent
}
```

Expected: schema validation FAIL

Watch RED before schema edit.

---

## Task 2.2 — Extend Evidence schema

Add:
```
evidence_class:
  OBSERVED | DERIVED | EXTERNAL_INTEL

source_name:
  string | null

observed_at:
  date-time | null

confidence:
  low | medium | high | null

provenance:
  object

references:
  array[string]

related_evidence_ids:
  array[string]
```

Required for newly generated records:
```
evidence_class
provenance
references
related_evidence_ids
```

---

## Task 2.3 — Lineage semantic validation

JSON Schema cannot guarantee that `related_evidence_ids[]` actually exist.

Pin this via traceability code/test.

Test:
```
EV2.related_evidence_ids = ["MISSING_EV"]
```
Expected: traceability violation

Valid:
```
EV2 → EV1
```
Expected: traceability valid

---

## Task 2.4 — Validate orchestrator-generated case

Run a real orchestrator fixture producing:
```
OBSERVED
DERIVED
EXTERNAL_INTEL
```

Validate entire case with `investigation_case.json`.

---

## Verification

```bash
pytest -q \
  tests/test_evidence_v2.py \
  tests/test_schema_contracts.py \
  tests/test_traceability.py \
  tests/test_integration.py
```

Then full suite.

## Output

```
Runtime Evidence V2
=
JSON Schema Evidence V2
=
traceability validator
```

## Acceptance

```
[ ] missing evidence_class rejected
[ ] valid OBSERVED accepted
[ ] valid DERIVED accepted
[ ] valid EXTERNAL_INTEL accepted
[ ] dangling related_evidence_ids caught
[ ] orchestrator case validates
```

Commit: `feat(schema): enforce evidence v2 investigation contract`
