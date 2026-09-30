# R2 Evidence and Controller Remediation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:executing-plans` to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Status:** AUTHORIZED FOR OFFLINE EXECUTION theo ch? th? ng??i d?ng ng?y 2026-09-30; paid/model workflow v?n b? c?m.

**Goal:** Khôi phục CI, sửa đường chạy R2 và báo cáo để số liệu, safety, telemetry và provenance có thể kiểm chứng.

**Architecture:** Thống nhất tools và controller v2 trong package hiện có. Sử dụng scorer R2 đã khóa; các script frozen cũ được chặn trước provider creation. Artifact lịch sử giữ nguyên và được bổ sung hồ sơ đính chính riêng.

**Tech Stack:** Python 3.11/3.12, pytest, DuckDB, OpenAI SDK, GitHub Actions.

**Spec:** `docs/superpowers/specs/2026-09-25-dualsql-lite-agent-handoff-spec.md`; `docs/evaluation_protocol_v1.md`; các quyết định remediation trong plan này là phần bổ sung chờ người dùng review.

**Audited baseline:** Remote `master@cf46fb4abec295e43a31e9c026e7908e214fe43b`. CI run `36680054156` lỗi collection trên Python 3.11; Python 3.12 bị hủy. Local checkout dùng để lưu draft đang ở SHA cũ `8d9eacb`; chưa sync hay sửa code trong phiên soạn plan.

## Global Constraints

- Làm trực tiếp trên `master` sau khi plan được duyệt. Fetch và fast-forward; nếu HEAD mới hơn audited baseline thì đối chiếu thay đổi trước khi sửa. Không reset/force-push về commit cũ.
- Giữ nguyên `.env`, file untracked, thay đổi của người dùng, artifact lịch sử, source bytes và DuckDB snapshot.
- Không workflow dispatch, model/API call, E0-E3 rerun, frozen inference, demo, R1 run, ThreatFox/OTRF download hoặc snapshot rebuild trong task này.
- Chỉ dùng synthetic fixture và S5/S7 dev snapshot đã verify cho kiểm chứng offline. Không dùng S1/S4 hoặc output frozen để tối ưu prompt, retrieval, cap hay model.
- Không sửa câu hỏi, gold SQL, comparator, split lock, artifact cũ, v1 selection lock hay prompt để cải thiện điểm.
- No RL/fine-tune. Execution Accuracy vẫn là headline; chặn generator có thể làm điểm giảm nhưng phải báo cáo trung thực.
- Contract cho fake requests: model `gpt-5-mini-2025-08-07`, `reasoning_effort=low`, cap 1000, temperature key vắng mặt, SDK retries 0. No-tool role phải bỏ key `tools`.
- Mỗi role tối đa 5 model turns và 5 DB calls tổng cộng; chỉ 3 capability `database_profiler`, `value_search`, `sql_probe`.
- Không raw exception, credential, prompt/IOC nhạy cảm trong public error. Không overwrite output path.
- Mỗi checkbox chỉ đánh dấu sau khi verification liên quan thật sự pass. Không biến lỗi import thành test pass bằng skip/xfail/xóa test.
- Khi thay đổi contract code, tạo identity/version remediation mới. Không gán identity mới vào run lịch sử.

## Design Decisions for Review

Hướng được đề xuất là sửa trên package v2 hiện có, tái sử dụng scorer và boundary an toàn từ v1. Sửa riêng README chưa giải quyết đường chạy; viết lại toàn bộ framework tăng phạm vi và nguy cơ drift. Plan này tập trung vào những điểm bị hỏng đã được xác minh.

`V2DatabaseTools(snapshot_path, manifest_path)` là interface v2 thống nhất vì agents, metrics, offline gate và test source-grounding đang yêu cầu nó. Caller v2 đang dùng `CTUDatabaseTools` phải chuyển sang interface này. Không tạo alias giả để chỉ hết lỗi import.

