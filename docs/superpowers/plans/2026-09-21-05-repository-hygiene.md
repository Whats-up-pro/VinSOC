# PLAN 05 — Repository Hygiene

**Save as:** `docs/superpowers/plans/2026-09-21-05-repository-hygiene.md`

## Goal

Remove repository artifacts known to contradict current architecture, without touching product runtime.

## Precondition

None. Can run in parallel with Plans 01/02.

## Input

Known stale files:
```
.claude/agents/INDEX.md
.claude/agents/soc-architect.md
.claude/agents/soc-security-reviewer.md
.claude/agents/soc-skill-dev.md
.claude/agents/soc-test-engineer.md
```

Inventory itself states: `DO NOT RESTORE`

## Output

Repository contains no stale agent instructions that can mislead local coding agents.

---

## Task 5.1 — Capture evidence before deletion

Read each file.

Confirm stale claims against current master.

Record reasons in commit body.

---

## Task 5.2 — Delete stale files

```bash
git rm .claude/agents/INDEX.md
git rm .claude/agents/soc-architect.md
git rm .claude/agents/soc-security-reviewer.md
git rm .claude/agents/soc-skill-dev.md
git rm .claude/agents/soc-test-engineer.md
```

If directory becomes empty, remove it.

---

## Task 5.3 — Verify

```bash
git ls-files '.claude/agents/*'
```

Expected: no output

Search docs for claims saying these agents are active.

Remove references only if they incorrectly claim runtime/development authority.

---

## Test requirement

No product behavior changes, but still run:
```bash
pytest -q
```

to prove deletion had no accidental package/tool coupling.

## Output

Clean development metadata.

## Acceptance

```
[ ] .claude/agents absent
[ ] no product code changed
[ ] full suite unaffected
```

Commit: `chore: remove stale claude agent definitions`
