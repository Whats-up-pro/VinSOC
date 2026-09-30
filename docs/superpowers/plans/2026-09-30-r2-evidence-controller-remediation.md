# R2 Evidence and Controller Remediation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:executing-plans` to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Phạm vi phiên hiện tại:** Người dùng đã mở Tasks 8-10 sau remediation và exact-SHA CI: đúng một smoke E3, smoke qua gate thì chạy ngay một suite 8 dev cases trên cùng implementation SHA; không commit giữa hai lượt, không retry hoặc prompt rescue. Trần live mới $0.75 trong ngân sách còn lại; account owner đã xác nhận credit/hard limit đủ cho đúng project. Commit evidence khi live kết thúc rồi STOP FOR HUMAN REVIEW. Frozen S1/S4 vẫn closed. CLI offline cũ giữ disabled; chỉ entrypoint live mới có gates được phép tạo client.

**Status:** AUTHORIZED FOR REMEDIATION + LIVE R2 DEV VALIDATION. Người dùng đã duyệt ngày 2026-09-30: hoàn tất offline/CI rồi chạy một smoke E3 và, nếu smoke qua gate, một suite E3 dev. Tasks 8-10 thay thế điểm dừng offline trước đây. Không mở frozen.

**Goal:** Khôi phục tính đúng của pipeline R2 và chứng minh đường chạy question -> linker -> DB tools -> generator -> safety -> execution -> scoring -> report bằng model thật trên dev.

**Architecture:** Thống nhất tools và controller v2 trong package hiện có. Sử dụng scorer R2 đã khóa; các script frozen cũ được chặn trước provider creation. Artifact lịch sử giữ nguyên và được bổ sung hồ sơ đính chính riêng.

**Tech Stack:** Python 3.11/3.12, pytest, DuckDB, OpenAI SDK, GitHub Actions.

**Spec:** `docs/superpowers/specs/2026-09-25-dualsql-lite-agent-handoff-spec.md`; `docs/evaluation_protocol_v1.md`; các quyết định remediation trong plan này là phần bổ sung chờ người dùng review.

**Audited baseline:** Remote `master@cf46fb4abec295e43a31e9c026e7908e214fe43b`. CI run `36680054156` lỗi collection trên Python 3.11; Python 3.12 bị hủy. Local checkout dùng để lưu draft đang ở SHA cũ `8d9eacb`; chưa sync hay sửa code trong phiên soạn plan.

## Global Constraints

- Làm trực tiếp trên `master` sau khi plan được duyệt. Fetch và fast-forward; nếu HEAD mới hơn audited baseline thì đối chiếu thay đổi trước khi sửa. Không reset/force-push về commit cũ.
- Giữ nguyên `.env`, file untracked, thay đổi của người dùng, artifact lịch sử, source bytes và DuckDB snapshot.
- Tasks 1-7 chỉ kiểm chứng offline. Sau khi các gate đạt, Tasks 8-10 cho phép tối đa một smoke E3 và một suite E3 dev bằng API thật. Không E0/E1/E2/E0' rerun, frozen inference, demo SOC toàn hệ thống, R1 run, ThreatFox/OTRF download hoặc snapshot rebuild. Không tự retry lượt thất bại.
- Chỉ dùng synthetic fixture và S5/S7 dev snapshot đã verify cho kiểm chứng offline. Không dùng S1/S4 hoặc output frozen để tối ưu prompt, retrieval, cap hay model.
- Không sửa câu hỏi, gold SQL, comparator, split lock, artifact cũ, v1 selection lock hay prompt để cải thiện điểm.
- No RL/fine-tune. Execution Accuracy vẫn là headline; chặn generator có thể làm điểm giảm nhưng phải báo cáo trung thực.
- Contract cho fake và live requests: model `gpt-5-mini-2025-08-07`, `reasoning_effort=low`, cap 1000, temperature key vắng mặt, SDK retries 0. No-tool role phải bỏ key `tools`.
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

