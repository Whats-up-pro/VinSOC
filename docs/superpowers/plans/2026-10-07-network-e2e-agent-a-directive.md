# Chỉ thị Agent A — bàn giao demo VinSOC end-to-end ngày 06–07/10/2026

> Thực hiện bằng superpowers:executing-plans, một writer trên master. Đây là chỉ thị triển khai, kiểm chứng và bàn giao phần mềm; không tạo thêm một vòng decision packet rồi dừng. Checklist là việc phải làm, không phải kết quả đã đạt.

**Mục tiêu:** Người dùng chạy CLI trên laptop: model chọn network tool và tự tạo arguments → production tool truy vấn DuckDB read-only → EvidenceStore ghi evidence → model viết assessment → kiểm chứng facts/citations → người thật review. JSON và HTML cho phép xem lại toàn bộ luồng mà không gọi API thêm.

**Thiết kế:** Tái sử dụng public InvestigationOrchestrator.investigate(), provider và NetworkSkill hiện có. Thêm một policy network-only tùy chọn và một transport guard có ledger bền vững. Không tạo pipeline song song gọi private dispatcher để giả lập lifecycle.

**Phương pháp triển khai:** Test-first cho các boundary mới; fixture/synthetic provider chỉ trong unit test. Live dùng OpenAI SDK thật. Commit và push trực tiếp master theo từng mốc; CI xác minh đúng implementation SHA trước API.

**Phạm vi thời gian:** Ưu tiên bản demo dùng được trong ngày 06–07/10. Không hứa kết quả model sẽ pass. Nếu run thất bại, vẫn bàn giao code chạy được, partial receipt và HTML hiển thị đúng lỗi.

## 1. Điểm xuất phát và thứ tự ưu tiên

### Execution cursor khi chỉ thị được commit — 07/10/2026

