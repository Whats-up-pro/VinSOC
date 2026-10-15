# VinSOC - Bàn giao thực nghiệm ngày 15/10/2026

Calibration 48, evaluation 192 và R1 bổ sung120 đã có artifacts thật và CI của các commit công bố. Pipeline 32 **chưa hoàn tất**:16 case hoàn tất,1 partial,15 chưa chạy. Ba case đạt kỹ thuật còn chờ người duyệt; không case nào trong bốn demo ID cố định đạt đủ gate.

## Mở bản báo cáo và xem lại E2E

Bản chiếu8 trang: [PDF](VinSOC_Official_Experiments_Report_2026-10-15.pdf), [Markdown](VinSOC_Official_Experiments_Report_2026-10-15.md). Bản báo cáo22 trang trước được giữ nguyên, không thay lịch sử bằng kết quả mới.

Từ PowerShell tại thư mục repo sau khi pull:

```powershell
Expand-Archive .\results\evaluation_v1\text2sql_integration_v1\pipeline_protocol3_20261015\offline_demo_bundle.zip -DestinationPath .\vinsoc_offline_demo
Start-Process .\vinsoc_offline_demo\index.html
```

Đây là xem lại lượt API thật đã lưu. Không cần API key, không gọi mô hình hoặc DB. Bundle giữ nguyên byte của index, report và 17 case JSON; native responses được giữ cả khi parse thất bại. Giữ thư mục giải nén mới để tránh ghi đè bản review đã làm.

Viewer có 32 câu và bốn ID không đổi: COUNT missing, UDP incomplete, NULL technical_failed, AVG missing. Không thay các ID đó bằng một câu đạt. Trace bổ sung trong PDF chỉ giải thích kiến trúc, không được tính là nghiệm thu bộ demo.

## Kết quả nào đã đóng?

| Mốc | Producer/live | Commit công bố | CI đúng SHA |
|---|---|---|---|
| Calibration protocol 3 |38532017308|2f8234a3db086fb634b91dc2e5ba50d1a77db4fe|38684701741 SUCCESS|
| Evaluation 96 E0/E3 |38687383299|ff37425719b3009d33d166ae3faa19ccc35a09e8|38698148403 SUCCESS|
| R1 generalization120 |38699129318|aea0b9b2197db69ba45727142b2fd5c5c3dbd58f|38701290199 SUCCESS|
| Pipeline 32 |38699219559 FAILURE|Gói hiện tại giữ partial thật|CI phân phối phải xem đúng SHA chứa gói này|

CI công bố R1/evaluation: mỗi Python 3.11/3.12 có 1465 passed,7 skipped; required140 guards và 13 real-data checks đều 0 skip. CI xanh của gói nguồn không biến workflow pipeline thất bại thành pipeline đạt.

R1 là decision-only119/120, không phải thực thi120 cuộc điều tra SOC. IOC ởgen_096 dài 66 thay vì64 ký tự do thêm hai `e`; đây là đính chính cho diễn giải “thay một ký tự” trong REPORT.md của lần công bố R1. Xem [đính chính](../../results/evaluation_v1/r1/generalization_v1_20261015/ANALYSIS_CORRECTION.md). Output, matcher và điểm119/120 không đổi. Bộ authored có họ/template liên quan nên chưa đại diện cho toàn bộ SOC.

Evaluation E0 đạt 69/96, E3 đạt 17/96. Active selection vẫn E0 từ 48 calibration records; không tuning sau khi xem evaluation. Không dùng điểm23/32 CTU ở evaluation để điền vào pipeline.

## Vì sao pipeline chưa đạt?

Ởcase thứ 17, SQL thật trả 9780 dòng. Result tối thiểu177205 byte vượt ngưỡng32768 byte ở NetworkQueryPolicy.tool_response, trước assessment. Runner chỉ giữValueError và dừng toàn suite. Chẩn đoán dựa trên result thật và đúng source; không giả rằng log đã lưu message/stack chi tiết.

Trong16 case đã chấm,12 SQL đúng; 5 assessment qua xác minh dữ kiện; 3 luồng đạt kỹ thuật. Re-parse cho 9 lỗiUNKNOWN_OR_DUPLICATE_QUERY_OBSERVATION và 2 lỗiMISSING_QUERY_OBSERVATION. Contract không định vị row/cell làm nhiều diễn giải bảng bị từ chối. Ba kết quả này đo các khía cạnh khác nhau, không được gộp thành một tỷ lệ đẹp hơn.

