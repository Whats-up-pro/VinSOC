# Thiết kế mở rộng đánh giá R1 Tool Calling

**Ngày:** 09/10/2026  
**Trạng thái:** Phương án tích hợp đã được duyệt; chờ xác nhận bản đặc tả cập nhật trước khi lập kế hoạch triển khai
**Mục tiêu:** Mở rộng chính môđun R1 Tool Calling hiện có bằng một split đánh giá mới có sức khái quát tốt hơn, không thay đổi hoặc chấm lại kết quả lịch sử.

## 1. Phán quyết và phạm vi

Kết quả `r1_a1_dev_v2` hiện tại, GPT-4.1 Mini đạt 22/24, tiếp tục là bằng chứng phát triển và kiểm thử hồi quy. Nó không được đổi mẫu số, sửa gold hoặc diễn giải thành hiệu năng tổng quát. Tám ca frozen hiện có tiếp tục được giữ nguyên, không đọc kết quả, không chạy model và không nhập vào bộ mới.

Tạo split `generalization_v1` gồm 120 ca mới ngay trong `evaluation/tool_calling`. Split dùng chung `DecisionRunner`, matcher, scorer, production schemas, provenance và CI của R1 hiện tại. Nó chỉ có case lock, quyền chạy và kết quả thống kê riêng để giữ tính độc lập với dữ liệu phát triển.

Split mới vẫn đo native tool call một lượt trên đúng ba production schema:

- `cti_enrichment`;
- `network_investigation`;
- `endpoint_investigation`.

Track không đo thực thi công cụ, điều tra nhiều lượt hoặc thành công đầu-cuối. Các phần đó phải có phép đo riêng và không được cộng vào điểm R1.

## 2. Các lựa chọn đã cân nhắc

### A. Chỉ tăng tập dev hiện tại

Không chọn. Cách này làm mất đường ranh giữa dữ liệu đã dùng để điều chỉnh và dữ liệu dùng để đánh giá, đồng thời biến 22/24 thành một kết quả không còn cùng hợp đồng.

### B. Chỉ dùng tám ca frozen hiện tại

Không chọn. Với tám ca, mỗi ca làm điểm thay đổi 12,5 điểm phần trăm; ngay cả 8/8 cũng có khoảng tin cậy 95% quá rộng để kết luận tổng quát.

### C. Bổ sung split 120 ca vào R1 hiện tại và khóa riêng trước khi chạy

Chọn. Cách này tái sử dụng đúng mã và production contract hiện có, đồng thời giữ split mới độc lập về dữ liệu, khóa và kết quả. Nó giữ nguyên lịch sử, cho phép báo khoảng tin cậy hữu ích hơn và tạo đủ mẫu cho các nhóm hành vi quan trọng. Nếu tỉ lệ quan sát quanh 90%, 120 ca cho sai số Wilson 95% xấp xỉ 5,4 điểm phần trăm ở mức toàn bộ tập.

## 3. Cấu trúc 120 ca

Phân bổ bắt buộc:

| Nhóm quyết định | Số ca | Phân bổ |
|---|---:|---|
| Không gọi công cụ | 24 | yêu cầu khái niệm, thiếu bằng chứng, yêu cầu dừng, loại đầu vào không hỗ trợ |
| Một công cụ | 54 | 18 CTI, 18 network, 18 endpoint |
| Hai công cụ | 30 | 10 CTI+network, 10 CTI+endpoint, 10 network+endpoint |
| Ba công cụ | 12 | CTI+network+endpoint |
| **Tổng** | **120** | mỗi ca chỉ thuộc một hàng chính |

Ít nhất 30 ca phải đồng thời mang nhãn robustness, bao phủ các tình huống sau mà không tạo thêm mẫu số:

- IOC sai hoặc không đầy đủ;
- loại đầu vào không được công cụ hỗ trợ;
- yêu cầu mâu thuẫn hoặc thiếu pivot;
- bẫy gọi thừa, gọi lặp;
- sai hoặc nhầm giá trị tham số;
- chỉ dẫn cố ép gọi công cụ không phù hợp;
- nội dung chèn chỉ dẫn độc hại trong phần dữ liệu;
- yêu cầu cần từ chối hoặc cần hỏi thêm thông tin.

Mỗi nhóm chính phải có basic, intermediate và advanced. Không được dùng một IOC, hostname, nội dung cảnh báo hoặc cốt truyện giống nhau cho nhiều ca. Các bản viết lại của cùng một template không được tính là ca độc lập.

