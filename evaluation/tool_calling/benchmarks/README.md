# R1 Tool Calling Benchmarks

`dev/` hiện có **24 case, 5 case không yêu cầu tool**. `frozen/` có 8 holdout riêng; case và gold không được thay trong remediation R2.

Mỗi JSON khai báo `case_id`, `request`, `reference_time`, `expected_calls`, `forbidden_tools`, `ordering_constraints`. Expected call gồm `tool`, `required_arguments`, `critical_arguments`, `optional`. Production schemas là nguồn xác định tool thật.

Category gồm CTI/network/endpoint đơn lẻ hoặc phối hợp, hostname/hash/URL và `no_tool`; difficulty là `basic`, `intermediate`, `advanced`.

Decision-only A1 không thực thi tool; MockProvider/A2 chỉ kiểm integration. Case success, exact-call F1 và no-tool accuracy là metric riêng. Frozen chỉ mở theo protocol đã khóa, không dùng để chỉnh dev.

```powershell
python -m evaluation.tool_calling list dev
```

[R1 contract](../README.md) · [Evaluation protocol](../../../docs/evaluation_protocol_v1.md)
