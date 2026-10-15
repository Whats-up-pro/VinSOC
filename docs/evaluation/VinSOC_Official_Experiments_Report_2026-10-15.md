# VinSOC - Báo cáo thực nghiệm chính thức ngày 15/10/2026

Bản cập nhật ngày 15/10/2026 cho mentor và báo cáo cuối khóa. Nguồn là các lượt API thật đã lưu; mọi chỗ thiếu vẫn được giữ để người xem đánh giá đúng mức độ hoàn thiện.

## 1. Hệ thống đã chứng minh được điều gì?

VinSOC đã có bằng chứng thật cho quyết định chọn tool của R1 và phép đo Text-to-SQL rộng hơn bộ tám câu ban đầu. R1 bổ sung đạt 119/120. Với R2, E0 đạt 69/96 và E3 đạt 17/96; E0 đã được chọn từ calibration trước khi chạy evaluation.

Luồng tích hợp cũng đã chạy thật từ câu hỏi qua tool call, SQL, DB và assessment. Tuy nhiên, lượt 32 câu dừng ở case thứ 17 do kết quả vượt giới hạn payload. Vì vậy có thể phân tích năng lực và lỗi của hệ thống, nhưng chưa được tuyên bố nghiệm thu đầy đủ pipeline hoặc bộ bốn demo đã khóa.

| Phạm vi | Bằng chứng hiện có | Trạng thái |
| --- | --- | --- |
| Calibration | 48/48 bản ghi thật | Đã khóa E0 |
| Evaluation R2 | 192/192 bản ghi thật | Đã đối soát và CI |
| R1 bổ sung | 120/120 phản hồi; 119 đúng | Đã đối soát và CI |
| Pipeline CTU32 | 16 hoàn tất; 1 partial; 15 thiếu | Chưa hoàn tất |
| SOC trace chính thức | 0/128; preflight không gọi API | Thiếu review nguồn/gates |

Không có mô hình nào được gọi lại để sửa một kết quả xấu. Khôi phục DB, gold SQL, prompt, scorer và hai ZIP đã pin được bảo toàn. Human review không được tự điền hoặc tự phê duyệt.


---

## 2. Kiến trúc chung và vị trí từng môđun

Hệ thống có hai kiểu đầu vào: cảnh báo/IOC cho điều tra SOC và câu hỏi ngôn ngữ tự nhiên cho nhánh query. Orchestrator điều phối công cụ, EvidenceStore giữ bằng chứng và liên kết nguồn, assessment tổng hợp diễn giải, còn kiểm chứng và người duyệt là hai bước riêng.

Luồng query: câu hỏi gốc → native routing → network_query → TextToSQLService(E0) → worker SQL cách ly → typed result/evidence → assessment → kiểm chứng → người duyệt.

Sơ đồ mô tả nhánh query đã thực thi trong lượt này. SQL của mô hình chỉ chạy trong worker tách biệt, DB chỉ đọc, có giới hạn mạng, bộ nhớ, CPU và thời gian. Bằng chứng cách ly đến từ các quan sát độc lập ở required CI jobs, không lấy field isolation do executor tự khai làm chứng minh.

R1 đo quyết định chọn ba tool SOC: cti_enrichment, network_investigation và endpoint_investigation. Benchmark R1 trả native calls nhưng không chạy công cụ sản xuất. Trong pipeline query, routing vào network_query được đo riêng; không dùng điểm R1 để suy ra điểm routing của pipeline.

R2 dùng cùng TextToSQLService và SqlExecutor ở benchmark và public investigate_query. Điều này nối phép đo SQL với luồng thật. Chia sẻ runtime không có nghĩa toàn bộ pipeline tự động đạt: routing, khả năng chuyển result sang assessment, kiểm chứng dữ kiện và người thật duyệt đều có thể thất bại độc lập.


---

## 3. R1: mạnh ở hợp đồng tool, còn rủi ro đối số

Từ câu yêu cầu gốc và schema công cụ, mô hình trả native tool calls. Runner chuẩn hóa đối số và đối chiếu với matcher/scorer đã khóa. Bộ bổ sung có 24 no-tool, 54 single-tool, 30 two-tool và 12 three-tool; bộ dev lịch sử vẫn được giữ riêng.

| Chỉ số | Kết quả | Ý nghĩa |
| --- | --- | --- |
| Trajectory success | 119/120 = 99,17% | Đúng cả tool và đối số |
| Wilson 95% | 95,43%-99,85% | Giả định độc lập |
| No-tool | 24/24 | Biết không gọi tool |
| Required/critical coverage | 154/155 | Mẫu số gồm mọi expected args |
| Native requests/phản hồi | 120/120 | Không retry; đủ ID/usage |

