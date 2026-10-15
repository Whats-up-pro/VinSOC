# Pipeline E0 ngày 15/10/2026: dở dang, chưa nghiệm thu 32 câu

Lượt chính thức đi qua public `investigate_query` và dùng E0 đã khóa từ calibration. Có **16 case hoàn tất, 1 case dở dang và 15 case chưa chạy**. Window đã consumed; không chạy lại, không lấy SQL hay điểm của evaluation để lấp chỗ thiếu.

| Hạng mục | Quan sát trên mẫu số 32 | Điều cần hiểu |
|---|---:|---|
| Integrated EX | 12 đúng; 16 đã chấm | Chưa đủ dữ liệu để công bố EX cho toàn bộ 32 |
| Native routing có trace đầy đủ | 16 | Case dở dang có native call nhưng thiếu case trace hoàn chỉnh |
| Dùng shared runtime đúng câu hỏi | 17 | Bao gồm checkpoint dở dang |
| Provenance hoàn chỉnh | 16 | Result của case17 còn lưu, chưa có case receipt hoàn chỉnh |
| Factual verification | 5 | Trong 16 assessment thật đã trả về |
| Technical workflow | 3 | Còn chờ người thật duyệt |
| Human approved | 0 | Không tự ký hoặc thay người duyệt |

Các tỷ lệ chính thức vẫn là `null`, mẫu số luôn 32. Bộ báo cáo gốc coi một số stage thiếu ở partial như gate=false; điều này không phải bằng chứng rằng mô hình đã viết một assessment sai ở stage chưa được gọi.

## Vì sao dừng

Case `ctu_cross_66b8e92a76c3359b` hỏi danh sách UDP destination IP ở scenario5 nhưng không ở scenario7. SQL thật đã chạy và trả **9.780 dòng**, không bị row truncation. Riêng phần result cần tối thiểu **177.205 byte**, vượt ngưỡng **32.768 byte** tại `NetworkQueryPolicy.tool_response`, trước request assessment. Luồng gọi truyền ngoại lệ ra runner, làm dừng cả suite thay vì giữ lỗi ở một case rồi xử lý phần còn lại.

Receipt gốc chỉ giữ `ValueError`, không giữ message/stack. Chẩn đoán suy ra và tái hiện điều kiện chặn từ typed result thật và đúng source đã chạy; không giả rằng message chi tiết đã có trong log. Xem `diagnostic.json`, checkpoint `live/E0_ctu_cross_66b8e92a76c3359b.json` và giới hạn trong `agent/network_query_policy.py`.

Re-parse ngoại tuyến 16 native assessment với đúng evidence đã lưu cho kết quả: **5 OK, 9 UNKNOWN_OR_DUPLICATE_QUERY_OBSERVATION, 2 MISSING_QUERY_OBSERVATION**. Contract hiện chỉ chấp nhận một field/value xác định; output nhiều dòng lặp cùng tên cột thiếu địa chỉ dòng nên không qua xác minh. Hai trường hợp thiếu observation cũng được giữ. Không sửa parser/scorer/prompt sau khi thấy output để đổi điểm lượt này.

## Bốn demo ID không đổi

| Demo | ID | Trạng thái |
|---|---|---|
| COUNT | ctu_cross_708b66575657429a | missing |
| UDP | ctu_cross_66b8e92a76c3359b | incomplete |
| NULL | ctu_cross_3f659571f998adb0 | technical_failed |
| AVG | ctu_cross_bce6d3679ade4cd6 | missing |

Chưa có demo nào trong bốn ID đáp ứng gate kỹ thuật và review. Ba trace khác đạt kỹ thuật được lưu để phân tích và review, không thay vào danh sách demo đã khóa.

## Bằng chứng và chi phí

50/50 responses: routing17, R2 SQL17, assessment16; **0,03810390 USD**, input52.875/output10.663/cached0. Không unknown cost hoặc pending exposure. Query ledger tích lũy **1,33381910 USD**. Mỗi khoản phí có case/condition/role/internal request/provider request/response ID và usage thật.

Producer `ff37425719b3009d33d166ae3faa19ccc35a09e8`; [CI38698148403](https://github.com/Whats-up-pro/VinSOC/actions/runs/38698148403), [preflight38698575633](https://github.com/Whats-up-pro/VinSOC/actions/runs/38698575633), [live38699219559](https://github.com/Whats-up-pro/VinSOC/actions/runs/38699219559). ZIP gốc633.998byte có digest đã tải và đối soát độc lập trong receipt. JSON gốc/17 bindings giữ nguyên byte; report gzip lossless. `native_responses.json.gz` là projection công khai có đủ response SDK thật, không chép wholesale private journal hoặc gate/account files.

Xem `pipeline_viewer.html` hoặc giải nén `offline_demo_bundle.zip`. Viewer chỉ đọc artifacts, giữ đủ32 câu, bốn ID cố định và cả native output trước parse; không gọi API/DB. Preview của case dở dang ghi rõ chỉ 5/9780 dòng, full result còn trong checkpoint JSON.

Kiểm lại từ repo Linux/checkout giữ byte Git:

```bash
python results/evaluation_v1/text2sql_integration_v1/pipeline_protocol3_20261015/verify.py
```

Audit tính lại báo cáo và usage từ records thật; chỉ cho sai số cộng float tối đa1e-12 giữa Python3.11/3.12. Không gọi SDK hay chạy SQL. Chênh lệch API workflow failure và offline audit PASS được giữ: audit PASS chỉ xác nhận partial trung thực.

## Việc cần làm sau

Thiết kế phiên bản mới cho projection bằng chứng có giới hạn, giữ full typed result và hash ngoài prompt; citation phải định vị được row/cell hoặc biểu diễn empty-result. Thêm xử lý lỗi từng case và cơ chế tiếp tục có ledger, bảo đảm không gửi trùng. Các thay đổi cần protocol/source identity mới và kiểm thử từ result thật; không nới payload hoặc sửa version đang khóa để cứu lượt này. Independent holdout và matched8 cũ vẫn deferred.

`human_review_queue.json` chỉ liệt kê3 case đủ kỹ thuật, không phải quyết định duyệt. Người duyệt tự nhập identity/decision/rationale/UTC bằng CLI. Với Windows, dùng các JSON giải nén từ bundle để giữ byte LF gốc; không ký review từ file đã đổi newline. Review của3 case này không tự đóng gate bốn demo cố định.
