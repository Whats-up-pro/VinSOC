# VinSOC: quyết định ngân sách R6, chưa được phép gọi mô hình

Đây là gói chuẩn bị, không phải release đã được cấp tiền. Chưa có SDK client, request hay response mới; chi phí mô hình mới của công việc ngoại tuyến này là **0 USD**. Calibration, evaluation và pipeline vẫn pending.

Giữ đúng snapshot `gpt-5-mini-2025-08-07` và `gpt-4.1-mini-2025-04-14`. Giá standard/default hiện hành, USD trên một triệu token: GPT-5 mini input 0,25 / cached 0,025 / output 2; GPT-4.1 mini input 0,4 / cached 0,1 / output 1,6. Nguồn: [GPT-5 mini](https://developers.openai.com/api/docs/models/gpt-5-mini), [GPT-4.1 mini](https://developers.openai.com/api/docs/models/gpt-4.1-mini), [pricing](https://developers.openai.com/api/docs/pricing). Thời điểm kiểm và digest tài liệu tải thật nằm trong `public_cost_bound.json`; phải refresh giá và account confirmation trong vòng sáu giờ trước từng scope.

## Cận request và tiền mới

Reserve không trừ cached discount, không retry. Calibration và evaluation chạy E0 rồi E3 trong cùng invocation đã khóa. Pipeline chỉ chạy condition được selection lock chọn sau 48 calibration records thật.

| Scope | GPT-5 mini tối đa | GPT-4.1 mini tối đa | Tổng request | Dự toán byte + framing 512 chưa xác minh | Cận bảo thủ dùng tài liệu hiện hành |
|---|---:|---:|---:|---:|---:|
| Calibration 24 × 2 | 168 | 0 | 168 | 1,73376 USD | 17,136 USD |
| Evaluation 96 × 2 | 672 | 0 | 672 | 6,93504 USD | 68,544 USD |
| Pipeline 32, nếu E0 | 32 | 64 | 96 | 1,7040384 USD | 30,1843456 USD |
| Pipeline 32, nếu E3 | 192 | 64 | 256 | 3,3552384 USD | 46,5043456 USD |
| Tổng, nếu pipeline E0 | 872 | 64 | 936 | 10,3728384 USD | **115,8643456 USD** |
| Tổng, nếu pipeline E3 | 1.032 | 64 | 1.096 | 12,0240384 USD | **132,1843456 USD** |

Bốn câu viewer: **0 request mới**. Những con số này chưa cộng prior cost hoặc unknown exposure; chưa xác minh số dư/allocation của tài khoản, nên chưa có tổng hạn mức tài khoản được phép sử dụng.

## Vì sao có hai cận

Ước tính thấp giả định toàn input không quá serialized UTF-8 bytes cộng 512 token framing. Các cap thực vẫn là 32.768 bytes cho R2/routing, 65.536 bytes cho assessment, tối đa 20 messages và 1.000 output tokens; mọi history/schema/results nằm trong kiểm kích thước payload trước transmission. Chưa có chứng cứ đủ để chốt framing 512 cho mọi payload, nên cờ `input_bound_verified=true` tự khai đã bị chặn.

Cận bảo thủ lấy **toàn context window công bố** làm trần input: 400.000 cho GPT-5 mini, 1.047.576 cho GPT-4.1 mini; vẫn reserve thêm 1.000 output tokens. Cận này bao trùm input/history/schema/results/framing và cố ý dư, không phải dự đoán số token thực. Runtime đọc lại tài liệu model thật có digest, kiểm snapshot/endpoint/giá/trần input trước reserve; tài liệu bị sửa hoặc quá hạn sẽ chặn truyền request. Cận từng request: R2 0,102 USD; routing và assessment đều 0,4206304 USD. Không tăng request/output cap, không thay model hay prompt.

Nếu muốn cấp khoảng 12 USD thay vì cận bảo thủ, cần đóng gate framing bằng chứng cứ phù hợp trước freeze mới; tuyệt đối không chỉ đánh dấu cờ verified. Đây là lựa chọn cần quyết định trước calibration, không được chỉnh runtime sau khi xem đầu ra.

## Gate còn mở và phạm vi cần cấp

Canonical scan chỉ quan sát filesystem hiện tại. Ledger vắng không có nghĩa prior cost hoặc exposure bằng 0; chưa có authoritative host, allocation, prior-host sealing, unknown exposure hoặc remaining được xác minh. Không mượn quyền/budget của network E2E cũ, không tạo ledger/account receipt giả.

Owner tài khoản cần xác nhận allocation ID, prior cost, unknown exposure đã giải quyết, số dư còn lại, authoritative consumed state của mọi scope và host cũ đã khóa. Sau đó quyết định cụ thể hạn mức và scope: calibration tối đa 168 R2 requests; evaluation tối đa 672 R2 requests sau selection; pipeline tối đa 192 R2 + 64 outer nếu E3, hoặc 32 R2 + 64 outer nếu E0. Có thể cấp từng scope, không suy ra quyền lượt sau từ lượt trước.

Selection hiện **pending, 0/48 records thật**; evaluation/pipeline bị chặn trước SDK. Positive report/trace/review của bộ mới cần artifacts thật sau khi có quyền: 192 evaluation records, 32 pipeline cases, review do người thật nhập identity/decision/rationale/UTC. Không có prediction hay approval được tạo để lấp chỗ thiếu.

Preflight-only từng scope phải giữ `attempted=0`, `received=0`, `client_created=false`. Receipt bị chặn ghi gate thực, không ghi PASS khi Windows thiếu backend hoặc working tree chứa các untracked files sẵn có. Linux CI exact SHA là bằng chứng riêng về DB/worker/full suite/compile/preservation; không thay thế account/selection/paid authorization.

**Dừng trước request trả phí đầu tiên.** Chỉ mở lại khi có quyết định ngân sách/phạm vi mới và toàn bộ gate tương ứng thực sự đạt.