- [x] Test fixture assert numerator khớp per-case flags, case IDs unique, report/per-case mismatch bị phát hiện; output cũ không bị overwrite; test monkeypatch provider và DuckDB access để fail.
- [x] Chạy targeted tests để ghi failure, implement auditor tối thiểu rồi chạy lại.
- [x] Auditor phải xác minh E0 EX 0/8, v2 E3 EX 2/8; E3 có 3 nonempty SQL chạy thành công theo flags lịch sử, 2 `EXEC_ERROR`, 3 `EMPTY_SQL`. Không đổi `EXEC_ERROR` thành `SYNTAX_ERROR`.
- [x] Báo cáo ghi metric `syntax_valid` của script cũ mang semantics thực thi; syntax validity đúng nghĩa chưa được verify trong task này. Nhận diện case 003/008 schema error và case 004/006/007 output rỗng. Mô tả case 005 là result mismatch.
- [x] Bỏ kết luận causal/validated. Ghi hai case khớp kết quả có stored-value grounding nhưng chưa tách được confound về complexity. Không kết luận fix nâng accuracy dựa trên số này.
- [x] Receipt lưu original file SHA-256, audited repository SHA, verification time, summary counts, missing provenance list và `official_eligible=false`. Hash mới chỉ xác nhận artifact hiện tại, không chứng minh code/request gốc.
- [x] Đánh dấu `cost_complete=false`, `cost_unknown=true`; giữ con số cũ dưới nhãn `reported_cost_usd`. Không suy ra total cost từ số turns, không đi vào account/API để bù dữ liệu.
- [x] Chạy auditor, targeted tests và `git diff --check`; commit auditor, test, receipt và docs. So sánh inventory để chứng minh JSON cũ không đổi.

### Task 3: Khôi phục tools interface và offline grounding gate

**Files:** Modify `evaluation/dualsql_lite_ctu_gpt5_v2/tools.py`, `agents.py`, `metrics.py`, `offline_gate.py`, `runner.py`, `experiment.py`; Modify `tests/test_dualsql_ctu_gpt5_v2.py`, `tests/test_dualsql_lite_ctu_gpt5_v2.py`.

**Interfaces:** `V2DatabaseTools(snapshot_path: Path, manifest_path: Path)` exposes `schema`, `catalog`, `catalog_sha256`, `source_references(question: str)`, `schema_context()`, `database_profiler(dict)`, `value_search(dict)`, `sql_probe(dict)`, `invoke(name: str, arguments: Any)`. Cả 3 tools dùng bounds và safe error categories từ boundary v1 hiện có.

- [x] Đối chiếu collection recovery: lỗi cũ không còn tái hiện; 639 tests collect/pass. Đọc cả hai test files và caller; giữ semantic assertions, chỉ cập nhật interface theo design đã duyệt.
- [x] Thêm tests cho manifest/snapshot source mismatch, source reference unknown/ambiguous, high-cardinality row-ID lookup và low-cardinality domain listing. Mapping phải đến từ source metadata đã verify; không benchmark lookup table.
- [x] Implement interface thống nhất; controller-owned `evidence_id` có thể truy về actual tool result. Test evidence ID giả/mismatch không được chấp nhận.
- [x] Xóa raw DuckDB error serialization trong v2 tools. Test error chứa sensitive sentinel không xuất hiện trong tool result/report.
- [x] Chạy `python -m pytest tests/test_dualsql_ctu_gpt5_v2.py tests/test_dualsql_lite_ctu_gpt5_v2.py tests/test_dualsql_ctu_gpt5.py tests/test_dualsql_tools.py -q`.
- [x] Nếu có verified S5/S7 snapshot, chạy `python -m evaluation.dualsql_lite_ctu_gpt5_v2.offline_gate --snapshot <verified-dev-snapshot> --manifest evaluation/ctu_network_public/dataset_manifest.json --output <new-output-path>`. Assert 7 referenced cases resolved, no-reference case 008, 2 negative controls, 27 v1 calls replayed. Synthetic gate không thay thế gate full snapshot; nếu thiếu snapshot thì ghi blocker, không download/rebuild trong task này.
- [x] Full pytest phải hết collection error; ghi kết quả thực tế. Commit tools/interface fix sau focused verification.

