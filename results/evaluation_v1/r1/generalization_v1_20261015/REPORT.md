# R1 - Kết quả 120 case bổ sung ngày 15/10/2026

Lượt thật đã chạy đủ 120/120 case trên `gpt-4.1-mini-2025-04-14`, giữ nguyên prompt, schema và scorer đã khóa. Kết quả **119/120 = 99,17%** cho quyết định chọn tool và đối số. Khoảng Wilson 95% là **95,43%-99,85%**, với giả định các quan sát độc lập; các họ tình huống/template có liên hệ nên không suy rộng thành độ đúng của mọi cảnh báo SOC.

Đây là phép đo decision-only: mô hình trả native tool calls nhưng benchmark không thực thi các công cụ SOC. Số này không thay thế độ đúng routing hoặc E2E của pipeline query.

| Phạm vi | Kết quả | Diễn giải |
|---|---:|---|
| Dev lịch sử | 22/24 | Giữ riêng; 11/24 gold đã được adjudicate sau khi xem output |
| Generalization bổ sung | 119/120 | Bộ authored/reviewed, chưa phải mẫu ngẫu nhiên của SOC thực tế |
| Không cần tool | 24/24 | Không gọi công cụ ở các câu định nghĩa/huấn luyện |
| Required arguments, mẫu số đầy đủ | 154/155 | Tính cả đối số của call bị thiếu |
| Critical arguments, mẫu số đầy đủ | 154/155 | Một IOC hash bị mô hình thay ký tự |

Case duy nhất không đạt là `gen_096`. Mô hình chọn đúng `cti_enrichment` và `endpoint_investigation`, nhưng giá trị `indicator` không khớp hash gốc. Vì vậy tool-name metrics cao không đủ chứng minh toàn bộ tham số đúng. Xem `matches` trong report và native response `responses/096-gen_096.json` trong archive.

Trường legacy `critical_arg_errors` và `error_summary` không phản ánh lỗi đó: DecisionRunner giữ mặc định của field, trong khi frozen matcher vẫn đánh dấu partial và trajectory failure. Audit bổ sung ghi rõ một mismatch từ matcher, giữ nguyên report/scorer gốc. Không sửa gold hay tăng điểm.

**Chi phí thật:** 120/120 responses, input 88.185 token, output 7.163 token, cached 0; **0,04673480 USD**. Mọi internal request ID, provider request ID và response ID đều duy nhất; không unknown cost, không pending exposure, không retry. Latency SDK p50 0,959s, p95 1,714s; số này không bao gồm toàn bộ thời gian gate/CI.

Producer: `ff37425719b3009d33d166ae3faa19ccc35a09e8`; [CI 38698148403](https://github.com/Whats-up-pro/VinSOC/actions/runs/38698148403); [preflight 38698592384](https://github.com/Whats-up-pro/VinSOC/actions/runs/38698592384); [live 38699129318](https://github.com/Whats-up-pro/VinSOC/actions/runs/38699129318).

`native_io.zip` giữ nguyên byte của 120 requests và 120 responses; `native_io_hashes.json` đối soát từng thành viên. Các JSON điều khiển/report/journal và tài liệu giá cũng giữ byte producer. Receipt ghi digest của ZIP gốc tải từ GitHub và đã so khớp độc lập. Reviewer identities là identities đã có trong lock; runner không chứng nhận đó là hai người thật và không tự ký review mới.

Kiểm lại ngoại tuyến, không SDK/API hoặc tool execution:

```bash
python results/evaluation_v1/r1/generalization_v1_20261015/verify.py
```

Auditor dựng lại native predictions và frozen scorer cho từng case, rồi tính lại report. Hai field wall-clock latency legacy không có trong serialized CaseResult nên chỉ được bảo toàn, không tuyên bố tính lại; phân bố latency SDK được tính lại từ journal. Bộ 120 được giữ riêng bộ dev 24, không gộp thành một mẫu 144 hoặc dùng McNemar cho hai tập khác nhau.
