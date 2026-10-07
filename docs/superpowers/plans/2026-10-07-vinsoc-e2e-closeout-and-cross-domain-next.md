# VinSOC E2E Closeout and Cross-domain Evaluation — Implementation Plan

> **For agentic workers:** Use superpowers:executing-plans to implement this directive task-by-task. Agent A is the single writer. Do not delegate writes or create a branch/PR.

## Execution cursor — cập nhật trước khi giao ngày 07/10

Remote đã tiến từ checkpoint audit d704da1 lên **a347ff9a35de60acba9b902308330f5c65c8977f**. Commit implementation **8736ab7801bf9fcf15da0003220097e0cbb14d58** đã thêm lock builder/validator, canonical ledger root, renderer mới, factual checks và human packet. Đây là tiến độ mới phải giữ nguyên, không reimplement hoặc revert về d704da1. Handoff tại results/evaluation_v1/network_e2e_v1/20261006/HANDOFF.md báo CI implementation run37569993136:1070passed/2skipped mỗi Python; agent phải kiểm bằng chứng đúng SHA dùng tiếp, không lấy skip làm local snapshot acceptance.

**Điểm bắt đầu thực thi hiện tại:** đọc handoff/runbook và kiểm phần A1 bằng code/tests mới. Phần đã đạt thì đánh dấu VERIFIED_EXISTING rồi bỏ qua bước viết lại; chỉ sửa residual regression đã tái hiện. Bằng chứng blocked hiện có ghi attempted0/responses0/client=false, chưa có live success. Snapshot/gates thiếu ở môi trường agent trước không chứng minh chúng thiếu trên laptop người dùng.

**Thao tác tiếp trên laptop:** xác minh file CTU thật đã có → chạy required local-snapshot rehearsal → tạo release lock thật một lần → commit/push lock → full CI đúng SHA mới → lập private account/pricing/reconciliation gates từ evidence thật → preflight PASS → một live invocation A2 → A3 JSON/HTML/human review và commit/push. Commands release hiện có ở mục8 docs/VinSOC_Verified_Demo_Runbook_2026-10-05.md; dùng python -m evaluation.finalization.network_contract --snapshot "$Snapshot" --output "evaluation/finalization/NETWORK_E2E_v1.lock.json" sau snapshot qualification. Không tải lại nguồn hoặc tạo snapshot giả để lấp acceptance gate; nếu file thật không có, báo đúng input/path thiếu và bàn giao phần offline hợp lệ.

Trước rehearsal đặt $env:VINSOC_LOCAL_SNAPSHOT=$Snapshot, rồi chạy python -m pytest tests/test_network_e2e_lifecycle.py -k local_verified_snapshot_two_scenario_rehearsal -q. Rehearsal dùng tool/DB thật nhưng model/reviewer synthetic; không gọi nó là live. Không reuse/overwrite blocked_handoff.json/html hoặc technical/review receipt đã tồn tại; giữ ledger/window canonical xuyên mọi output namespace. Partial/unknown allocation và human review gates vẫn phải giữ đúng. Phần B chỉ offline như bên dưới; không mở cross-domain paid bằng chỉ thị demo.

**Goal:** Bàn giao ngay một demo network E2E dùng OpenAI thật, evidence thật, public orchestrator lifecycle và human review thật; sau đó hoàn thiện đo lường module/cross-domain ở chế độ offline, không trộn với demo.

**Architecture:** Tái sử dụng runner, public InvestigationOrchestrator, NetworkSkill và snapshot CTU hiện có. Sửa các khoảng hở contract/ledger/renderer, không dựng pipeline song song. Track cross-domain có cổng chạy và ngân sách riêng, không được chạy bằng quyền/budget của demo.

**Tech Stack:** Python 3.11/3.12, DuckDB read-only, OpenAI Chat Completions, pytest, GitHub Actions, HTML standalone.

**Spec:** Đọc đầy đủ docs/superpowers/plans/2026-10-07-network-e2e-agent-a-directive.md. Văn bản này là delta closeout sau audit master@d704da16f754fa4c96753e493db3e8b38aca7665, không yêu cầu làm lại các phần đã đúng. Đối chiếu code mới hơn nếu remote tiến thêm trước khi bắt đầu.