Source reference phải được rút từ manifest đã verify và dataset có trong snapshot. Không hardcode case ID, gold literal hoặc một bảng map riêng cho benchmark. Nhận diện literal trong question và value có DB provenance vẫn là hai lớp evidence riêng.

Hai run frozen cũ được gán trạng thái historical/exploratory, provenance incomplete, cost incomplete. S1/S4 đã được xem và phân tích; không thể dùng chung bộ này làm holdout độc lập cho các sửa đổi dựa trên kết quả đó. Điều này không tự động ảnh hưởng R1 frozen hoặc tập dữ liệu khác.

## Review Focus

- Import được nhưng interface sai: test khởi tạo tools và chạy offline gate thực tế, không chỉ test import (Task 3).
- Linker failure bị che bằng schema rỗng: generator call count phải bằng 0 khi link không hợp lệ (Task 4).
- Response đã tính phí nhưng parse/turn-limit fail: telemetry của tất cả response vẫn được giữ (Task 4).
- SQL đúng cú pháp nhưng sai schema; empty SQL; duplicate/ordered rows: scorer phân biệt từng trường hợp (Task 5).
- Provenance bổ sung bị nhầm thành provenance tại thời điểm run, hoặc artifact bị overwrite: receipt ghi rõ verification time và missing fields (Task 2, Task 6).

---

### Task 1: Xác minh checkout, khóa evidence và chặn đường chạy frozen cũ

**Files:** Modify `scripts/run_frozen_v2_e3.py`, `scripts/run_frozen_baseline_e0.py`; Create `tests/test_r2_historical_entrypoints.py`.

**Interfaces:** Hai `main()` cũ fail-fast với safe category `HISTORICAL_ENTRYPOINT_DISABLED` trước khi tạo client, mở DB, tạo output hoặc gọi model. Run cũ vẫn truy vết được qua commit/script hash trong receipt.

- [x] Ghi initial SHA và `git status --short`; fetch `origin`, fast-forward master nếu không conflict. Nếu có overlap với thay đổi user thì STOP và báo file cụ thể.
- [x] Hash toàn bộ tracked artifact dưới `results/evaluation_v1/ctu_network_frozen/`, E0 dev run `36520685612` và v1 result/receipt/selection lock. Lưu inventory riêng để so sánh cuối task; không đọc/in `.env`.
- [x] Thêm `test_historical_main_stops_before_client_database_or_output` cho cả hai scripts: patch OpenAI constructor, DuckDB connect và output write để fail nếu bị gọi; assert category đúng và không có side effect.
- [x] Chạy `python -m pytest tests/test_r2_historical_entrypoints.py -q`; ghi failure thực tế trước patch. Chỉ chạy file này để lỗi collection của v2 chưa sửa không che verification.
- [x] Chặn hai entrypoint và chạy lại targeted test, `py_compile` hai scripts, `git diff --check`. Đọc diff để xác nhận không sửa artifact.
- [x] Commit riêng các file Task 1 sau khi verification pass. Không dispatch workflow.

### Task 2: Đính chính báo cáo từ artifact bất biến

**Files:** Modify `docs/evaluation/frozen_comparison_results.md`; Create `scripts/audit_r2_historical_reports.py`, `tests/test_r2_historical_reports.py`; Create `results/evaluation_v1/ctu_network_frozen/remediation_audit_v1/receipt.json`.

**Interfaces:** `audit_historical_reports(root: Path) -> dict[str, Any]`, chỉ đọc JSON/script bytes, không connect DB/provider. CLI: `python -m scripts.audit_r2_historical_reports --root results/evaluation_v1/ctu_network_frozen --output <new-path>`; output tồn tại thì fail.

Chỉ scan hai thư mục `baseline_e0/` và `v2_e3/` đã pin trong inventory. Receipt mới không trở thành input của chính auditor. Public error chỉ chứa category và tên file an toàn.