### Task 4: Một controller, fail-closed và telemetry đầy đủ

**Files:** Modify `evaluation/dualsql_lite_ctu_gpt5_v2/runner.py`, `agents.py`, `experiment.py`; Modify `tests/test_dualsql_lite_ctu_gpt5_v2.py`.

**Interfaces:** `RoleResult` giữ `content`, `error`, `linked_schema`, `usage`, `trajectory`, attempted/response counts và `cost_unknown`. `run_case(...)` giữ cả linker và generator result ở mọi return path; không tính điểm tại inference. `validate_link(...)` là một validation gate được actual runner sử dụng.

Giữ interface `run_role(role: str, question: str, system_prompt: str, tools: V2DatabaseTools | None, client: Any, max_turns: int = 1, telemetry_sink: Callable | None = None) -> RoleResult` và `run_case(case: SQLBenchmarkCase, condition: str, tools: V2DatabaseTools, client: Any, schema_context: str) -> dict[str, Any]`. `telemetry_sink(request, telemetry)` lưu record trước parsing; không log credential hoặc raw provider error.

- [x] Thêm offline fake-client tests: malformed JSON, empty tables/columns, unknown table/column, unresolved source, invented evidence, provider error, cap exhaustion, empty response. Assert generator `create()` count 0 sau linker failure và failure category rõ ràng.
- [x] Test linker success có usage nhưng generator fail; malformed arguments sau response; role hết 5 turns; nhiều tool calls trong một turn. Assert telemetry được giữ, call 6/tool 6 bị chặn, no-tool request không có key `tools`.
- [x] Gọi gate trước generator. Phân biệt no-reference grounding: grouping question không cần value vẫn có thể hợp lệ; schema rỗng không hợp lệ. Question literal giữ nguyên mà không giả mạo DB provenance. Không thêm heuristic số cột hoặc gold-column lookup để quyết định schema hợp lệ; mọi giới hạn mới phải có contract được review.
- [x] Lưu response ID, actual model, input/output tokens, latency và usage trước parsing. Mọi return path phải giữ usage/trajectory; sum report bằng sum tất cả observed responses. Request không có response/usage phải để `cost_unknown=true`, không giả zero complete cost.
- [x] Giữa các role chỉ truyền question, schema/evidence đã validate. Test gold sentinel vắng mặt trong inference requests. Failure kết thúc case; không fallback E0, không increase cap/turns, không thay prompt.
- [x] Tạo client chỉ trên một boundary có retries 0; regression tests chặn secret trong serialized public errors. Giữ legacy entrypoints disabled.
- [x] Chạy targeted controller tests và historical `tests/test_dualsql_agents.py`; commit controller fix khi pass.

### Task 5: Nối actual evaluator và safety boundary vào v2

**Files:** Modify `evaluation/dualsql_lite_ctu_gpt5_v2/experiment.py`, `runner.py`, `METRICS.md`; Modify `tests/test_dualsql_lite_ctu_gpt5_v2.py`; Create `tests/test_r2_v2_scoring_contract.py`.

**Interfaces:** Sau inference, `evaluate_sql_case(case: SQLBenchmarkCase, predicted_sql: str, snapshot: DuckDBSnapshot) -> SQLEvaluationResult` từ `evaluation/text_to_sql.py` là scorer duy nhất. `run_condition(...)` phải score mỗi final SQL qua interface này và export flags/aggregate từ kết quả đó.

