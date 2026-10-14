# VinSOC Live Demo Acceptance and Handoff Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans, thực hiện tuần tự. Làm trực tiếp trên master, không tạo branch/PR và không dùng subagent.

**Goal:** Nghiệm thu giao diện và artifact E2E thật hiện có, đối soát chi phí mới, xuất gói demo gọn để bàn giao mentor; không chạy lại model để cứu kết quả.

**Architecture:** Streamlit điều khiển Linux Actions và đọc artifact gắn đúng request/run/SHA. Nghiệm thu tách trạng thái workflow, chất lượng truy vấn, assessment và quyết định review. Artifact lịch sử giữ nguyên; bằng chứng bổ sung lưu thư mục mới.

**Tech Stack:** Python 3.11/3.12, Streamlit, GitHub Actions/gh, DuckDB và runner hiện có.

**Spec:** `docs/superpowers/specs/2026-10-14-vinsoc-live-interface-design.md`; đọc cùng `docs/superpowers/plans/2026-10-14-vinsoc-live-interface.md` và `docs/evaluation/VinSOC_Live_Interface_2026-10-14.md`.

## Global Constraints

- Đồng bộ master mới nhất; mốc đã kiểm tra: `3c9e44a68d887f90b7ef23c8f64fcf2fc7f39fe6`. CI đúng SHA: https://github.com/Whats-up-pro/VinSOC/actions/runs/38440995847 — success.
- Quyền tác vụ này: đọc/download artifact, kiểm chứng offline, hoàn thiện tài liệu và commit/push master. Không dispatch live, rerun workflow hoặc gọi model mới.
- Cap cumulative query allocation giữ $3. Base lịch sử $0.08155920 chỉ là trước các lượt UI; phải cộng claims/receipts mới, không báo $2.91844080 là số dư hiện tại.
- Không sửa protected benchmarks/gold/prompts/scorers/history/ZIPs; không xóa claim, mở lại consumed window, hạ reserve hoặc tự nâng cap.
- Không tự nhập danh tính/quyết định/UTC cho người khác. Agent review phải có nhãn riêng, không tính thành human approval.
- Không coi workflow success là technical PASS hay semantic correctness. Không cộng bốn demo khác run/SHA thành một suite pipeline32.
- Calibration 48, evaluation 192, pipeline32 chỉ có kết quả khi có đầy đủ artifact đúng hợp đồng; catalog/UI không phải bằng chứng đã chạy.
- Nếu blocker xuất hiện, lưu receipt và báo chính xác. Không bỏ mẫu, tạo output giả hoặc sửa review/gold để ép PASS.

## Review Focus

1. Artifact tải về sai request/run/SHA: từ chối nhập, không thay bằng ví dụ cũ.
2. Live thất bại hoặc claim chưa có end: giữ partial, unknown exposure phải chặn trả phí tiếp.
3. Case technical_failed/incomplete: giữ trạng thái và nguyên mẫu số, không đổi thành awaiting_human.
4. Receipt review không hợp lệ hoặc khác case hash: từ chối, không giả chữ ký.
5. Session restart/download lại: không dispatch lại; không lộ private journal/key trong Git hoặc gói mentor.

## Tình hình đã kiểm tra — dùng làm mốc, không thay kiểm chứng

Bốn demo đã có record trong `results/evaluation_v1/text2sql_integration_v1/mentor_four_case_demo_20261013/`:
- COUNT `ctu_cross_708b66575657429a`: 459, awaiting_human.
- UDP `ctu_cross_66b8e92a76c3359b`: 9.780 hàng, incomplete trước assessment/scorer.
- NULL `ctu_cross_3f659571f998adb0`: technical_failed, EX false.
- AVG `ctu_cross_bce6d3679ade4cd6`: TCP, awaiting_human.
Đây là 4/4 records, không phải 4/4 thành công.

Các run UI mới trên 3c9e44a cần mở artifact để xác định kết quả:
- Preflight 38442148674 → live 38442744166: live workflow failure.
- Preflight 38444046451 → live 38444497641: live workflow success, chưa được tác vụ này chứng nhận technical outcome.
- Preflight 38496130495: workflow success; không suy ra đã có lượt live tương ứng.
Artifact live success: ID 11837992856, digest `sha256:6a80429c9b3d09b70b618a034ae7110e20768d6e184f180e73fe6678588abfc8`.
Artifact live failure: ID 11837061024, digest `sha256:f28ea6fec1f9d8a96584e2614760bbbeebe1180e85a492746c3e86c6168c6654`.
README `remaining_demo_preflight_20261013` là bằng chứng blocker lịch sử, không là trạng thái hiện tại.

### Task 1: Thu bằng chứng và đối soát run/cost hiện tại

**Files:** Read `scripts/vinsoc_live_protocol.py`, `scripts/run_query_live_ui_cloud.py`, `scripts/vinsoc_live_ui.py`, workflow `query-live-ui.yml`, các tài liệu Spec, bốn demo và `source_artifacts.json`. Create `results/evaluation_v1/text2sql_integration_v1/live_ui_acceptance_20261014/{run_inventory,artifact_hashes,cost_reconciliation,acceptance_receipt}.json`.

**Interfaces:** Consumes actual Actions metadata/artifact/append-only ledger. Produces public receipts chứa source SHA, run/execution/request IDs, artifact digest, case hashes, observed outcome và known/unknown costs. Raw ZIP/private journals giữ ngoài Git.

