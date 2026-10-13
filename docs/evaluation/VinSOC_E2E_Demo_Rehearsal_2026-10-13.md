# VinSOC — lời dẫn demo tiến độ ngoại tuyến (5–7 phút)

Mở [trang offline](../../results/evaluation_v1/text2sql_integration_v1/offline_rehearsal_20261013/report.html). Trang được render từ artifact sống `full-e2e-8`; [manifest](../../results/evaluation_v1/text2sql_integration_v1/offline_rehearsal_20261013/manifest.json) ghi hash nguồn và `api_calls_during_render=0`. Có execution `full-e2e-9` mới hơn, vẫn `technical_incomplete` (6/6 response, không có SQL vì linker chạm output cap); trang này chỉ xem lại **run 8**, chưa bao gồm artifact của run 9. Đây là buổi trình bày tiến độ và lỗi thật, chưa phải nghiệm thu E2E.

| Thời gian | Trình bày và thao tác |
|---|---|
| 0:00–1:00 | Mục tiêu: câu hỏi SOC đi từ public orchestrator qua `network_query` tới TextToSQLService chung, DB chỉ đọc, evidence, assessment và người duyệt. Phân biệt một trace demo với điểm R2 hoặc pipeline `/32`. |
| 1:00–2:00 | Chỉ bốn ID được chọn trước output, sau đó cuộn bảng 32 câu CTU. Đọc đúng: 1 recorded nhưng incomplete, 31 missing. Không đổi câu để tìm ví dụ đẹp. |
| 2:00–4:00 | Mở `ctu_cross_708b66575657429a`. Cho xem câu hỏi nguyên gốc, native routing, các lần dò schema/value, SQL và DB result trong trace. SQL trả hai số `1529`/`1210`, trong khi gold giao hai tập là `459`; kết quả không đạt semantic EX. |
| 4:00–5:00 | Mở tóm tắt run: `planned=1`, `completed=0`, report thô ghi 9 reservation/8 response. Audit đã đối chiếu checkpoint: request assessment thứ 9 bị chặn trước provider, nên chỉ 8 request thực truyền, cumulative cost `$0.04565135`, `cost_unknown=false` sau audit. Cận `$0.4206304` trên report thô không phải actual spend. Chưa có human review. |
| 5:00–6:30 | Nêu CI đúng SHA xanh nhưng chỉ chứng minh code/tests. [Kế hoạch tiếp](../superpowers/plans/2026-10-13-vinsoc-e2e-demo-recovery.md): đối soát ledger, xử lý ambiguity và lỗi tổng quát, preflight một execution mới, human review; sau đó calibration `0/48`, evaluation `0/192`, pipeline `0/32` theo quyền riêng. |

Nếu được hỏi “đã E2E thành công chưa?”, trả lời: **chưa**. Trace gần nhất partial và không khớp gold; viewer là bản xem lại offline, không phải live replay. Nếu được hỏi “tại sao còn thiếu 31?”, trả lời: suite pipeline 32 câu chưa được cấp và thực thi theo protocol; không tự chia nhỏ mẫu số.