Interface v2 sau hợp nhất: `run_condition(condition: str, cases: list[SQLBenchmarkCase], snapshot_path: Path, client: Any, output_dir: Path, manifest_path: Path) -> dict[str, Any]`. Caller truyền manifest đã verify; case IDs/file hashes phải khớp locked dev contract trước inference.

- [x] Thêm tests synthetic: invalid syntax; syntactically valid SQL với unknown table/column; empty SQL; executable result mismatch; exact match; unsafe SQL. Assert syntax, execution success, safety rejection và EX độc lập.
- [x] Thêm ordered-row và duplicate-row fixtures theo existing comparator. Test không tự sort ordered rows, không bỏ duplicate, không đổi column semantics/tolerance ngoài locked contract.
- [x] Bỏ `syntax_valid = sql is not None`; `run_case()` chỉ tạo inference record. `experiment.run_condition()` phải gọi scorer, thay cho aggregate `execution_accurate` chưa được tính.
- [x] Tool probes và final SQL đều đi qua existing read-only safety boundary; test multi-statement, write, external file/function và provenance/internal table access bị chặn trước DB execution.
- [x] Giữa inference và scoring có gold-isolation gate; diagnostic linker/literal metrics không thay đổi EX. Không sửa core scorer trong task này. Nếu scorer core không đáp ứng test thì STOP và báo blocker để review contract mới.
- [x] `METRICS.md` đồng bộ với actual locked comparator; bỏ placeholder SHA. Mô tả version/implementation hash do verifier ghi, không tự gán SHA chưa tồn tại.
- [x] Chạy `python -m pytest tests/test_r2_v2_scoring_contract.py tests/test_text_to_sql_runner.py tests/test_dualsql_lite_ctu_gpt5_v2.py -q`; commit scoring integration sau PASS.

### Task 6: Offline report contract và evidence immutability

**Files:** Modify `evaluation/dualsql_lite_ctu_gpt5_v2/experiment.py`; Create `tests/test_r2_v2_report_contract.py`; Create receipt bổ sung ở đường dẫn mới cạnh receipt Task 2. Mỗi receipt đã commit giữ nguyên bytes.

**Interfaces:** `build_report_identity(snapshot_path: Path, manifest_path: Path, cases_dir: Path) -> dict[str, Any]` ghi git SHA, dirty-state, file/content hashes và model request contract. Schema report mới dùng raw counts/rates, explicit complete/partial status và eligibility reasons. Task 6 tạo report bằng fake client; live evidence chỉ được tạo theo Tasks 8-10.

- [x] Test report fake-client có git SHA, exact condition, case IDs/hash, snapshot logical hash, sources, scorer/builder hash, prompt/tool/schema/catalog hash, serialized request contract, response IDs/model/usage, per-case score và cost completeness.
- [x] Test output final/partial tồn tại thì reject, duplicate/missing case IDs reject, actual model/usage mismatch ghi safe failure và giữ partial evidence. Generic `--cases-dir` ngoài verified S5/S7 dev phải fail trước provider.
- [x] Tính complete cost chỉ khi usage của tất cả attempted calls được xác nhận đầy đủ. Dirty implementation và incomplete evidence không được official eligibility. Fake-client report luôn có `official_eligible=false` với reason `synthetic_provider`; không tạo headline accuracy cho model thật từ fixture.
- [x] Giữ CLI cũ fail-fast trước client creation. Fake-client entrypoint vẫn kiểm thử được. Chỉ entrypoint live mới của Task 8 được tạo client sau snapshot, identity, key-source, pricing và budget gates; hai entrypoint frozen lịch sử luôn bị chặn.
- [x] History receipt liệt kê missing run-time provenance; backfill chỉ những field có bằng chứng trực tiếp (original log, response ID, exact request bytes). Ghi inferred/reconstructed riêng. Không dùng filesystem mtime làm run timestamp proof, không đặt `provenance_complete=true` từ các hash mới.
- [x] Chạy report-contract tests; so sánh inventory artifact/E0/v1 selection ban đầu. Commit verification contract và receipt bổ sung ở path mới.