Tất cả tỷ lệ chính thức của pipeline 32 cònnull. Một số gate=false trong partial là stage chưa có receipt, không phải một prediction sai được tạo ra để lấp dữ liệu thiếu.

## Người duyệt cần làm gì?

[Queue 3 case](../../results/evaluation_v1/text2sql_integration_v1/pipeline_protocol3_20261015/human_review_queue.json) chỉ là hàng đợi, chưa có quyết định. Đọc câu hỏi, SQL, typed result, evidence, raw assessment, verification và limitations. Chỉ chấp thuận khi kết luận có căn cứ; nếu chưa đủ thì rejected/escalated cùng lý do.

Dùng JSON giải nén từ ZIP để tránh CRLF của Git Windows làm đổi hash. Ví dụ:

```powershell
python -m scripts.review_vinsoc_query_case .\vinsoc_offline_demo\live\E0_ctu_cross_09368110b7091cb8.json --output .\reviews\ctu_cross_09368110b7091cb8.json
```

Người duyệt tự nhập tên, decision, rationale và UTC thực tế. CLI không xác thực danh tính ngoài hệ thống; receipt chứng minh những gì người nhập khai báo và hash của case. Không tự ký thay. Review ba case này không tự đóng gate bốn demo cố định.

SOC 128 còn 0/12 review nguồn và thiếu SOC_E2E_GATES_JSON; preflight38688783572 dừng trước SDK,0 request/0 phí. Review nguồn nằm ởsource_audit_queue.json vàsource_audit_pack.json củaresults/evaluation_v1/soc_traces_v1. Quyền ngân sách mới không tạo ra bằng chứng review còn thiếu.

## Thứ tự công việc còn lại

1. Chốt protocol mới cho phần bằng chứng vào prompt: giới hạn projection, bảo toàn full typed result/hash, địa chỉ row/cell và biểu diễn kết quả rỗng. Kiểm bằng chính result UDP9780 dòng và 16 native assessment đã có.
2. Thiết kế xử lý lỗi từng case và continuation có ledger/idempotency. Chứng minh không gửi lại case hoặc double-charge; không reset window cũ hoặc mở run khác để chọn output đẹp.
3. Khóa source/config, yêu cầu selection/calibration và phạm vi phép đo của phiên bản mới trước API. Giữ toàn bộ kết quả protocol 3 như lịch sử; không vá source đã chấm rồi gán điểm cũ cho bản mới.
4. Người thật duyệt các case đủ kỹ thuật, và 12 review nguồn cho SOC. Chỉ mở các scope khi đủ gate cụ thể, không chỉ vì còn ngân sách.
5. Bộ matched 8 cũ và independent holdout tiếp tục deferred. R1 authored120, R2 public-dev96 và pipeline dùng CTU 32 không tự trở thành holdout độc lập.

## Kiểm lại và chi phí

Từ checkout Linux giữ đúng byte Git:

```bash
python results/evaluation_v1/r1/generalization_v1_20261015/verify.py
python results/evaluation_v1/text2sql_integration_v1/evaluation_protocol3_20261015/verify.py
python results/evaluation_v1/text2sql_integration_v1/pipeline_protocol3_20261015/verify.py
python -m scripts.verify_query_preservation
```

Các auditor không gọi SDK hoặc SQL. Hash manifest ở từng gói giữ byte artifacts. report.json.gz lossless; native_io.zip củaR1 chứa120 request/120 response gốc. Private ledger/gates/account không được chép wholesale lên repo.

Bản PDF có source tác giả tại build_vinsoc_official_experiments_report.py: chạy từ repo root với ReportLab và DejaVuSerif fonts. Chạy lại phần soạn báo cáo không gọi mô hình.

Hai scope chạy thêm sau khi tiếp tục chat là R1120 và pipeline50: **170 requests thật,0,08483870USD**. Tính cảcalibration protocol 3 vàevaluation đã có:892 responses,0,95400045USD cho bốn scope được liệt kê. Query canonical ledger1,33381910USD; R1 mới0,04673480USD làledger riêng. Không unknown cost hoặc pending exposure. Đây không phải tổng hóa đơn mọi lượt R1/SOC lịch sử hoặc số dư tài khoản nhà cung cấp.

Xem delivery_receipt.json, public_cost_summary.json, evidence_ci_receipts.json vàpreservation.json trongresults/evaluation_v1/text2sql_integration_v1/release_20261015. Release cuối, pipeline 32 và bốn demo vẫn mở gate; không ghi COMPLETE.