## 4. Nguồn và tính độc lập

Nguồn chuẩn để xác định khả năng công cụ là `agent.tools.get_tool_schemas()` và hành vi production tương ứng. Ca có thể được gợi ý từ các cảnh báo SOC công khai hoặc từ các family trong `soc-agent-traces-100k`, nhưng phải viết lại theo năng lực thật của VinSOC và phải ghi nguồn gợi ý.

`soc-agent-traces-100k` là dữ liệu tổng hợp, có tool vocabulary khác và có dấu hiệu oracle/leakage. Vì vậy:

- không ánh xạ tự động chín tool của nguồn thành ba tool VinSOC;
- không lấy `success`, `decision`, `decisive` hoặc tool sequence của nguồn làm gold;
- không gọi ca phái sinh là incident thật;
- không dùng cùng scenario/template/entity giữa tập soạn và tập đánh giá khóa;
- không đưa nội dung chỉ có trong gold vào prompt của model.

Mỗi ca lưu `source_kind`, `source_reference`, `scenario_family`, `template_family` và `coverage_tags` trong manifest. Runner chỉ đọc request và production schemas.

## 5. Soạn gold và duyệt độc lập

Gold phải được xác định trước khi xem output của model được đánh giá. Mỗi ca cần hai người duyệt độc lập:

1. Người duyệt A chọn tool và required/critical arguments từ request và production schema.
2. Người duyệt B thực hiện độc lập, không xem quyết định của A hoặc gold do tác giả đề xuất.
3. Bất đồng được đưa vào hàng đợi phân xử và lưu lý do.
4. Chỉ ca có trạng thái `approved` và đủ hai chữ ký định danh mới được khóa.

Candidate chỉ chứa request và metadata nguồn, chưa chứa final gold. Hai review record được lưu riêng; builder chỉ tạo `expected_calls` sau khi hai review khớp hoặc bất đồng đã được người phân xử giải quyết. Agent triển khai có thể tạo candidate, kiểm tra cấu trúc và lập gói duyệt, nhưng không được tự phê duyệt gold. Không được sửa gold sau khi có output model. Nếu gold sai được phát hiện sau khi chạy, phải tạo phiên bản mới và giữ nguyên artifact cũ.

## 6. Tích hợp vào môđun hiện có

Không tạo runner hoặc scorer cạnh tranh với R1 hiện tại. Không sửa 24 ca dev hoặc tám ca frozen. Cấu trúc sau triển khai:

- `evaluation/tool_calling/authoring/generalization_v1/candidates/`: 120 request và metadata nguồn, chưa có final gold và chưa được phép chạy;
- `evaluation/tool_calling/authoring/generalization_v1/reviews/`: hai bộ quyết định độc lập và biên bản phân xử;
- `evaluation/tool_calling/benchmarks/generalization_v1/`: split chính thức chỉ được tạo từ candidate đã duyệt;
- `evaluation/tool_calling/benchmarks/generalization_v1/GENERALIZATION.lock`: số ca, hash, phân bổ, nguồn, reviewer receipt và trạng thái khóa;
- `evaluation/tool_calling/generalization.py`: kiểm tra chất lượng, review gate, lock, khoảng tin cậy và so sánh paired;
- `evaluation/tool_calling/decision_runner.py`, `matching.py`, `metrics.py` và provenance hiện có: được tái sử dụng; chỉ mở rộng giao diện chung khi cần;
- `results/evaluation_v1/r1/generalization_v1/`: preflight, artifact chạy và báo cáo; không chứa output giả.

CLI hiện có được mở rộng bằng các lệnh `list`, `preflight` và `run` cho `generalization_v1`. Lệnh `run` phải kiểm đầy đủ gate trước khi tạo provider hoặc gửi request. `dev`, `frozen` và `generalization_v1` cùng đi qua một đường chạy; split mới không được có đường tắt hoặc scorer riêng.

## 7. Gate trước khi gọi API

Mọi gate sau phải đạt:

1. Đủ đúng 120 ca và đúng phân bổ 24/54/30/12.
2. Case ID, normalized request và critical pivot tuple không trùng; source scenario/row ID phải riêng khi nguồn cung cấp ID, còn nhiều ca được phép cùng trích một dataset hoặc tài liệu nguồn.
3. Báo cáo near-duplicate không còn cặp chưa xử lý.
4. Mọi critical value xuất hiện trong input model; không lộ field chỉ dành cho gold.
5. Tool và argument tồn tại trong production schema hiện hành.
6. Ít nhất 30 ca robustness và mọi nhóm bắt buộc đều có mẫu.
7. Hai người duyệt đã duyệt toàn bộ 120 ca; không còn bất đồng mở.
8. Manifest, scorer, prompt, schema và case directory đã khóa hash.
9. Cấu hình model, giới hạn output, zero retry, giá và ngân sách đã được ghi.
10. Có quyền rõ ràng cho đúng một suite. Không dùng quyền của R1 frozen, R2 hoặc E2E.