## Global Constraints

- Làm trực tiếp master; mỗi mốc code hoàn tất phải commit và push origin master, rồi kiểm CI đúng SHA.
- Không tạo branch/PR; không force push, reset --hard, clean -fdx hoặc xóa thay đổi ngoài task.
- Không coi untracked ngoài task là lý do dừng mọi việc. Giữ nguyên; chỉ stage explicit allowlist. Tracked/staged ngoài scope hoặc remote divergence phải đối chiếu, không tự merge/rebase.
- Không sửa benchmark/gold/scorer/prompt R1/R2 lịch sử, winner_lock hoặc artifact cũ. Không đọc/chạy gold frozen.
- Không mở official ba nguồn ThreatFox/OTRF; không thêm endpoint/CTI vào demo network.
- Không overwrite, commit, in key hoặc fingerprint của .env. Tái sử dụng key được cấu hình; không tạo thêm request thử key.
- Demo: gpt-4.1-mini-2025-04-14, temperature=0, max_completion_tokens=1000, retries=0, tool_choice=auto, duy nhất network_investigation.
- Demo chỉ một live invocation, tối đa 4 model requests cho hai scenario botnet/normal. Budget demo tối đa USD0.25, đồng thời không vượt allocation thật còn lại.
- Window cố định network-finalization-20261006. Không tạo window/ledger mới để chạy lại. Cross-domain paid authorization hiện false, không được dùng live demo để mở quyền đó.
- Tests có thể fake/synthetic nhưng phải ghi rõ. Demo live không được mock provider, hardcode tool arguments/assessment hoặc thay dữ liệu fixture để tạo thành công.
- Không trả báo cáo tiến độ thay cho phần code/test/push còn có thể làm. Chỉ dừng khi blocker cụ thể, cửa sổ paid đã dùng, hoặc đến human review thật.

## Review Focus

1. Receipt mới/partial phải render được, kể cả assessment=null, lifecycle=[], usage thiếu; không hiển thị thiếu cost thành USD0.
2. Thay output/clone/ledger path không được mở một lượt paid mới; hai process không được claim cùng window.
3. Đổi policy, prompt, schema hoặc request config phải làm lock validation thất bại trước OpenAI client.
4. Evidence và observation phải kiểm trên DB thật trước approval; prose inference vẫn cần người review, không được tự gắn nhãn đã đúng ngữ nghĩa.
5. Provider/usage/model/finish_reason lỗi phải giữ partial cùng exposure/cost, không retry/fallback và không chạy tiếp scenario.

---

## Tình trạng đầu vào đã xác minh ngày 07/10

- HEAD được audit: d704da16f754fa4c96753e493db3e8b38aca7665.
- CI: https://github.com/Whats-up-pro/VinSOC/actions/runs/37561432731 ; 1027 passed, 1 skipped trên từng Python 3.11/3.12. Không lấy skip thay cho xác minh snapshot trên laptop.
- R1 dev v2 lịch sử: 22/24, exact-call F1=0.9508, no-tool=5/5; giữ nguyên.
- R2 CTU dev E3 lịch sử: 7/8, 44 responses, cost USD0.0208585; case006 TOOL_LIMIT/no final SQL; giữ nguyên.
- Cross-domain đã khóa 24 calibration + 96 evaluation, 8 external evaluation DB thuộc 7 domain, 120 base gold replays; external model calls=0.
- E2E đã gọi public investigate(). Không viết lại phần đó.
- Còn lỗi: renderer đọc schema cũ; E2E lock chưa commit và thiếu prompt/policy/envelope binding; ledger chưa khóa canonical root.
- Chưa thấy live technical receipt E2E mới trong repository. Trước API, kiểm ledger local và các receipt hiện có; không suy ra “chưa chạy” chỉ vì GitHub chưa có artifact.

## Task A1 — Đóng lỗi tích hợp E2E, commit/push và CI

