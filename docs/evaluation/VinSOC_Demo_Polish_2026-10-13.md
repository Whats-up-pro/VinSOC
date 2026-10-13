# VinSOC — sửa reporter và rút gọn review CLI (13/10/2026)

Nguồn tiếp tục: `master@9b44eb605f418fea2d65e5b3eaa043949a200e6f`, CI
[38347712931](https://github.com/Whats-up-pro/VinSOC/actions/runs/38347712931) success.
Tiếp tục Task D của [kế hoạch recovery](../superpowers/plans/2026-10-13-vinsoc-e2e-demo-recovery.md).

## Thay đổi và bằng chứng

Reporter cũ báo factual/technical fail cho ca `ctu_cross_708b66575657429a`:
observation dùng tên cột `distinct_dst_ips`, nhưng reporter chỉ tìm key trực tiếp
trong evidence metadata. Giá trị thật `459` nằm trong `columns/rows`.

Test trên artifact thật đã RED rồi GREEN: cột duy nhất của một hàng được đọc
đúng kiểu/giá trị; sai field/value/type, evidence lạ, observation trùng, cột trùng
hoặc nhiều hàng mơ hồ đều fail. Result evidence được kiểm lại hash và gắn với
execution đang hiển thị, SQL, snapshot và parent execution evidence.

CLI `query-review` mặc định in SQL một lần, result preview, checks, evidence IDs,
assessment và limitations. `--verbose` giữ toàn bộ projection JSON. Receipt vẫn
ghi case ID/hash và identity/decision/rationale/UTC do người nhập cung cấp.
CLI công bố identity là khai báo, chưa xác thực; không tự tạo human approval.

Code review độc lập bằng agent phát hiện hai vấn đề và đã có một vòng sửa TDD:

| Finding | RED | GREEN |
|---|---|---|
| CLI có thể approve evidence khác execution hiển thị | 4 trường hợp execution cell/hash/lineage/parent evidence khác nhau vẫn được chấp nhận | CLI và reporter dùng cùng gate execution/evidence; cả 4 bị chặn, không tạo receipt |
| Tên cột trùng metadata có thể đọc nhầm | `row_count` đọc metadata thay vì cell | Collision bị coi là mơ hồ; không chứng nhận observation |

Lệnh kiểm offline bắt buộc:

```bash
python -m pytest -q tests/test_query_pipeline_contract.py tests/test_query_acceptance_preflight.py tests/test_query_selection_lock.py tests/test_query_journal_persistence.py tests/test_query_record_normalization.py tests/test_query_reporting.py tests/test_query_pipeline_reporting.py tests/test_query_cli_viewer.py
```

Output: **71 passed**. Compile và `git diff --check` đạt.
`scripts/verify_query_preservation.py` kiểm baseline `3573496a...`, **3640 protected
files**, `protected_changed=[]`, hai ZIP pin giữ nguyên hash, `external_model_calls=0`.

## Bàn giao

[Viewer v2](../../results/evaluation_v1/text2sql_integration_v1/offline_demo_v2_20261013/report.html),
[projection](../../results/evaluation_v1/text2sql_integration_v1/offline_demo_v2_20261013/pipeline_projection.json),
[preview CLI](../../results/evaluation_v1/text2sql_integration_v1/offline_demo_v2_20261013/review-preview.txt)
và [manifest](../../results/evaluation_v1/text2sql_integration_v1/offline_demo_v2_20261013/manifest.json)
được tạo từ output thật đã lưu. Source/code/generated hashes có trong manifest.
Artifact và projection cũ được giữ nguyên; đây là bản diễn giải mới có code hash riêng.

Trạng thái mới: một trace `awaiting_human`, 31 missing; factual/provenance/technical
đạt, `human_approved=false`, `official_eligible=false`. Không có receipt analyst được
bàn giao trong repo lúc triển khai. Manifest audit nguồn vẫn lệch một mục (8/9);
metric phụ grounding `0/6/5` chưa được giải quyết.

Phần việc này có **0 model calls và $0 chi phí mới**. Chi phí run nguồn là
`$0.00739705`, cumulative demo `$0.06115500`. Các suite chính thức vẫn `0/48`,
`0/192`, `0/32`; code review của agent không thay quyết định người duyệt ca demo.