Gate thất bại phải dừng trước provider creation. Không tự retry hoặc giảm mẫu số.

## 8. Chỉ số và phân tích thống kê

Chỉ số chính là Single-Turn Case Success. Báo cáo bắt buộc gồm:

- số đạt/tổng và khoảng tin cậy Wilson 95%;
- Tool-Set Exact Match;
- Exact-Call Precision, Recall và F1;
- no-tool accuracy;
- forbidden/extra/duplicate call rate;
- required và critical argument accuracy trên các call đã ghép;
- required và critical argument coverage trên toàn bộ gold call;
- provider/execution error rate;
- kết quả theo nhóm chính, độ khó, tool, source kind và robustness tag;
- latency, token và chi phí thực tế.

Các call trong cùng ca không được xem là quan sát độc lập khi tính khoảng tin cậy. So sánh hai model trên cùng 120 ca phải dùng bảng paired wins/losses/ties và exact McNemar test. Không tuyên bố model tốt hơn chỉ từ chênh lệch điểm.

Báo cáo R1 chung hiển thị `dev v2: 22/24` và `generalization_v1: x/120` ở hai hàng riêng. Không cộng thành `(22+x)/144`, vì dev đã được dùng để phát triển và 11/24 gold từng được phân xử sau khi xem output model. Split mới bổ sung bằng chứng cho cùng môđun nhưng không thay mẫu số lịch sử.

Một tập ổn định 30 ca phát triển có thể chạy ba lượt để đo dao động. Bộ 120 ca khóa chỉ chạy theo quyền đã cấp; không chạy lại để cứu điểm.

## 9. Điều kiện kết luận

Kết quả được phép gọi là bằng chứng tổng quát trong phạm vi **single-turn native tool decision trên ba production tools** khi:

- suite chạy đủ 120 ca, không lỗi thiếu artifact;
- lower bound Wilson 95% của case success đạt ít nhất 80%;
- không có forbidden tool violation;
- không có nhóm chính nào bị bỏ trống hoặc bị giảm mẫu số;
- provenance, cost và per-case traces đầy đủ;
- không có thay đổi prompt/schema/gold/scorer sau khi mở output.

Nếu lower bound dưới 80%, vẫn bàn giao kết quả thật và phân tích lỗi; không đổi threshold hoặc sửa gold. Không dùng kết quả này để tuyên bố thành công E2E, chất lượng SQL hoặc hiệu quả điều tra thực tế.

## 10. Kiểm thử và bằng chứng bàn giao

Triển khai phải dùng kiểm thử trước cho:

- contract và phân bổ 120 ca;
- schema/tool compatibility;
- duplicate và near-duplicate audit;
- review gate và lock verification;
- fail-closed trước provider creation;
- Wilson interval và paired McNemar calculation;
- full-denominator argument coverage;
- artifact completeness và hash verification;
- bảo toàn byte/hash của dev, frozen và kết quả lịch sử.

Đầu ra cuối gồm candidate pack, review pack, audit receipt, lock, preflight, một artifact model thật nếu được cấp quyền, báo cáo R1 chung có các split tách biệt và CI receipt đúng commit SHA. Không tạo điểm bằng mock, replay hoặc response viết sẵn.

## 11. Thứ tự triển khai

1. Khóa contract và kiểm thử bảo toàn lịch sử.
2. Tạo schema/manifest và bộ kiểm tra candidate.
3. Soạn 120 candidate theo ma trận phân bổ.
4. Chạy kiểm tra trùng, độ phủ và schema offline.
5. Xuất review pack; dừng tại human-review gate.
6. Sau khi đủ hai người duyệt, tạo locked benchmark và hash manifest.
7. Mở rộng CLI/runner/report chung, hoàn thiện preflight, thống kê và hành vi fail-closed.
8. Chạy toàn bộ kiểm thử/CI offline.
9. Chỉ khi có quyền và ngân sách, chạy đúng một suite model thật.
10. Bàn giao artifact, báo cáo và giới hạn kết luận.

