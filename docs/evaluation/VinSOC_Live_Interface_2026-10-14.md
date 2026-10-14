# VinSOC: chạy pipeline từ giao diện

Đây là bổ sung chức năng chạy mới, tách khỏi viewer artifacts ngày 13/10.
Trang **Chạy pipeline thật** gửi yêu cầu đến Linux GitHub Actions; model SDK và
SQL worker chạy ở runner đó, không ở process Streamlit/Windows.

## Khởi động và một lượt end-to-end

```powershell
Set-Location D:\VINUNI_AI2026\Phase3_VinSOC
.\.venv\Scripts\python.exe -m pip install -r requirements-demo.txt
gh auth status
.\.venv\Scripts\python.exe -m streamlit run scripts/vinsoc_demo_app.py
```

1. Mở `http://localhost:8501`, chọn **Chạy pipeline thật**.
2. Chọn một query demo và nhập/dán đúng câu hỏi gốc. Có thể dùng AVG để trình bày
   một luồng mới; câu hỏi khác case đã khóa bị chặn trước SDK.
3. Bấm **Chạy preflight Linux (0 model calls)**. UI tìm CI đạt của đúng SHA đã
   commit; source chưa commit/CI chưa đạt thì không dispatch. Runner kiểm dữ liệu,
   worker, source, pricing, allocation và scope đã dùng.
4. Xem gates/cận tiền. Preflight pass có attempted=received=0, client_created=false.
5. Tự tick quyền chi trong allocation $3 rồi bấm **Chạy pipeline API thật**.
   Input hoặc SHA đổi sau preflight phải preflight lại. Mỗi execution chỉ dispatch
   live một lần, kể cả khi mất kết nối; không retry model để cứu output.
6. Theo dõi job steps và begin/end request checkpoints thật. Không có progress
   mô phỏng bằng timer. UI tự làm mới; server restart vẫn mở lại session đã lưu.
7. Khi runner kết thúc, UI tải artifacts của đúng run/SHA/request, giữ cả partial
   và lỗi. Không dùng case cũ thay output của lượt mới.
8. Xem câu hỏi → native routing → schema/value → SQL → typed result → evidence →
   assessment/verification → human review. Review tự nhập identity/decision/
   rationale/UTC, gắn hash case gốc; không tự approve.

API key chỉ nằm trong GitHub secret. UI sử dụng phiên `gh` của operator để
dispatch/poll, không nhập hoặc lưu model key vào giao diện. Server bind localhost.

## Coverage và gates

| Profile | Catalog / số records | Module gọi model |
|---|---|---|
| Demo | 4 ID đã pin; mỗi lượt một case E3 | routing, R2, assessment |
| Pipeline | Đủ 32 CTU cases theo inventory | routing, R2, assessment |
| Calibration | 24 cases × E0/E3 = 48 records | R2 |
| Evaluation | 96 cases × E0/E3 = 192 records | R2 |

Catalog đầy đủ không có nghĩa đã chạy/đạt đủ suite. Calibration cần đủ ngân sách
cho full reserve. Evaluation/pipeline cần selection lock từ 48 records thật và
CI/source đúng identity. Với allocation hiện tại, UI phải lưu receipts blocked
nếu cận tiền hoặc lock chưa đủ; không giảm reserve, bỏ case hoặc điền predictions.
Calibration/evaluation/pipeline vẫn NOT_RUN cho đến khi actual artifacts tồn tại.

R1 dev24 và SOC insufficient_evidence giữ phần presentation riêng. Những trang
đó đọc history; không được báo là R1/SOC vừa gọi API do một query demo mới.

## Ngân sách và tính bền vững

Base query-demo spend xác minh từ 10 prior receipts và remaining3 run:
$0.08155920, remaining cap $2.91844080 trước các lượt UI mới. Runner cộng tất cả
append-only UI allocation receipts sau đó. Claim không có end, unknown usage/cost
hoặc chain mismatch chặn lượt trả phí tiếp. Allocation không là provider balance.

Sau hai live UI runs có model calls, cumulative đã xác minh là $0.09061250 và
remaining cap là $2.90938750. Lượt UDP bị source-change gate chặn trước SDK nên
không tạo claim và không phát sinh chi phí. Chi tiết nằm trong
`live_ui_acceptance_20261014/cost_reconciliation.json` và báo cáo
`VinSOC_Live_UI_Acceptance_2026-10-14.md`.

Workflow dùng concurrency chung cho allocation, immutable per-window claims và
begin/end cost events. Raw response/usage được giữ trước parse. Private journals
được upload sau failure/cancellation, không commit private requests vào Git.

Mỗi session nằm ở `.vinsoc/live-ui/sessions/liveui-<nonce>/`. State, request,
workflow ID, public artifact hashes và import metadata được lưu. Không xóa
consumed windows hoặc tự reset claim sau lỗi. Download lại artifact là read-only,
không tạo thêm paid attempt.

## Kiểm chứng

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_vinsoc_live_protocol.py tests/test_query_live_ui_cloud.py tests/test_vinsoc_live_ui.py tests/test_vinsoc_demo_ui.py -q
.\.venv\Scripts\python.exe -m compileall -q scripts/vinsoc_live_protocol.py scripts/run_query_live_ui_cloud.py scripts/vinsoc_live_ui.py scripts/vinsoc_demo_app.py
.\.venv\Scripts\python.exe scripts/verify_query_preservation.py
```

Boundary fixtures chỉ kiểm state machine, không là actual CI/preflight/model
receipts. Acceptance thật phải bấm preflight/live từ trình duyệt rồi ghi workflow,
actual responses, usage/cost và result thật. Không đánh COMPLETE bằng tests/mock.
