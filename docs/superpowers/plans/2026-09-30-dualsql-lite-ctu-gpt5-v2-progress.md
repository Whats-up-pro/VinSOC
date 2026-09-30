# DualSQL CTU GPT-5 v2 execution ledger

Original execution started on master at
`f16d412c9172d764d45c20f31d852dc2cda03f94`, equal to origin/master after fetch.
The offline checkpoint was committed and pushed as
`92e20d589e00ace33f896b4d24279181c51230a8`.
On resumption, `git fetch origin master` confirmed HEAD and origin/master at
`cf46fb4abec295e43a31e9c026e7908e214fe43b`. The only tracked working change at
resumption was this executor's unfinished runner tests, which were removed
after the newer implementation and frozen attempts were discovered.

- [x] Offline checkpoint: seven source references resolved, case 008 recognized
  as no-reference, two negatives passed, 27 old calls replayed; $0 API spend.
  `python -m pytest -q` returned 614 passed and exact checkpoint CI passed
  Python 3.11/3.12 in run 36667345032.
- [x] Reproduce newer CI failure: missing `V2DatabaseTools` import at cf46fb4.
  CI run 36680054156 failed collection; d21a030 CI run 36669985928 also failed.
- [x] Restore the offline adapter API from 92e20d5 in `source_tools.py` while
  preserving the historical `CTUDatabaseTools` implementation.
- [x] Reproduce local-snapshot dependence: from an empty temporary cwd the
  newer test module had 4 passes and 8 fixture errors. After using synthetic
  DuckDB fixtures, the same invocation returned 12 passed.
- [x] Freeze-consumption guard RED→GREEN: both frozen entrypoints now block
  before constructing an API client, including a changed output directory;
  missing registry fails closed. Focused command
  `python -m pytest tests/test_frozen_reentry_gate.py tests/test_dualsql_ctu_gpt5_v2.py tests/test_dualsql_lite_ctu_gpt5_v2.py -q`
  returned 27 passed.
- [x] Full verification:
  `python -m pytest -q --disable-warnings` returned **629 passed, 1612 warnings**
  in 147.48 seconds. The warnings are pre-existing datetime deprecations.
  `python -m py_compile` on all changed Python files and `git diff --check`
  returned exit 0.
- [x] Verify all 18 frozen Git blob artifact digests at cf46fb4 and record
  Windows checkout digests separately in `CONSUMED.lock`; CRLF normalization
  explains the byte differences. Offline adapter bytes match 92e20d5.
- [x] Fresh reviewer checked import compatibility and pre-client guards. Its
  important documentation finding was fixed by withdrawing improvement and
  future-tuning claims from the exploratory frozen summary.
- [x] Recovery CI Python 3.11/3.12 passed on implementation SHA
  `c7f6d5bef63aeb8931c7b86472c9dd72939100f9` in
  [run 36683245016](https://github.com/Whats-up-pro/VinSOC/actions/runs/36683245016).
- [ ] E0′ development run, representative v2 development run and winner lock.
  **Blocked:** v2 was changed and frozen consumed before this sequence.
- [ ] Protocol-eligible frozen result and subsequent E2E demonstration.
  **Blocked:** preserve the consumed holdout; no rerun or silent substitution.

Ruling: preserve the newer paid-attempt code and evidence; restore the broken
offline API in a separate source-metadata adapter. This repair changes no
evaluated model behavior and does not certify the historical frozen attempts.

Ruling: the failed pre-run gates cannot be repaired retrospectively with new
locks or CI. The consumed holdout remains closed. Recorded cost is a lower
bound of $0.06508150; intermediate usage and possible SDK retries are unknown.
This recovery made zero API calls.

Eligibility details and immutable digests:
[protocol audit](../../evaluation/ctu_frozen_protocol_audit_2026-09-30.md).