- Remote master hiện ở 815c6787769318474d08ddae6484f9ba36093974; CI run 37447225522 đã xanh.
- Commit a4a75117dba908a0c0fdcfe1a23f95d111f4a781 đã tạo LiveWindow, policy/network contract, E2E CLI, renderer và bốn test files; 815c678 sửa missing ValidatedAssessment import.
- Không làm lại hoặc xóa các file này. Bắt đầu bằng diff/audit implementation hiện có so với acceptance matrix của chỉ thị, viết failing tests cho phần thiếu rồi sửa tiếp.
- Read-only audit tại 815c678 cho thấy scripts/demo_ctu_network_public_model_driven.py vẫn chứa private _execute_tool_call, không có lời gọi .investigate( trong E2E script và vẫn còn PRIOR_TASK_COST_USD. Vì vậy CI xanh hiện tại chỉ chứng minh các tests hiện có pass; chưa chứng minh public lifecycle, ledger reconciliation hoặc live E2E hoàn tất.
- Việc đầu tiên của Agent mới là chứng minh bằng test rằng --e2e đi qua InvestigationOrchestrator.investigate(), tool_choice=auto và provider guarded client. Nếu test đỏ, sửa đúng boundary đó trước preflight/live. Không dispatch API trên 815c678 chỉ vì CI đã xanh.
- Các CLI flags/code đã có phải được giữ tương thích nếu đúng contract. Chỉ thêm/sửa phần thiếu; không tạo entrypoint E2E thứ hai.

Baseline lịch sử đã đối chiếu trước khi implementation trên được thêm:

- 62da30100cac9375691a2d82587fde48f23f7a51 là planning baseline, không phải SHA để checkout hoặc chạy live. Luôn sync HEAD hiện hành theo Mốc 0.

- master: 62da30100cac9375691a2d82587fde48f23f7a51.
- CI exact SHA: https://github.com/Whats-up-pro/VinSOC/actions/runs/37423537492 — Python 3.11/3.12 đều 911 passed, 1 skipped. Một test skipped không chứng minh snapshot local đã qua gate.
- R1 dev v2: 22/24, exact-call F1 0.9508, no-tool 5/5. Giữ nguyên kết quả.
- R2 Phase2 dev: 7/8. Case006 vẫn TOOL_LIMIT / NO_FINAL_SQL. Giữ nguyên predictions và scoring lịch sử.
- Cross-domain đã có 12 DB và 24 calibration + 96 evaluation candidates. Đây là candidate inventory; annotation/semantic instances/release lock chưa hoàn tất, không có paid cross-domain score mới.
- Demo hiện chưa có bằng chứng hoàn tất hai scenario bằng public lifecycle. CLI cũ không có các flags mới trong chỉ thị này; không chạy lệnh mới trước khi implement.

**Chỉ thị này thay thế thứ tự ưu tiên của bản demo trước.** Tiếp nhận các requirements public lifecycle, facts, HITL và partial receipts trong docs/superpowers/plans/2026-10-06-network-e2e-completion.md; chia lại thành các mốc bên dưới để giao phần mềm sớm. Các mục đã code tại a4a7511/815c678 được xem là candidate implementation chờ audit theo chính acceptance criteria bên dưới, không tự động được đánh dấu hoàn tất.

Tạm dừng implementation/inference cross-domain ở checkpoint hiện có. Giữ tất cả code/candidates/receipts. Hoãn Tasks 9–11 về matched R2 E0/E3 trong plan cũ đến task riêng sau bàn giao demo; không hủy công việc đó và không chạy cặp R2 trong cửa sổ này.

Không yêu cầu hoàn tất 96 câu, benchmark thống kê, endpoint, CTI hoặc frozen trước demo. Không đổi mục tiêu thành demo SQL trực tiếp từ LLM vào production.

## 2. Quyền thực hiện và ràng buộc bắt buộc

- Quyền gọi OpenAI thật cho demo đã được cấp. Sau exact-SHA CI và preflight PASS, thực hiện lượt live bên dưới; không hỏi lại quyền gọi API.
- Model demo: gpt-4.1-mini-2025-04-14; temperature=0; max_completion_tokens=1000; SDK max_retries=0; endpoint OpenAI chính thức; không fallback.
- Giới hạn một invocation live, hai scenario Botnet và Normal, tối đa hai requests/scenario, bốn attempted requests cả task. Không smoke trước, không diagnostic bổ sung, không retry hay gọi lại case sai.
- Dữ liệu chỉ CTU-13 S5/S7 đã có. Không tải lại nguồn mặc định. Không ThreatFox/OTRF, endpoint synthetic, frozen hay R1 model suite.
- Ngân sách demo tối đa USD 0.25, đồng thời không vượt phần allocation còn được người dùng cấp. Không tự cộng ngân sách cũ USD 0.75, không dùng ngân sách benchmark cross-domain, không coi số credit cũ là balance hiện tại.
- Không mua credit, tăng spend limit, đổi key/model hoặc dùng key khác khi lỗi.
- Không reset --hard, clean -fdx, force push, tạo branch/PR, tự sửa history. Không git add . hoặc git add -A.
- Giữ nguyên .env, staged/untracked ngoài task, snapshots, source bytes và artifacts lịch sử. Không in key, prefix/length/fingerprint, auth header, raw provider exception hoặc raw traceback.
- Có thể dùng loader/check_env hiện có để đọc cấu hình bình thường. Không mở/in/copy nội dung .env, không viết .env.example chứa giá trị thật, không ghi đè .env.
- Không chỉnh gold/prompt/analytics sau khi thấy output để lấy một run đẹp; không splice predictions hoặc hợp nhất các lần thử thành một demo.
- Không đổi default production behavior ngoài profile network-only. Sửa provider dùng chung chỉ để inject guarded client; phải có regression tests.
- Human decision phải do người thật. Agent không tự approve thay người dùng. Deferred review là trạng thái hợp lệ để bàn giao phần kỹ thuật, nhưng chưa là human-approved E2E.

## 3. Đầu ra cuối cùng phải có

1. Một entrypoint CLI canonical: scripts.demo_ctu_network_public_model_driven với mode --e2e.
2. Preflight-only không tạo OpenAI client và không gửi request.
3. Public orchestrator lifecycle cho từng scenario; native network schema, tool_choice=auto, arguments do model sinh.
4. JSON technical receipt hoàn chỉnh hoặc partial, có per-request usage/cost và truy ngược evidence.
5. HTML standalone đọc chính JSON đó, mở offline, không CDN/API/re-query DB.
6. Review mode interactive hoặc deferred + offline review finalization; không chế ra human approval.
7. Code/tests/lock/sanitized receipt/runbook đã commit và push; CI exact implementation SHA và CI final handoff SHA được báo riêng.
8. PowerShell commands copy-paste chạy được trên laptop, kèm giải thích live vs replay.

Definition of Done chỉ đạt khi cả hai scenario có valid assessment, factual validation và review thật hoàn tất. Nếu kỹ thuật đạt nhưng người dùng chưa review, báo TECHNICAL_COMPLETE / AWAITING_HUMAN. Nếu model hoặc tool fail, báo PARTIAL/BLOCKED và bàn giao bằng chứng; không ghi COMPLETE.

## 4. Các file được phép triển khai

| File | Trách nhiệm |
|---|---|
| agent/investigation_policy.py — mới | Protocol policy, ValidatedAssessment, safe validation error |
| agent/network_investigation_policy.py — mới | Network schema/prompt, validate arguments, complete tool message, structured facts |
| agent/orchestrator.py | Policy injection vào public investigate; verification/termination/HITL |
| agent/provider.py | Optional injected guarded client; giữ default behavior |
| evaluation/finalization/live_window.py — mới | Durable claim, attempts, reservations, usage/cost và unknown-cost latch |
| evaluation/finalization/network_contract.py — mới | Snapshot/scenario qualification, independent evidence verification |
| evaluation/finalization/NETWORK_E2E_v1.lock.json — mới | Khóa data/scenario/policy/schema/prompt/request envelope |
| scripts/demo_ctu_network_public_model_driven.py | CLI modes, preflight, public lifecycle, receipts/review |
| scripts/render_network_e2e_report.py — mới | JSON → HTML offline |
| tests/test_finalization_live_window.py — mới | Budget, race/crash, error/privacy, transport |
| tests/test_network_e2e_lifecycle.py — mới | Public lifecycle, native calls, termination, real review boundary |
| tests/test_network_e2e_policy.py — mới | Facts, evidence/parents, coverage, argument scope |
| tests/test_network_e2e_report.py — mới | Renderer và partial/awaiting-human statuses |
| Existing demo/provider/HITL tests | Regression cho interfaces đã sửa |
| docs/VinSOC_Verified_Demo_Runbook_2026-10-05.md | Commands mới đã chạy, không viết trước thành công |
| results/evaluation_v1/network_e2e_v1/20261006/ | Sanitized actual receipts và hashes sau run |

Chỉ sửa vinsoc_data/network_source.py, vinsoc_data/domain_queries.py hoặc skills/network_skill.py nếu một failing test chứng minh coverage/provenance bị mất trong luồng này. Không refactor rộng, không thay ngưỡng analytics để ép Botnet/Normal verdict.

Không sửa scripts/run_vinsoc_finalization_dev.py, R2 matcher/scorer/benchmark, historical locks hoặc cross-domain candidates trong task demo.

## 5. Mốc 0 — sync và bảo vệ workspace, rồi bắt tay code

**Input:** Repo trên laptop, .env hiện có, CTU snapshot hiện có.

1. Chạy riêng từng lệnh; ghi kết quả Git an toàn:
   - git branch --show-current
   - git rev-parse HEAD
   - git status --short
   - git diff --name-only
   - git diff --cached --name-only
   - git remote -v
   - git fetch origin master
   - git rev-parse origin/master
2. Xác nhận repo Whats-up-pro/VinSOC, master tracking origin/master. Nếu chỉ có untracked ngoài task: ghi danh sách path, giữ nguyên, tiếp tục. Untracked không được dùng làm lý do ngồi chờ dọn máy.
3. Nếu master chỉ behind và tracked/staged sạch, git pull --ff-only origin master. Nếu có local commits hoặc overlapping tracked changes, không tự rebase/merge; giữ nguyên và báo đúng SHA/path xung đột.
4. Nếu tracked/staged ngoài task làm mất clean implementation gate, dùng fresh clone cùng repo/master trong thư mục riêng; giữ checkout cũ nguyên vẹn. Snapshot có thể dùng absolute path read-only từ checkout cũ. Không copy .env: thêm --env-file PATH vào demo CLI, default Path('.env'), rồi dùng scripts.check_env.load_env(path) và resolve_openai_key(os.environ, dotenv_values) hiện có. Flag chỉ chứa đường dẫn, không key; không ghi absolute personal path vào public report. Trong fresh clone, truyền path của .env cũ vào CLI. Test chứng minh file không bị ghi và conflicting process/.env vẫn bị chặn. Không phải sửa file .env hoặc loader hiện có.
5. Ghi initial SHA, danh sách protected paths và hashes của historical receipts/locks tracked mà task phải giữ. Chỉ ghi tên untracked ngoài task; không đọc/stage chúng. Ngoại lệ đầu vào được phép là .env qua safe loader và snapshot/source identity đang dùng cho demo. Không đọc/ghi gold frozen.
6. Đọc code public investigate(), NetworkSkill, EvidenceStore, provider và HITL. Chuyển ngay sang Mốc 1; không tạo commit tài liệu-only cho Mốc 0.

**Output:** Workspace có thể sửa đúng allowlist, initial SHA và preservation inventory. Git divergence có thật là blocker; untracked unrelated không phải blocker.

## 6. Mốc 1 — sửa luồng thật, transport guard và CLI

**Input:** HEAD đã sync, public orchestrator, production network tool, CTU snapshot.
**Output:** CLI E2E và preflight có tests; chưa gọi API.

### 1A. Transport guard trước mọi client/request

Interfaces cần giữ:

    LiveWindow.open(root: Path, window_id: str, gates: dict) -> LiveWindow
    LiveWindow.claim(condition: str, implementation_sha: str, output: Path) -> dict
    LiveWindow.guarded_client(client: Any, condition: str, contract: dict) -> Any
    LiveWindow.record_terminal(condition: str, receipt: dict) -> None

- Dùng một condition NETWORK_DEMO cho task này. Không mở R2_E0/R2_E3.
- Ledger/claim canonical nằm ngoài checkout: %USERPROFILE%/.vinsoc/live-windows/network-finalization-20261006/. Root này giữ nguyên qua clone, output directory và code commit. Không tạo window ID khác để chạy lại.
- Claim exclusive trước request đầu tiên. Ghi attempted + reservation trước SDK call; ghi response/model/usage/cost trước parse/scoring. Dùng atomic persistence/flush để crash không xóa chi phí.
- Changing --output hoặc --ledger không cấp lượt mới. Nếu ledger path khác root đã đăng ký, reject. Claim đã consumed không được xóa để chạy lại.
- Missing usage, model mismatch, provider failure hoặc interrupted attempt tạo stop/unknown-cost state. Known usage vẫn được giữ dù parse/validation fail.
- SDK request phải nhận thật model pin, temperature=0, cap1000, retry0, tool_choice=auto, network-only schemas. Test bắt arguments tại chat.completions.create, không chỉ constructor.
- Guard tất cả requests kể cả assessment. Client được inject vào OpenAIProvider; không tạo client thứ hai. Cleanup fail không được làm mất report/cost.
- Khóa đường legacy/diagnostic để không bypass cửa sổ sau run. Không dispatch chúng trong task này.

Tests bắt buộc: preflight tạo client=0; cap request đúng; duplicate/concurrent claim; crash sau attempted; đổi output; missing usage/model; bool/NaN/negative budget; charged malformed output; safe 429; formatted traceback không chứa sentinel secret/raw error; cleanup failure.

### 1B. Public lifecycle và policy network-only

Interfaces:

    InvestigationOrchestrator(..., investigation_policy: InvestigationPolicy | None = None)
    OpenAIProvider(..., client: Any | None = None)

    InvestigationPolicy.tool_schemas() -> list[dict]
    InvestigationPolicy.system_prompt() -> str
    InvestigationPolicy.validate_tool_call(call: dict) -> dict
    InvestigationPolicy.tool_response(call: dict, result: Any, store: EvidenceStore) -> str
    InvestigationPolicy.parse_final_response(content: str, store: EvidenceStore) -> ValidatedAssessment
    InvestigationPolicy.validate_case(case: InvestigationCase) -> dict

- None giữ legacy behavior. Network profile dùng schema production nguyên trạng, chỉ quảng bá/cho phép network_investigation.
- Runner gọi orchestrator.investigate() đúng một lần/scenario; không gọi private _execute_tool_call(), không dùng fixed_pipeline, không manually dựng lifecycle giả.
- max_steps=2, max_review_cycles=0. Lượt 1 phải có đúng một native network call; lượt 2 final assessment và không tool call. No-tool, nhiều calls ở lượt1 hoặc xin thêm tool ở lượt2 đều có termination riêng, không tạo final assessment thay model. Test chứng minh một response nhiều calls không được thực thi lén thành nhiều tool executions.
- Initial request chỉ có IPv4, historical interval và câu hỏi điều tra trung tính. Không gửi nhãn Botnet/Normal, seed/gold row, gold SQL hoặc verdict mong muốn.
- Arguments model đi qua validation scope và sanitizer hiện có; không điền hộ giá trị thiếu, không thay wrong interval/IP bằng gold. Reject out-of-scope trước tool.
- Giữ native tool_call_id trong conversation; evidence IDs phải là IDs đã assign trong EvidenceStore.
- Triage → investigate → verify → review được public lifecycle ghi thật. Không gọi verify completed trước khi facts/schema pass.
- Không cắt model assessment còn 2000 chars trong network profile. Không lấy một planning message làm final answer, không dùng deterministic _analyze_evidence() thay assessment model.
- Kiểm legacy provider, HITL, CLI và schema regressions.

### 1C. Evidence/facts kiểm được, không chỉ citation có tồn tại

Structured final response gồm assessment, hypotheses, risk_level, confidence, evidence_ids, observations, limitations.

Observation shape:

    {"evidence_id": "...", "field": "connection_count", "value": 7}

- Ghi toàn bộ OBSERVED và DERIVED evidence, parent links, source references và coverage metadata thật vào receipt/tool message. Bỏ hidden slices 12 evidence, 20 references và 4000-char clipping trong network profile.
- Không ép tool trả toàn bộ DB. Phân biệt full query population, tool retrieval limits, source-reference samples và aggregate coverage. Nếu tool vốn bounded: giữ thông tin đó, không gọi sample là complete.
- verify_network_evidence(snapshot, arguments, evidence) độc lập kiểm source_dataset/source_row_id và predicate IP/time; recompute count/time/endpoints/bytes trên đúng population được khai báo.
- Validate structured observations đối với exact evidence đã gửi. Wrong count/IP/port/protocol/time với valid evidence ID vẫn FAIL; bool không được coi là int.
- Mỗi scenario nonempty phải có ít nhất một count observation và một endpoint/port/protocol fact đúng. DERIVED candidate phải có valid parent IDs; candidate không phải kết luận malware.
- Không tự chọn risk HIGH cho Botnet hoặc LOW cho Normal. CTU labels chỉ dùng làm scenario ground truth ngoài model input, không phải CTI verification.
- No evidence phải giữ uncertainty; tool trả rỗng không phải R1 no-tool.
- Factual validator không chứng minh mọi câu văn tự do đúng. Ghi prose_semantics_machine_verified=false; human review xem causal claims/verdict/limitations.
- Nếu entire next request quá lớn, PAYLOAD_BOUND_EXCEEDED trước call; giữ cost trước đó. Không slice âm thầm để pass.

Tests dùng real fixture DuckDB: wrong facts với valid IDs; wrong parent; cùng row_id khác dataset; source sample vs population; truncation; injected tool text; no evidence; Unicode; first scenario pass/second fail. Không source download/API.

### 1D. CLI và human review thật

Thêm vào entrypoint hiện có:

    --e2e
    --preflight-only
    --scenario all
    --budget-usd 0.25
    --ledger ABSOLUTE_PATH
    --gates PATH
    --env-file PATH
    --review-mode interactive|deferred
    --review-receipt PATH

Giữ --snapshot/--output. --diagnostic-first-request mutually exclusive với --e2e; không dùng trong task. Live task chỉ --scenario all; không chạy riêng Botnet rồi Normal bằng hai invocations.

- Preflight: key source/presence, Git/CI, snapshot/lock/scenario, ledger và costs; không tạo OpenAI client. Ghi preflight JSON ở file khác technical receipt để không overwrite.
- Interactive dùng ConsoleHumanReviewGate/agent.hitl thật; người dùng approve/reject/escalate. More evidence ở cửa sổ này phải escalate, không phát request thứ 5.
- Deferred: lưu technical receipt awaiting_human. Offline --review-receipt recheck identity, mở review thật và ghi linked review receipt mới; SDK/client/API đều 0. Không sửa technical JSON đã đóng.
- Aggregate model_generated_* flags chỉ tính sau tất cả stages; first scenario success không che second failure. Tách model_generated_assessment khỏi assessment_validation_passed.
- --help và missing/invalid argument errors có message an toàn, exit code nhất quán.

**Test → implement → verify → commit/push:**

1. Viết failing tests cho 1A, chạy để thấy boundary lỗi; implement, chạy GREEN.
2. Làm tương tự 1B, 1C, 1D. Có thể commit từng subtask đã pass; không commit một feature chưa có tests.
3. Chạy targeted: test_finalization_live_window, test_network_e2e_lifecycle, test_network_e2e_policy, test_demo_ctu_network_public_model_driven, test_check_env, test_hitl và provider tests có thật trong tree.
4. py_compile file sửa; git diff --check; kiểm staged paths theo allowlist.
5. Commit atomic + git push origin master. Không dừng chỉ với "đang viết tests"; tiếp tục Mốc 2 khi offline checks pass.

## 7. Mốc 2 — HTML, contract lock và CI trước API

**Input:** Technical receipt schema từ Mốc 1.
**Output:** Viewer offline + release lock + implementation SHA xanh; chưa API.

### Renderer

    render_report(receipt_path: Path, output_path: Path) -> dict

CLI:

    python -m scripts.render_network_e2e_report --receipt PATH --output PATH

- Một HTML standalone: stage/status, scenario request, native arguments, tool trace, OBSERVED/DERIVED + parents/source IDs, structured facts/checks, full assessment/limitations, human decisions, usage/cost/latency và provenance.
- Long content có thể collapse nhưng không mất. Escape HTML/script; không CDN, không API button, không query DuckDB.
- Hiển thị COMPLETE / PARTIAL / AWAITING_HUMAN khác nhau, failed stage cụ thể. Không render fixture thành live evidence.
- Cho phép panel historical R1 22/24 và R2 7/8 chỉ nếu đọc artifact/lock đã lưu và ghi historical/replay rõ; không biến chúng thành scores của demo.
- Tests dùng fixture đánh dấu synthetic: partial/invalid/missing receipt, XSS, cost_unknown, missing source, JSON/HTML counts parity, renderer client/model calls=0.

### Contract/scenario qualification

    qualify_demo(snapshot: Path) -> dict

1. Verify logical snapshot SHA:
   42c8e0a62441295cc5d95329a65dc22409c37de5b26a1e37dd56fbf0164a758c.
2. Hai bảng dataset_provenance/network_flows; 243906 flows, distinct source pairs 243906; S5=129831, S7=114075. Open read_only=True.
3. Hash binary thật và đối chiếu nếu snapshot lock hiện có pin đúng binary đó. Không lấy một binary SHA cũ làm thay thế logical verification. Binary khác giữa independent builds không tự chứng minh nội dung khác; nếu một file-specific lock mismatch, dừng đối chiếu, không rewrite lock.
4. Giữ deterministic scenario selector có trước live; verify IP/time/source pair từ snapshot. Không chọn lại một case dễ hơn sau output.
5. NETWORK_E2E_v1.lock mới pin snapshot/schema/scenario/policy/prompt/request envelope hashes. Không sửa historical v4 locks.
6. Không đưa HEAD của chính commit chứa lock thành hash tự tham chiếu. Lock pin content files; runtime receipt ghi actual implementation HEAD.
7. Giữ source/reference IDs ngoài prompt đầu tiên; factual tool output tới model không được leak CTU labels/gold.

### Freeze implementation và CI

- Full pytest và relevant targeted suite; py_compile, diff/staged checks. Không gọi 5 lỗi Windows là environment-specific nếu chưa có bằng chứng cùng SHA trên Linux.
- Commit/push code, renderer và new lock. Gọi SHA này A.
- Chờ full CI A: Python 3.11 và 3.12 success; đọc jobs/logs, không dùng CI SHA cũ. Nếu đỏ, sửa trong scope rồi push SHA mới A và chờ lại.
- Nếu local tests còn fail mà exact-SHA CI xanh, ghi tên/traceback sanitized và giới hạn local; fixture CI vẫn không thay local snapshot gate.
- Không tạo push trigger gọi API. Code push/CI hoàn toàn offline.
- Ghi commands --help/preflight/render đã kiểm. Tiếp tục Mốc 3 khi CI đạt; không hỏi lại quyền API.

## 8. Mốc 3 — preflight thật, rồi đúng một live invocation

**Input:** SHA A sạch/tracking remote, CI A xanh, .env laptop, snapshot đủ điều kiện, ledger/gates thật.
**Output:** Actual technical receipt hoàn chỉnh hoặc partial; không code change giữa run.

### Trước request

1. Check key source bằng scripts.check_env; conflict/custom BASE_URL/missing key dừng trước client. Không thử key bằng extra API call.
2. Ghi private gates từ bằng chứng thực: implementation SHA; exact CI run/jobs; UTC; current applicable prices; xác nhận account/project access và allocation còn lại nếu có thể kiểm. Không tự ghi booleans PASS hoặc owner_confirmation chưa nhận.
3. Không coi số credit/limits cũ là current balance. Nếu không thể xác minh một required account/budget gate, báo field thiếu; vẫn hoàn tất code/HTML bàn giao, không tạo score.
4. Ledger bỏ hard-coded PRIOR_TASK_COST_USD làm source of truth. Import prior receipts thực thuộc allocation; chống double count. Giữ known và unknown riêng. Unknown liên quan allocation đang dùng chưa reconcile phải block paid run.
5. Kiểm giá hiện hành từ OpenAI: https://developers.openai.com/api/docs/models/gpt-4.1-mini. Ngày 06/10 đã đối chiếu standard input USD0.40/1M, cached input0.10/1M, output1.60/1M. Preflight không giảm theo cache.
6. Tính input bound của toàn bộ payload thực: messages/history/system/schema/native tool metadata/evidence. Không dùng tokens smoke để suy ra bound; không chỉ đếm user prompt.
7. Proposed envelope: tối đa 50000 reserved input tokens/request, output cap1000, payload byte limit45000. Tokenizer/framing reserve phải có cách tính và assumptions được ghi; nếu không chứng minh bound phù hợp actual request, stop trước transmission. Không gọi 45000 bytes đơn thuần là một token proof.
8. Với envelope đó và giá chưa đổi:
   per-request reserve = (50000×0.40 +1000×1.60)/1000000 = USD0.0216;
   bốn requests reserve = USD0.0864.
   Đây là conditional application bound, không phải credit balance hay billing hard cap của OpenAI. Recompute khi giá/bound đổi; approved window phải fit USD0.25 và allocation thực còn lại.
9. Trước từng request: known charged + unresolved/reserved exposure + request reserve + remaining planned reserves phải fit budget. Evidence-dependent request 2 được kiểm lại sau actual tool execution. Oversize/budget fail giữ partial, không call.
10. SDK/client chỉ tạo SAU full preflight. Guard không cho gửi request thiếu cap. Usage được charge trước parsing; sai actual model/usage/error dừng, không tiếp tục scenario sau.

**Private gates schema cần implement thống nhất:** schema_version=1; window_id=network-finalization-20261006; task_budget_usd=0.25; implementation_sha; ci gồm head_sha/run_url/conclusion/jobs với name/conclusion/job_url của cả Python3.11/3.12; account gồm source/confirmed_utc/project_verified/remaining_allocation_usd; pricing gồm checked_utc/source_url/input_usd_per_million/cached_input_usd_per_million/output_usd_per_million; reconciliation gồm receipt_hashes/known_prior_cost_usd/unresolved_cost_unknown. Source của account phải là kiểm tra thật hoặc owner_confirmation thật; không tự chế xác nhận. Account/pricing tối đa21600giây tuổi; CI SHA phải bằng HEAD và origin/master. Missing/stale/false gate reject trước client; unit tests dùng receipt fixture rõ synthetic. Không commit private identifiers hoặc gates file.

**Technical receipt schema tối thiểu:** schema_version; run_id; status; scope=network_only_public_lifecycle_demo; transport; implementation_sha; ci; contract/snapshot/scenario/prompt/schema hashes; request_config; attempted_calls/responses_received/valid_usage_records; requests[] với stage/provider/actual_model/request_id/response_id/finish_reason/usage/cost/latency; scenarios[] với native tool_calls/evidence/coverage/assessment/observations/validation/lifecycle/human_review/termination; cost_summary với known_cost_usd/cost_unknown/reserved_exposure_usd; review_status. Field không có từ provider phải null kèm lý do, không sao chép requested model thành actual model. Ghi snapshot identity vào receipt trước API; terminal status chỉ tính sau toàn bộ stages. Full receipt giữ model-authored nội dung cần audit; không lưu full raw SDK response hoặc secrets.

### Lệnh PowerShell sau khi CLI đã implement

Chạy từ repository root. Agent phải xác nhận paths thật và ghi chúng vào runbook; không để placeholder cần người dùng đoán.

Commands dưới đây dùng .env mặc định tại repo root. Nếu triển khai bằng fresh clone, thêm --env-file trỏ tới .env gốc vào preflight và live; không copy/ghi lại key. Entry point demo phải in source/presence an toàn giống check_env.

~~~powershell
$Snapshot = (Resolve-Path "data/ctu_network_public/snapshots/ctu_dev.duckdb").Path
$WindowRoot = Join-Path $env:USERPROFILE ".vinsoc/live-windows/network-finalization-20261006"
$Ledger = Join-Path $WindowRoot "ledger.json"
$Gates = Join-Path $WindowRoot "gates.json"
$Out = "results/evaluation_v1/network_e2e_v1/20261006/technical_receipt.json"

python -m scripts.check_env --check
python -m scripts.demo_ctu_network_public_model_driven --e2e --preflight-only --scenario all --snapshot "$Snapshot" --output "$Out" --budget-usd 0.25 --ledger "$Ledger" --gates "$Gates" --review-mode deferred
~~~

Preflight output bắt buộc attempted=0, responses=0, client_created=false; đủ identity/CI/ledger/budget PASS. Preflight không consume live claim.

**Sau preflight PASS, chạy đúng một lần:**

~~~powershell
python -m scripts.demo_ctu_network_public_model_driven --e2e --scenario all --snapshot "$Snapshot" --output "$Out" --budget-usd 0.25 --ledger "$Ledger" --gates "$Gates" --review-mode deferred
~~~

Nếu người dùng đang trực tiếp ngồi review, có thể dùng interactive ngay trong invocation này; không chạy lại để đổi review mode. Nếu thiếu human, deferred là lựa chọn triển khai mặc định; offline review sau.

### Sau invocation

- Không rerun dù exit1. Kiểm JSON và ledger; first response phải có actual provider/model/usage, executed native arguments, source evidence; second có full model assessment và validation.
- Hoàn tất cả hai scenario phải có 4 attempts, 4 responses, 4 valid usage records. Nếu ít hơn, ghi stage/termination thật.
- Cost = uncached input×input rate + cached input×cached rate + output×output rate, từng request rồi cộng. Không dùng estimated_cost=0 khi cost_complete=false.
- Missing usage: cost_unknown=true, known cost không phải total cost. RateLimit/timeout có thể unknown; không viết miễn phí.
- Không đòi verdict Botnet=malicious/Normal=benign để pass kỹ thuật. Kiểm source facts, uncertainty và limitations; analytics không được thay đổi sau output.
- Technical invalid phải dừng trước human approval, giữ safe reason và all preceding evidence/charges.
- Xong một live window thì tiếp tục bàn giao/HTML offline. Paid run lỗi không cho phép mốc code+handoff bị bỏ dở.

## 9. Mốc 4 — review, render, commit/push và bàn giao

**Input:** Actual complete/partial technical receipt từ Mốc 3.
**Output:** Kết quả xem được, instructions chạy được, GitHub evidence kiểm chứng được.

1. Sanitize theo allowlist trước stage: không secret/error body/raw response dump; giữ model-authored assessment, native arguments, validated public CTU facts, provenance, usage và safe errors cần audit. Không sửa scores/status để tạo thành công.
2. Ghi private full receipts khi cần; public copy phải có schema/hash và nêu redaction, không làm mất facts/stage/cost. Không commit source CSV, DB binary hay whole dataset dumps.
3. Với valid technical receipt awaiting_human, bàn giao command offline review. Người thật approve/reject/escalate; linked receipt mới ghi input SHA, UTC, decision/rationale. Agent không impersonate analyst.
4. Render actual receipt, kể cả partial, rồi kiểm JSON↔HTML counts/cost/model/status equality và mở HTML local. Không lấy fixture xanh làm demo.
5. Kiểm preservation hashes: historical R1/R2/case006/frozen policies không đổi; cross-domain candidates vẫn giữ nguyên.
6. Update runbook bằng lệnh đã chạy và giới hạn thực. Không tạo thêm documentation-only task rồi dừng thiếu sản phẩm.
7. Commit/push sanitized technical receipt, artifact hashes, viewer/runbook. Commit evidence không thay implementation SHA A ghi trong run. Final SHA B có thể khác A.
8. Chờ CI B Python3.11/3.12. Nếu cần sửa renderer/report validation offline, push fix và kiểm CI lại; không mở paid retry.
9. Báo cáo bàn giao theo mẫu ở dưới. STOP sau bàn giao/human review, không tự mở matched R2, frozen hay cross-domain paid run.

### Commands xem lại — không API

~~~powershell
python -m scripts.render_network_e2e_report --receipt "$Out" --output ".vinsoc/demo/network-e2e.html"
Start-Process ".vinsoc/demo/network-e2e.html"
~~~

Offline review khi người dùng có mặt và technical validation pass:

~~~powershell
python -m scripts.demo_ctu_network_public_model_driven --review-receipt "$Out" --output "results/evaluation_v1/network_e2e_v1/20261006/human_review_receipt.json"
~~~

Lệnh review không được tạo provider/client hoặc model call. Exit/receipt phải phân biệt approve, reject, escalate và cancelled. Không overwrite technical receipt.

Historical R2 replay và R1 winner summary có thể demo thêm bằng commands đã có trong runbook; ghi rõ zero new inference / archived development results. Không dùng replay làm bằng chứng model E2E mới.

## 10. Kiểm chứng bắt buộc và điểm dễ tạo thành công giả

| Tình huống | Hành vi/test bắt buộc |
|---|---|
| Preflight-only | Client0, attempted0, không consume claim |
| Native tool selection | tool_choice auto; chỉ schema network; model arguments không được điền hộ |
| Dùng private dispatcher | Lifecycle test thất bại; public investigate là entrypoint |
| Valid citation, wrong number | Factual validation FAIL |
| DERIVED không có parent | FAIL; không bỏ record để che lỗi |
| Source sample/truncated query | Coverage khai báo thật; không claim toàn population |
| Scenario1 pass, scenario2 fail | Aggregate incomplete; giữ scenario1 và toàn cost |
| Model trả thêm tool ở lượt2 | NO_FINAL_ASSESSMENT; không request3 |
| Error/missing usage | Partial + stop + unknown khi cần; không success/no-tool giả |
| Deferred HITL | Awaiting_human; không approved/COMPLETE |
| Đổi output/clone | Không tạo budget/lượt mới |
| Renderer/review offline | API0; HTML parity và XSS escaped |
| CI xanh với fixture | Không suy ra live success hoặc snapshot local đã verified |

Trước API, chạy python -m pytest -q, focused mới và regressions có liên quan, py_compile, git diff --check, staged allowlist check. Targeted assertion cần chứng minh behavior, không chỉ field tồn tại.

CI có thể kiểm synthetic responses; đó là test harness, không phải model result. Live receipt phải ghi transport=openai_sdk_live, actual response/request IDs nếu provider cung cấp, usage và independently verified source facts. Receipt là evidence audit được; tự gắn nhãn live không phải chứng minh độc lập server-side. Nếu cần đối chiếu mạnh hơn, giữ thời gian/project privately để owner đối chiếu Usage Dashboard; không in account/key.

## 11. Quy tắc vận hành để tránh báo vòng quanh

- Thực hiện nối tiếp Mốc0→1→2→3→4. Không trả một final answer chỉ có "đã thêm tests/manifest, còn phần khác" khi vẫn còn việc được phép làm.
- Cập nhật ngắn khi có kết quả mới hoặc blocker thật; không tái kể checklist mỗi lượt.
- Mỗi mốc code phải commit+push rõ ràng; không coi code local là bàn giao. Chờ CI trước API, không dừng xin quyền API lại.
- Blocker thật: network/runtime không thực hiện được lệnh; Git conflict; missing key/gate; snapshot mismatch; CI đỏ chưa sửa được; budget/unknown cost; provider/model/cap fail; human review cần người thật.
- Blocker phải có lệnh, exit code, safe reason, attempted/responses/cost và file partial. Không tự tạo artifact PASS thay cho lệnh không chạy.
- Nếu hết thời gian hoặc paid failure: giữ partial và hoàn thiện renderer/handoff offline. Đừng mở thêm mục tiêu để tránh bàn giao.

## 12. Báo cáo cuối gửi người dùng

1. Initial SHA; implementation SHA A; final HEAD/origin/master B; các commit và files changed.
2. Exact CI URLs/jobs/results cho A và B; local commands/results, failures/skips còn lại.
3. Snapshot logical + actual binary SHA, source counts/schema/scenario hashes; evidence source-pair verification.
4. Bảng Botnet/Normal: attempted/received, executed tool/arguments, evidence count/coverage, model assessment, factual checks, human status, termination.
5. Model/provider actual, config/cap/retry, input/cached/output tokens, per-call latency/cost, tổng known/unknown/reserved.
6. Preflight cost envelope, actual cost và budget remaining theo ledger thật; không gọi token-cost estimate là invoice.
7. Links sanitized JSON, HTML, review receipt hoặc awaiting-human state; PowerShell commands đã kiểm.
8. Nêu chính xác claim: "network-only public-lifecycle demo"; không "complete SOC coverage", không thay R1/R2 scores, không generalization claim.

**Sau demo:** Task riêng tiếp theo là review kết quả và khóa lại ưu tiên. Matched R2 comparison và cross-domain module/statistical evaluation vẫn pending; tiếp tục chúng sau bàn giao, trên contract/budget riêng được duyệt. Frozen vẫn đóng.

## 13. Tự rà trước bàn giao chỉ thị

- Một canonical CLI và một public lifecycle, không hai demo khác nhau.
- Model4.1mini demo và GPT5mini R2 không bị trộn.
- Bốn requests là maximum toàn cửa sổ, không phải bốn/scenario hoặc bốn/lần retry.
- USD0.25 không cộng với USD0.75 cũ; prior unknown không tự thành0.
- Deferred human được phép bàn giao kỹ thuật nhưng không được nhận COMPLETE.
- Atomic implementation commits/CI trước API; evidence commit/CI sau API có provenance tách biệt.
- Không cần benchmark96 câu hoặc matchedpair để demo.
- Không evidence clipping, không script-authored assessment, không gold leakage.
- Mọi kết quả chưa chạy đều là pending; plan không tuyên bố sản phẩm đã hoàn tất.