- [ ] Test fixture assert numerator khớp per-case flags, case IDs unique, report/per-case mismatch bị phát hiện; output cũ không bị overwrite; test monkeypatch provider và DuckDB access để fail.
- [ ] Chạy targeted tests để ghi failure, implement auditor tối thiểu rồi chạy lại.
- [ ] Auditor phải xác minh E0 EX 0/8, v2 E3 EX 2/8; E3 có 3 nonempty SQL chạy thành công theo flags lịch sử, 2 `EXEC_ERROR`, 3 `EMPTY_SQL`. Không đổi `EXEC_ERROR` thành `SYNTAX_ERROR`.
- [ ] Báo cáo ghi metric `syntax_valid` của script cũ mang semantics thực thi; syntax validity đúng nghĩa chưa được verify trong task này. Nhận diện case 003/008 schema error và case 004/006/007 output rỗng. Mô tả case 005 là result mismatch.
- [ ] Bỏ kết luận causal/validated. Ghi hai case khớp kết quả có stored-value grounding nhưng chưa tách được confound về complexity. Không kết luận fix nâng accuracy dựa trên số này.
- [ ] Receipt lưu original file SHA-256, audited repository SHA, verification time, summary counts, missing provenance list và `official_eligible=false`. Hash mới chỉ xác nhận artifact hiện tại, không chứng minh code/request gốc.
- [ ] Đánh dấu `cost_complete=false`, `cost_unknown=true`; giữ con số cũ dưới nhãn `reported_cost_usd`. Không suy ra total cost từ số turns, không đi vào account/API để bù dữ liệu.
- [ ] Chạy auditor, targeted tests và `git diff --check`; commit auditor, test, receipt và docs. So sánh inventory để chứng minh JSON cũ không đổi.

### Task 3: Khôi phục tools interface và offline grounding gate

**Files:** Modify `evaluation/dualsql_lite_ctu_gpt5_v2/tools.py`, `agents.py`, `metrics.py`, `offline_gate.py`, `runner.py`, `experiment.py`; Modify `tests/test_dualsql_ctu_gpt5_v2.py`, `tests/test_dualsql_lite_ctu_gpt5_v2.py`.

**Interfaces:** `V2DatabaseTools(snapshot_path: Path, manifest_path: Path)` exposes `schema`, `catalog`, `catalog_sha256`, `source_references(question: str)`, `schema_context()`, `database_profiler(dict)`, `value_search(dict)`, `sql_probe(dict)`, `invoke(name: str, arguments: Any)`. Cả 3 tools dùng bounds và safe error categories từ boundary v1 hiện có.

- [ ] Reproduce collection error. Đọc cả hai test files và caller; giữ semantic assertions, chỉ cập nhật interface theo design đã duyệt.
- [ ] Thêm tests cho manifest/snapshot source mismatch, source reference unknown/ambiguous, high-cardinality row-ID lookup và low-cardinality domain listing. Mapping phải đến từ source metadata đã verify; không benchmark lookup table.
- [ ] Implement interface thống nhất; controller-owned `evidence_id` có thể truy về actual tool result. Test evidence ID giả/mismatch không được chấp nhận.
- [ ] Xóa raw DuckDB error serialization trong v2 tools. Test error chứa sensitive sentinel không xuất hiện trong tool result/report.
- [ ] Chạy `python -m pytest tests/test_dualsql_ctu_gpt5_v2.py tests/test_dualsql_lite_ctu_gpt5_v2.py tests/test_dualsql_ctu_gpt5.py tests/test_dualsql_tools.py -q`.
- [ ] Nếu có verified S5/S7 snapshot, chạy `python -m evaluation.dualsql_lite_ctu_gpt5_v2.offline_gate --snapshot <verified-dev-snapshot> --manifest evaluation/ctu_network_public/dataset_manifest.json --output <new-output-path>`. Assert 7 referenced cases resolved, no-reference case 008, 2 negative controls, 27 v1 calls replayed. Synthetic gate không thay thế gate full snapshot; nếu thiếu snapshot thì ghi blocker, không download/rebuild trong task này.
- [ ] Full pytest phải hết collection error; ghi kết quả thực tế. Commit tools/interface fix sau focused verification.

