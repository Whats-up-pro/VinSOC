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

## Remediation offline Tasks 1-7

Initial SHA `abfac96967dabc9452b5422f7d86e7d0a579d126`, master = origin sau fetch/ff, tracked clean. Giữ recovery adapter/consumption lock/entrypoint closure/synthetic fixtures. Các thay đổi bổ sung và command/output đầy đủ trong [remediation status](../../evaluation/r2_remediation_status.md).

- [x] Evidence inventory: 43 file trước/sau không đổi; 18 historical Git blob digests đã đối chiếu. E0/v1 selection không đổi.
- [x] Auditor chỉ đọc JSON: E0 EX 0/8, E3 EX 2/8, execution success 3/8 theo flags cũ; 2 EXEC_ERROR, 3 EMPTY_SQL. Syntax validity đúng nghĩa/cost/provenance chưa đầy đủ. Append hai receipt mới, không overwrite.
- [x] Unified V2 tools và gate snapshot S5/S7: 7 references, 008 no-reference, 2 negatives, 27 replay calls; exit 0.
- [x] Một controller actual path, linker fail-closed, response trước parse, giữ usage trên mọi return, cap 5 turns/5 DB calls, no-tool bỏ key tools.
- [x] Actual locked scorer/safety integration; synthetic fixtures kiểm syntax/schema/empty/unsafe/mismatch/ordered/duplicate. Không sửa scorer, gold hoặc prompt.
- [x] Exclusive partial/final fake reports có current identity và cost completeness; `synthetic_provider`, không official eligibility; live client boundary closed.
- [x] Full suite sau fresh-review fix: `python -m pytest -q` → 681 passed, 1612 warnings, 191.38s. Targeted Tasks 1-6 184 passed; review fix targeted 72 passed. Compileall/py_compile/diff exit 0. Implementation SHA `dcf9f2fe3ce619808a97208679f6febebdbfb83e`, [CI 36694506063](https://github.com/Whats-up-pro/VinSOC/actions/runs/36694506063) cả Python 3.11/3.12 success. Evidence-commit CI chờ trước final response.

Ruling: remote `4886b57` thêm live Tasks 8-10 trong khi thực hiện, được giữ qua merge `ca9d78d`. Chỉ thị trực tiếp hiện tại yêu cầu zero API, không dispatch và STOP FOR HUMAN REVIEW, nên chưa thực thi continuation mới. Chi phí remediation $0; frozen vẫn consumed/closed. Không tạo provenance hồi tố, không gọi R1 hoặc E2E.

## Continuation live Tasks 8-10 — phê duyệt trực tiếp tiếp theo

Chỉ thị live mới thay điểm dừng offline ở checkpoint trên, không mở frozen. Initial `0973d5a6`, implementation `90acf451c264d98c3cc35662670b3b772366136a`; [exact-SHA CI](https://github.com/Whats-up-pro/VinSOC/actions/runs/36700628921) cả Python 3.11/3.12 success, 704 tests/job. Adapter/controller/scorer/prompts/gold/snapshot giữ nguyên; thêm gated live boundary và pin SDK/transport đã test.

- [x] Task 8 focused tests, full 704 passed, compile/diff pass và exact-SHA CI xanh; preflight source/identity/account/pricing/budget PASS.
- [x] Task 9 đúng một smoke E3 PASS pipeline rồi một suite E3 đủ 8 cases cùng SHA, không commit/retry/prompt change giữa hai lượt.
- [x] Audit current evidence: EX 1/8, syntax 4/8, execution success 3/8, safety 1/8; 41 attempted/41 responses, cost $0.02185315 complete; 45 historical hashes không đổi.
- [ ] Task 10 evidence commit/push và CI của evidence SHA (checkpoint ghi sau verification).

[Live report và artifact links](../../evaluation/r2_remediation_live_results.md). Frozen S1/S4 vẫn consumed/closed; không R1/new experiments/SOC demo. STOP FOR HUMAN REVIEW sau nghiệm thu evidence CI.

Fresh reviewer phát hiện field thừa trong table handoff có thể lọt sang generator; regression RED 1 failed, đã reject keys ngoài table/columns và GREEN/full pass. Không có deferred minor. Final SHA và exact evidence-commit CI được báo ở thông báo nghiệm thu.
