# VinSOC — gói demo E2E và bàn giao người duyệt (13/10/2026)

> **Bản viewer mới:** dùng [offline demo v2](../../results/evaluation_v1/text2sql_integration_v1/offline_demo_v2_20261013/report.html)
> và [manifest v2](../../results/evaluation_v1/text2sql_integration_v1/offline_demo_v2_20261013/manifest.json).
> Reporter trước đây tìm observation trực tiếp trong `evidence.data`, nên báo
> factual/technical failed dù scalar nằm trong `columns/rows`. Bản mới kiểm
> cột duy nhất của một hàng, giá trị/kiểu và hash result evidence. Artifact,
> gold, SQL và các projection trước được giữ nguyên. Review vẫn pending vì chưa có receipt.
> CLI duyệt hiện tóm tắt; thêm `--verbose` để xem JSON đầy đủ.

## Trạng thái có thể công bố

Lượt `full-e2e-10`, ca khóa `ctu_cross_708b66575657429a` / E3, trên mã
`0d813371a713839e712bb36c2a2ca6a8fd60ebab` đã **hoàn chỉnh về kỹ thuật,
đang chờ người thật duyệt** (`technical_complete_awaiting_human`).
[CI đúng SHA](https://github.com/Whats-up-pro/VinSOC/actions/runs/38337917138),
[preflight không gọi API](https://github.com/Whats-up-pro/VinSOC/actions/runs/38338323675),
[live run](https://github.com/Whats-up-pro/VinSOC/actions/runs/38338493466).
Trang [xem ngoại tuyến](../../results/evaluation_v1/text2sql_integration_v1/offline_demo_20261013/report.html)
được dựng từ report và case record đã commit, không phát sinh lời gọi model.
[Manifest đối soát](../../results/evaluation_v1/text2sql_integration_v1/offline_demo_20261013/manifest.json)
ghi hash từng nguồn, HTML và một sai lệch manifest gốc.

| Mốc | Bằng chứng |
|---|---|
| Routing → `network_query` | Native call giữ nguyên câu hỏi khóa. |
| Linker và SQL | 3 call linker; candidate `UNION ALL` bị semantic audit chặn; candidate `EXISTS` được thực thi sau 2 call generator. |
| DB và evidence | Worker cô lập, snapshot CTU pin; scalar `459`, independent replay và execution accuracy đều đạt; assessment dẫn hai evidence ID. |
| Chi phí | 7/7 response có usage, `$0.00739705` lượt này; lũy kế allocation demo `$0.06115500/$3`. |
| Human review | `awaiting_human`, không có quyết định; semantic correctness của phần diễn giải chưa được người duyệt chứng nhận. |
| Phạm vi chính thức | Calibration `0/48`, evaluation `0/192`, pipeline `0/32`. Viewer 32 ID có 1 trace demo đang chờ duyệt và 31 missing; trace demo không trở thành điểm pipeline `/32`. |

## Bàn giao cho người duyệt thật

Đọc [case record](../../results/evaluation_v1/text2sql_integration_v1/single_demo_full_e2e_10_20261013/case_record.json),
[outcome audit](../../results/evaluation_v1/text2sql_integration_v1/single_demo_full_e2e_10_20261013/outcome_audit.json)
và trang offline. Người duyệt xác minh cách hiểu câu hỏi, giá trị `459`, SQL,
trích dẫn evidence và tính phù hợp của assessment. Câu hỏi dùng chữ “in scenario 5
and ... in scenario 7”; audit thực thi phép giao destination IP giữa hai scenario.
Nếu cách hiểu này không được chấp nhận, ghi `rejected` hoặc `escalated` cùng lý do;
không sửa gold hay output đã mở.

Tại checkout có snapshot này, CLI tương tác tạo **một receipt riêng** và tự gắn SHA-256
của case record (hiện là `374224fff7c242d6a2c7f66d07bb0c6c5768cc97964c9d998e1bafa0a5041eb4`):

```bash
python -m scripts.review_vinsoc_query_case \
  results/evaluation_v1/text2sql_integration_v1/single_demo_full_e2e_10_20261013/case_record.json \
  --output <duong-dan-receipt-moi>.json
```

Người duyệt tự nhập tên, `approved`/`rejected`/`escalated`, lý do và UTC. Không
nhập danh tính hay quyết định thay người. Sau khi receipt thật được kiểm và lưu,
render trang mới bằng `--review <duong-dan-receipt-moi>.json`; renderer chỉ ghép
review khi case ID và hash khớp. Trang hiện tại vẫn là trạng thái trước duyệt.

## Kịch bản trình diễn 5–7 phút

1. Mở viewer, chỉ bốn ID đã chọn trước output và bảng 32 ca: 1 trace demo
   `awaiting_human`, 31 `missing`; nhấn mạnh suite chính thức chưa chạy.
2. Mở ca đầu: câu gốc → native tool call → SQL cuối với hai `EXISTS` → typed result
   `459` → hai evidence → assessment. Candidate `UNION ALL` trước đó bị chặn.
3. Mở outcome audit: 7 call và usage/cost; nêu rõ CI và worker isolation; không
   diễn giải 1/1 demo thành accuracy chung.
4. Chỉ ô `human_review` đang pending và đưa người duyệt case record/CLI. Công bố
   quyết định thật sau khi có receipt hash hợp lệ, kể cả khi bị từ chối.
5. Kết thúc bằng mốc còn thiếu: human review, đối soát manifest nguồn dưới đây,
   sau đó các quyền và ngân sách riêng cho 48/192/32 nếu cần nghiệm thu đầy đủ.

## Sai lệch hash cần công bố

Trong `artifact_manifest.json` của run 10, **8/9 file khớp** hash và byte.
Mục `outcome_audit.json` ghi `13187` byte và
`bc412ef320fb52ee2b7b30ce647d56809fc4f9f7ab967e88df1618a2df402a92`, trong khi
file đã commit có `12824` byte và
`274c4815f01ba3db471ab6045d8f5e5f0e12be78a08cc718cbb004fae760957e`.
Hai file gốc được giữ nguyên. Manifest mới ghi cả giá trị khai báo lẫn byte đã
commit, nên có thể kiểm riêng report/case/HTML. ZIP workflow đã tải và kiểm
SHA-256 `ed290e86e1342bc0c9bb5d45d1319094c90d477597015d75480fa92f97c52540`.
Sáu file public trong ZIP khớp byte với bản commit, gồm report và case record.
ZIP **không chứa `outcome_audit.json`**; mục audit trong manifest nguồn được ghi
cho một file dẫn xuất sau run nhưng không khớp byte đã commit. Không tuyên bố
manifest nguồn `PASS`; cần versioned correction hoặc giải trình từ người tạo audit.

Metric phụ `value_grounding.predicates` là `0/6/5`, còn witness precision `3/3`
và unsupported literal `0/3`. Đây là chênh lệch annotation cần điều tra riêng;
không thay EX của ca `459`, cũng không được ghi thành chất lượng grounding đạt.
