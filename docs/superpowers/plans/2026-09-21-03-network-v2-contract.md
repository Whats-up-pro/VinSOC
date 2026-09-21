# PLAN 03 — Network V2 Contract & Reasoning

**Save as:** `docs/superpowers/plans/2026-09-21-03-network-v2-contract.md`

## Goal

Xóa triệt để Network V1 attack-conclusion semantics khỏi schema + reasoning, để toàn pipeline dùng Network V2 candidate evidence.

## Precondition

Plan 02 complete.

## Input

Correct runtime signals:
```
periodicity_candidates
scan_candidates
transfer_metrics
service_fanout_candidates
OBSERVED evidence
DERIVED evidence
```

Stale semantics to remove from production interpretation:
```
data_exfiltration
lateral_movement
unusual_port
normal
```

## Output

```
NetworkSkill
=
NetworkResult schema
=
Orchestrator reasoning
```

---

## Task 3.1 — Fix NetworkResult schema

### Files
- schemas/network_result.json
- tests/test_network_skill_v2.py
- tests/test_schema_contracts.py

RED:
Construct output containing:
```json
{
  "pattern": "data_exfiltration"
}
```
Expected schema rejection.

Then remove old conclusion enums.

Add schema sections for:
```
analytics.periodicity_candidates
analytics.scan_candidates
analytics.transfer_metrics
analytics.service_fanout_candidates
evidence_items
```

---

## Task 3.2 — Audit scenarios without modifying ground truth blindly

Search:
```bash
git grep -n \
  -e 'data_exfiltration' \
  -e 'lateral_movement' \
  scenarios/
```

Classify each occurrence:
```
A. input/context text describing an alert
B. old fixture output from NetworkSkill V1
C. expected conclusion
```

Only B/C are candidates for semantic normalization.

---

## Task 3.3 — Make orchestrator reason from Evidence V2

Current stale pattern parsing should no longer be primary reasoning source.

Use:
```python
network_derived = [
    ev for ev in evidence
    if ev.source_tool == "network_investigation"
    and ev.evidence_class == "DERIVED"
]
```

Reason by `ev.type`.

---

## Task 3.4 — Pin wording/risk boundaries

### Large transfer
Input: large bytes_out only
Must NOT: Confirmed exfiltration

### Periodicity
May produce: Periodic communication candidate
Must NOT: Confirmed C2

### Admin-service fanout
May produce: fanout candidate warrants investigation
Must NOT: lateral movement confirmed

### Suricata alert
Alert is OBSERVED evidence, not confirmed compromise.

---

## Task 3.5 — Update summary code

`_summarize_result()` must summarize V2 analytics without relying on removed V1 pattern names.

Example:
```
Connections: 24
Derived candidates: periodicity=1, scans=0, fanout=0
Alerts: 2
```

---

## Verification

```bash
pytest -q \
  tests/test_network_adapters.py \
  tests/test_network_query.py \
  tests/test_network_analytics.py \
  tests/test_network_skill_v2.py \
  tests/test_orchestrator_network_reasoning.py \
  tests/test_integration.py
```

Search runtime/schema:
```bash
git grep -n \
  -e '"data_exfiltration"' \
  -e '"lateral_movement"' \
  -e '"unusual_port"' \
  agent skills schemas
```

Every remaining result must have an explicit justified reason.

## Output

Network pipeline that reports evidence/candidates, not attack verdicts.

## Acceptance

```
[ ] Network schema V2
[ ] orchestrator reads DERIVED evidence
[ ] large transfer ≠ exfil verdict
[ ] fanout ≠ lateral movement verdict
[ ] periodicity ≠ confirmed C2
```

Commit: `fix(network): converge schema and reasoning on v2 evidence`
