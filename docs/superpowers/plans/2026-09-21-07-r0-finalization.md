# PLAN 07 — R0 Baseline Reconciliation & Final Verification

**Save as:** `docs/superpowers/plans/2026-09-21-07-r0-finalization.md`

## Goal

Freeze one trustworthy R0 engineering baseline after all fixes, reconcile documentation, independently review it, and decide whether R1 may start.

## Preconditions

Plans 01–06 all integrated and individually reviewed.

## Input

Final `feat/r0-closeout` HEAD.

## Output

One evidence-backed R0 baseline with:
```
current SHA
full pytest status
CI status
A2 Tool Calling regression metrics
architecture documentation
independent review verdict
```

---

## Task 7.1 — Fresh local verification

Record:
```bash
git rev-parse HEAD
git status --short
python --version
python -m pytest -q
```

`git status` must be clean before baseline recording.

---

## Task 7.2 — Re-run A2 integration metric

```bash
python scripts/measure_tool_calling.py \
  --output results/r0-final-tool-calling.json
```

Record:
```
scenario count
actual calls
TP
FP
FN
P
R
F1
ToolSetEM
SequenceEM
execution success
```

Label: `A2 deterministic MockProvider integration regression`
NOT: `LLM tool-calling accuracy`

---

## Task 7.3 — Reconcile baseline docs

Update:
- docs/dev/current_baseline.md
- docs/evaluation_results_preliminary.md
- docs/evaluation.md
- README.md
- docs/dev/r0_convergence_inventory.md

### current_baseline.md

Replace old SHA/result with fresh final HEAD.

### r0_convergence_inventory.md

Change to:
```
Status: Completed
```
with actual final verification.

### README.md

Must state:
```
Evidence V2
Network V2
CTI provider runtime
DuckDB Option A
HITL
```
and that official frozen benchmark is still future work.

---

## Task 7.4 — Semantic grep audit

```bash
git grep -n \
  -e 'Call this FIRST in most investigations' \
  -e 'Call this AFTER CTI enrichment'
```
Expected: none

```bash
git grep -n \
  -e '"data_exfiltration"' \
  -e '"lateral_movement"' \
  -e '"unusual_port"' \
  agent skills schemas
```

Every hit must be classified. Forbidden: production conclusion logic.

---

## Task 7.5 — Independent whole-branch review

Fresh reviewer receives:
```
Base SHA: 4a8261f
Head SHA: final closeout HEAD
Plans 01–07
full diff
verification results
```

Checks:
```
CTI runtime provider wiring
fail-closed semantics
Evidence V2 schema/runtime consistency
Network V2 semantics
routing correctness
DuckDB read-only boundary
CI coverage
repo hygiene
docs truthfulness
```

Output:
```
SPEC COMPLIANCE: PASS / FAIL
CODE QUALITY: PASS / FAIL
```

---

## Task 7.6 — Remote CI verification

Require GitHub Actions:
```
Python 3.11 → PASS
Python 3.12 → PASS
```

---

## Task 7.7 — R0 closeout decision

R0 can close only if ALL:
```
[ ] fresh full local suite = 0 failures
[ ] remote CI 3.11 pass
[ ] remote CI 3.12 pass

[ ] CTI providers reachable
[ ] CTI fail-closed preserved

[ ] Evidence runtime/schema aligned
[ ] Network runtime/schema/reasoning aligned

[ ] routing contract aligned
[ ] hostname CTI false positives addressed

[ ] stale agents absent

[ ] baseline docs reference final SHA
[ ] A2 metrics freshly regenerated

[ ] final independent review PASS
```

Only then:
```
R0 → CLOSED
R1 → UNBLOCKED
```
