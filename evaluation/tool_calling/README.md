# R1 Tool Calling

R1 A1 đo native `tool_calls` trên production schemas: tên tool và argument cần thiết. Suite dev v2 có **24 case, 5 no-tool**; frozen có 8 case riêng. A1 không thực thi tool. A2 chạy orchestrator/skill bằng fixture là integration regression, không phải accuracy của model thật.

## Metric

| Metric | Field |
|---|---|
| Tool multiset exact match | `tool_set_exact_match_rate` |
| Exact call precision / recall / F1 | `exact_call_precision`, `exact_call_recall`, `exact_call_f1` |
| Required argument accuracy | `argument_field_accuracy` |
| Critical argument accuracy | `critical_argument_accuracy` |
| No-tool accuracy | `no_tool_accuracy` |
| Single-turn case success | `trajectory_success_rate` |

Field legacy `trajectory_success_rate` không phải BFCL multi-turn trajectory. Provider/parse failure không nhận no-tool success. Token/cost/latency, forbidden-tool và errors phải báo cùng metric.

## Contract và sử dụng

```powershell
python -m evaluation.tool_calling list dev
python -m pytest -q
```

Model evidence cần model/request, prompt/schema, benchmark/scorer identity và cost/CI gates. [Baseline lịch sử 22/24](../../results/evaluation_v1/r1/r1_a1_dev_v2_852e543.json) dùng model/contract khác; [phân tích GPT-5](../../docs/evaluation/r1_gpt5_dev_error_analysis.md) ghi khác biệt. Gold adjudicate sau khi quan sát model phải công bố giới hạn; không đổi gold để nâng điểm.

[Benchmarks](benchmarks/README.md) · [Protocol](../../docs/evaluation_protocol_v1.md) · [R2 remediation](../../docs/evaluation/r2_remediation_status.md)

Phiên R2 remediation này không gọi R1, không mở frozen và không chạy demo.
