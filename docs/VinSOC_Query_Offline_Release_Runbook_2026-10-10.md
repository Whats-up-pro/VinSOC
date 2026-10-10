# VinSOC query — tiếp tục ngoại tuyến ngày 10/10/2026

R1/T2 đã đạt ở các receipts gốc: 13 exact DB, 120 trusted gold, CI 38019271076. Giữ nguyên ZIP/benchmark/gold/prompts/scorers/kết quả lịch sử. SQL model lưu sẵn chỉ kiểm worker; không tính vào điểm mới.

## Viewer mặc định

```powershell
python -m cli.main query --case-id ctu_cross_708b66575657429a --question "Count distinct destination IPs receiving TCP flows after 2011-08-15 17:00:00 in CTU scenario 5 and after 2011-08-16 14:00:00 in scenario 7; use strict time boundaries." --output query-viewer.html
```

Viewer chỉ đọc artifacts, không tạo SDK/call/claim. Thêm `--source <pipeline/report.json>` khi đã có lượt thật. Nếu chưa có artifacts, cả 32 IDs hiện missing; bốn IDs trong `demo_selection.json` luôn giữ nguyên. Không gọi viewer là demo live thành công. Lệnh sai nguyên văn câu hỏi bị chặn trước hành động.

## Preflight-only

```powershell
python -m cli.main query --scope calibration --preflight-only --output preflight-calibration-new.json
python -m cli.main query --scope evaluation --preflight-only --output preflight-evaluation-new.json
python -m cli.main query --scope pipeline --preflight-only --output preflight-pipeline-new.json
```

Output mới append-only, public-safe, `attempted=0`, `received=0`, `client_created=false`. Thiếu selection/canonical ledger/account/pricing/token-bound/authorization sẽ blocked. Không tự tạo account/gates/ledger/records để pass.

`--release <private-release.json>` là đường paid riêng của runner đã freeze, vẫn cần quyết định ngân sách/phạm vi cụ thể. Với pipeline, case ID/câu hỏi người nhập chỉ chọn câu trong batch 32 đã cấp; không tạo lượt chạy riêng một case. Batch gọi public `InvestigationOrchestrator.investigate_query` cho nguyên văn 32 câu, cùng shared service/worker. Transcript native/routing/assessment mới còn pending tới R8.

## Review thật

```powershell
python -m cli.main query-review <pipeline/E3_case-id.json> --output <new-review.json>
python -m scripts.render_query_pipeline_report <pipeline/report.json> --review <new-review.json> --output <new-viewer.html>
```

Người duyệt tự nhập identity, approved/rejected/escalated, rationale và UTC ISO 8601. Không có giá trị tự duyệt hoặc timestamp tự điền. Approval yêu cầu integrated EX đúng cùng technical/factual/provenance checks; receipt gốc bất biến, review liên kết raw file hash. Hash sai hoặc thiếu identity giữ pending, không nâng thành công. CLI hiển thị câu hỏi, native call, SQL, typed result, evidence, assessment, verification và limitations.

## Required Linux worker CI

CI dùng Ubuntu 22.04, Python 3.11/3.12, nguồn/binaries exact đã pin. Supervisor và descendants cùng một systemd-delegated subtree, chạy dưới UID runner, worker vẫn bubblewrap unshare-all/cap-drop/clearenv/read-only DB. Mỗi cgroup có memory.max 536870912, swap.max 0, cpu.max 100000 100000 và atomic group kill; SQL không chạy trong process giữ secrets.

Boundary proof đọc độc lập `/proc` và cgroup filesystem/counters: network namespace khác, env chỉ locale/PWD=/tmp, duy nhất DB cần thiết mount chỉ đọc; tổng memory descendants thực gây OOM tại cap; CPU và wall timeout được kiểm. Required checks có skip sẽ fail. Regression skips được báo riêng, không tính thành nghiệm thu.

Giá/cận tiền ở R6 chỉ là dự toán cho tới khi token framing, account/allocation, prior cost/unknown exposure và canonical scope state có bằng chứng hiện hành. Dừng trước request trả phí đầu tiên; không dùng quyền network E2E cũ.
