# VinSOC Live UI acceptance package

Gói này đối soát ba executions mới của giao diện tại producer
`3c9e44a68d887f90b7ef23c8f64fcf2fc7f39fe6`:

- COUNT: 8/8 model responses, EX true, result 459, chờ human review.
- AVG: 3/3 responses, model SQL probe lỗi, không có final SQL.
- UDP: source đổi sau preflight, bị chặn trước SDK, 0 calls và $0.

Mở báo cáo đầy đủ tại
`docs/evaluation/VinSOC_Live_UI_Acceptance_2026-10-14.md`. Thư mục
`screenshots/` chứa tám stage của COUNT cùng hai failure views. Các JSON receipts
ghi workflow/artifact identity, SHA-256, cost và gates còn mở. Không có raw
private journal, API key hoặc human approval trong gói.

Calibration 0/48, evaluation 0/192 và pipeline32 0/32 vẫn `NOT_RUN`.
