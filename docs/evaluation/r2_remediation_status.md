# R2 remediation offline — 2026-09-30

## Phạm vi và checkout

Initial SHA: `abfac96967dabc9452b5422f7d86e7d0a579d126`, bằng `origin/master` sau fetch/fast-forward; tracked working tree sạch. Danh sách untracked ban đầu được giữ nguyên, `.env` không được mở hoặc stage. Làm trực tiếp master, không reset/clean/branch/PR.

Scope của chỉ thị trực tiếp: Tasks 1-7 offline, sau nghiệm thu **STOP FOR HUMAN REVIEW**. Remote thêm live Tasks 8-10 ở `4886b57` trong lúc thực hiện. Đã giữ thay đổi đó qua merge `ca9d78d`; không dùng thay đổi file để mở API trong phiên này.

Final SHA và exact-SHA CI URL được ghi trong thông báo nghiệm thu sau push; không tự ghi SHA tương lai vào artifact. CI recovery `c7f6d5b` đã kiểm trực tiếp: [36683245016](https://github.com/Whats-up-pro/VinSOC/actions/runs/36683245016), cả Python 3.11/3.12 success.

## Recovery được giữ và remediation bổ sung

| Task | Thực hiện / evidence |
|---|---|
| 1 | Giữ consumed lock và pre-client closure; thêm category `HISTORICAL_ENTRYPOINT_DISABLED`, tests chặn provider/DB/output. Commit `8c40f12`. |
| 2 | Auditor chỉ đọc flags JSON, không replay SQL; sửa report, append receipt. Commit `aec370c`. |
| 3 | Giữ source-metadata adapter recovery, baseline bytes khớp `92e20d5`; migrate callers sang `V2DatabaseTools`, chặn unknown/ambiguous source và fake evidence. Commit `0246694`. |
| 4 | Actual runner dùng một `validate_link` gate; linker failure không gọi generator; giữ response trước parse, cap 5 turns/5 DB calls. Bỏ column-count heuristic. Commit `95279d8`. |
| 5 | Score final SQL qua locked `evaluate_sql_case` và snapshot-only boundary; gold chỉ dùng sau inference. Commit `374caa4`. |
| 6 | Exclusive output/partial JSONL, current identity, raw flags/counts/rates, cost unknown và eligibility reasons. Fake clients luôn `official_eligible=false`. Commit `5995b87`, được tích hợp vào merge `ca9d78d`. |
| 7 | Đồng bộ README/status, full verification, fresh review và exact-SHA CI. Xem kết quả command bên dưới và thông báo nghiệm thu. |

Legacy tool implementation được giữ để truy lịch sử, không còn là interface cho runner hiện tại; raw DuckDB exception serialization đã bỏ. Prompt bytes, benchmark/gold, comparator/core scorer, snapshot và v1 selection lock không đổi. Identity mới là `dualsql_lite_ctu_gpt5_v2_remediation_v1`; không gán vào run cũ.

## Commands đã chạy

| Verification | Kết quả thực tế |
|---|---|
| Task 1 historical + reentry tests | RED 2 failures vì thiếu category; GREEN 5 passed |
| Task 2 auditor tests + CLI | RED 4 failures vì thiếu module; GREEN 4 passed; CLI exit 0 |
| Task 3 focused tools/CTU tests | RED 3 failed, 25 passed; GREEN 109 passed, 21.47s |
| Task 3 full suite | `python -m pytest -q --disable-warnings`: 639 passed, 1612 warnings, 178.99s |
| Task 4 controller/historical tests | RED 16 failed; thêm response/client boundary RED→GREEN; GREEN 57 passed, 9.80s |
| Task 5 scorer/runner tests | RED 9 failed, 5 passed; GREEN 41 passed, 6.29s |
| Task 6 report/controller/scoring tests | RED 6 failed; invalid usage aggregation RED→GREEN; GREEN 41 passed, 5.50s |
| Task 7 targeted Tasks 1-6 | 184 passed, 33.29s |
| Task 7 full trước final review | `python -m pytest -q`: 680 passed, 1612 warnings, 196.74s |
| Final review fix targeted | 72 passed, 11.90s |
| Full sau final review fix | `python -m pytest -q`: 681 passed, 1612 warnings, 191.38s |
| Compile checks | `python -m compileall -q evaluation/dualsql_lite_ctu_gpt5_v2 scripts/audit_r2_historical_reports.py` và `python -m py_compile scripts/run_frozen_v2_e3.py scripts/run_frozen_baseline_e0.py`: exit 0 |
| Diff check | `git diff --check`: exit 0 |

Targeted Task 7 command:

```powershell
python -m pytest tests/test_r2_historical_entrypoints.py tests/test_frozen_reentry_gate.py tests/test_r2_historical_reports.py tests/test_dualsql_ctu_gpt5_v2.py tests/test_dualsql_lite_ctu_gpt5_v2.py tests/test_dualsql_ctu_gpt5.py tests/test_dualsql_tools.py tests/test_r2_v2_controller_contract.py tests/test_dualsql_agents.py tests/test_r2_v2_scoring_contract.py tests/test_text_to_sql_runner.py tests/test_r2_v2_report_contract.py -q
```

Warnings là datetime deprecations đã có trước remediation. CI cuối được bổ sung sau khi có output.

Fresh reviewer xác nhận 43 digest unchanged và tìm một lỗi Important: table entry có field thừa được chuyển nguyên vào generator. Regression `test_linker_extra_fields_cannot_cross_validated_handoff` RED 1 failed; sửa bằng reject keys ngoài `table`/`columns`, GREEN 72 targeted và full 681 passed. Không có Critical hoặc Minor được báo. CI final được chờ trước nghiệm thu.

## Gate S5/S7 và hashes

```powershell
python -m evaluation.dualsql_lite_ctu_gpt5_v2.offline_gate --snapshot data/ctu_network_public/snapshots/ctu_dev.duckdb --manifest evaluation/ctu_network_public/dataset_manifest.json --output results/evaluation_v1/ctu_network_public/dualsql_lite_ctu_gpt5_v2/remediation_offline_gate_2026-09-30.json
```

Exit 0: 7/7 referenced cases resolved; `ctu_sql_008` no-reference; 2/2 negatives; 27 v1 lookups replayed. Gate chứng minh retrieval/controller offline; không chứng minh model chọn đúng tool hoặc SQL accuracy. [Artifact](../../results/evaluation_v1/ctu_network_public/dualsql_lite_ctu_gpt5_v2/remediation_offline_gate_2026-09-30.json), SHA-256 `de555541240dd39e61d9e14881ecca5404c0fb68116edb34adf34abfbb1d2e1a`.

Snapshot logical SHA `42c8e0a62441295cc5d95329a65dc22409c37de5b26a1e37dd56fbf0164a758c`; binary SHA `0b29765b9a175d00e0a193039a1b058691406e28a434e10030ae78265cfa67b9`. Sources S5 `ef5c9ed6895d4ca5aec723449dae30054ccd1f6b091713a52ffcb681ff78a02c`, S7 `df0b5338190b967bd340a0d6c1bb3c34d1bbfb4b7ffa764c2dd26f77f1a26680` được verifier kiểm từ bytes hiện có; không rebuild/download.

43 digest inventory trước/sau đều khớp; inventory SHA `7f92daacb980037fa054ee97dd95aa19df06237eb11add939c7442611ed3352a`. 18 Git blob digests tại `cf46fb4` và Windows checkout digests được kiểm riêng theo [CONSUMED.lock](../../evaluation/ctu_network_frozen/CONSUMED.lock).

- E0 report trước = sau: `33b35678171309c1a8958c1d9818499915986942e6936a03428df8fa0544bc15`.
- v1 selection trước = sau: `8be5cc4d9b677c794e6987b965a31dd77e61747b0bbcb4be0a93172014f90b00`.
- [Audit receipt](../../results/evaluation_v1/ctu_network_frozen/remediation_audit_v1/receipt.json) và [controller receipt](../../results/evaluation_v1/ctu_network_frozen/remediation_audit_v1/controller_receipt.json) là file mới, không overwrite historical evidence.

## Cost, provenance và deviation

Chi phí remediation **$0**; zero API calls, zero model dispatch, không R1/demo/paid/frozen suite. SDK client boundary vẫn disabled; retries 0 là request identity cho contract tương lai, không claim đã tạo SDK client trong offline task.

Historical E0 EX 0/8, E3 EX 2/8; E3 execution success 3/8 theo flags cũ, 2 `EXEC_ERROR`, 3 `EMPTY_SQL`. Syntax validity đúng nghĩa chưa xác minh. Cost/provenance incomplete; tổng $0.06508150 chỉ là recorded lower bound. Receipt hashes xác nhận bytes tại audit, không tạo run-time provenance hồi tố.

Rulings: không tái tạo lỗi collection đã recovery; giữ adapter thay vì viết lại. Multi-statement bị scorer cũ loại ở syntax gate trước execution; giữ semantics. Concurrent remote plan được merge giữ nội dung nhưng Tasks 8-10 chưa thực thi theo chỉ thị offline hiện tại. Verification ledger/logs được giữ để human review.

Frozen S1/S4 vẫn consumed/closed. Không thay nguồn/model, không chọn winner từ frozen. **STOP FOR HUMAN REVIEW** sau exact-SHA CI.