Case gen_096 cho thấy giới hạn thực tế: mô hình chọn đúng CTI và endpoint nhưng thêm hai ký tự e, làm IOC hash dài từ 64 thành 66 ký tự. Khi điều tra bảo mật, sai chuỗi định danh có thể dẫn tới truy vấn nhầm đối tượng. Tool-name F1 cao vì vậy không thay được kiểm tra đối số và nguồn IOC.

Scorer gốc đánh dấu case này không đạt. Trường thống kê cũ critical_arg_errors vẫn bằng 0 và error_summary rỗng do runner không gán lại field đó; audit đối chiếu từng match ghi rõ một critical mismatch (hash 64→66 ký tự), giữ nguyên artifacts và không sửa điểm lịch sử.

Độ chính xác cao áp dụng cho bộ được biên soạn và duyệt có các họ tình huống liên quan, chưa phải mẫu ngẫu nhiên đại diện toàn bộ SOC. Bộ dev lịch sử đạt 22/24, nhưng có 11 đáp án được điều chỉnh sau khi xem đầu ra. Không gộp hai bộ thành một mẫu 144 hoặc gọi đây là independent holdout.

Lượt mới tốn 0,04673480 USD; 88.185 input, 7.163 output, 0 cached token. Latency SDK p50 ≈ 0,959s và p95 ≈ 1,714s, không bao gồm toàn bộ gate/CI.


---

## 4. R2: đối chứng 96 câu cho thấy E0 phù hợp hơn

Calibration gồm 24 câu cho mỗi điều kiện; evaluation gồm 64 câu trên tám database ngoài SOC và 32 câu CTU. Tổng cộng có 192 bản ghi evaluation thật, chấm trên DB gốc bằng worker. Bộ evaluation dùng 9 database; 13 là tổng DB đã khôi phục cho cả calibration và evaluation.

| Tập đo | E0 | E3 |
| --- | --- | --- |
| Calibration 24 | 15/24 = 62,50% | 4/24 = 16,67% |
| External 64 | 46/64 = 71,875% | 10/64 = 15,625% |
| CTU32 | 23/32 = 71,875% | 7/32 = 21,875% |
| Tổng 96 | 69/96 = 71,875% | 17/96 = 17,708% |
| Calls / chi phí evaluation | 96 /0,07442350 USD | 482 /0,62127495 USD |

E0 sinh SQL trực tiếp từ schema. E3 thêm liên kết lược đồ và nhiều bước tool-assisted trước SQL. Dưới cùng hợp đồng giới hạn 1.000 output token và tối đa sáu call/case cho E3, chuỗi dài hơn tạo thêm điểm gãy thay vì cải thiện kết quả.

E3 có 52 INVALID_LINKED_SCHEMA, 21 MODEL_PARSE_ERROR; 17 trong 21 lỗi parse kết thúc vì chạm giới hạn output. Không quy cả 52 lỗi schema cho token cap. Phần lớn E3 không có final SQL, nên vấn đề chính xuất hiện trước bước thực thi DB.

Đối chứng theo cặp: E3 thắng 2, thua 54, hòa 40 so với E0. Chênh lệch E3-E0 là -54,17 điểm phần trăm; bootstrap theo database cho khoảng [-65,28; -43,75]. Kết quả ủng hộ lựa chọn E0 trong phạm vi bộ này, không chứng minh E0 vượt trội trên mọi miền.

EX so kết quả trên một snapshot; semantic test-suite accuracy chưa được đo. Các giá trị mặc định false/0 trong report gốc không phải một phép đo semantic mới. Các bảng trung bình theo database, miền dữ liệu, độ khó và đặc trưng SQL nằm trong JSON đầy đủ.


---

## 5. Pipeline: phân biệt SQL đúng và E2E đạt

Lượt chính thức gọi public investigate_query với câu hỏi nguyên gốc, E0 đã khóa và hash mã nguồn và dữ liệu khớp calibration. Có 50 phản hồi: 17 routing, 17 SQL và 16 assessment. Chi phí 0,03810390 USD, không unknown cost hay pending exposure.

| Chỉ số trên mẫu số 32 | Đã xác nhận | Cách đọc |
| --- | --- | --- |
| Integrated EX | 12 đúng; 16 đã chấm | Chưa tính tỷ lệ đủ 32 |
| Routing / runtime | 16 trace /17 dùng runtime | Partial không có trace trọn vẹn |
| Provenance / facts | 16 /5 | Facts dựa trên 16 assessment |
| Technical workflow | 3 | Cần người thật duyệt |
| Người duyệt chấp thuận | 0 | Không tự phê duyệt |