**Input:** master mới nhất, code E2E hiện có, snapshot CTU thật và quyền đọc .env đã được cấp.
**Output:** code + lock + regression tests trên GitHub, CI exact implementation SHA xanh. Chưa gọi model trong task này.

**Files allowed:**

- evaluation/finalization/network_contract.py
- evaluation/finalization/live_window.py
- evaluation/finalization/NETWORK_E2E_v1.lock.json — tạo mới
- scripts/demo_ctu_network_public_model_driven.py
- scripts/render_network_e2e_report.py
- agent/orchestrator.py hoặc agent/network_investigation_policy.py chỉ nếu cần chặn technical-invalid trước review
- tests/test_network_e2e_contract.py
- tests/test_network_e2e_runner.py
- tests/test_network_e2e_report.py
- tests/test_network_e2e_lifecycle.py
- tests/test_network_e2e_policy.py
- tests/test_finalization_live_window.py
- cli/main.py chỉ nếu console review chưa cho người thật xem đủ evidence/observations.

**Interfaces phải giữ/hoàn thiện:**

- build_lock(snapshot: Path, output_path: Path | None = None) -> dict và validate_lock(snapshot: Path, lock: dict) -> dict.
- render_report(receipt_path: Path, output_path: Path) -> dict.
- run_e2e_preflight()/run_e2e_live() tiếp tục dùng public InvestigationOrchestrator.investigate().
- Thêm canonical_window_root() -> Path trong live_window.py, trả Path.home()/".vinsoc"/"live-windows"/WINDOW_ID; production không có override mở quyền root khác.

### A1.1 — Git và preservation

- [ ] Chạy riêng từng lệnh: git branch --show-current; git status --short; git diff --cached --name-only; git remote -v; git fetch origin; git rev-parse HEAD; git rev-parse origin/master; git branch -vv.
- [ ] Branch master, remote Whats-up-pro/VinSOC, upstream origin/master. Nếu đang behind và không có tracked/staged changes, git pull --ff-only origin master. Nếu diverged, báo SHA + files, không tự hòa lịch sử.
- [ ] Ghi initial SHA. Hash danh sách artifact/lock lịch sử được bảo vệ trước thay đổi; sau cùng đối chiếu không đổi.
- [ ] Untracked ngoài allowlist giữ nguyên. Nếu chúng khiến exact-clean preflight không thể đạt, dùng fresh clone riêng của đúng repo/master; giữ nguyên checkout cũ, tham chiếu absolute path .env/snapshot cũ, không copy hoặc rewrite key. Ledger vẫn cùng root ngoài checkout.

### A1.2 — Test RED rồi sửa renderer theo output runner thật

- [ ] Tạo receipt bằng _scenario_receipt() với orchestrator/case fixture rõ synthetic; không handcraft lại schema cũ để renderer pass.
- [ ] Thêm test test_renderer_accepts_current_runner_receipt_schema: assessment là str, lifecycle là list, validation có policy/independent_snapshot/technical_valid, cost_summary nested; HTML phải hiện đúng.
- [ ] Thêm test test_renderer_handles_current_partial_receipt: assessment=null, lifecycle=[], missing usage/cost_unknown=true; render không crash, không ghi COMPLETE hay tổng chi phí USD0.
- [ ] Thêm test test_renderer_matches_receipt_counts_cost_status: JSON↔HTML khớp counts, model, cost, review status; technical_complete_awaiting_human không được hiện approved/COMPLETE.
- [ ] Chạy các test mới trước sửa, lưu bằng chứng fail. Root cause hiện tại: str.get() và list.items().
- [ ] Sửa renderer đọc đúng schema hiện tại, escape mọi model/public-data text. Hiện source_dataset/source_row_id, observation, hypothesis, limitations; review receipt riêng phải có input technical receipt hash khớp.
- [ ] Chạy lại, yêu cầu GREEN. Không sửa runner thành schema cũ chỉ để làm renderer pass.

### A1.3 — Khóa contract thật