### Task 7: Đồng bộ tài liệu và nghiệm thu exact-SHA CI

**Files:** Modify `README.md`, `evaluation/tool_calling/README.md`, `evaluation/tool_calling/benchmarks/README.md`, `evaluation/text_to_sql_benchmarks/README.md`, `docs/evaluation/frozen_comparison_results.md`; Create `docs/evaluation/r2_remediation_status.md`.

**Interfaces:** README là giới thiệu, track status, kết quả có link artifact, setup/tái lập và link report chi tiết. Remediation status ghi initial/final SHA, actual checks và deviations.

- [x] Viết tài liệu giải thích tiếng Việt, giữ code/identifier tiếng Anh. R1 24 dev, 5 no-tool; CTU dev S5/S7 8 cases và S1/S4 historical 8 cases được tách khỏi legacy three-source R2 8+6. Không biến CTU snapshot thành bằng chứng three-source đã hoàn tất.
- [x] Lấy mọi con số từ artifact/current command. Ghi test count gắn exact CI SHA/time hoặc bỏ fixed count để tránh drift. Phân biệt dev accuracy, holdout eligibility và historical exploratory findings.
- [x] Giữa README và docs cùng ghi frozen E3 2/8 theo historical script, execution success 3/8 theo flags cũ, syntax validity chưa được xác minh đúng nghĩa; incomplete cost/provenance. Không tạo kết quả mới từ replay scorer ngầm.
- [x] Chạy `python -m pytest -q`, targeted tests Tasks 1-6, `python -m compileall -q evaluation/dualsql_lite_ctu_gpt5_v2 scripts/audit_r2_historical_reports.py`, `python -m py_compile scripts/run_frozen_v2_e3.py scripts/run_frozen_baseline_e0.py`, `git diff --check`. Ghi command/output thực tế; thiếu dependency thì báo lỗi, không claim pass.
- [x] Kiểm staged diff chỉ có allowed code/tests/docs/new receipt; artifact cũ, `.env`, user edits không đổi. Commit/push trên master; ghi final SHA và CI URL.
- [x] Chờ CI Python 3.11 và 3.12 trên đúng final SHA xanh. Nếu fail thì sửa regression và đổi final SHA; không workflow model dispatch.
- [x] Hoàn thành báo cáo offline theo phạm vi chỉ thị trực tiếp: Tasks 1-7 đã có verification, implementation CI xanh; commit hồ sơ cuối và kiểm CI của chính SHA đó trước STOP FOR HUMAN REVIEW.

> Checkpoint Tasks 1-7 đã hoàn thành với zero API calls tại `0973d5a6`. Chỉ thị live mới của người dùng mở Tasks 8-10 trong phiên tiếp tục này: không xin lại quyền đã duyệt, vẫn dừng khi gate fail và giữ frozen closed.

## Acceptance Criteria

- Hai entrypoint frozen cũ không thể tạo provider/DB/output khi chạy.
- Cả hai nhóm v2 tests collect và pass; full CI Python 3.11/3.12 xanh trên exact final SHA.
- Actual v2 inference dùng một tools/controller gate; linker fail thì generator không chạy.
- Fake-client test chứng minh telemetry đầy đủ trên success, parse failure, provider failure, turn/tool limit và generator failure.
- Actual v2 scoring dùng evaluator/safety/comparator đã khóa; syntax validity độc lập execution success.
- Offline S5/S7 grounding gate pass trên snapshot đã verify, hoặc blocker được ghi rõ và task chưa được claim hoàn tất.
- Artifact lịch sử/E0/v1 selection SHA unchanged; corrected docs và receipt không fake retrospective provenance/cost.
- Tasks 1-7 có zero API calls. Phần live có tối đa một smoke E3 và một suite E3 dev, không retry; có evidence đầy đủ và chi phí trong bound. Không frozen rerun, prompt tuning, snapshot rebuild hoặc dataset download.