Case UDP thứ 17 trả 9.780 dòng, không bị cắt bớt dòng. Riêng result cần ít nhất 177.205 byte, vượt giới hạn 32.768 byte ở bước chuyển bằng chứng sang assessment. Ngoại lệ thoát khỏi case làm dừng suite. Receipt gốc chỉ giữ ValueError; kết luận payload dựa trên đối chiếu result thật với đúng nhánh code đã chạy.

Re-parse 16 assessment với đúng evidence lưu lại cho 5 OK, 9 UNKNOWN_OR_DUPLICATE_QUERY_OBSERVATION và 2 MISSING_QUERY_OBSERVATION. Các bảng nhiều dòng cần định vị row/cell; chỉ tên cột lặp lại không đủ để verifier xác nhận một giá trị cụ thể.

| Demo cố định | Trạng thái |
| --- | --- |
| COUNT -708b66575657429a | missing |
| UDP -66b8e92a76c3359b | incomplete |
| NULL -3f659571f998adb0 | technical_failed |
| AVG -bce6d3679ade4cd6 | missing |

Giữ nguyên cả bốn ID, không thay bằng case thành công. Tất cả tỷ lệ chính thức của pipeline còn null, mẫu số 32. Ba case đạt kỹ thuật ngoài bộ bốn chỉ phục vụ phân tích và review, không đóng gate demo.


---

## 6. Một trace thật để giải thích cơ chế

Ví dụ bổ sung: ctu_cross_09368110b7091cb8. Đây là trace đã lưu, không thay thế bốn demo ID. Câu hỏi yêu cầu đếm các cặp source/destination IP khác nhau của UDP ở CTU scenario 5, giữ ngữ nghĩa tuple DISTINCT với NULL của DuckDB.

Câu hỏi gốc: Count distinct source/destination IP pairs for UDP in CTU scenario 5, retaining NULL-containing pairs according to DuckDB tuple DISTINCT semantics.

Native routing truyền đúng câu hỏi vào network_query. SQL sau được TextToSQLService E0 sinh từ API.

```sql
SELECT COUNT(DISTINCT (src_ip, dst_ip)) AS distinct_udp_src_dst_pairs
FROM network_flows
WHERE protocol ILIKE 'udp'
  AND source_dataset LIKE '%5%';
```

| Typed result | Giá trị thật |
| --- | --- |
| Cột / kiểu | distinct_udp_src_dst_pairs /BIGINT |
| Số dòng / giá trị | 1 /38.695 |
| SQL EX / provenance /facts | Đạt các checks kỹ thuật đã lưu |

Trích nguyên văn assessment của mô hình: There are 38,695 distinct source/destination IP pairs for UDP traffic in CTU scenario 5, including pairs with NULL values, consistent with DuckDB tuple DISTINCT semantics.

Observation trỏ vào ev_8746607d_3, field distinct_udp_src_dst_pairs, value 38695. Result hash và execution lineage gắn SQL với snapshot. Validator kiểm lại dữ kiện có trong evidence; scorer đối chiếu kết quả SQL. Hai kiểm tra này không xác nhận toàn bộ ngữ nghĩa của lời diễn giải hoặc mức rủi ro bảo mật.

Trace hiện awaiting_human. Mô hình cũng nêu giới hạn snapshot tĩnh, phạm vi scenario 5/UDP và chưa kiểm chứng CTI/endpoint. Người trình bày nên mở native response, typed result và verification cạnh nhau; không nói một số đếm lưu lượng chứng minh có hoặc không có tấn công.

Viewer giữ toàn bộ chuỗi bằng chứng và raw response trước parse. Phần chưa chạy vẫn hiện thiếu; việc xem lại không gọi API.


---

## 7. Kết luận và thứ tự cải tiến

Ưu điểm rõ nhất là khả năng truy nguồn và kiểm tra lại: selection xuất phát từ 48 calibration bản ghi, evaluation có 192 bản ghi, R1 có 120 native phản hồi, và pipeline giữ cả checkpoint gây lỗi. DB thật và worker cách ly giúp phân biệt lỗi mô hình với lỗi thực thi; mô hình không được tự tạo evidence hoặc tự duyệt kết luận.