- [ ] Qualify snapshot CTU read-only: chỉ network_flows + dataset_provenance; 243906 flows, S5=129831, S7=114075, distinct source pairs=243906.
- [ ] Dùng identity algorithm hiện có; phân biệt binary SHA của file cụ thể với logical SHA. Snapshot rebuild logical giống nhưng binary khác không được tự coi là file đã freeze.
- [ ] build_lock phải fail nếu qualification/scenario thiếu; không tạo lock chứa error hoặc null rồi đánh dấu valid.
- [ ] Lock pin version, snapshot/source/manifest identities, cả scenario inputs + selection rule + seed evidence identity; policy/schema/system-prompt-template/request-envelope hashes.
- [ ] Request envelope pin model, temperature, output cap, retry, allowlist/tool_choice, byte/input/output/frame bounds. Hash canonical JSON; thứ tự key không đổi identity. Pin portable text hash khi cần để Windows CRLF không tạo identity giả.
- [ ] validate_lock kiểm tất cả binding, không chỉ snapshot. Không include hash của chính lock hoặc future Git commit theo cách gây vòng lặp; implementation SHA ghi trong runtime receipt.
- [ ] Thêm các test test_network_lock_rejects_policy_prompt_schema_envelope_mutation và test_network_lock_requires_qualified_snapshot_and_scenarios; từng mutation riêng phải bị chặn trước client/API.
- [ ] Tạo NETWORK_E2E_v1.lock.json từ snapshot thật sau khi code đã ổn định. Receipt preflight phải có prompt_sha256, policy_sha256, request_envelope_sha256 không null.

### A1.4 — Một canonical paid window, không bypass

- [ ] Preflight và LiveWindow.open đều reject root khác canonical_window_root(). Kiểm resolve/normalization phù hợp Windows; unit tests monkeypatch home sang tmp_path, không thêm runtime flag “allow arbitrary root”.
- [ ] Thêm test test_noncanonical_ledger_path_rejected_before_client.
- [ ] Thêm test test_consumed_window_cannot_restart_with_new_output_or_clone; giữ nguyên window ID/root và consumed state.
- [ ] Thêm test test_two_process_claims_allow_only_one_sender; claim phải atomic liên process, không chỉ threading.Lock.
- [ ] Chặn CLI legacy/default/diagnostic khỏi bypass cap/window authorization khi không đi qua guard. Test test_legacy_cli_cannot_bypass_live_window; không phá fake-provider unit tests.
- [ ] Không sửa/xóa ledger đã có để làm test operational pass. Claim sai/đã dùng là blocker paid, không phải lý do bỏ code/HTML handoff.

### A1.5 — Technical checks trước approval

- [ ] Assert public investigate() thực sự được gọi; native model arguments được execute, không ép tool_choice hoặc gán argument từ gold.
- [ ] Test evidence/observation bị thay count/source row/time window: technical invalid, không gọi human review để approve.
- [ ] Người review được xem assessment + observations + evidence/source + limitations. Agent không đóng vai analyst.
- [ ] Giữ prose_semantics_machine_verified=false. Botnet/Normal label chỉ là ground truth metadata, không nhét vào model context hoặc dùng để sửa assessment.

### A1.6 — Verify, commit/push, CI

- [ ] Chạy targeted bằng lệnh:
  python -m pytest -q tests/test_network_e2e_contract.py tests/test_network_e2e_runner.py tests/test_network_e2e_report.py tests/test_network_e2e_lifecycle.py tests/test_network_e2e_policy.py tests/test_finalization_live_window.py
- [ ] Chạy python -m pytest -q; py_compile các file Python đổi; git diff --check.
- [ ] Nếu lỗi ngoài scope thật: giữ output/test names, không tự gọi pre-existing khi chưa so với base. Có thể dùng CI exact-SHA làm full-suite gate theo thỏa thuận; CI đỏ thì không live.
- [ ] git add chỉ các file allowlist đã đổi; xem git diff --cached --name-only và git diff --cached --check; không git add .
- [ ] Commit: fix(e2e): bind network contract ledger and renderer ; git push origin master.
- [ ] Kiểm CI đúng SHA trên cả Python 3.11/3.12. Sửa lỗi scope và push nếu cần. Chỉ sau CI xanh mới sang A2; không dừng chỉ để báo “code đã push”.

