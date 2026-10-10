# VinSOC — bàn giao ngoại tuyến R2–R6 ngày 10/10/2026

Làm trực tiếp trên `Whats-up-pro/VinSOC:master`, không branch/PR/agent. Điểm tiếp tục `3573496a165876f36116b2716ca737d17091aaf7` là ancestor; không checkout ngược. Đầu vào yêu cầu được ghi digest/đọc đầy đủ trong `resume_inputs_manifest.json`.

**Số lần gọi mô hình VinSOC mới: 0. Response mới: 0. SDK client được tạo: 0. Chi phí mô hình mới: 0 USD.** Prior cost, unknown exposure và số dư allocation chưa được xác minh, đều giữ null. Calibration/evaluation/pipeline mới pending; không ghi COMPLETE hoặc điểm mới từ gold/SQL lưu sẵn.

## Commits và CI từng mốc

Mọi số test dưới đây là **trên mỗi phiên bản Python 3.11 và 3.12**, không cộng hai job để tăng số test. Các CI receipts mới pin full SHA, job IDs, artifact URLs/digests và log digest.

| Mốc | SHA | CI | Full suite pass/skip | Required DB/worker pass/skip |
|---|---|---|---:|---:|
| R2 boundary | `c63972f793e6151187fdc9b6761021b019afe51d` | [38021882592](https://github.com/Whats-up-pro/VinSOC/actions/runs/38021882592) | 1.270 / 7 | 13 / 0 |
| R3 journal/preflight | `96cf8abc71e967eebc678aa19cecf91714672618` | [38024007524](https://github.com/Whats-up-pro/VinSOC/actions/runs/38024007524) | 1.282 / 7 | 13 / 0 |
| R4 report adapters | `47f89cdf9b3a6bb9856cd3ec6234021453f56044` | [38024305327](https://github.com/Whats-up-pro/VinSOC/actions/runs/38024305327) | 1.286 / 7 | 13 / 0 |
| R5 CLI/viewer/review | `bb480b4726751e0c79e4e63b6853da89ab246677` | [38024879936](https://github.com/Whats-up-pro/VinSOC/actions/runs/38024879936) | 1.294 / 7 | 13 / 0 |
| Khóa compile/preservation | `20742903069fb9df0312a4098f9a9807ab82bb80` | [38025633969](https://github.com/Whats-up-pro/VinSOC/actions/runs/38025633969) | 1.294 / 7 | 13 / 0 |
| R6 cận tiền có chứng cứ | `26b7b0303b8bcd407f75f6f28695c679f99597ba` | [38026168018](https://github.com/Whats-up-pro/VinSOC/actions/runs/38026168018) | 1.297 / 7 | 13 / 0 |
| Guard cuối: partial/review/SQL parity | `285a9439d001bd3d2fd046b690730d791cb2c184` | [38029084117](https://github.com/Whats-up-pro/VinSOC/actions/runs/38029084117) | 1.300 / 7 | 13 / 0 |

Targeted guards bắt buộc ở mốc khóa: 28/0; mốc R6: 31/0; guard cuối local và CI cả hai Python: 34/0. Job required đọc XML và fail nếu có skip. Compile, diff, preservation chạy trong cả hai full-suite jobs. Regression skips được báo riêng; không dùng chúng làm nghiệm thu dữ liệu/worker. Bước diagnostic chỉ chạy khi CI thất bại có thể bị skip khi job thành công; đó không phải test required.

Giữ nguyên receipts của CI thất bại: R2 lần đầu thiếu quyền delegated cgroup; lần hai observer chưa cho phép `PWD=/tmp` do bubblewrap đặt; R3 callback checkpoint thêm phá contract test cũ. Các fix có SHA/CI mới, không sửa test lịch sử để lấy điểm. CI trước guard cuối còn phép parity SQL lưu sẵn trực tiếp trong pytest từ test R1; guard cuối chuyển parity sang gold qua worker thứ hai. Đây chỉ là kiểm worker ngoại tuyến, không phải model EX mới.

## Gate đã đóng và phần còn mở

R1/T2 giữ nguyên bằng chứng 13 DB đúng checksum, 120 câu chuẩn qua SqlExecutor và [CI 38019271076](https://github.com/Whats-up-pro/VinSOC/actions/runs/38019271076). Host Windows hiện tại thiếu 12 DB Spider ở runtime path: khôi phục đúng binaries từ ZIP đã pin, giữ CTU đã có; receipt mới `local_exact_bundle_restore.json` ghi restored 12/preserved 1. Không export hoặc build lại DB/nguồn. CI tải lại chỉ các nguồn exact đã pin để kiểm, không đổi locks.

R2 kernel boundary đạt trên Linux required jobs: observer ngoài worker đọc `/proc` và cgroup; network namespace khác, environment chỉ locale/PWD cố định và không có sentinel secret; duy nhất DB cần thiết mount read-only; memory.max 536.870.912, swap.max 0, cpu.max 100000/100000, affinity một CPU. Hai allocations 300 MiB trong cùng group thực gây `oom_kill`; CPU loop bị signal CPU limit; wall timeout giết hết descendants. Không dùng executor `isolation` fields làm proof. Evidence trong `r2_independent_kernel_observation.json`, `offline_seal_ci_verified.json` và artifacts mỗi CI.

R3 guards/journal sẵn sàng: missing/sai/mutation selection chặn trước SDK; selection recompute từ 48 records thật và artifact digests; scope đã claim không mở lại; unknown exposure chặn request tiếp; source/data/document pricing được kiểm trước transmission. Raw response/usage lưu bền trước parse, cost gắn case/condition/role/request/response, report partial giữ checkpoint đang dở. **Selection positive vẫn pending 0/48**, không tạo calibration records giả hoặc dùng historical outputs thay thế.

R4 adapters giữ đúng external64/CTU32/tổng96 và pipeline32; missing/invalid không bị loại để tăng điểm. Macro database/domain, difficulty, SQL features, paired/cluster statistics và role costs tách rõ; pipeline routing/runtime/EX/provenance/facts/technical/human dùng denominator 32. Positive aggregation của 192 evaluation records và 32 native pipeline cases còn chờ lượt thật R7/R8.

R5 CLI nhận đúng case ID/câu hỏi gốc; paid batch dùng public `investigate_query`; mặc định viewer chỉ đọc artifacts. HTML có 32 IDs và bốn demo IDs cố định, question/native call/SQL/typed result/evidence/assessment/verification/review. Artifact hiện có `offline_pipeline_viewer.html` hiển thị **32 missing**, không được gọi là demo live thành công. Human identity/decision/rationale/UTC phải do người nhập; null, thiếu hoặc review hash sai không hợp lệ. Positive transcript/JSON–HTML equality và human review còn pending sau R8.

## R6 và quyết định ngân sách

Ba `preflight_*_frozen.json` đã thực thi qua CLI, exit 1/blocked; sidecar `preflight_execution_verified.json` ghi exit và digest thực, tất cả attempted=received=0/client_created=false. Local preflight còn `LOCKED_DATA_FILE_IDENTITY_MISMATCH` (raw locked bytes trên Windows) và `GIT_NOT_EXACT_CLEAN_MASTER` vì các untracked files có sẵn. Tracked tree sạch; không xóa hay normalize file người dùng để né gate. Backend Linux/cgroup bắt buộc. CI exact-SHA PASS là bằng chứng riêng, không tự nâng local preflight hoặc account/selection thành PASS.

Canonical directory hiện không tồn tại cả ở lần scan có quyền đọc ngoài sandbox: không thấy local claims mới, nhưng authoritative consumed state vẫn unknown. `canonical_readonly_scan.json` giữ prior cost/exposure/remaining null; không tạo ledger hoặc tự xác nhận allocation. Network E2E cũ không cấp quyền cho scope mới; binary/content lock/ledger A2/A3 cũ vẫn là blockers riêng.

Đã đo 240 initial payloads từ catalog DB thật, max 15.986 bytes, không quá cap. Đây là audit payload, không phải prediction/model records. Future histories và outer payloads chưa được đo bằng actual model output; runtime vẫn kiểm cap bytes/messages trước mỗi request. Framing 512 token chưa xác minh, không thể tự khai verified để lấy cận thấp.

Xem [gói quyết định R6](VinSOC_R6_Budget_Decision_2026-10-10.md) và `public_cost_bound.json`: giá hiện hành từ tài liệu model thật có digest; cận bảo thủ dùng toàn context window. Calibration tối đa 168 requests / 17,136 USD; evaluation 672 / 68,544 USD; pipeline E0 96 / 30,1843456 USD hoặc E3 256 / 46,5043456 USD. Tổng mới tối đa **936 / 115,8643456 USD** hoặc **1.096 / 132,1843456 USD**, chưa cộng prior cost chưa rõ. Dự toán thấp 10,3728384/12,0240384 USD giữ nhãn conditional, không là quyền transmission.

Owner cần đối soát canonical ledger/allocation/prior/unknown/remaining và host cũ, xác nhận account/giá trong sáu giờ, rồi quyết định hạn mức cụ thể và phạm vi cấp (có thể calibration trước). Evaluation/pipeline vẫn cần selection thật trước SDK. **Dừng trước request trả phí đầu tiên; chưa dùng bất kỳ quyền network E2E cũ nào.**

## Receipts và tái lập

Các receipts mới nằm trong `results/evaluation_v1/text2sql_integration_v1/offline_release_20261010/`, có `artifact_manifest.json` để kiểm digest. Các receipts gốc và hai ZIP giữ nguyên bytes; preservation kiểm 3.640 file baseline. Local full suite Windows không đạt; lượt ngoài sandbox đứng lâu ở 78% đã dừng, receipt riêng `local_full_suite_blocker.json`. Full suite Linux trên cả hai Python là evidence nghiệm thu, không đổi local FAIL thành PASS.

Runbook CLI/viewer/review/preflight: [VinSOC_Query_Offline_Release_Runbook_2026-10-10.md](../VinSOC_Query_Offline_Release_Runbook_2026-10-10.md). Mỗi output mới append-only. Bốn demo IDs không thay đổi khi missing/failed. Runtime source hashes đã khóa trước paid; sửa semantics sau này phải freeze/CI/release lại, không giữ identity cũ.

Commit bàn giao chỉ thêm docs/receipts, không đổi source runtime. SHA bàn giao và CI cuối được xác minh sau push, ghi ở bàn giao người dùng và artifact CI cùng SHA; không hash future commit hoặc tự tạo vòng lặp manifest.