### Task 4: Một controller, fail-closed và telemetry đầy đủ

**Files:** Modify `evaluation/dualsql_lite_ctu_gpt5_v2/runner.py`, `agents.py`, `experiment.py`; Modify `tests/test_dualsql_lite_ctu_gpt5_v2.py`.

**Interfaces:** `RoleResult` giữ `content`, `error`, `linked_schema`, `usage`, `trajectory`, attempted/response counts và `cost_unknown`. `run_case(...)` giữ cả linker và generator result ở mọi return path; không tính điểm tại inference. `validate_link(...)` là một validation gate được actual runner sử dụng.

Giữ interface `run_role(role: str, question: str, system_prompt: str, tools: V2DatabaseTools | None, client: Any, max_turns: int = 1, telemetry_sink: Callable | None = None) -> RoleResult` và `run_case(case: SQLBenchmarkCase, condition: str, tools: V2DatabaseTools, client: Any, schema_context: str) -> dict[str, Any]`. `telemetry_sink(request, telemetry)` lưu record trước parsing; không log credential hoặc raw provider error.

- [ ] Thêm offline fake-client tests: malformed JSON, empty tables/columns, unknown table/column, unresolved source, invented evidence, provider error, cap exhaustion, empty response. Assert generator `create()` count 0 sau linker failure và failure category rõ ràng.
- [ ] Test linker success có usage nhưng generator fail; malformed arguments sau response; role hết 5 turns; nhiều tool calls trong một turn. Assert telemetry được giữ, call 6/tool 6 bị chặn, no-tool request không có key `tools`.
- [ ] Gọi gate trước generator. Phân biệt no-reference grounding: grouping question không cần value vẫn có thể hợp lệ; schema rỗng không hợp lệ. Question literal giữ nguyên mà không giả mạo DB provenance. Không thêm heuristic số cột hoặc gold-column lookup để quyết định schema hợp lệ; mọi giới hạn mới phải có contract được review.
- [ ] Lưu response ID, actual model, input/output tokens, latency và usage trước parsing. Mọi return path phải giữ usage/trajectory; sum report bằng sum tất cả observed responses. Request không có response/usage phải để `cost_unknown=true`, không giả zero complete cost.
- [ ] Giữa các role chỉ truyền question, schema/evidence đã validate. Test gold sentinel vắng mặt trong inference requests. Failure kết thúc case; không fallback E0, không increase cap/turns, không thay prompt.
- [ ] Tạo client chỉ trên một boundary có retries 0; regression tests chặn secret trong serialized public errors. Giữ legacy entrypoints disabled.
- [ ] Chạy targeted controller tests và historical `tests/test_dualsql_agents.py`; commit controller fix khi pass.

### Task 5: Nối actual evaluator và safety boundary vào v2

**Files:** Modify `evaluation/dualsql_lite_ctu_gpt5_v2/experiment.py`, `runner.py`, `METRICS.md`; Modify `tests/test_dualsql_lite_ctu_gpt5_v2.py`; Create `tests/test_r2_v2_scoring_contract.py`.

**Interfaces:** Sau inference, `evaluate_sql_case(case: SQLBenchmarkCase, predicted_sql: str, snapshot: DuckDBSnapshot) -> SQLEvaluationResult` từ `evaluation/text_to_sql.py` là scorer duy nhất. `run_condition(...)` phải score mỗi final SQL qua interface này và export flags/aggregate từ kết quả đó.

Interface v2 sau hợp nhất: `run_condition(condition: str, cases: list[SQLBenchmarkCase], snapshot_path: Path, client: Any, output_dir: Path, manifest_path: Path) -> dict[str, Any]`. Caller truyền manifest đã verify; case IDs/file hashes phải khớp locked dev contract trước inference.