- [ ] Ghi HEAD/origin/master, kiểm working tree và CI đúng implementation SHA. Nếu master mới hơn, ghi delta và kiểm CI mới; không tự trộn producer identity.
- [ ] Liệt kê toàn bộ preflight/live UI runs và allocation claims từ khi 3c9e44a phát hành. Download từng artifact có liên quan bằng `gh run download <run-id> --repo Whats-up-pro/VinSOC --dir <private-dir>`; kiểm digest ZIP bằng đường tải phù hợp trước giải nén, rồi kiểm manifest/per-file hashes.
- [ ] Đối chiếu exact request/run/SHA/execution, provider response IDs, attempted/received, usage, actual cost, end/claim và failure/partial. Preflight phải zero calls/client_created=false; checkpoint và outcome của live phải khớp receipt.
- [ ] Đối soát base $0.08155920 cộng tất cả UI spend/exposure, tránh tính hai lần một response. Thiếu end/usage/ledger phải ghi unknown, không bịa cost=0. Báo số dư allocation với trạng thái verified/unknown, không gọi đó là provider balance.
- [ ] Xuất receipts public đã loại private request/key/token. Không commit toàn bộ ZIP tải về.

### Task 2: Nghiệm thu UI và review bằng artifact thật

**Files:** Read `scripts/vinsoc_demo_app.py`, controller/protocol ở Task 1 và `scripts/review_vinsoc_query_case.py`. Create `docs/evaluation/VinSOC_Live_UI_Acceptance_2026-10-14.md`, `live_ui_acceptance_20261014/ui_checks.json`. Review receipts chỉ tạo từ dữ liệu người duyệt thực cung cấp.

**Interfaces:** Consumes Task 1 receipts và existing verified session artifacts. Produces observable UI checks và bảng trạng thái từng case/run, không tạo prediction hay paid attempt mới.

- [ ] Khởi động `python -m streamlit run scripts/vinsoc_demo_app.py` bằng môi trường có `requirements-demo.txt`, bind localhost. Kiểm trên browser; không bấm nút tạo lượt live/preflight mới trong tác vụ này.
- [ ] Mở/khôi phục session thật, kiểm request → routing → grounding → SQL → typed result → evidence → assessment/verification → review. Record cũ phải được ghi là lịch sử, record mới giữ đúng producer/run.
- [ ] Kiểm partial/failure cũng hiển thị nguyên nhân; preview 9.780 hàng không mất full JSON. Refresh/restart/download lại không dispatch hoặc tạo model client trong UI.
- [ ] Kiểm mismatch request/run/SHA, duplicate dispatch và review hash bằng tests ở Task 3; không thử paid click chỉ để kiểm guard.
- [ ] Kiểm receipt human review hiện có. Nếu thiếu, bàn giao case hash, các điểm cần kiểm và trường identity/decision/rationale/UTC cho người duyệt; giữ pending. Không tự ký thay người.
- [ ] Nếu lỗi runtime/UI mới được tái hiện: lưu repro, viết test RED trước fix nhỏ đúng phạm vi, GREEN rồi chạy checks Task 3. Nếu cần thay prompt/schema/scorer/payload contract, ghi thành task có spec/version riêng; không sửa trong nghiệm thu.

### Task 3: Checks và bàn giao mentor

**Files:** Test `tests/test_vinsoc_live_protocol.py`, `tests/test_query_live_ui_cloud.py`, `tests/test_vinsoc_live_ui.py`, `tests/test_vinsoc_demo_ui.py`; Read `.github/workflows/ci.yml`. Modify acceptance docs/receipts của Tasks 1–2.

**Interfaces:** Consumes all verified receipts. Produces một trang mở demo, kết quả test/CI đúng SHA và danh sách gate còn mở có bằng chứng.

- [ ] Chạy `python -m pytest tests/test_vinsoc_live_protocol.py tests/test_query_live_ui_cloud.py tests/test_vinsoc_live_ui.py tests/test_vinsoc_demo_ui.py -q`; lưu output thật, phân biệt AppTest và browser QA.
- [ ] Chạy `python -m compileall -q scripts/vinsoc_live_protocol.py scripts/run_query_live_ui_cloud.py scripts/vinsoc_live_ui.py scripts/vinsoc_demo_app.py`, `python scripts/verify_query_preservation.py`, `git diff --check`. Nếu có code fix, chạy thêm đúng full/required CI checks, không skip để lấy PASS.
- [ ] Viết hướng dẫn mentor ngắn: khởi động, mở saved run, xem SQL/result/evidence/cost/review. Chọn COUNT/AVG nếu verified, ghi rõ đó là saved output; giữ UDP/NULL để minh họa failure thật.
- [ ] Bảng bàn giao phải phân biệt: recorded coverage, technical PASS, EX, human reviewed/approved, NOT_RUN formal scopes, actual/unknown cost. Ghi blocker và bước tiếp theo, không tự tuyên bố calibration/evaluation/pipeline hoàn tất.
- [ ] Chỉ stage file đúng phạm vi; commit `docs(e2e): verify live UI acceptance and handoff`, push thẳng master không force. Kiểm GitHub Actions đúng commit SHA.
- [ ] Bàn giao SHA/link CI, link run success/failure, receipts/hashes, test output, cost reconciliation và số model calls của riêng tác vụ này = 0. Nếu chưa đủ receipt/browser QA, ghi NOT_VERIFIED và blocker cụ thể.

## Chỉ thị thực thi

Đọc toàn bộ tài liệu này rồi làm Tasks 1–3 tuần tự bằng Superpowers và GitHub. Không bắt đầu bằng chạy lại ba demo; chúng đã có kết quả thật. Ưu tiên thu và nghiệm thu các lượt UI đã chạy. Không dispatch thêm workflow trả phí, không sửa lịch sử và không ký review thay người. Hoàn thiện gói bàn giao, commit/push master và kiểm CI đúng SHA; mọi gate thiếu bằng chứng phải giữ mở.
