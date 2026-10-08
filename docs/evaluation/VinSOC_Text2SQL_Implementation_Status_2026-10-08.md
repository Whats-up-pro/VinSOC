# VinSOC — trạng thái triển khai Text-to-SQL ngày 08/10/2026

Mã kết nối đã bổ sung trên nền master e786c8b; **chưa nghiệm thu chạy model/pipeline thật**. Không dùng mock trong mã, dữ liệu và bằng chứng mới. Các tests tổng hợp lịch sử chỉ giữ để kiểm hồi quy.

## Phần đã thực hiện

- T0: clone master sạch; CI baseline 37723119103 đạt; lập protected_hashes.json và setup_receipt.json. Trạng thái canonical window trên laptop chưa truy cập được, không suy ra unused và không tạo/reset window.
- T1: preflight E2E cũ dừng trước SDK, 0 requests. Thiếu đầu vào riêng và exact snapshot. A2/A3 vẫn BLOCKED; không thay khóa cũ để gắn mã mới vào kết quả cũ.
- T2: tải Spider theo archive SHA đã pin và hai nguồn CTU S5/S7 đúng SHA; kiểm schema/logical content, SQLite–DuckDB parity và đủ 120 base gold trên các bản dựng riêng. Kết quả này là audit nguồn thật, không thay exact-binary acceptance. Bốn demo IDs đã chọn trước model output bằng hash-order seed 20261008.
- T3–T5: một thuật toán sinh SQL dùng chung; DTO không có gold; adapter benchmark; executor namespace chỉ đọc và không secrets/network; network_query question-only; trusted CTU scope; evidence OBSERVED/DERIVED; kiểm facts/citations và query replay; public investigate_query dùng chung lifecycle verify/review; nhật ký cả routing/R2/assessment; không retry/fallback.
- T6 một phần: runner calibration/evaluation/pipeline gọi shared service/public API; preflight-only không tạo client; scorer phía evaluator; báo coverage external64/CTU32 và macro DB/domain; CLI query/query-review/query-render; review người thật tạo receipt liên kết hash, không sửa bản gốc. Chưa có bundle exact runtime cho real-data CI, chưa có kết quả model mới và paired statistics mới.
- T7 một phần: dự toán bảo thủ đã lập. Theo giá Standard tại https://developers.openai.com/api/docs/pricing, cận inference mới là **12,0240384 USD nếu pipeline chọn E3**, hoặc **10,3728384 USD nếu chọn E0**; chưa cộng prior costs chưa đối soát. Đây không phải số đã chi hoặc paid authorization. Account allocation và framing bound còn phải xác minh.

## Trạng thái nghiệm thu

| Gate | Trạng thái | Bằng chứng / việc cần bổ sung |
|---|---|---|
| Source bytes | Đã xác minh | source_acquisition_receipt.json, ctu_acquisition_receipt.json |
| 120 gold trên source thật dựng riêng | Đạt về nội dung | reconstructed_source_gold_audit.json; không là model score |
| Exact runtime binaries | BLOCKED | 12 Spider DB + CTU cross-domain phải chuyển từ môi trường đã khóa; bản dựng riêng khác binary |
| Worker isolation | BLOCKED | worker_probe.json; namespace backend chưa thực thi được ở môi trường hiện tại, không fallback cùng process |
| Guards và hồi quy mã | Đã kiểm tại môi trường hiện tại | validation_receipt.json; một required local-snapshot test vẫn thiếu đầu vào |
| Real-data CI restore | Chưa đạt | Cần bundle/manifest/hash/artifact identity thực; chưa sửa CI thành skip/fake fallback |
| Calibration 48 records | Chưa chạy | preflight_calibration.json; 0 attempts/0 responses/client=false |
| Evaluation 192 records | Chưa chạy | Cần calibration selection lock thật + scope ngân sách mới |
| Pipeline 32 cases | Chưa chạy | preflight_pipeline.json; 0 attempts/0 responses/client=false |
| Human review và demo bốn case | Chưa có | Cần model/tool/DB/assessment thật trước; không tạo trace/approval thay người |

## Thứ tự tiếp tục

1. Chuyển exact-binary bundle 13 runtime DB từ máy đã chạy validator, giữ đường dẫn của runtime_registry.json; kèm official Spider archive/members và nguồn CTU đã pin. Network E2E dùng bundle riêng VinSOC_Qualified_Network_Snapshot_20261007.zip, không trộn hai CTU binary identities.
2. Cấp môi trường Linux cho bubblewrap network namespace hoạt động; chạy real-DB kiểm executor/typed results/lineage và saved live SQL. Sau đó mới khóa execution identity mới và CI restore bundle, kiểm cả Python 3.11/3.12.
3. Xác minh authoritative window/gates riêng của E2E cũ. Khóa cũ vẫn mô tả source version cũ; không đổi content lock theo mã query mới. Không chạy lại cửa sổ đã dùng.
4. Đối soát account/allocation/prior costs, framing bound và giá còn mới; quyết định budget cho scope calibration/evaluation/pipeline mới. Không chuyển API key hoặc private gate/ledger vào public Git.
5. Chạy calibration đủ 24×2, chốt lựa chọn; evaluation đủ 96×2; pipeline đủ 32 bằng chính service đã đánh giá. Giữ mọi lỗi và partial receipts, không sửa prompt/gold/scorer sau output.
6. Người thật duyệt technical-valid cases; dựng JSON/HTML/demo từ bốn IDs đã khóa. Hoàn thiện paired statistics, module coverage, report/runbook/manifest và kiểm tái lập. T8–T10 chưa hoàn tất.

## Lệnh có sẵn

```bash
python -m cli.main query --scope calibration --preflight-only --output .vinsoc/calibration-preflight.json
python -m cli.main query --scope pipeline --preflight-only --output .vinsoc/pipeline-preflight.json
python -m scripts.run_vinsoc_query_acceptance --release .vinsoc/authorized-release.json --output .vinsoc/new-live-run
python -m cli.main query-review .vinsoc/new-live-run/E3_case.json --output .vinsoc/review-case.json
python -m cli.main query-render .vinsoc/new-live-run/report.json --output .vinsoc/new-live-run/report.html
```

Lệnh live cần private release hợp lệ, exact clean master/source/CI, exact dữ liệu và worker PASS; thiếu gate thì dừng trước client. Preflight blocked trả exit 1. CLI batch dùng câu hỏi nguyên văn từ inventory; public API cũng nhận câu hỏi từ ứng dụng. Chưa có chế độ query tùy ý với scope/budget riêng.

## Bảo vệ và giới hạn

R1 22/24 và R2 Phase-2 E3 7/8 được giữ nguyên. R1 có caveat gold dev adjudication; R2 lịch sử 5/8, CTU GPT-5 E0 0/8 và Phase-2 7/8 thuộc các contracts khác nhau. R1 frozen/R2 holdout và matched tám câu cũ vẫn deferred. Không nhận điểm 96 mới là completion của protocol tám câu cũ.

Mã mới có kiểm tra chặn lỗi và giữ hành vi profile cũ, nhưng chưa được chứng minh positive path bằng DB trong worker thật hoặc live provider. Không gọi đây là sản phẩm hoàn tất, real-data CI PASS hay demo đã sẵn sàng. Trạng thái này phải giữ cho tới khi có receipt thực.