- [ ] Thêm tests synthetic: invalid syntax; syntactically valid SQL với unknown table/column; empty SQL; executable result mismatch; exact match; unsafe SQL. Assert syntax, execution success, safety rejection và EX độc lập.
- [ ] Thêm ordered-row và duplicate-row fixtures theo existing comparator. Test không tự sort ordered rows, không bỏ duplicate, không đổi column semantics/tolerance ngoài locked contract.
- [ ] Bỏ `syntax_valid = sql is not None`; `run_case()` chỉ tạo inference record. `experiment.run_condition()` phải gọi scorer, thay cho aggregate `execution_accurate` chưa được tính.
- [ ] Tool probes và final SQL đều đi qua existing read-only safety boundary; test multi-statement, write, external file/function và provenance/internal table access bị chặn trước DB execution.
- [ ] Giữa inference và scoring có gold-isolation gate; diagnostic linker/literal metrics không thay đổi EX. Không sửa core scorer trong task này. Nếu scorer core không đáp ứng test thì STOP và báo blocker để review contract mới.
- [ ] `METRICS.md` đồng bộ với actual locked comparator; bỏ placeholder SHA. Mô tả version/implementation hash do verifier ghi, không tự gán SHA chưa tồn tại.
- [ ] Chạy `python -m pytest tests/test_r2_v2_scoring_contract.py tests/test_text_to_sql_runner.py tests/test_dualsql_lite_ctu_gpt5_v2.py -q`; commit scoring integration sau PASS.

### Task 6: Offline report contract và evidence immutability

**Files:** Modify `evaluation/dualsql_lite_ctu_gpt5_v2/experiment.py`; Create `tests/test_r2_v2_report_contract.py`; Create receipt bổ sung ở đường dẫn mới cạnh receipt Task 2. Mỗi receipt đã commit giữ nguyên bytes.

**Interfaces:** `build_report_identity(snapshot_path: Path, manifest_path: Path, cases_dir: Path) -> dict[str, Any]` ghi git SHA, dirty-state, file/content hashes và model request contract. Schema report mới dùng raw counts/rates, explicit complete/partial status và eligibility reasons. Chỉ tạo report bằng fake client trong task này.

- [ ] Test report fake-client có git SHA, exact condition, case IDs/hash, snapshot logical hash, sources, scorer/builder hash, prompt/tool/schema/catalog hash, serialized request contract, response IDs/model/usage, per-case score và cost completeness.
- [ ] Test output final/partial tồn tại thì reject, duplicate/missing case IDs reject, actual model/usage mismatch ghi safe failure và giữ partial evidence. Generic `--cases-dir` ngoài verified S5/S7 dev phải fail trước provider.
- [ ] Tính complete cost chỉ khi usage của tất cả attempted calls được xác nhận đầy đủ. Dirty implementation và incomplete evidence không được official eligibility. Fake-client report luôn có `official_eligible=false` với reason `synthetic_provider`; không tạo headline accuracy cho model thật từ fixture.
- [ ] CLI v2 tạo OpenAI client phải luôn fail-fast trước client creation cho đến khi task paid riêng được duyệt và triển khai đầy đủ gates. Fake-client entrypoint vẫn kiểm thử được. Budget/pricing/account gate và workflow paid mới thuộc task sau.
- [ ] History receipt liệt kê missing run-time provenance; backfill chỉ những field có bằng chứng trực tiếp (original log, response ID, exact request bytes). Ghi inferred/reconstructed riêng. Không dùng filesystem mtime làm run timestamp proof, không đặt `provenance_complete=true` từ các hash mới.
- [ ] Chạy report-contract tests; so sánh inventory artifact/E0/v1 selection ban đầu. Commit verification contract và receipt bổ sung ở path mới.

### Task 7: Đồng bộ tài liệu và nghiệm thu exact-SHA CI

