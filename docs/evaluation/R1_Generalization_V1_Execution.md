# Chạy bộ R1 mở rộng generalization v1

Bộ này bổ sung 120 tình huống vào R1 hiện có: 24 ca không dùng tool, 54 ca một tool, 30 ca hai tool và 12 ca ba tool. Lượt chạy gọi trực tiếp DecisionRunner hiện có, giữ nguyên prompt, production schemas, thuật toán matching và scorer đã khóa. Kết quả dev 22/24 và kết quả mới trên 120 ca được trình bày thành hai hàng riêng.

## Entry point và gate

```bash
python -m evaluation.tool_calling.generalization_cli list generalization_v1
python -m evaluation.tool_calling.generalization_cli lock generalization_v1
python -m evaluation.tool_calling.generalization_cli preflight generalization_v1 --authorization .vinsoc/r1/authorization.json --budget-usd 100 --output .vinsoc/r1/preflight.json
```

Entry point này kiểm lock, review, authorization, ngân sách, master sạch và CI đúng SHA trước khi tạo provider. CLI/runner lịch sử nằm trong tập preservation và được giữ nguyên byte. Vì vậy, các lệnh CLI lịch sử không phải đường chạy được chấp nhận cho kết quả generalization chính thức. Đây là adapter bổ sung dùng chung runner/scorer, không phải một benchmark hoặc agent độc lập.

Workflow **VinSOC R1 generalization v1** chỉ chạy thủ công trên master, Python 3.11. Chế độ preflight không nhận OpenAI secret; chế độ live gọi đúng một suite, retry bằng 0 và không fallback. Remote claim cố định `vinsoc-r1-generalization-v1-once` ngăn dùng lại cửa sổ đã chiếm. Frozen tiếp tục là scope riêng.

Authorization ghi rõ model `gpt-4.1-mini-2025-04-14`, split SHA, implementation SHA, CI run, tối đa 120 request, output cap 1.000 và ngân sách hữu hạn. File không chứa API key. Cloud entrypoint lấy tài liệu model OpenAI hiện hành, giữ hash nguồn giá và dùng toàn bộ context window để tính cận tiền bảo thủ; đây không phải số dư tài khoản.

## Bằng chứng và báo cáo

Response gốc và usage được lưu trước khi provider parse tool arguments. Journal được ghi sau từng request, report sau từng case. Mỗi khoản chi có case, role, request ID nội bộ, provider request ID, response ID, token, latency và giá. Request/response gốc nằm trong artifact của chính run.

Lỗi provider, thiếu telemetry hoặc lỗi parse làm suite dừng, không retry. Artifact partial giữ case hiện tại, đủ danh sách 120 case dự kiến, các case đã có record, các case còn thiếu, chi phí đã biết và unknown exposure. Case thiếu không được sinh prediction để bù.

Báo cáo gồm case success và Wilson 95%, call metrics, no-tool, forbidden/extra/duplicate, coverage trên toàn bộ gold, breakdown theo difficulty/tool count/scenario/template/tag, token, latency và chi phí. McNemar chỉ áp dụng cho hai kết quả trên cùng tập case; dev và bộ mở rộng không được coi là paired.

## Giới hạn kết luận

Đây là decision-only: R1 sinh native tool calls nhưng không thực thi production tool. Kết quả không đại diện cho điều tra E2E thành công hoặc độ chính xác báo cáo cuối. Bộ mở rộng được biên soạn và review, không phải mẫu ngẫu nhiên đại diện mọi cảnh báo SOC. Mỗi subgroup nhỏ cần được đọc cùng khoảng tin cậy.

Danh tính reviewer được giữ nguyên từ lock, gồm `Whats-up-pro` và `openai-codex-reviewer-b`; runner không đổi reviewer AI thành người. Không có human review mới nào được tự ký trong quá trình chạy. Kết quả API và receipt sau xác minh mới là bằng chứng thực nghiệm; lock/preflight không được tính thành điểm mô hình.