## Required Final Report

Ghi initial SHA, LIVE_IMPLEMENTATION_SHA và final evidence SHA; files changed; command/output và exact-SHA CI URL; inventory hashes unchanged; corrected historical counts; cost/provenance completeness; offline gate; smoke và suite attempted/response counts, actual model, calls/tokens/cost, EX/syntax/execution/safety và từng error class; deviations/blockers; STOP FOR HUMAN REVIEW sau Task 10. Phân biệt kết quả smoke, dev accuracy và historical frozen evidence.

### Task 8: Triển khai entrypoint live R2 dev có kiểm soát

**Files:** Create `scripts/run_r2_v2_dev_live.py`, `tests/test_r2_v2_dev_live.py`; Modify `evaluation/dualsql_lite_ctu_gpt5_v2/experiment.py` chỉ khi cần nối runtime guard vào controller hiện tại.

**Interfaces:** `run_live_dev(mode: Literal["smoke", "suite"], snapshot_path: Path, output_path: Path, client_factory: Callable, smoke_report_path: Path | None = None) -> dict[str, Any]`. CLI chỉ hỗ trợ condition E3, split dev S5/S7; smoke chỉ case `ctu_sql_001`, suite đúng 8 ID đã khóa. Entry point dùng actual controller, native DB tools và evaluator; không FakeProvider/fallback trong live mode.

- [x] Viết offline tests cho fixed condition/split, real-provider identity, retries 0, model/cap/reasoning/no-temperature contract; gold sentinel không có trong request.
- [x] Test mọi preflight failure chặn trước `client_factory()`: snapshot/source/split/hash mismatch, key-source conflict, pricing/budget không xác minh được, output tồn tại. Không log key, raw exception hoặc credential.
- [x] Budget mới: tổng trần bảo thủ của smoke + suite không quá USD 0.75, trong phần còn lại của ngân sách USD 2 đã duyệt. Smoke reserve tối đa USD 0.10. Chi phí lịch sử incomplete không được coi là 0; dùng thông tin tài khoản/ngân sách mới có thể xác minh để xác nhận khả năng chi trả. Không tự mua credit hay tăng spend limit.
- [x] Pin giá theo nguồn OpenAI chính thức và verification time ngay trước lượt live. Tính bound từ request/context đã serialize, cap 1000, tối đa 5 turns và 5 DB calls mỗi role. Trước từng API call reserve cả remaining bound; không dựa vào giá trị `estimated_cost_usd=0` để mở gate.
- [x] Test partial evidence được lưu trước/sau response, kể cả lỗi parsing/tool/provider. API 429/model unavailable/parameter mismatch thì dừng, lưu safe category và cost-unknown state. Không SDK retry, không đổi model/prompt rồi gọi lại.
- [x] Suite gate đọc immutable smoke report, yêu cầu cùng implementation SHA, snapshot/split/scorer/prompt/tool/schema/catalog/request identity. Smoke subset luôn `official_eligible=false`; report suite phải kiểm chứng eligibility theo dev protocol, không tự gán true.
- [x] Chạy targeted tests, full pytest, compile checks và `git diff --check`. Commit/push code/tests; ghi `LIVE_IMPLEMENTATION_SHA` và chờ CI Python 3.11/3.12 xanh trên đúng SHA đó.

### Task 9: Một smoke E2E thật, rồi một suite E3 dev

**Files:** Không commit bất kỳ tracked file nào giữa smoke và suite. Tạo evidence ở đường dẫn mới; commit sau khi phần live kết thúc.

