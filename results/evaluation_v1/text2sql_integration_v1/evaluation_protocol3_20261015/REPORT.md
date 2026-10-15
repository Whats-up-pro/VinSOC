# Evaluation Text-to-SQL — 96 câu, hai cấu hình E0/E3

Lượt API thật đã tạo đủ **192/192 records** cho 96 câu: 64 câu ngoài miền SOC và 32 câu CTU. E0 đạt **69/96 (71,875%)**; E3 đạt **17/96 (17,708%)**. Cấu hình E0 được chọn từ calibration trước khi chạy evaluation và vẫn được giữ nguyên.

Đối soát ngoại tuyến đã khớp toàn bộ records, câu hỏi, database, usage, định danh request/response, chi phí, giới hạn lượt gọi và các chỉ số tính lại. Mốc này còn chờ CI của commit công bố bằng chứng; pipeline 32 câu là lượt riêng tiếp theo.

## Kết quả và tài nguyên

| Phép đo | E0 | E3 |
|---|---:|---:|
| EX trên toàn bộ 96 câu | 69/96 — 71,875% | 17/96 — 17,708% |
| Ngoài miền SOC | 46/64 — 71,875% | 10/64 — 15,625% |
| CTU | 23/32 — 71,875% | 7/32 — 21,875% |
| Macro theo database | 71,875% | 16,319% |
| Macro theo domain | 70,703% | 15,234% |
| Số request/response | 96/96 | 482/482 |
| Input token | 122.414 | 1.117.655 |
| Output token | 21.910 | 229.697 |
| Cached input token, nằm trong input | 0 | 522.368 |
| Chi phí theo usage và giá đã xác minh | 0,07442350 USD | 0,62127495 USD |

Tổng: **578/578 response**, 1.240.069 input token, 251.607 output token; chi phí mới **0,69569845 USD**. Ledger query tích lũy đã đối soát là **1,29571520 USD**, gồm 0,60001675 USD của các lượt trước. Không có unknown cost hoặc pending exposure.

Model giữ nguyên `gpt-5-mini-2025-08-07`, reasoning low, output tối đa 1.000 token và SDK retry bằng 0. E0 tối đa một request/case; E3 tối đa sáu. Không mở thêm cửa sổ hoặc chạy lại prediction để cứu điểm.

## Đối chứng trên cùng 96 câu

So với E0, E3 thắng 2 câu, thua 54 câu và hòa 40 câu. Chênh lệch EX của E3 trừ E0 là **−54,167 điểm phần trăm**. Khoảng bootstrap theo database là **[−65,278; −43,750] điểm phần trăm**, theo đúng thuật toán và seed đã khóa.

Đây là mô tả trên tập đã chọn. Các câu có thể tương quan theo database, family hoặc template; khoảng tin cậy không chứng minh khả năng tổng quát trên một holdout độc lập.

## Điểm mạnh, lỗi và nguyên nhân quan sát được

E0 tạo được SQL cho 95/96 câu. Trong đó, 69 câu đúng, 25 câu chạy được nhưng khác kết quả chuẩn và một câu lỗi thực thi; câu còn lại bị kiểm tra ngữ nghĩa chặn. Trên bộ này, E0 có đường sinh SQL ngắn, dùng ít request hơn E3 và chi phí thấp hơn. Kết quả chưa đồng đều: `car_1` đạt 3/8, còn `orchestra` đạt 8/8; mỗi nhóm chỉ có tám câu nên chưa đủ để kết luận rộng theo ngành.

E3 có 52 records `INVALID_LINKED_SCHEMA`, 21 `MODEL_PARSE_ERROR`, hai `TOOL_FAILURE` và một `SAFETY_REJECTION`. Có 76/96 records không đến được SQL cuối. Điểm nghẽn quan sát được nằm ở liên kết lược đồ, hợp đồng đầu ra và bước parse trước khi thực thi SQL. Trong 21 lỗi parse, 17 response cuối có `finish_reason=length`; cần thí nghiệm riêng để tách ảnh hưởng của giới hạn output và reasoning.

Hai ví dụ thật để kiểm tra:

- `ctu_cross_111e791fb862cf30`, E3: response cuối viết yêu cầu `value_search` trong phần content; bước kiểm tra link không nhận được cấu trúc link hợp lệ. Xem record gốc trong `live/`.
- `ctu_cross_09368110b7091cb8`, E3: response cuối không có content, dùng đủ 1.000 output token và kết thúc bằng `length`. Record giữ nguyên lỗi parse.

Ở phiên bản sau, ưu tiên làm rõ hợp đồng giữa native tool calls và JSON link, kiểm chứng witness/value, rồi kiểm tra các lỗi ngữ nghĩa JOIN và truy vấn lồng. Mỗi thay đổi cần được khóa và đánh giá theo protocol mới. Lượt hiện tại giữ nguyên prompt, scorer, dữ liệu và kết quả.

## Phạm vi và bằng chứng

Evaluation bao phủ chín database trong bộ đã chọn; toàn bộ nguồn khôi phục ban đầu có 13 DB cho cả calibration và evaluation. Đây không phải điểm Spider chính thức, holdout độc lập hoặc chứng nhận SOC tổng quát. Các trường mặc định `semantic_test_accuracy=false` trong report gốc **không phải** kết quả một semantic test suite đã được đo.

- Producer: `3c3ce816ed2f5dbf04c35433267b599b31d8c2bd`.
- CI producer: [38685818952](https://github.com/Whats-up-pro/VinSOC/actions/runs/38685818952).
- Preflight: [38686134129](https://github.com/Whats-up-pro/VinSOC/actions/runs/38686134129).
- Lượt API thật: [38687383299](https://github.com/Whats-up-pro/VinSOC/actions/runs/38687383299), attempt 1.
- Artifact: `11953127514`; ZIP SHA-256 `4c79fe3543ef17151e8bfabfebf9e5ab63fbfad7e89d1de87cdad16f09d868dd`, khớp digest GitHub.
- [Receipt](acceptance_receipt.json), [đối soát độc lập](audit_summary.json), [giá và nguồn](pricing_facts.json), [manifest](artifact_hashes.json).

192 file JSON trong `live/` giữ nguyên byte của producer. Report đầy đủ được lưu không mất dữ liệu ở `live/report.json.gz`; giải nén cho ra đúng hash JSON gốc trong receipt. Cờ `official_eligible=false` của producer được giữ nguyên vì kiểm tra độc lập và CI công bố là bước riêng. Private gates, raw HTTP journal và thông tin tài khoản không được công bố vào Git.

Kiểm lại ngoại tuyến từ repo đã cài dependencies:

```bash
python results/evaluation_v1/text2sql_integration_v1/evaluation_protocol3_20261015/verify.py
```

Lệnh chỉ đọc artifact và tính lại chỉ số; không tạo SDK client, không chạy SQL và không gọi mô hình. Chưa có human review mới nào được ký trong gói này. Pipeline chính thức phải tự sinh trace và assessment cho đủ 32 câu qua public `investigate_query`; điểm evaluation không được điền thay cho pipeline.