## Task A2 — Preflight và một live E2E thật

**Input:** implementation SHA A = origin/master, CI A xanh, contract lock, snapshot/key thật, gates/ledger bền vững.
**Output:** hai scenario completed về kỹ thuật hoặc một partial có nguyên nhân/cost thật. Không tạo model score benchmark từ demo.

- [ ] Kiểm ledger/receipt local trước mọi API; nếu đã attempted/consumed, không chạy lần nữa, chuyển A3 để bàn giao output hiện có.
- [ ] Chạy scripts.check_env --check: chỉ source/present, không in key. Không load dotenv theo cách overwrite process env; conflicting sources/custom endpoint/missing key phải block.
- [ ] Dùng account/project/allocation confirmation thật, không dựa balance cũ hay tự ghi owner_confirmation. Giá kiểm từ OpenAI chính thức tại lúc run. Account/pricing tối đa 6 giờ tuổi; ghi source và UTC.
- [ ] Reconcile receipt costs thuộc allocation, deduplicate theo receipt identity; unknown giữ riêng. Unknown chưa có upper bound an toàn hoặc usage thật thì chặn transmission, không ghi USD0.
- [ ] Bound toàn payload từng request, kể cả schema/history/evidence. Các constants hiện có 50000 input reserve, 1000 output, 45000 serialized bytes phải có framing/token assumptions kiểm được.
- [ ] Nếu giá standard mini vẫn input0.40/output1.60 USD/1M thì conditional reserve là USD0.0216/request, USD0.0864/4 request; đây KHÔNG phải giá hiện hành đã xác minh hay trần hóa đơn. Recompute từ pricing thật trước run.
- [ ] Guard reserve trước từng request, charge usage trước parsing, kiểm actual model/usage/finish reason; missing usage/model mismatch/provider error/oversize/budget risk phải dừng ngay và giữ partial.
- [ ] Không extra smoke, models-list call, retry hoặc fallback. Hai scenario, mỗi scenario tool turn rồi assessment turn: tối đa bốn requests.

Chạy từ repository root bằng PowerShell, xác nhận paths thật:

~~~powershell
$Snapshot = (Resolve-Path "data/ctu_network_public/snapshots/ctu_dev.duckdb").Path
$EnvFile = (Resolve-Path ".env").Path
$WindowRoot = Join-Path $env:USERPROFILE ".vinsoc/live-windows/network-finalization-20261006"
$Ledger = Join-Path $WindowRoot "ledger.json"
$Gates = Join-Path $WindowRoot "gates.json"
$Out = "results/evaluation_v1/network_e2e_v1/20261007/technical_receipt.json"
python -m scripts.check_env --check
python -m scripts.demo_ctu_network_public_model_driven --e2e --preflight-only --scenario all --snapshot "$Snapshot" --env-file "$EnvFile" --output "$Out" --budget-usd 0.25 --ledger "$Ledger" --gates "$Gates" --review-mode deferred
~~~

Nếu fresh clone, $EnvFile trỏ tới .env gốc đã cấp quyền, không copy key. $Gates được tạo từ evidence thật bên ngoài repo, không dùng unit fixture.

- [ ] Preflight phải status=preflight_pass, attempted=0, responses=0, client_created=false. SHA/CI/lock/snapshot/account/price/reconciliation đều hợp lệ.
- [ ] Sau PASS, chạy đúng một lần:

~~~powershell
python -m scripts.demo_ctu_network_public_model_driven --e2e --scenario all --snapshot "$Snapshot" --env-file "$EnvFile" --output "$Out" --budget-usd 0.25 --ledger "$Ledger" --gates "$Gates" --review-mode deferred
~~~

- [ ] Success kỹ thuật cần 2 scenario và 4 attempts/4 responses/4 valid usage records; native arguments, tool execution, evidence row identity và model assessment đều có trace.
- [ ] Provider error: stop paid ngay, nhưng vẫn làm A3 offline. Exit1 không cho phép chạy lại.
- [ ] Không đòi botnet verdict=malicious hoặc normal verdict=benign bằng hardcode để tạo “success”.

