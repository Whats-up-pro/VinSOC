# VinSOC — kịch bản demo cho mentor

Gói này xem lại artifacts của các lượt model đã chạy thật. Việc tạo gói không gọi API, không tạo prediction, không tạo human review và không sửa code. Bản sao query giữ nguyên bytes nguồn; xem `manifest.json`.

## Mục tiêu và phạm vi

Trong 20–25 phút, mentor thấy: chọn đúng tool theo dữ liệu đầu vào; một luồng query có model/API/DB/evidence/assessment thật; một luồng SOC biết báo thiếu bằng chứng; các lỗi được giữ lại; và vai trò người duyệt.

Đây chưa phải nghiệm thu đủ bốn query demo hoặc toàn bộ 32 pipeline cases. Một query có record, 31 missing. Runner ghi `technical_complete_awaiting_human`, nhưng reporter `/32` hiện ghi `technical_failed` vì factual verification. Không che hoặc đổi trạng thái này.

## 1. Mở màn — 2 phút

Lời dẫn: “VinSOC hỗ trợ analyst điều tra: model chọn công cụ, công cụ đọc dữ liệu, kết quả trở thành bằng chứng, model tạo nhận định có dẫn chứng, rồi người thật quyết định. Chúng tôi giữ cả lỗi và phần thiếu để kiểm lại được.”

Mở `query.html` cùng `outcome_audit.json`. Nêu SQL result và reporter status là hai gate khác nhau.

## 2. Các case routing chính — 4 phút

Mở artifact `results/evaluation_v1/r1/r1_a1_dev_v2_852e543.json`, đối chiếu câu hỏi/expected calls trong `evaluation/tool_calling/benchmarks/dev/`.

| Case | Nhánh cần thể hiện | Giải thích cho mentor |
|---|---|---|
| case_001 | network | Hỏi tần suất kết nối thì cần flow telemetry. |
| case_004 | CTI | Chỉ có domain, không tự tạo IP để query flow. |
| case_003 | endpoint | DLP trên host cần endpoint context. |
| case_005 | CTI + network + endpoint | Có IOC và host pivot nên có thể chọn đủ ba tool. |
| case_007 | CTI + endpoint | Có domain/host nhưng thiếu resolved IPv4. |
| case_022 | no-tool | Hỏi khả năng công cụ thì không cần lookup. |
| case_002 | lỗi routing thật | Gold yêu cầu CTI, model đã chọn network. |

Những records này chứng minh quyết định routing, không chứng minh ba tool đã cùng thực thi trong incident thật. R1 dev 22/24; giữ caveat adjudication và holdout pending trong winner lock.

## 3. Một luồng end-to-end query — 7 phút

Mở `query.html` và `E3_ctu_cross_708b66575657429a.json`. Đi lần lượt:

1. Câu hỏi nguyên văn: đếm IP đích xuất hiện trong cả S5 và S7, sau hai mốc thời gian riêng; strict boundary dùng `>`.
2. Native routing: model chọn `network_query`, giữ nguyên câu hỏi trong arguments.
3. Grounding: `generation.trajectory` tra `source_dataset` và `protocol`; giá trị thật là `ctu13_s5`, `ctu13_s7`, `TCP`, có catalog evidence.
4. Candidate SQL đầu dùng `UNION ALL` bị semantic audit chặn: hai phép đếm riêng không giải câu hỏi giao hai tập.
5. Candidate sau dùng hai correlated `EXISTS`, ràng buộc cùng một destination IP.
6. Worker chạy trên DB thật: `metadata.query_execution`, `BIGINT`, rows `[[459]]`, không truncated.
7. Evidence `ev_bf7ff9fc_2` ghi execution; evidence `ev_03d85032_3` ghi kết quả và liên kết về execution.
8. Assessment dẫn hai evidence ID; observations ghi 459. Risk là UNKNOWN vì số lượng không chứng minh độc hại.
9. Score SQL đúng, independent replay đúng. Human chưa review. Reporter factual gate đang fail.

Lời giải thích dễ hiểu: “Câu hỏi tìm những địa chỉ xuất hiện ở cả hai tập. SQL đầu đếm riêng từng tập nên sai ý nghĩa. Pipeline yêu cầu model sửa; SQL sau kiểm cùng một địa chỉ có mặt ở cả hai tập và trả 459. Kết quả có nguồn và hash để đối chiếu, nhưng chưa cho biết các IP là độc hại.”

Run có 7 responses API thật: routing 1, linker 3, generator 2, assessment 1. Chi phí riêng run: $0.00739705. Workflow: https://github.com/Whats-up-pro/VinSOC/actions/runs/38338493466.

