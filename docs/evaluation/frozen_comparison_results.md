# CTU frozen: evidence lịch sử, không đủ điều kiện protocol

Hai lượt S1/S4 đã tiêu thụ holdout. Không rerun hoặc dùng kết quả này để chỉnh hệ thống. Xem [protocol audit](ctu_frozen_protocol_audit_2026-09-30.md) và [receipt offline](../../results/evaluation_v1/ctu_network_frozen/remediation_audit_v1/receipt.json).

| Điều kiện lịch sử | Execution Accuracy theo script cũ | Execution success theo flags cũ | Syntax validity | Chi phí được báo cáo |
|---|---|---|---|---|
| Baseline E0 | 0/8 | 8/8 | Chưa xác minh đúng nghĩa | $0.00438375 |
| v2 E3 | 2/8 | 3/8 | Chưa xác minh đúng nghĩa | $0.01022375 |

`syntax_valid` trong script cũ thực chất ghi query thực thi được; không phải kiểm tra cú pháp độc lập. Auditor chỉ đọc JSON, không replay scorer hoặc chạy SQL.

## Đính chính từng case E3

| Case | Flags lịch sử | Diễn giải giới hạn |
|---|---|---|
| 001, 002 | Khớp kết quả | Có stored-value grounding; chưa tách confound độ phức tạp |
| 003, 008 | EXEC_ERROR | Lỗi schema; không đổi thành SYNTAX_ERROR |
| 004, 006, 007 | EMPTY_SQL | Không có SQL final |
| 005 | RESULT_MISMATCH | SQL thực thi được nhưng kết quả khác gold |

Chênh lệch 2 case không chứng minh remediation hoặc linker cải thiện accuracy. Claim causal/validated và đề nghị tuning từ holdout đã rút lại. Snapshot/case lịch sử giữ nguyên; không sửa artifact.

## Cost và provenance

Tổng hai report là $0.01460750; cộng spend đã ghi nhận trước đó $0.05047400 thành **lower bound $0.06508150**, không phải chi phí thực đầy đủ. `cost_complete=false`, `cost_unknown=true`: thiếu usage trung gian và retry policy. Không suy cost từ số turn hoặc gọi Billing để bù evidence.

Thiếu implementation SHA, exact request bytes, response IDs, pre-run CI/cost lock và winner lock. Hash receipt là hash bytes tại thời điểm audit; không chứng minh provenance gốc. Các con số này chỉ là historical/exploratory findings, không phải frozen accuracy được nghiệm thu.

Artifact gốc: [baseline](../../results/evaluation_v1/ctu_network_frozen/baseline_e0/report.json), [E3](../../results/evaluation_v1/ctu_network_frozen/v2_e3/report.json). Bản trước remediation truy tại commit `cf46fb4`. S1/S4 vẫn closed.