## Task A3 — Demo xem được, human review và commit/push bằng chứng

**Input:** receipt thật từ A2, completed hoặc partial.
**Output:** JSON + HTML + lệnh chạy + CI + linked human decision nếu người thật đã review.

- [ ] Render receipt thật, không lấy fixture thay thế:

~~~powershell
python -m scripts.render_network_e2e_report --receipt "$Out" --output ".vinsoc/demo/network-e2e.html"
Start-Process ".vinsoc/demo/network-e2e.html"
~~~

- [ ] Kiểm thực tế JSON↔HTML: status, 2 scenario hoặc partial count, request count, model, token/cost, source evidence/observations/hypotheses/limitations.
- [ ] Nếu technical valid awaiting_human, bàn giao lệnh người thật chạy:

~~~powershell
python -m scripts.demo_ctu_network_public_model_driven --review-receipt "$Out" --output "results/evaluation_v1/network_e2e_v1/20261007/human_review_receipt.json"
~~~

- [ ] Human chưa có mặt: giữ technical_complete_awaiting_human, vẫn bàn giao sản phẩm. Không tự approve. Human reject/escalate là kết quả hợp lệ cần giữ, không sửa model output.
- [ ] Review receipt ghi input technical receipt SHA, implementation SHA, UTC và actual decision/rationale; không overwrite technical receipt.
- [ ] Nếu chưa hoàn thành live, bàn giao partial HTML/JSON + đúng blocker, không tuyên bố demo thành công và không dựng mock substitute.
- [ ] Sanitize public artifacts theo allowlist; giữ model-authored content/public CTU facts cần audit, không key/private account/secret path/raw SDK response/provider error body. Private ledger/gates ở ngoài repo.
- [ ] Commit JSON + standalone HTML public-safe + runbook thực tế vào results/evaluation_v1/network_e2e_v1/20261007/ và docs/VinSOC_Verified_Demo_Runbook_2026-10-05.md.
- [ ] Artifact cần hash/manifest và original implementation SHA A; final evidence commit SHA B khác A là bình thường.
- [ ] Commit: chore(e2e): publish verified network demo evidence ; push origin master; CI B xanh. Preservation lịch sử không đổi.
- [ ] Bàn giao ngay A trước khi mở rộng B. Đến human review thật thì dừng paid; B dưới đây chỉ chuẩn bị offline và không làm trễ demo.

---

## Task B — Hoàn thiện ba yêu cầu cross-domain sau khi A đã bàn giao

Đây là track evaluation riêng, không mở endpoint/CTI production, không dùng ngân sách hoặc claim của demo. Không lấy 20 endpoint synthetic events làm bằng chứng generalization.

### B0 — Đối chiếu inventory đã khóa, không dựng lại 120 case

- [ ] Đọc benchmark.lock.json, runtime_registry.json, source manifest và benchmark_validation_receipt.json.
- [ ] Chạy:
  python -m scripts.validate_r2_cross_domain --registry evaluation/r2_cross_domain_v1/runtime_registry.json --benchmarks evaluation/r2_cross_domain_v1/benchmarks --lock evaluation/r2_cross_domain_v1/benchmark.lock.json --output .vinsoc/cross-domain/current-validation.json
- [ ] Xác nhận 24 calibration + 96 evaluation, DB calibration/evaluation tách biệt ở external set; giữ 8 CTU anchors lịch sử riêng, không cộng vào denominator 96.
- [ ] Xác nhận source URL/license/real source-file hashes, runtime conversion parity và snapshot logical identity. Runtime generation nhận RuntimeCase(case_id,database_id,question), không nhận gold/annotation/oracle IDs.
- [ ] 120 base gold replay + 2 semantic fixtures/case là kiểm scorer/data, không phải 120 model predictions. Fixture dữ liệu giả phải ghi synthetic.
- [ ] “Dữ liệu không liên quan” ở đây là dữ liệu ngoài SOC/CTU nhưng vẫn có schema SQL; không nhét dữ liệu không liên quan ngẫu nhiên vào request để rồi gọi đó là tính tổng quát.