## 4. Bốn query đã chọn — 2 phút

| Case ID | Ý nghĩa | Trạng thái |
|---|---|---|
| ctu_cross_708b66575657429a | Giao tập IP, DISTINCT, strict time | Có record; reporter technical_failed |
| ctu_cross_66b8e92a76c3359b | UDP có ở S5 nhưng không có ở S7, bỏ trùng | Missing |
| ctu_cross_3f659571f998adb0 | Nhóm protocol, cả hai byte fields NULL, sắp xếp | Missing |
| ctu_cross_bce6d3679ade4cd6 | AVG nhóm lớn hơn AVG toàn S7, sắp xếp | Missing |

Nguồn: `results/evaluation_v1/text2sql_integration_v1/demo_selection.json`. Không thay case hoặc tự điền SQL/result cho ba case thiếu. Muốn đủ bốn API traces cần runner phù hợp, scope mới và preflight mới.

## 5. SOC thiếu bằng chứng — 4 phút

Mở `results/evaluation_v1/soc_traces_v1/demo_e2e/SCT-087094_S1.html`.

Alert domain enumeration trên WKS-034 → model gọi soc_search_events → no_match → model gọi soc_get_context process_tree → unavailable → model trả insufficient_evidence → analyst review pending.

Lời dẫn: “Không tìm được event không có nghĩa host sạch. Không có process tree là thiếu dữ liệu. Hệ thống phải nêu hạn chế và yêu cầu điều tra thêm.”

Gắn nhãn rõ: dữ liệu synthetic, API model thật. Có 3/3 responses, $0.0028932; một case integration, không phải kết quả suite. Nguồn: `results/evaluation_v1/soc_traces_v1/demo_execution_receipt.json`. Workflow: https://github.com/Whats-up-pro/VinSOC/actions/runs/37875105762.

## 6. Edge cases — 3 phút

- Wrong SQL semantics: candidate UNION ALL của run10 bị chặn; accepted candidate dùng EXISTS.
- No final SQL: mở audit run9 tại `single_demo_full_e2e_9_20261013/outcome_audit.json`; linker hết output tokens, không DB execution/assessment.
- Missing data: SOC no_match khác unavailable; cả hai không đủ chứng minh benign.
- Reporter mismatch: typed result lưu columns/rows nhưng reporter tìm field trực tiếp trong evidence.data. Xem `evaluation/finalization/query_pipeline_reporting.py` dòng 84–95 và case JSON phần evidence/query_policy. Giữ factual=false và technical=false.
- Guard tests: người dùng đã chạy 82 tests, gồm exact question, selection, preflight, CTI semantics, report citations, SQL safety và semantic shape. Đây là regression tests; không phải 82 model cases.

Worker boundary: mở receipt `results/evaluation_v1/text2sql_integration_v1/offline_release_20261010/r2_independent_kernel_observation.json` và required Linux CI. Không dùng trường isolation tự khai làm chứng cứ duy nhất; không suy Windows skip thành pass.

## 7. Kết luận — 1 phút

“Đã có luồng model/API/DB/evidence/assessment thật và các guard kiểm được. Đã giữ ví dụ model sai và thiếu dữ liệu. Còn thiếu ba query demo, reporter factual gate, human review và các suite đầy đủ. Chúng tôi chưa công bố COMPLETE cho calibration/evaluation/pipeline.”

## Lệnh mở gói

```powershell
Set-Location D:\VINUNI_AI2026\Phase3_VinSOC
Start-Process 'results/mentor_demo_20261013_104603/query.html'
Start-Process 'results/evaluation_v1/soc_traces_v1/demo_e2e/SCT-087094_S1.html'
```

## Việc cần làm để demo đủ case có API thật

1. Cho phép thay đổi code: sửa factual report mapping, mở runner cho đúng bốn ID đã pin, giữ mọi guard/ledger/checkpoint; không thay gold/questions/prompts/scorer lịch sử.
2. Kiểm targeted/full/required real-data và CI đúng SHA mới; preflight-only 0 calls.
3. Tính cận chi phí mới cho ba case còn thiếu, đối soát allocation/unknown exposure và lập scope mới. Quyền của run10 không tự mở scope khác.
4. Chạy các case được cấp quyền; giữ failed/partial nếu model lỗi. Không cam kết mọi output sẽ đúng.
5. Người thật review; render đủ bốn trạng thái từ artifacts thật và rehearsal bài nói trên.

Không có bước nào trong danh sách này đã được thực thi hoặc tự đánh đạt bởi gói ngoại tuyến.
