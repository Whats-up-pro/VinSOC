# PLAN 06 — CI Full-Suite Verification

**Save as:** `docs/superpowers/plans/2026-09-21-06-ci-full-suite.md`

## Goal

Biến GitHub Actions thành independent verification source cho toàn repository.

## Precondition

Plans 01–05 integrated into `feat/r0-closeout`.

## Input

Current stale CI:
- subset pytest only
- pull_request/manual only
- known CTI failure note

## Output

Every PR and master push runs the full repository suite on Python 3.11 and 3.12.

---

## Task 6.1 — Update triggers

Target:
```yaml
on:
  pull_request:
  push:
    branches:
      - master
  workflow_dispatch:
```

---

## Task 6.2 — Replace subset with full suite

Primary command:
```bash
python -m pytest -q
```

Remove curated test list.

Remove:
```
Document known baseline failures
```

There must be no intentionally accepted failing baseline.

---

## Task 6.3 — Keep matrix

```yaml
python-version:
  - "3.11"
  - "3.12"
```

Both install exactly the repository requirements.

---

## Task 6.4 — Optional A2 smoke artifact

After pytest, optionally execute:
```bash
python scripts/measure_tool_calling.py \
  --output tool_calling_baseline.json
```

Failure of evaluator execution may fail CI.

Metric value itself must NOT be subject to an arbitrary score threshold in R0.

Upload artifact if useful.

---

## Task 6.5 — Validate workflow

Run local YAML/syntax check if tooling exists.

Push **feature branch only** when authorized so GitHub Actions can execute.

Observe:
```
Python 3.11
Python 3.12
```

Do not claim CI green from local pytest.

---

## Output

GitHub-hosted verification for every repository test.

## Acceptance

```
[ ] full pytest in CI
[ ] 3.11 job
[ ] 3.12 job
[ ] pull_request trigger
[ ] master push trigger
[ ] stale known-failure note gone
[ ] both remote jobs pass before R0 closure
```

Commit: `ci: run full repository suite on python 3.11 and 3.12`
