# VinSOC — phụ lục khóa ngoại tuyến Text-to-SQL ngày 11/10/2026

## Kết luận

`master@69b3c9b82325564df60a4b692fee51273dee2062` đã khôi phục đúng hợp đồng R2 đã duyệt: `gpt-5-mini-2025-08-07`, reasoning `low`, `max_completion_tokens=1000`, không retry. Commit `e1077be` từng nâng cap lên 4000 sau demo lỗi, nhưng thay đổi đó không có sửa đổi protocol/budget tương ứng và trái với toàn bộ preflight/cost receipt đã khóa. Không tăng cap để cứu output lỗi.

CI đúng SHA là [run 38144605030](https://github.com/Whats-up-pro/VinSOC/actions/runs/38144605030), kết luận `success`:

| Gate | Python 3.11 | Python 3.12 |
|---|---:|---:|
| Full suite | 1322 pass, 7 skip | 1322 pass, 7 skip |
| Required offline R3–R5 | 46 pass, 0 skip | 46 pass, 0 skip |
| Required real DB/worker | 13 pass, 0 skip | 13 pass, 0 skip |

Bảy skip chỉ thuộc full suite; hai nhóm bắt buộc đều không skip. Compile, preservation và hai ZIP pin đều đạt. Không sửa benchmark, gold, prompt, scorer, artifacts lịch sử hoặc bốn demo ID.

Receipt máy đọc được: `results/evaluation_v1/text2sql_integration_v1/offline_release_20261011/release_decision_receipt.json`.

## Trạng thái R2–R5

- R2: bằng chứng kernel độc lập và required real-data CI tiếp tục đạt. Không dùng trường `isolation` tự khai của executor làm bằng chứng.
- R3: guard preflight/accounting/checkpoint đạt ngoại tuyến. Selection vẫn `pending`, có 0/48 record calibration thật; không tạo record giả.
- R4: normalization/reporting/fixed denominator đạt ngoại tuyến. Chưa có 192 record evaluation hoặc 32 record pipeline thật nên không có tuyên bố điểm.
- R5: CLI/viewer/review/escaping/missing/partial/duplicate/hash mismatch đạt ngoại tuyến. Hai lần demo một case trước đây đều technical-incomplete, không có SQL cuối và không được người thật duyệt; không tuyên bố demo thành công.

## R6 — gói quyết định, chưa truyền request

Nguồn model/pricing chính thức được đối soát lại ngày 11/10/2026. Giá và context bound không đổi: GPT-5 mini là $0.25 input / $2 output trên một triệu token, context 400.000; GPT-4.1 mini là $0.40 input / $1.60 output, context 1.047.576. Cận bảo thủ vẫn dùng toàn bộ context, không dùng cached discount.

| Scope | Request tối đa | Cận tiền mới (USD) |
|---|---:|---:|
| Calibration | 168 | 17.1360000 |
| Evaluation | 672 | 68.5440000 |
| Pipeline E0 | 96 | 30.1843456 |
| Pipeline E3 | 256 | 46.5043456 |
| Một demo E3 | 8 | 1.4532608 |
| Calibration + evaluation + pipeline E0 | 936 | 115.8643456 |
| Calibration + evaluation + pipeline E3 | 1096 | 132.1843456 |

Ba preflight-only calibration/evaluation/pipeline đều dừng trước SDK: `attempted=0`, `received=0`, `client_created=false`. Canonical ledger, prior exposure, allocation và số dư xác minh vẫn chưa có từ authoritative host. Vì vậy cấm request trả phí mới.

Hai lần demo một case trước đó đã dùng tổng cộng 8 model calls, chi phí thực tế cộng dồn `$0.0056888`; cả hai không phải calibration/evaluation/pipeline và không có official score. Phiên tiếp tục ngày 11/10 dùng 0 model call, chi phí `$0`.

## Quyết định còn cần

Trước request trả phí đầu tiên phải cung cấp đủ:

1. canonical ledger đã đối soát trên authoritative host, kể cả unknown exposure và khóa các host cũ;
2. allocation tổng, prior cost và verified remaining balance;
3. phê duyệt ngân sách ghi rõ scope (`calibration` trước), limit USD và decision reference;
4. release/preflight mới gắn đúng SHA, data/source identities và scope chưa dùng;
5. sau calibration: đủ 48 record thật và selection lock hợp lệ mới được mở evaluation/pipeline.

`gpt-5-mini-2025-08-07` được OpenAI thông báo ngừng ngày 11/12/2026. Nếu chạy vào hoặc sau ngày đó phải sửa protocol/model/budget qua một quyết định mới; không tự đổi model.

Calibration, evaluation và pipeline vẫn là `PENDING_NO_ARTIFACTS`, không phải `COMPLETE`.
