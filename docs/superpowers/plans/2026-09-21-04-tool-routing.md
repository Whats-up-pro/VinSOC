# PLAN 04 — Tool Routing & MockProvider Contract

**Save as:** `docs/superpowers/plans/2026-09-21-04-tool-routing.md`

## Goal

Xóa CTI-first bias khỏi tool contracts/system prompt và làm MockProvider phản ánh đúng routing semantics.

## Precondition

Plans 01 and 03 complete.

## Input

Supported pivots:
```
CTI:
ipv4
domain
hash
url

Endpoint:
hostname
endpoint/process context

Network:
ipv4/domain + network evidence need
```

## Output

Model receives neutral tool descriptions and can select tools based on evidence need rather than hard-coded CTI ordering.

---

## Task 4.1 — Fix tool descriptions

File: agent/tools.py

Remove:
```
Call this FIRST in most investigations
Call this AFTER CTI enrichment
```

CTI description explicitly says:
```
Do not call directly for endpoint hostname.
```

Network description uses:
```
flow evidence
IDS alerts
periodicity candidates
scan candidates
transfer metrics
fanout candidates
```
not `data exfiltration`.

---

## Task 4.2 — Fix system prompt

File: agent/orchestrator.py

Remove universal sequence:
```
CTI → Network → Endpoint
```
from evidence-driven mode.

Keep that ordering only inside explicitly named **fixed baseline pipeline**, where deterministic baseline behavior is intentional.

Decision guidance:
```
hostname/process/EDR → endpoint first
hash/url → CTI
network IP/domain alert → network and/or CTI
```

---

## Task 4.3 — Prevent pointless retry

If CTI responds:
```
No source configured
```
agent may record limitation but should not repeatedly retry the same call without new evidence.

Pin regression test.

---

## Task 4.4 — Align MockProvider

File: agent/provider.py

MockProvider must route based on:
```
indicator type
context
current evidence/tool history
```

Never:
```python
if case_id == ...
```
and never first-call-CTI unconditionally.

---

## Required routing tests

```
hostname → endpoint
hash → CTI
URL → CTI
IP network alert → network is valid initial call
endpoint context → endpoint
```

For case_012–014:
```
no unnecessary CTI call
```

Do NOT edit `expected_tools` to make test pass.

---

## Task 4.5 — Re-run legacy A2 baseline

```bash
python scripts/measure_tool_calling.py \
  --output results/r0-routing-baseline.json
```

Record:
```
TP
FP
FN
Precision
Recall
F1
ToolSetEM
SequenceEM
execution failures
```

---

## Verification

```bash
pytest -q \
  tests/test_benchmark.py \
  tests/test_integration.py \
  tests/test_cti_semantics.py
```

Search:
```bash
git grep -n \
  -e 'Call this FIRST in most investigations' \
  -e 'Call this AFTER CTI enrichment'
```
Expected: no production matches.

## Output

Routing contract suitable for future A1 Tool Calling benchmark.

## Acceptance

```
[ ] hostname endpoint-first
[ ] CTI-first hard bias removed
[ ] network usable without prerequisite CTI
[ ] repeated failed CTI avoided
[ ] MockProvider uses semantic routing
```

Commit: `fix(routing): align tool selection with evidence contracts`