Giới hạn lớn nhất nằm ở hợp đồng tích hợp: bước chuyển result chưa có bản chiếu rút gọn và verifier chưa diễn đạt tốt bảng nhiều dòng hoặc kết quả rỗng. E0 có SQL đúng trong 12 case đã chấm của pipeline nhưng chỉ 3 case đạt toàn bộ kỹ thuật. Một chỉ số SQL riêng lẻ không đại diện chất lượng báo cáo cuối.

| Ưu tiên | Thay đổi cần thiết | Cách chứng minh |
| --- | --- | --- |
| 1 | Giới hạn phần kết quả vào prompt; giữ result đầy đủ và hash | Result UDP9780 dòng; không tăng cap ngầm |
| 2 | Dẫn chứng theo dòng/ô và kết quả rỗng | Re-parse 16 native assessment, giữ lỗi cũ |
| 3 | Lỗi từng case và resume có ledger, chống gửi trùng | Partial 1+missing 15; không reset window |
| 4 | Sửa telemetry lỗi R1 trong phiên bản sau | gen_096:matcher≠legacy error field |
| 5 | Đánh giá độc lập và review nguồn SOC | Không gọi bộ authored là holdout |

Các thay đổi có ý nghĩa với prompt/runtime phải là protocol phiên bản mới, được khóa trước phép đo mới; không vá ngược source đã chấm hoặc chạy lại lịch sử để cứu điểm. Thực nghiệm SOC128 còn chờ đủ 12 review nguồn (hiện 0/12) và bộ gate riêng. Tập kiểm tra độc lập và đối chứng matched 8 cũ vẫn để sau.

Bốn lượt được trình bày (calibration protocol 3, evaluation, R1 mới, pipeline partial) có 892 phản hồi, tổng 0,95400045 USD. Riêng query canonical ledger tích lũy 1,33381910 USD; R1 mới là 0,04673480 USD riêng. Đây là đối soát usage đã lưu, không phải tuyên bố số dư tài khoản hay toàn bộ hóa đơn lịch sử.


---

## 8. Bằng chứng và cách mở khi báo cáo

Nên chiếu kết quả trước, sau đó giải thích kiến trúc và trace. Nếu mở viewer, nói rõ đang xem lại lượt API thật đã lưu. Tình trạng pipeline partial và bốn demo ID cần được nói ngay từ đầu để người nghe không nhầm một trace minh họa với nghiệm thu đầy đủ.

Trên Windows, từ thư mục repo, giải nén bundle rồi mở index.html. Việc xem không cần API key, không chạy DB và không phát sinh phí. JSON trong ZIP giữ nguyên byte Linux để có thể đối soát hash và ký review đúng receipt.

```sql
Expand-Archive .\results\evaluation_v1\text2sql_integration_v1\pipeline_protocol3_20261015\offline_demo_bundle.zip -DestinationPath .\vinsoc_offline_demo
Start-Process .\vinsoc_offline_demo\index.html
```

Calibration: https://github.com/Whats-up-pro/VinSOC/actions/runs/38532017308

2f8234a3db086fb634b91dc2e5ba50d1a77db4fe /CI 38684701741

Evaluation: https://github.com/Whats-up-pro/VinSOC/actions/runs/38687383299

ff37425719b3009d33d166ae3faa19ccc35a09e8 /CI 38698148403

R1 bổ sung: https://github.com/Whats-up-pro/VinSOC/actions/runs/38699129318

aea0b9b2197db69ba45727142b2fd5c5c3dbd58f /CI 38701290199

Pipeline partial: https://github.com/Whats-up-pro/VinSOC/actions/runs/38699219559

producer ff374257; CI 38698148403; không COMPLETE

Gói dữ liệu có receipt, manifest SHA-256 và verify.py ở từng thư mục kết quả. Auditor đọc artifacts, tính lại thống kê/usage và không gọi mô hình hoặc SQL. Bản report gốc giữ nguyên; kiểm chứng bổ sung nằm trong audit_summary và diagnostic.

CI của producer và các commit công bố evaluation/R1 đều đạt trên Python 3.11/3.12: full 1465 passed, 7 skipped mỗi phiên bản; required 140 guards và 13 real-data checks mỗi phiên bản đều 0 skip. Các skip full suite không được dùng làm bằng chứng cho job bắt buộc. CI của gói bàn giao cuối cần đối chiếu đúng SHA trên GitHub Actions.

Kết luận hiện tại: R1 và R2 đã có phép đo rộng hơn và bằng chứng có thể kiểm lại. Pipeline đã chứng minh có luồng thực thi thật, đồng thời bộc lộ lỗi tích hợp cụ thể; chưa đủ điều kiện tuyên bố hoàn tất 32 case, bốn demo hoặc release cuối.
