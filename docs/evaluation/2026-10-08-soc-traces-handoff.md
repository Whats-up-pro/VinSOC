# VinSOC — Điểm tiếp tục SOC và điều kiện bàn giao

Triển khai kỹ thuật ngoại tuyến đã có; **lượt E2E model thật chưa chạy**. Text-to-SQL mở rộng vẫn tạm hoãn theo quyết định đã duyệt. Không chạy lại R1 dev 22/24 hay ghép các kết quả R2 khác contract thành một điểm mới.

Implementation: `7e4aa943d62dc7ed91d40778f5dec603c5053b65`. [CI đúng implementation](https://github.com/Whats-up-pro/VinSOC/actions/runs/37791179365) **completed/success**: cả Python 3.11/3.12 restore corpus success và 1.198 passed/2 historical skipped. `ci_verification.json` giữ run/job IDs và receipt DB thực của từng môi trường; đây không phải phiếu cấp quyền operator. Hướng dẫn lệnh và định dạng private gates: [runbook](2026-10-08-soc-traces-runbook.md). Kế hoạch có điểm tiếp tục: [P0–P9](../superpowers/plans/2026-10-08-vinsoc-soc-traces-e2e.md).

## Phần đã có bằng chứng

| Hạng mục | Bằng chứng và giới hạn |
|---|---|
| Corpus | Test 5.031 + validation 4.984, 87.028 observations nhập, quarantine 0; revision/file/importer/DB/logical hashes trong `corpus_receipt.json`. Nguồn là dữ liệu tổng hợp, Apache-2.0. |
| Lựa chọn | 64 hồ sơ, 32 mỗi nhãn; 12 hồ sơ được xếp hàng rà nguồn, bốn demo chọn trước output. `inventory.json`, `gold.json`, `source_audit_queue.json`, `demo_selection.json`. Chưa freeze vì review 0/12. |
| Kiểm nguồn và tools | Required acceptance đối chiếu con trỏ/mã băm parquet cho toàn bộ 64 hồ sơ, truy vấn DuckDB read-only thật, scope/UTC/bytes/null. Không kiểm bằng observations giả. |
| Tích hợp | `InvestigationOrchestrator.investigate_alert` nhận alert/IOC, kiểm scope rồi model chọn hai tools; đăng ký đúng bằng chứng đã delivered. Mode SOC không dùng `_analyze_evidence`, auto-close hay scripted review. Positive SDK/model/tool conversation còn chờ lượt thật. |
| Báo cáo | Schema đầy đủ; JSON/HTML/Markdown giữ summary, hypotheses, findings, risk/confidence và lý do, limitations, actions, citations, tools, nguồn, usage/cost và review. Không điền nội dung khi thiếu final model. Kiểm citation tách khỏi hoàn tất kỹ thuật. |
| Release | Canonical journal riêng, reserve trước transmission, raw body/usage bền vững trước parse, giới hạn 1/6/448 requests, không retry, unknown cost dừng toàn lượt. Chưa tạo release được cấp hoặc claim journal. |
| Bảo toàn | `preservation_receipt.json`: 3.485 file đánh giá/schema/Text-to-SQL lịch sử byte-identical với base `9a1fd81`; không rerun model lịch sử. Snapshot CTU riêng chưa được kiểm trên máy này. |

Kiểm local: bộ hồi quy trước hai regression tests cuối **1.196 passed, 2 historical skipped**; toàn bộ SOC cuối **48 passed**, target reporting/corpus/release **18 passed**. Compile và diff checks exit 0. Full CI final **1.198 passed/2 historical skipped** mỗi phiên bản là bằng chứng cho toàn bộ cây mã hiện tại. Binary hashes các lần phục hồi khác nhau được giữ riêng, logical/source/importer hashes khớp; không tráo DB lịch sử.

`results/evaluation_v1/soc_traces_v1/readiness_preflight.json` là kết quả preflight thật của implementation trên: status `blocked`, model attempts/responses/cost mới 0, SDK client chưa tạo, leakage field scan pass, planned slots 128. `planned` không phải số outputs đã sinh.

## Việc còn lại theo ưu tiên

| Thứ tự | Người thực hiện và gate | Bằng chứng cần giao |
|---|---|---|
| 1 | Người thật rà 12 hồ sơ nguồn, đủ 6/nhãn. Đọc `source_audit_pack.json`; nếu ambiguous, ghi phiếu thật và tái chọn đúng thuật toán trước output. | `source_reviews.json` riêng: analyst, UTC, scenario, payload/inventory hashes, supportability, decision, rationale. Gate PASS mới freeze selection. |
| 2 | Operator đối soát tài khoản/phạm vi/canonical state, giá và model availability ngày chạy, ngân sách USD SOC cụ thể đủ cận toàn 448 requests, chứng minh request bound, xác nhận CI đúng SHA. | `account.json`, `pricing.json` + chứng cứ giá, `budget.json`, `request_bound.json` + chứng cứ bound, `ci.json`. Không lấy quyền/tiền R1/R2 hay điền approvals thay người dùng. |
| 3 | Người thực hiện chạy lại preflight tại môi trường sẽ gọi API. Tất cả gates PASS, runtime/source/environment khớp; attempts 0. | Release có hashes đầy đủ ở canonical private directory. Public receipt trạng thái; không public key, private gates hoặc journal. |
| 4 | Chạy đúng một lượt S0/S1 qua public orchestrator, thứ tự 64 IDs cố định. | 128 vị trí có trạng thái thật; actual model/request/completion/native tool IDs, input hashes, delivered evidence, raw response/usage riêng, sanitized checkpoints và summary. Lỗi/partial/not_run/unknown giữ nguyên; không rerun để tăng điểm. |
| 5 | Chấm và render offline từ outputs thật. | Báo cáo 64/condition và 64 cặp; agreement với nhãn tổng hợp, coverage, class/family/confusion, citations input/tool, calls/tokens/latency/cost known/unknown. Bốn demo JSON/HTML/Markdown vẫn hiện kể cả case lỗi. |
| 6 | Người thật rà ngữ nghĩa bốn demo. | Phiếu bind receipt hash: approve/reject/escalate/request-more-evidence, factual support, contradiction và action suitability. Chưa duyệt thì awaiting_human; kỹ thuật sai không nâng thành approved completion. |

Demo IDs đã chọn: `SCT-087094`, `SCT-017066`, `SCT-004523`, `SCT-096313`. **D-SOC6–D-SOC8 chưa nghiệm thu**: chưa có predictions, báo cáo model mới, phép đo hoặc phiếu demo thật. Không dùng gói rà nguồn làm demo model.

## Quyết định và giới hạn rà mã

- Thực hiện trực tiếp trên master, một người, không branch/PR/subagents theo chỉ thị. Rà mã bởi tác giả yếu hơn một người rà độc lập.
- Quyền triển khai/push không thay thế các phiếu nguồn người thật hoặc mức ngân sách USD riêng mà spec yêu cầu; do đó P9 giữ blocked.
- Đổi tiêu đề task trong plan để công cụ ghi tiến độ đọc được; không đổi phạm vi.
- Hash exact duplicate dựa canonical toàn payload, gồm IDs/timestamps. Hash gần trùng chuẩn hóa số chỉ là heuristic; không bảo đảm độc lập template hoặc semantic dedupe. Không gọi 64 hồ sơ là family holdout hay đánh giá SOC tổng quát. Nếu bỏ qua giới hạn này, kết luận khả năng tổng quát sẽ bị thổi phồng.
- Hai lỗi rà được đã sửa bằng RED→GREEN: phục hồi chấp nhận receipt importer cũ; tỷ lệ citation hồ sơ dùng nhầm completion count. Không dựng positive SDK responses để nghiệm thu.

Giữ nguyên bản thiết kế, bảng gate và trạng thái lỗi. Nếu chưa đủ điều kiện trước 16/10/2026, bàn giao các mục chưa chạy/chưa duyệt như trên; không dựng báo cáo thay thế để gọi là hoàn tất.
