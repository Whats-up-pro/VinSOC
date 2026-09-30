# R2 remediation metric contract

Identity mới: `dualsql_lite_ctu_gpt5_v2_remediation_v1`; không phải lock của paid run. Scorer duy nhất: `evaluation.text_to_sql.evaluate_sql_case`, portable SHA-256 trong `evaluation/ctu_network_public/VERSION.lock` là `bd3d9da9e78bbcab560cefabae93a8c5592757a53375bdd31b7ee613d0c66fdf`. Verifier ghi implementation SHA thực tế, không gán SHA tương lai.

Execution Accuracy = số final SQL khớp gold / toàn bộ case khóa, kể cả failure. Syntax Validity dùng DuckDB parser và yêu cầu đúng một statement; unknown column có thể syntax valid nhưng execution fail. Multi-statement được syntax gate loại trước execution. Safety, execution success và EX là flags riêng từ evaluator.

Comparator giữ thứ tự select-list values, bỏ khác biệt alias. `ordered_rows`, `scalar`, `boolean` giữ row order; `unordered_rows` và `multiset_rows` bỏ order nhưng giữ duplicate multiplicity. Float canonicalization làm tròn 9 chữ số; không thêm tolerance hoặc tự sort ordered rows.

Final SQL và probe dùng cùng snapshot-only read-only boundary: cấm writes, external readers và internal/provenance tables. Gold chỉ dùng sau inference, không truyền sang linker/generator.

Diagnostic literal grounding và column precision không thay EX, không vào selection lock hoặc input inference. Catalog có cap; không tìm thấy trong catalog chưa đủ chứng minh không tồn tại trong snapshot. Không dùng metric này để tuning từ frozen.

Report fixture có raw counts/rates và luôn `official_eligible=false`; không biến fixture thành accuracy của model thật. Frozen lịch sử E3 EX 2/8, execution 3/8 theo flags cũ; syntax validity đúng nghĩa chưa xác minh. Cost/provenance lịch sử incomplete.