### B1 — Hoàn thiện report từng module, không thay headline EX

**Files:** evaluation/r2_cross_domain_v1/module_metrics.py; evaluation/r2_cross_domain_v1/controller.py; tests/test_r2_cross_domain_module_metrics.py; tests/test_r2_cross_domain_pipeline.py. Thêm evaluation/r2_cross_domain_v1/reporting.py và tests/test_r2_cross_domain_reporting.py nếu chưa có.

**Interfaces:** score_modules(reference_case,record,context=None); aggregate_module_metrics(records) tiếp tục dùng. reporting.build_evaluation_report(case_records: list[dict], inventory: dict) -> dict tạo báo cáo thuần offline, không gọi provider.

- [ ] Schema linking: tables/columns/relationships TP/FP/FN, precision/recall/F1, exact set success, valid join path.
- [ ] Value grounding: typed literal/operator metric, DB witness precision, unsupported literal rate; giữ thiếu context là NA, không gán verified.
- [ ] SQL generation: có final SQL hay không, syntax validity, execution success, EX trên base + semantic tests, no-final-SQL/TOOL_LIMIT, số model/DB calls và latency/cost.
- [ ] Safety/provenance: unsafe attempts/rejections; false reject đo trên benign SQL fixtures; witness fabrication; missing stage/usage/model mismatch. Không gọi tỷ lệ rejection cao là accuracy cao.
- [ ] Mỗi module có numerator/denominator, coverage trên toàn bộ 96; stage không chạy=NA có reason. Không bỏ case lỗi khỏi headline denominator.
- [ ] Primary error có rule deterministic: transport/quota, stage limit/no output, schema linking, grounding, safety, syntax, execution, semantic mismatch; lưu secondary errors, không “chẩn đoán” nhân quả nếu thiếu trace.
- [ ] Test thiếu linker vẫn được ghi coverage missing; linker đạt rồi generator TOOL_LIMIT vẫn giữ module record; no-final-SQL EX=false; fake witness không pass; empty sets theo policy hiện có.
- [ ] Test metric schema/predicate tốt nhưng Boolean SQL sai vẫn EX=false.

### B2 — Báo cáo thống kê đúng mức

**Files:** tạo evaluation/r2_cross_domain_v1/statistics.py và tests/test_r2_cross_domain_statistics.py.

**Interfaces:** summarize_statistics(case_records: list[dict], *, seed: int = 20261007, bootstrap_replicates: int = 10000) -> dict.

- [ ] Report micro EX trên 96, macro theo database/domain, breakdown difficulty và SQL features, kèm n ở mọi hàng.
- [ ] Ghi 95% interval: Wilson ở cấp case ghi rõ giả định độc lập/chỉ diagnostic; cluster bootstrap theo database/family đã pin, 10000 replicates, seed20261007.
- [ ] Không coi 96 câu là 96 quan sát độc lập; ghi 93 evaluation families và giới hạn chỉ 8 external evaluation DB/7 domain.
- [ ] So E0/E3 bằng cùng IDs/snapshot/scorer: win/loss/tie + paired delta và paired cluster interval. Release đầy đủ phải có cả hai records cho mọi ID; NO_FINAL_SQL/TOOL_LIMIT vẫn EX=false và vẫn nằm trong cặp. Missing case hoặc telemetry/provenance không hợp lệ khiến paired release incomplete, không loại riêng chúng để tăng điểm; partial summary phải nêu denominator planned và completed.
- [ ] Synthetic test fixtures kiểm deterministic seed, toàn đúng/toàn sai, missing cases, correlated families, one-cluster cannot-estimate. Không dùng synthetic metrics làm published model score.

### B3 — Cổng live cross-domain, code-only trước quyền paid

**Files:** evaluation/r2_cross_domain_v1/controller.py; tạo release.py, live.py, scripts/run_r2_cross_domain.py và tests/test_r2_cross_domain_release.py/test_r2_cross_domain_live.py. Workflow nếu cần phải workflow_dispatch-only, không push-trigger gọi API.

