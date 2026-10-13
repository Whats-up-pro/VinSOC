# VinSOC Live Interface Implementation Plan

> Use superpowers:executing-plans, inline on master. User forbids branches, PRs and agents.

**Goal:** Start and inspect an actual guarded pipeline from Streamlit.

**Architecture:** Streamlit dispatches/polls a Linux Actions workflow. The workflow
reuses run_preflight/run_live and an append-only remote allocation registry.

**Spec:** docs/superpowers/specs/2026-10-14-vinsoc-live-interface-design.md

**Tech stack:** Python 3.11/3.12, Streamlit 1.65.0, gh, GitHub Actions, existing SDK/worker.

## Global constraints

- Original cumulative cap $3; prior known $0.08155920; unknown blocks transmission.
- No changes to protected benchmarks/gold/prompts/scorers/history/two ZIPs.
- Model SQL remains in the Linux isolated worker.
- No fabricated records, forecasts promoted to usage, or automatic human review.
- Calibration/evaluation/pipeline completion requires real artifacts.

## Review focus

Changed question after preflight must invalidate live start. A double click or
restart must not dispatch a second paid run. Open remote allocation claims must
block spend. A failed/cancelled job must retain its partial result. A new run must
not show an older successful record as its own output.

## Task 1: request and allocation protocol

Files: scripts/vinsoc_live_protocol.py, tests/test_vinsoc_live_protocol.py.

- [ ] RED: test exact selection, live consent, scope/window identities, budget
  reconciliation, orphan claims, duplicate responses, unknown costs.
- [ ] Implement pure request validation and reconciliation from real saved costs.
- [ ] GREEN, compile, preservation; bind new source files to runtime identity.

## Task 2: guarded cloud runner

Files: scripts/run_query_live_ui_cloud.py, .github/workflows/query-live-ui.yml,
tests/test_query_live_ui_cloud.py.

- [ ] RED: absent/altered request fails before SDK; preflight is zero-call;
  unknown allocation blocks; workflow binds exact SHA and preserves journals.
- [ ] Reuse preflight/live and public investigate_query; publish durable events.
- [ ] GREEN; targeted/full/required checks; commit, push, exact-SHA CI.

## Task 3: UI controller and presentation

Files: scripts/vinsoc_live_ui.py, scripts/vinsoc_demo_app.py,
tests/test_vinsoc_live_ui.py, tests/test_vinsoc_demo_ui.py.

- [ ] RED: transitions, altered request, repeat dispatch, missing/partial output,
  browser/app navigation without model client creation.
- [ ] Implement scope/catalog form, preflight/start/poll/import and eight-stage
  actual result view; preserve human-review gates.
- [ ] GREEN; browser QA; docs and receipts; commit/push/CI exact SHA.

## Task 4: real acceptance and handoff

- [ ] Fetch current official pricing; reconcile prior scope state and cap.
- [ ] From browser UI, run preflight and then one fresh live demo under $3.
- [ ] Preserve real receipt, outputs, IDs, usage/cost and failures; no rescue retry.
- [ ] Document commands and all gates, including formal suite blockers.
- [ ] Commit public handoff, push and check final exact-SHA CI.

## Ledger

2026-10-14: user explicitly requests implementation of the previously described
missing live functionality. Existing full authority and master-only instructions
authorize proceeding inline. UI budget remains $3; formal scopes are exposed but
their existing gates are enforced, rather than claiming coverage from sample runs.