**Files:** Modify `README.md`, `evaluation/tool_calling/README.md`, `evaluation/tool_calling/benchmarks/README.md`, `evaluation/text_to_sql_benchmarks/README.md`, `docs/evaluation/frozen_comparison_results.md`; Create `docs/evaluation/r2_remediation_status.md`.

**Interfaces:** README là giới thiệu, track status, kết quả có link artifact, setup/tái lập và link report chi tiết. Remediation status ghi initial/final SHA, actual checks và deviations.

- [ ] Viết tài liệu giải thích tiếng Việt, giữ code/identifier tiếng Anh. R1 24 dev, 5 no-tool; CTU dev S5/S7 8 cases và S1/S4 historical 8 cases được tách khỏi legacy three-source R2 8+6. Không biến CTU snapshot thành bằng chứng three-source đã hoàn tất.
- [ ] Lấy mọi con số từ artifact/current command. Ghi test count gắn exact CI SHA/time hoặc bỏ fixed count để tránh drift. Phân biệt dev accuracy, holdout eligibility và historical exploratory findings.
- [ ] Giữa README và docs cùng ghi frozen E3 2/8 theo historical script, execution success 3/8 theo flags cũ, syntax validity chưa được xác minh đúng nghĩa; incomplete cost/provenance. Không tạo kết quả mới từ replay scorer ngầm.
- [ ] Chạy `python -m pytest -q`, targeted tests Tasks 1-6, `python -m compileall -q evaluation/dualsql_lite_ctu_gpt5_v2 scripts/audit_r2_historical_reports.py`, `python -m py_compile scripts/run_frozen_v2_e3.py scripts/run_frozen_baseline_e0.py`, `git diff --check`. Ghi command/output thực tế; thiếu dependency thì báo lỗi, không claim pass.
- [ ] Kiểm staged diff chỉ có allowed code/tests/docs/new receipt; artifact cũ, `.env`, user edits không đổi. Commit/push trên master; ghi final SHA và CI URL.
- [ ] Chờ CI Python 3.11 và 3.12 trên đúng final SHA xanh. Nếu fail thì sửa regression và đổi final SHA; không workflow model dispatch.
- [ ] Hoàn thành report và STOP FOR HUMAN REVIEW.

## Acceptance Criteria

- Hai entrypoint frozen cũ không thể tạo provider/DB/output khi chạy.
- Cả hai nhóm v2 tests collect và pass; full CI Python 3.11/3.12 xanh trên exact final SHA.
- Actual v2 inference dùng một tools/controller gate; linker fail thì generator không chạy.
- Fake-client test chứng minh telemetry đầy đủ trên success, parse failure, provider failure, turn/tool limit và generator failure.
- Actual v2 scoring dùng evaluator/safety/comparator đã khóa; syntax validity độc lập execution success.
- Offline S5/S7 grounding gate pass trên snapshot đã verify, hoặc blocker được ghi rõ và task chưa được claim hoàn tất.
- Artifact lịch sử/E0/v1 selection SHA unchanged; corrected docs và receipt không fake retrospective provenance/cost.
- Không có API call, paid suite, frozen rerun, prompt tuning, snapshot rebuild hoặc dataset download trong task này.

## Required Final Report

Ghi initial/final SHA; file changed; command và output thực; implementation CI URL; inventory hashes unchanged; corrected historical counts; cost/provenance completeness; offline gate result; zero paid attempts; deviations/blockers; STOP FOR HUMAN REVIEW.

## Gate Sau Remediation - Chưa Được Phép Chạy

Một plan riêng mới quyết định E0' (baseline + domain listing) và DualSQL comparison trên dev, model/budget/request lock và một lần chạy mỗi condition. Không dùng frozen cũ để chọn winner. Holdout mới cần nguồn/case chưa được dùng cho tuning và human approval trước khi mở. Gate này chờ review riêng.
