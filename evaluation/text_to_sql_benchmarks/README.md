# Legacy R2 Text-to-SQL Benchmarks

Thư mục này là contract **three-source ThreatFox / CTU-13 / OTRF**: 8 dev + 6 frozen. Nó tách khỏi `evaluation/ctu_network_public/dev` (8 CTU S5/S7) và 8 case CTU S1/S4 lịch sử đã consumed. Có snapshot CTU không chứng minh snapshot three-source đã hoàn tất.

Execution Accuracy là headline, dùng cùng read-only snapshot cho generated/gold SQL. Syntax Validity, Execution Success và Safety Rejection là flags riêng. `ordered_rows` giữ order; `unordered_rows` và `multiset_rows` bỏ order nhưng giữ duplicates. Alias không quyết định đúng/sai; thứ tự select-list values được giữ theo scorer hiện tại.

Canonical snapshot trong legacy case là `data/snapshots/vinsoc_public_v1.duckdb`. Runner kiểm path/ID/SHA từ manifest trước provider. Unit fixtures chỉ chứng minh evaluator bắt DISTINCT, boundary, Boolean và ordering errors; không phải benchmark accuracy.

R2 remediation dùng scorer đã khóa, chỉ fake clients và verified S5/S7 hiện có. Frozen lịch sử E3 EX 2/8 và execution success 3/8 theo script cũ; syntax validity đúng nghĩa chưa xác minh, cost/provenance incomplete. Không replay scorer ngầm để tạo kết quả mới.

[Remediation status](../../docs/evaluation/r2_remediation_status.md) · [Historical correction](../../docs/evaluation/frozen_comparison_results.md) · [Data protocol](../../docs/duckdb_data_layer.md)
