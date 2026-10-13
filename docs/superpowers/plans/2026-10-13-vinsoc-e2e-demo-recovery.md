# VinSOC — kế hoạch chốt E2E và demo gấp (13/10/2026)

> Tiếp nối [đặc tả tích hợp 08/10](2026-10-08-vinsoc-text2sql-integration-and-final-demo.md) và [closeout 12/10](2026-10-12-vinsoc-e2e-r2-closeout.md). Thực hiện từng task với `superpowers:executing-plans`, TDD cho thay đổi mã và `verification-before-completion` trước khi công bố PASS. Mọi paid scope có preflight và quyền riêng. Không đổi lịch sử, gold, bốn demo ID hoặc mẫu số.

**Đích gần:** một gói offline mở được ngay và mô tả trung thực các lần thất bại gần nhất; sau khi khóa protocol và ngân sách, một execution E2E mới có SQL đúng, real DB result, evidence, assessment hợp lệ và quyết định của người duyệt. **Đích đầy đủ:** 48 calibration, 192 evaluation và 32 pipeline records thật theo đặc tả; demo một câu không thay các tập đó.

**Checkpoint tiếp tục 13/10:** master nguồn `9b44eb605f418fea2d65e5b3eaa043949a200e6f`,
CI [38347712931](https://github.com/Whats-up-pro/VinSOC/actions/runs/38347712931) success.
Task A có gói offline; Task C đã preflight và chạy một execution `full-e2e-10`
ở `0d813371...` với 7/7 response, `$0.00739705`, cumulative `$0.06115500`.
Task D có trace kỹ thuật nhưng reporter cũ fail factual vì lookup nhầm vị trí
scalar trong typed result. Tiếp tục sửa mapping bằng test RED/GREEN, kiểm
result evidence hash và rút gọn CLI review với `--verbose`; xuất projection/viewer
v2 trong thư mục mới, không sửa output/scorer lịch sử. Chưa nhận receipt review,
nên chưa đóng human approval. Task E vẫn `0/48`, `0/192`, `0/32`; không mở paid scope mới.
Nguồn bàn giao: [runbook hiện hành](../../VINSOC_E2E_DEMO_RUNBOOK.md),
[manifest v2](../../../results/evaluation_v1/text2sql_integration_v1/offline_demo_v2_20261013/manifest.json).

**Mốc đầu:** execution `full-e2e-8` tại `09cfbfaee49e780d3ca1afd02c89ae3ef55c3168`, CI [38335064157](https://github.com/Whats-up-pro/VinSOC/actions/runs/38335064157) success; workflow [38335534597](https://github.com/Whats-up-pro/VinSOC/actions/runs/38335534597) có artifact partial. `0e85e637bbc5828c221f1d0d2dac0a91090c3c28` đã commit audit và bản sửa checkpoint/semantic; [CI #339](https://github.com/Whats-up-pro/VinSOC/actions/runs/38336323978) success. [Workflow #10](https://github.com/Whats-up-pro/VinSOC/actions/runs/38336761761) trên SHA đó thất bại (`full-e2e-9`, 6/6 response, `technical_incomplete`, cost lũy kế `$0.05375795`); [audit run 9](../../../results/evaluation_v1/text2sql_integration_v1/single_demo_full_e2e_9_20261013/outcome_audit.json) đã commit tại `master@7c6e5b907934b8ce76f7f88d4dd9edd80834d9eb`, xác định lỗi linker ba lần chạm output cap, không có SQL cuối. SHA mới nâng cap R2 1.000→2.000, chưa có live success. [Status 13/10](../../evaluation/VinSOC_E2E_Demo_Status_2026-10-13.md) và [audit run 8](../../../results/evaluation_v1/text2sql_integration_v1/single_demo_full_e2e_8_20261013/outcome_audit.json) là checkpoint. Chưa có E2E approved; official scopes `0/48`, `0/192`, `0/32`.

## Quy tắc quyết định

- Không request/model/provider mới khi có cost chưa đối soát. Run 8 đã đối soát pretransmission trong audit commit `0e85e63`; vẫn phải xác nhận account/project, budget còn lại, window cũ đã khóa và quyền scope/SHA mới trước preflight tiếp theo.
- Không sửa gold `ctu_cross_708b66575657429a`, prompt/schema/scorer đã dùng, artifact thất bại hoặc selection bốn ID. Nếu câu hỏi mơ hồ, ghi finding trong protocol gốc. Câu diễn đạt rõ “shared destination IPs in both scenarios” chỉ được dùng cho một demo phiên bản mới, đánh dấu **unscored**; không gọi đó là điểm trên câu khóa.
- Không tự nâng cap, retry, replay response, giảm mẫu số, đổi case sau output, tạo assessment/review giả hoặc biến SQL thực thi được thành SQL đúng. Cap 2.000 vừa được commit ở `7c6e5b`: phải kiểm protocol version, request/cost bound, CI và authorization của SHA này trước paid run; không coi commit là quyền chạy. Không mở R1 Task 6 trong nhánh công việc E2E; remote đã revert mã đó.
- Mỗi milestone: checkout sạch từ `master`, tests offline, preservation/hash, `git diff --check`, commit/push chính phạm vi, CI đúng full SHA. Run paid dùng exact SHA/CI đã khóa; artifact partial vẫn lưu bất biến.

## Task A — chốt bằng chứng và rehearsal offline (làm ngay, $0)

**Tệp:** audit run 8, status 13/10, bản HTML viewer/speaker notes nếu renderer có đủ dependency. **Input:** ZIP artifact `11784501792` với digest đã pin; chỉ trích phần public. **Output:** một gói chỉ đọc cho người xem, không claim success.

1. Kiểm ZIP và hash ba tệp public, đối chiếu control/report/case: SHA, CI, 9 reservation/8 response, token usage, cờ unknown *trên report thô* và audit pretransmission đã commit, SQL/result 1529/1210, gold 459; ghi `planned=1`, `completed=0`. Nếu thiếu hoặc lệch, dừng ở audit blocker.
2. Đối chiếu các outcome audit trước; không ghi đè. Render viewer ngoại tuyến bằng `scripts.render_query_pipeline_report` trên artifact đã lưu. Viewer phải thể hiện bốn ID khóa, đủ 32 hàng, missing/partial trung thực và không gọi API. Nếu dependency thiếu, cài môi trường kiểm thử riêng rồi kiểm HTML/JSON, không mock dữ liệu.
3. Viết kịch bản 5–7 phút: kiến trúc, một trace thật, SQL sai và gate đã chặn claim, bảng `0/48`, `0/192`, `0/32`, bước cần để đạt. Hash nguồn và HTML; kiểm link mở ngoại tuyến và escaping. Không gọi đây là E2E PASS.
4. Verify `git diff --check`, JSON parsing, artifact hash và test renderer/report. Ghi output lệnh thật; commit/push/check exact-SHA CI. Chi phí/model calls của Task A = 0.
5. Audit `full-e2e-9` đã có trên master và cho biết linker `MODEL_PARSE_ERROR` do ba response dài 1.000 token; xác minh ZIP workflow #10 (`11785262841`, digest `sha256:f2e0935674056f6a03230485df508573a2d46a7417d42af9627b519b0c98d243`) độc lập khi công cụ tải hoạt động lại. Không sửa audit đã commit để đổi kết quả.

## Task B — xác định nguyên nhân và quyết định case/protocol ($0)

**Tệp dự kiến:** dated finding dưới `docs/evaluation/`, tests của service/pipeline contract nếu cần fix tổng quát. **Output:** quyết định trước một paid run mới.

1. Kiểm lại trace run 7/8/9 theo vai trò: routing, linker, generator, DB, assessment. Run 8 vướng checkpoint remote `1..8`; fix `MAX_DEMO_REQUESTS=10` đã qua CI. Run 9 dừng trước SQL ở linker vì ba lần chạm output cap. Xác minh bằng audit và test, không gán lỗi mới thành thành công vì guard đã PASS.
2. Rà câu khóa và gold bằng chuyên gia miền độc lập: “in scenario 5 and ... in scenario 7” có nêu rõ *giao* destination IP hay không. Ghi finding, không điều chỉnh benchmark sau model outputs. Nếu chọn demo minh họa wording mới, cấp identity/protocol mới và công bố unscored.
3. Rà test RED/GREEN đã commit trong `0e85e63` cho checkpoint request 9/10 và cảnh báo semantic `UNION ALL` trên câu tổng quát; rà bản cap 2.000 ở `7c6e5b` và test linker length. Kiểm không cấy SQL hoặc hint theo case ID; test fail-closed nếu model hết turn vẫn sai ngữ nghĩa. Xác minh protocol/budget đã versioned trước output mới.
4. Chạy GREEN, offline full suite, protected-history hash, `git diff --check`; push và đợi CI đúng SHA. Nếu không tìm được fix hợp lệ, giữ trạng thái blocked và dùng rehearsal ở Task A.

## Task C — đối soát tài chính và preflight mới (trước mọi paid call)

**Input bắt buộc:** audit `full-e2e-8` và `full-e2e-9` đã commit, cumulative `$0.05375795`, window claims, số dư account/project có thẩm quyền, giá hiện hành, cận mới sau cap 2.000; authorization riêng cho **một** single-query demo mới trên SHA/CI đúng, execution ID mới, max request, hard USD limit. Quyền demo trước đây không tái sử dụng.

1. Kiểm audit đã commit: run 8 có tám request truyền thật và reservation assessment thứ 9 chưa tới SDK; run 9 có sáu response/usage và cost `$0.0081066`, cumulative `$0.05375795`, `cost_unknown=false`. Không ghi cận `$0.4206304` của report thô run 8 thành actual. Kiểm source/window identity và đối soát số dư tài khoản trước release mới; nếu phát sinh mismatch hoặc unknown khác thì dừng.
2. Test gate fail-closed cho unknown exposure, prior-cost mismatch, wrong scope/SHA/CI, reused ID, budget thiếu; assert zero provider creation/calls khi fail. Preflight-only ghi receipt với exact runtime, snapshot, schema, prompt, price, ledger và cửa sổ mới.
3. Chỉ khi gate PASS mới cho **một execution**. Không tự động retry/rescue và không đổi source/prompt/schema sau khi mở output. Dừng ở kết quả thật, kể cả partial.

## Task D — nghiệm thu một trace E2E và human review

1. Kiểm native `network_query` giữ nguyên câu hỏi, TextToSQLService chung, SQL an toàn, DuckDB read-only trên snapshot pin, result exact với câu gốc, evidence lineage, assessment có observation/citation hợp lệ, query replay độc lập, usage/cost đủ. SQL trả hai con số riêng không đạt câu gold 459.
2. Nếu kỹ thuật hợp lệ, chuyển case receipt hash cho người duyệt thật nhập identity/decision/rationale/UTC qua CLI; `approved`, `rejected`, `escalated` đều lưu thật. Không tự nhập quyết định thay người.
3. Render JSON/HTML offline, đối chiếu trường, hash và link artifact. Demo chỉ được nói “một câu cố định E2E đạt” khi technical receipt và review đều hợp lệ; phải hiển thị cả bốn case đã chọn, kể cả missing/fail.

## Task E — đóng yêu cầu E2E đầy đủ theo đặc tả (không gộp vào demo một câu)

1. Quyết định budget riêng cho 48 calibration. Cận bảo thủ lịch sử `$17.136` calibration, `$68.544` evaluation, `$30.1843456` pipeline E0 hoặc `$46.5043456` E3 phải được tính lại từ giá/account và request payload đã khóa; không suy diễn đủ tiền từ chi phí demo thấp. Nếu ngân sách không đủ, ghi blocked hoặc một pilot mới không official.
2. Nếu được cấp quyền: 24 ID × E0/E3 = 48 records thật, khóa selection; sau đó authorization evaluation 96 × 2 = 192 records thật, điểm EX ngoài SOC `/64`, CTU `/32`, tổng `/96`, paired và chi phí; cuối cùng authorization pipeline 32 cases qua public orchestrator và human review. Mỗi scope có fixed denominator, preflight, ledger và artifact riêng.
3. Demo cuối khóa dùng bốn ID đã chọn từ 32 pipeline receipts; báo failure/missing cùng success. Xuất HTML standalone, 5–7 phút speaker notes, manifest/hash, CI exact SHA. Không gọi E2E demo đơn ca là đánh giá chất lượng SQL đa miền hoặc kết quả pipeline `/32`.

## Mốc thực tế cho 13–15/10

| Thứ tự | Có thể hoàn tất ngay | Điều kiện để mở bước kế |
|---|---|---|
| 13/10 | Task A: rehearsal offline của run 8, kiểm audit run 9; Task B: finding, CI và tests offline | Hash/artifact đúng, CI sau commit xanh; cap mới có protocol/budget receipt hợp lệ. |
| Sau CI SHA mới | Task C rồi tối đa một execution Task D | Runs 8/9 đã có audit; cần cận cap 2.000, account/budget/authorization đúng scope/SHA và preflight mới. |
| Sau selection lock | Task E calibration → evaluation → pipeline | Quyền và budget cho từng scope, đủ denominator; nếu không đạt, báo pending trung thực trước deadline. |

**Tiêu chuẩn bàn giao:** status thật, command/test output, commit SHA/CI, artifact digest, ledger actual/unknown tách rõ, trace và review có hash, giới hạn kết luận. Task A/B không phát sinh model call hoặc cost.
