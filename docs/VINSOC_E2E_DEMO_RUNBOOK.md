# VinSOC — runbook demo E2E

Cập nhật 13/10/2026. Demo hiện xem lại một trace thật từ `full-e2e-10`,
ca `ctu_cross_708b66575657429a` / E3. [Viewer mới](../results/evaluation_v1/text2sql_integration_v1/offline_demo_v2_20261013/report.html)
kiểm factual từ typed result, giữ đủ bốn demo ID và bảng 32 câu CTU.

## Trạng thái và phạm vi

| Phạm vi | Bằng chứng hiện có |
|---|---|
| Demo query cố định | Native routing → linker → generator → DB cô lập → evidence → assessment. Result `459`; EX, replay, provenance và factual đạt; review pending. |
| R1 dev | Kết quả lịch sử `22/24`, phục vụ phát triển/hồi quy. Generalization 120 ca đã khóa; chưa có suite model mới trong công việc này. |
| R2 calibration | `0/48` record thật của protocol tích hợp mới. |
| R2 evaluation | `0/192` record thật. |
| Pipeline chính thức | `0/32`; viewer có một trace demo và 31 missing, không tạo điểm suite. |

Lượt demo dùng 7 API calls, chi phí `$0.00739705`; lũy kế allocation demo
`$0.06115500/$3`. Render và review artifact đã lưu không gọi model.
Nguồn: [outcome audit](../results/evaluation_v1/text2sql_integration_v1/single_demo_full_e2e_10_20261013/outcome_audit.json),
[workflow thật](https://github.com/Whats-up-pro/VinSOC/actions/runs/38338493466).

## Mở demo và trình bày 5–7 phút

Từ repo root trên PowerShell:

```powershell
Start-Process 'results/evaluation_v1/text2sql_integration_v1/offline_demo_v2_20261013/report.html'
```

1. Chỉ bốn ID được chọn trước output và bảng 32 ca: một trace đang chờ duyệt, 31 missing.
2. Mở ca đầu: câu hỏi nguyên văn, native `network_query`, SQL cuối, result `459`, hai evidence và assessment.
3. SQL cuối đếm destination IP có mặt ở cả S5 và S7 với TCP và hai điều kiện thời gian strict `>`.
   Candidate `UNION ALL` trước đó bị semantic audit chặn; trace lưu cả hai candidate.
4. Nêu risk `UNKNOWN`: số IP không chứng minh IP độc hại. Người duyệt phải xác nhận cách hiểu câu hỏi và giới hạn kết luận.
5. Chốt phần còn thiếu: receipt review thật, ba query demo khác và các suite 48/192/32 theo quyền/ngân sách riêng.

## Ghi review

Đọc case record và audit trước khi chọn quyết định. CLI mặc định hiện tóm tắt;
`--verbose` hiện toàn bộ JSON. Tên, quyết định, lý do và UTC được nhập tương tác:

```powershell
py -m cli.main query-review 'results/evaluation_v1/text2sql_integration_v1/single_demo_full_e2e_10_20261013/case_record.json' --output 'results/analyst-review.json'
```

Case SHA-256 phải là
`374224fff7c242d6a2c7f66d07bb0c6c5768cc97964c9d998e1bafa0a5041eb4`.
CLI ghi hash byte của input vào receipt và từ chối ghi đè output.

- `approved`: chấp nhận nội dung và bằng chứng của ca theo cách hiểu được nêu trong lý do.
- `rejected`: nêu lỗi cụ thể.
- `escalated`: cần làm rõ ngữ nghĩa hoặc thêm bằng chứng.

UTC thực tế có thể lấy trong PowerShell khác:

```powershell
(Get-Date).ToUniversalTime().ToString("yyyy-MM-dd'T'HH:mm:ss'Z'")
```

CLI ghi danh tính do người nhập khai báo; chưa xác thực danh tính. Agent có thể
thao tác ghi hộ quyết định người duyệt đã cung cấp. Quyết định do agent tự đưa ra
cần contract `agent_review` riêng để ghi đúng nguồn quyết định.

Sau khi receipt thật tồn tại, tạo trang mới bằng renderer có `--review`:

```powershell
py -m scripts.render_query_pipeline_report 'results/evaluation_v1/text2sql_integration_v1/single_demo_full_e2e_10_20261013/runner_report.json' --review 'results/analyst-review.json' --output 'results/query-reviewed.html'
```

Reporter chỉ ghép review có case ID/hash hợp lệ. Approval cũng cần technical checks đạt.

## Chỉ số R1 và R2

R1 dùng phép đo kiểu BFCL: tool set exact match, exact-call precision/recall/F1,
required/critical argument accuracy và coverage, no-tool accuracy, extra/duplicate
calls và provider errors. Ba production tools của track R1 là `cti_enrichment`,
`network_investigation`, `endpoint_investigation`.
[Scorer R1](../evaluation/tool_calling/metrics.py),
[matching](../evaluation/tool_calling/matching.py).

R2 dùng execution accuracy làm chỉ số chính, cùng syntax/execution/error metrics.
Comparator theo hợp đồng ca; phép so sánh multiset giữ số lần xuất hiện của hàng,
ordered giữ thứ tự. Model không nhận gold SQL từ evaluator.
[Semantic scorer](../evaluation/r2_cross_domain_v1/semantic_scoring.py),
[query scoring](../evaluation/finalization/query_scoring.py),
[service chung](../vinsoc_text2sql/service.py).

Các số VinSOC là phép đo của repo; không phải điểm trên bộ BFCL, Spider hoặc BIRD chính thức.

## Kiểm tra và vấn đề còn mở

[Gói preflight ba demo còn thiếu](../results/evaluation_v1/text2sql_integration_v1/remaining_demo_preflight_20261013/README.md)
có receipt thật và blocker cụ thể. CLI public nhận `--scope demo`; grant phải
khớp case/E3/execution trong canonical ledger và release phải khớp lựa chọn CLI.
Cloud wrapper vẫn chỉ chạy ca đầu; gói preflight không cấp paid release mới.

Nhóm offline bắt buộc của CI kiểm contract, preflight, selection, journal,
normalization, reporting, pipeline reporting và CLI/viewer. Required real-data
CI khôi phục 13 DB pin, replay 120 gold queries và kiểm worker cô lập. Số test lấy
trực tiếp từ CI đúng SHA; không ghi số cố định thay cho output thật.

- Manifest nguồn run 10 còn lệch hash `outcome_audit.json` (8/9 mục khớp).
  ZIP gốc đã kiểm digest và sáu file public khớp byte; audit là file dẫn xuất sau run.
  Xem [receipt đối soát](../results/evaluation_v1/text2sql_integration_v1/offline_demo_20261013/manifest.json).
- Viewer/projection cũ từng fail factual vì tìm field trực tiếp thay vì cột typed result.
  Phiên bản mới kiểm cột duy nhất của một hàng và hash evidence; các artifact cũ được giữ để đối chiếu.
- Metric phụ value-grounding predicates `0/6/5` cần điều tra riêng; không diễn giải thành grounding đạt.
- Chưa có receipt review được bàn giao trong repo tại thời điểm cập nhật.

Snapshot/hash mismatch hoặc preflight fail: dừng và đối soát input. Chạy model mới
cần đúng scope/SHA/CI, allocation, giá, request bound và preflight; hướng dẫn xem
artifact này không cấp quyền paid run mới.
