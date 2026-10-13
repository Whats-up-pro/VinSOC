# VinSOC — trạng thái E2E trước buổi demo (13/10/2026)

## Kết luận có thể trình bày

`full-e2e-8` chạy trên `09cfbfaee49e780d3ca1afd02c89ae3ef55c3168` với [CI đúng SHA xanh](https://github.com/Whats-up-pro/VinSOC/actions/runs/38335064157). `0e85e637bbc5828c221f1d0d2dac0a91090c3c28` đã commit audit và bản sửa checkpoint/semantic; [CI đúng SHA #339](https://github.com/Whats-up-pro/VinSOC/actions/runs/38336323978) thành công. [Lượt live #10](https://github.com/Whats-up-pro/VinSOC/actions/runs/38336761761) trên SHA đó kết thúc `technical_incomplete`. `master@7c6e5b907934b8ce76f7f88d4dd9edd80834d9eb` đã thêm audit #10 và nâng cap R2; chưa có bằng chứng live đạt trên commit này. Public orchestrator, `network_query`, dịch vụ Text-to-SQL chung, DuckDB chỉ đọc, evidence, assessment, HITL và viewer ngoại tuyến đã có đường mã và kiểm thử. CI xanh là bằng chứng mã và dữ liệu, **chưa phải một lần E2E sống thành công**.

| Phạm vi | Kết quả xác minh | Còn thiếu để đạt mục tiêu |
|---|---|---|
| Một câu demo tích hợp | `full-e2e-8` partial đã được audit; lần mới nhất `full-e2e-9` vẫn `technical_incomplete`, 6/6 response, không có SQL cuối do `MODEL_PARSE_ERROR` ở linker. | Xác minh cap/protocol/budget mới và CI; một execution mới được cấp quyền phải đạt kiểm tra kỹ thuật và được người thật duyệt. |
| R2 calibration | 0/48 record model thật của protocol mới | Ngân sách và quyền riêng cho calibration, đủ 24 ID × E0/E3, khóa selection. |
| R2 evaluation | 0/192 record model thật | Selection lock, quyền và ngân sách evaluation; đủ 96 ID × 2. |
| E2E pipeline | 0/32 câu CTU qua luồng production được chấm | Chọn cấu hình từ calibration, quyền pipeline riêng, 32 trace, facts/provenance và human review. |
| R1 generalization | Split 120 ca đã khóa tại Task 5; Task 6 trên master bị revert chủ ý ở `3ac9a56` | Giữ riêng; không lấy R1 dev 22/24 hoặc CI làm điểm E2E. |

## Artifact đã đối soát của run #9

Lần `full-e2e-8` chạy trên `09cfbfa`, CI [38335064157](https://github.com/Whats-up-pro/VinSOC/actions/runs/38335064157), workflow [38335534597](https://github.com/Whats-up-pro/VinSOC/actions/runs/38335534597), artifact `11784501792`, ZIP SHA-256 `cdfea925759faa5b5281778180435703a8086d2ff2b49a752de459821ce1e045`. [Outcome audit](../../results/evaluation_v1/text2sql_integration_v1/single_demo_full_e2e_8_20261013/outcome_audit.json) đã được commit ở `0e85e63`. Viewer offline kèm theo là **bản xem lại lượt này**, không đại diện cho lượt mới hơn.

Preflight đã PASS. Public report thô ghi `status=partial`, `planned=1`, `completed=0`, `attempted=9`, `received=8`, `valid_usage=8`, `cost_unknown=true`, `pending_exposure_usd=$0.4206304`. [Audit đã commit ở `0e85e63`](../../results/evaluation_v1/text2sql_integration_v1/single_demo_full_e2e_8_20261013/outcome_audit.json) đối chiếu checkpoint begin/end và mã đường truyền: reservation thứ 9 bị chặn **trước** `ScopedOpenAIClient`/SDK, không có request thứ 9 tới provider; `cost_unknown=false` sau đối soát và chi phí của reservation này bằng `$0`. Tám request truyền thật có cost `$0.00809355` lần này, lũy kế `$0.04565135`. Cận exposure của report thô không phải actual spend. Cần quyền/window/budget mới và CI đúng SHA mới trước bất kỳ request nào nữa.

## Run #10 mới nhất — đã có audit

Workflow #10 là execution `full-e2e-9` trên `0e85e63`, CI [38336323978](https://github.com/Whats-up-pro/VinSOC/actions/runs/38336323978) success, [workflow 38336761761](https://github.com/Whats-up-pro/VinSOC/actions/runs/38336761761) failed, artifact `11785262841`, digest `sha256:f2e0935674056f6a03230485df508573a2d46a7417d42af9627b519b0c98d243`. Log ghi `status=technical_incomplete`, `attempted=6`, `received=6`, `completed=1`, `cost_unknown=false`, chi phí execution `$0.0081066`, lũy kế `$0.05375795`, `official_eligible=false`. [Audit chính thức đã commit ở `7c6e5b`](../../results/evaluation_v1/text2sql_integration_v1/single_demo_full_e2e_9_20261013/outcome_audit.json) xác định schema linker có ba phản hồi chạm trần 1.000 output token; `MODEL_PARSE_ERROR`, không có SQL cuối, DB execution hoặc assessment. Commit `7c6e5b` nâng `max_completion_tokens` R2 lên 2.000 và thay cận request; CI đúng SHA, protocol/budget và preflight cần được kiểm trước bất kỳ paid run tiếp theo. Việc tải ZIP #10 trực tiếp qua công cụ bị hệ thống duyệt tự động từ chối vì giới hạn sử dụng; phần kết luận trên dựa vào audit đã commit và log công khai, chưa kiểm ZIP độc lập.

Đầu ra SQL lấy `COUNT(DISTINCT dst_ip)` riêng cho `ctu13_s5` và `ctu13_s7`, trả `1529` và `1210`. Gold khóa của câu này dùng giao hai tập IP và trả `459`. Không thay gold hoặc sửa output. Cách viết “in scenario 5 and ... in scenario 7” có khả năng được hiểu là hai phép đếm riêng; cần quyết định phạm vi trình diễn tương lai trước khi mở output mới, ghi rõ nếu dùng câu demo không chấm điểm với wording mới. Bốn ID demo đã khóa của protocol gốc không được thay sau khi xem kết quả để báo một bộ điểm đẹp hơn.

Các lần trước cũng là bằng chứng thất bại thật: `full-e2e-7` tại `3ac9a56` là `technical_incomplete` dù nhận đủ 8/8 response, do result mismatch và assessment thiếu dẫn chứng; các lần `full-e2e-5/6` đã được checkpoint tại kế hoạch cũ. Mỗi lần có ID, ledger và kết luận riêng.

## Kịch bản demo an toàn hiện tại

Có thể trình bày offline kiến trúc và trace thật từ artifact `full-e2e-8`, nêu rõ partial, SQL sai ngữ nghĩa, assessment thiếu và chưa có human approval. Viewer pipeline hiện có hiển thị bốn demo ID và đủ 32 ID; 31 ID chưa chạy phải hiện `missing`, case đang có partial phải hiện `incomplete`. Mở đầu phải thông báo có execution `full-e2e-9` mới hơn, thất bại ở linker trước SQL; viewer là snapshot của lượt trước. Đây là buổi **xem tiến độ và lỗi thật**, không phải nghiệm thu E2E thành công hay điểm R2.

Điểm nghiệm thu theo [đặc tả gốc](../superpowers/plans/2026-10-08-vinsoc-text2sql-integration-and-final-demo.md) vẫn cần ít nhất một trace kỹ thuật hợp lệ trong bốn case đã chọn và human review, cùng báo trạng thái cả bốn; kết quả đầy đủ còn cần 48 calibration, 192 evaluation và 32 pipeline record thật. Kế hoạch cập nhật: [E2E demo recovery](../superpowers/plans/2026-10-13-vinsoc-e2e-demo-recovery.md).