**Interfaces:** release.preflight_release(inventory: dict, identities: dict, account: dict, pricing: dict, budget: dict) -> dict; live.run_authorized_release(release: dict, *, case_ids: list[str], conditions: tuple[str, ...], output_dir: Path, ledger_path: Path, env_file: Path) -> dict chỉ nhận release đã qua validation. Release chứa verified registry_path, benchmark_dir, benchmark_lock_sha256, implementation_sha, request_contract, account/pricing/budget evidence và canonical paid-window identity; runner revalidate chúng ngay trước transmission, không tin mỗi cờ authorized=true. CLI --preflight-only không tạo OpenAI client.

- [ ] Tách authentic OpenAI transport khỏi synthetic, giữ gold isolation, cap1000/retry0 và model contract hiện có gpt-5-mini-2025-08-07, reasoning_effort=low, không tự thêm temperature.
- [ ] E0 một turn/case, no tools; E3 hiện tối đa3 linker +3 generator turns/case. Full matched 96-case E0/E3 có cận tối đa672 requests, KHÔNG phải192.
- [ ] REQUEST_BYTES_CAP hiện là payload cap, chưa tự chứng minh billable token bound. Tính reserve từ complete payload/history/schema/tool results và verified pricing; giữ timeout/missing usage exposure.
- [ ] Preflight full planned calls phải fit ngân sách còn lại được cấp riêng. Không lấy trung bình của run8 để chứng minh cận trên cho96.
- [ ] Không fit: xuất số thiếu/bound/calls rồi dừng trước API; không âm thầm giảm case, tăng budget, giảm cap hoặc đổi model. Có thể trình human một design/budget mới.
- [ ] Không sửa paid_authorized=false trong historical benchmark lock để giả lập quyền. Quyền nếu được cấp nằm trong release record mới, giữ benchmark bytes.
- [ ] Test missing/stale account/pricing/identity, repeated window, fallback, model mismatch, missing usage, early partial; charge trước parsing/scoring.
- [ ] Chạy targeted cross-domain + full pytest, py_compile, diff/preservation; commit/push và CI exact-SHA xanh.
- [ ] STOP cross-domain trước API: bàn giao preflight đầy đủ và xin quyết định ngân sách/release, không hỏi lại quyền demo đã cấp và không gọi model cross-domain bằng quyền đó.

## Mẫu bàn giao bắt buộc, không dùng báo cáo vòng quanh

1. Initial SHA, implementation SHA A, final SHA B; commit links; files changed.
2. Exact CI run/jobs; targeted/full commands, counts/failures/skips; không gọi tests chưa chạy là pass.
3. Demo: request IDs hoặc unavailable reason, actual provider/model, attempted/received/valid usage; token/cost từng call, tổng known/unknown/exposure và budget remaining.
4. Snapshot/source/lock/prompt/schema/request hashes; native arguments; evidence row identities; observations/hypotheses/limitations.
5. Technical receipt + HTML + human receipt nếu có + artifact SHA; lệnh PowerShell thật để xem lại OFFLINE.
6. Status: approved, rejected, escalated, technical_complete_awaiting_human hoặc partial đúng evidence. Không gộp technical pass với semantic/human approval.
7. Ba yêu cầu cross-domain: cái gì locked/tested, cái gì mới mock-only, cái gì đã OpenAI-live. Chưa chạy96 thì ghi “chưa có cross-domain model score”.
8. Blocker nếu có: lệnh, exit code, safe error, stage dừng, attempted count và exposure; vẫn commit/push phần code/test/artifact hợp lệ đã hoàn tất.

**Definition of Done A:** Repo có code/CI + actual live receipt hoặc partial thật + HTML render thực tế + runbook dùng được; không có mock substitute. Demo thành công kỹ thuật chỉ khi đủ2 scenario/4 calls/4 usage/evidence validation, approval chỉ từ human thật.

**Definition of Done B trước paid:** Benchmark locked, module/statistics reporting tested, real transport/release gate/preflight implemented, CI xanh và full-run cost bound tính được. Generalization result vẫn pending cho đến khi có authentic outputs trên96; không công bố từ gold replay hoặc fixture tests.