- [x] Xác nhận checkout sạch đối với code thực thi, `origin/master == LIVE_IMPLEMENTATION_SHA`, CI đúng SHA xanh và verified dev snapshot đang có sẵn. Chạy preflight budget/account/key-source; không tự tải nguồn mới.
- [x] Chạy smoke E3 `ctu_sql_001` đúng một lần. SDK có thể có nhiều API turns trong role theo contract; đây là một smoke scenario, không phải một API request. Ghi toàn bộ attempted/response/tool calls và usage.
- [x] Smoke PASS khi actual provider/model đúng, usage hợp lệ, linker/tools/generator đã thực sự chạy, final SQL không rỗng và đi qua safety/DB execution, scorer/report hoàn tất, cost trong bound. EX không bắt buộc true: kết quả SQL sai gold vẫn là một quan sát hợp lệ. Nếu pipeline dừng vì lỗi linker/API/empty SQL/safety/execution thì smoke FAIL, không suite, không retry.
- [x] Nếu smoke PASS, chạy ngay một suite E3 trên đúng 8 dev cases và cùng SHA. Smoke case xuất hiện lại trong suite là lượt đo đã khai báo trước; không lựa chọn rerun riêng case sai.
- [x] Lỗi model từng case được ghi đúng và tính trong mẫu số 8. Khi runtime guard cho phép, tiếp tục các case còn lại; lỗi hạ tầng/provider hoặc vượt budget kết thúc partial run. Không loại bỏ case thất bại để tăng điểm.
- [x] Dùng inventory riêng để xác nhận artifact E0/E1-E3/v1/frozen lịch sử không đổi. Không đưa smoke vào numerator/denominator của suite accuracy.

### Task 10: Commit live evidence và báo cáo, rồi human review

**Files:** Append immutable evidence tại `results/evaluation_v1/ctu_network_public/dualsql_v2_remediation_live/<run-id>/`; Create `docs/evaluation/r2_remediation_live_results.md`; cập nhật remediation status/README chỉ từ evidence đã kiểm chứng.

- [x] Verify final/partial report identity, SQL/scoring trace, calls/tokens và sum cost của mọi observed response. Response thiếu usage phải giữ cost incomplete; không diễn giải thành cost 0.
- [x] Báo smoke riêng; suite có EX trên 8, syntax validity, execution success, safety rejection, model/DB calls, token usage, cost, latency và per-case error class. Nếu suite partial, ghi partial và số case thực sự hoàn tất, không công bố như suite complete.
- [x] Chỉ đối chiếu immutable E0 run `36520685612` nếu snapshot/split/scorer/model/request contracts tương thích và được verify. Không rerun E0. Ghi rõ E3/controller đã sửa; kết quả dev không chứng minh độ tổng quát trên holdout.
- [x] Commit evidence sau khi smoke/suite kết thúc hoặc dừng vì lỗi; push master, đọc evidence-commit CI. Không sửa code để làm đẹp kết quả live trong task này.
- [x] STOP FOR HUMAN REVIEW với bằng chứng live R2 E2E. Không claim demo SOC toàn hệ thống hoàn tất; không mở frozen S1/S4 đã consumed.

**Verified checkpoint Tasks 8-10:** initial `0973d5a6`, implementation `90acf451c264d98c3cc35662670b3b772366136a`, CI `36700628921` Python 3.11/3.12 success. Một smoke PASS, một suite 8/8 complete: EX 1/8, syntax 4/8, execution 3/8, safety 1/8; 41 attempted/response calls, $0.02185315 cost complete. Evidence commit `82598875d2b415508a69fa86e8290a5656702444`, CI `36703577420` đúng SHA xanh cả hai jobs, 704 tests/job. [Report/commands/artifact hashes](../../evaluation/r2_remediation_live_results.md). 45 historical digests giữ nguyên, frozen closed. Closure docs chỉ ghi kết quả đã pass; final SHA/CI được xác nhận sau push trước STOP.

## Phần Chờ Review Riêng

Ablation E0' (baseline + domain listing), các condition E1/E2 khác, full SOC demo và holdout mới cần task riêng. Phê duyệt live R2 dev ở trên không cho phép chạy frozen cũ hoặc tự chọn nguồn/case holdout thay thế.
