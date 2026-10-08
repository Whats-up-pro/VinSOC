# VinSOC — Thực nghiệm SOC và báo cáo đầu–cuối

**Ngày:** 08/10/2026. **Trạng thái:** Người dùng đã duyệt văn bản này trong hội thoại ngày 08/10/2026; đã chuyển sang lập kế hoạch triển khai. Chưa triển khai runtime hoặc cấp quyền gọi API.

**Mục tiêu:** Trước 16/10/2026, bổ sung thực nghiệm điều tra SOC trên corpus đã làm sạch, chạy qua chính `InvestigationOrchestrator`, từ cảnh báo/IOC đến báo cáo đầy đủ do model sinh. Phân biệt rõ dữ liệu tổng hợp, output model mới, kiểm tra tự động và quyết định người duyệt.

**Đổi ưu tiên:** Tạm hoãn phần đánh giá mở rộng và tích hợp toàn diện Text-to-SQL T0–T11/D1–D10. Giữ nguyên mã, nguồn, khóa, quyền gọi API và kết quả lịch sử. Không hủy hay đánh dấu hoàn tất các công việc đang hoãn. Spec này không mở frozen R1/R2, ThreatFox/OTRF hoặc cửa sổ E2E network cũ.

## 1. Cơ sở và giới hạn

- HEAD đối chiếu: `d42dcc8869e950b77733cf4598a138a94d2d3f25` trên `master` của `Whats-up-pro/VinSOC`.
- Nguồn: `alirezaaminzadeh/soc-agent-traces-100k`, revision `fe94a95dadbd188c2bf137a9785b82cb5f7865c2`, Apache-2.0. Giữ attribution và digest các file nguồn.
- Đã audit toàn bộ test 5.031 và validation 4.984: 10.013 traces lộ `decisive`, 145 traces có citation chưa thấy trong tool responses, 99 trong số đó mang `success=true`. Không lấy success-filter làm bảo đảm chất lượng.
- Đây là dữ liệu tổng hợp do chính sách tham chiếu dựng; không phải incident SOC thật hay output model VinSOC. Ground truth do tác giả cung cấp, không mặc định đã được chuyên gia kiểm.
- Public parquet không chứa toàn bộ evidence store của bộ sinh. Chỉ nhập các observations thực sự xuất hiện trong tool messages; không gọi lại bộ sinh, không suy ra bằng chứng bị thiếu.
- `agent/orchestrator.py` hiện có nhánh tạo giả thuyết/rủi ro bằng `_analyze_evidence`; nhánh policy hiện chỉ cho một tool call rồi final. `cli/main.py::display_case` cắt nhận định ở 500 ký tự. Những đường đó chưa đáp ứng thực nghiệm mới.
- Schema cũ khóa ba tools và IOC types; không nới schema lịch sử để ép kết quả mới vào đó. Tạo schema SOC riêng, dùng lại case DTO/lifecycle/evidence store khi tương thích.
- `QueryProvider` và `RunJournal` hiện gắn với E0/E3 và release Text-to-SQL. Không đổi tên scope/condition để dùng quyền cũ cho SOC.

Tham chiếu: [nghiên cứu nguồn](../../research/2026-10-08-soc-agent-traces-100k-vinsoc-assessment.md), [receipt audit](../../../results/research/soc_agent_traces_100k/audit_receipt.json), `agent/{orchestrator,investigation_policy,evidence,provider,hitl}.py`, `schemas/investigation_case.json`.

## 2. Phạm vi đầu tiên

**Làm:** Corpus có nguồn kiểm được; hai tools đọc corpus; policy điều tra nhiều bước trong public orchestrator; model sinh báo cáo có cấu trúc; runner so sánh có/không dùng tools; xuất JSON/HTML/Markdown đầy đủ; lưu bằng chứng, chi phí và review.

**Giữ ngoài phạm vi:** Fine-tune/RL, SQL generation, thêm cả chín tools của tác giả, tool thực thi containment, gọi CTI ngoài, tạo logs/flows giả, rebuild DB lịch sử, simulator tái tạo đáp án, đánh giá cả 100k bằng API. Không mở thêm UI server hoặc dịch vụ cloud cho demo đầu tiên.

Model và tool phải được chạy mới; cấm `MockProvider`, mock-data hooks, scripted verdict, canned reports hoặc phát lại transcript của tác giả làm lượt điều tra mới. Tool truy vấn dữ liệu tổng hợp đã nhập vẫn là thực nghiệm trên dữ liệu tổng hợp; không được báo là backend/incident SOC thật.

Hai cách triển khai đã cân nhắc: (a) adapter corpus trong public orchestrator, được chọn vì kiểm hệ thống dùng chung; (b) runner riêng với chín tools của tác giả, bỏ vì không chứng minh tích hợp VinSOC. Hai tools mới dưới đây có khả năng riêng, không đổi tên thành CTI/network/endpoint để tuyên bố tương đương.

## 3. Corpus và tách đáp án

### 3.1 Các phần được nhập

Importer chỉ phân tích JSON từ nguồn đã pin, không execute Python của tác giả. Nhập vào DuckDB riêng ở chế độ read-only khi chạy agent:

| Nguồn trong tool messages | Dữ liệu nhập | Điều không được suy ra |
|---|---|---|
| `get_surrounding_events.events` | Events, timestamp, host, user, source, channel, message và fields quan sát có trong bản ghi | Không đổi narrative thành CTU flow hoặc suy count/bytes/ports |
| `get_process_tree.tree` | Process nodes và quan hệ được nguồn nêu | Không thêm parent, timestamp hoặc process absent; host chỉ kế thừa từ container có host rõ |
| `get_asset_context.asset` | Context tài sản đã trả về | Không tạo asset inventory còn thiếu |
| `get_related_alerts.alerts` | Cảnh báo liên quan có trong payload | Không dựng correlation hoặc bản ghi mới |

Không nhập `calculate_risk`, final assistant prose/JSON, summaries mang kết luận, `ground_truth`, top-level evidence list được oracle chọn, `success`, `decision`, `verdict`, `confidence` hoặc `archetype` vào agent DB/input. Không nhập `lookup_attack/search_sigma/search_cve/retrieve_playbook` trong bản đầu: không có KB đầy đủ để cung cấp lookup độc lập đáng tin.

Alert cho model chỉ gồm allowlist: alert_id, title, severity, source, host, user, timestamp, description. Bỏ `technique_hints` và nhãn đáp án. Input môi trường chỉ giữ thông tin tổ chức/tài sản có schema allowlist; văn bản là dữ liệu không đáng tin, không là chỉ thị.

Mọi nested object được nhập phải loại `decisive` và label-only fields. Dùng allowlist theo từng loại payload; không chỉ xóa vài khóa rồi nhận mọi trường còn lại. Lưu rejection/conflict/unsupported counts và source pointers; raw nguồn giữ bất biến.

### 3.2 Định danh và chất lượng

- Source record ID gồm dataset revision, scenario_id, loại payload và ID/JSON pointer gốc. ID như `EV-0001` không được join giữa scenarios.
- Provenance gồm file digest, split, scenario_id, original tool_call_id, JSON pointer, raw record hash và `data_origin=synthetic`. Giữ timestamp gốc; thiếu timestamp thì null, không dùng thời gian import thay thời gian quan sát.
- Dedupe theo native key + nội dung. Native key trùng nhưng nội dung khác phải quarantine; không silent overwrite. Đếm và giải thích mọi exclusion.
- Gold/coverage metadata nằm ở evaluator riêng. Agent không đọc file gold, label inventory hoặc toàn corpus khác case. Trusted `scenario_scope` do ứng dụng cấp, không là argument model tự chọn.
- Read-only connection không đủ nếu model client đọc được file gold. Runner chỉ truyền allowlisted input và kết quả tools; kiểm hash/sentinel rằng gold/reference trace không xuất hiện trong serialized requests. Không claim đây là sandbox OS nếu chưa có.
- Coverage chỉ trên observations đã ghi lại; missing/unsupported khác với kết luận benign. Không dùng `success=true` để chọn cases, không lọc theo output model mới.

## 4. Tools và luồng thực thi

### 4.1 Hai tools đọc dữ liệu

`soc_search_events`: lọc events trong trusted scenario theo host, user, source, từ khóa literal trong message và khoảng thời gian UTC. Các filters có thể null; khoảng thời gian nếu dùng phải đủ start/end và start <= timestamp < end. Không nhận SQL hoặc scenario_id từ model. Sắp theo timestamp rồi source record ID; tối đa 20 rows/lượt.

`soc_get_context`: resource thuộc `process_tree`, `asset`, `related_alerts`; lọc theo host/user phù hợp loại nguồn trong trusted scenario. Process nodes không có timestamp vẫn được trả với timestamp null. Unsupported filter/resource bị từ chối, không bỏ qua filter. Tối đa 20 rows/lượt.

Kết quả gồm rows, matched_count tính trên tập dữ liệu đã nhập, returned_count, truncated, availability và limitations. `matched_count` không được trình bày là tổng incident thực tế. Tập nguồn không chứa loại dữ liệu yêu cầu trả `unavailable`; dữ liệu hiện có không match filters trả `no_match`; không đổi hai trạng thái này thành successful benign evidence.

Mỗi payload model nhận tối đa 20.000 UTF-8 bytes. Nếu vượt, giảm rows theo thứ tự cố định và ghi truncated; một row vượt giới hạn trả lỗi giới hạn, không âm thầm cắt nội dung thành bằng chứng khác. Receipt giữ full source pointer và bytes đã thực gửi. Model chỉ cite phần đã delivered.

### 4.2 Cùng public orchestrator

Thêm entrypoint `InvestigationOrchestrator.investigate_alert(alert, *, soc_context)`. Input `alert` hoặc `ioc`; IOC cần trusted scenario mapping tìm được từ observations hoặc alert allowlist. Không map từ ground truth IOCs. Mapping không có hoặc mơ hồ bị chặn trước model; không tự chọn incident. IOC có thể lấy từ bản ghi nhập đã đủ provenance. Đây là corpus case-bound, không arbitrary IOC internet lookup.

Luồng: validate input/scope → mở case → model chọn tool → thực thi adapter → EvidenceStore → model chọn bước tiếp hoặc kết luận → kiểm report → lưu receipt → xuất báo cáo → chờ người duyệt.

- Mode SOC dùng policy và tool dispatch riêng, tái dùng public lifecycle; không gọi private tool executor như một runner thay thế public entrypoint.
- Tối đa 5 lượt tool và 6 requests model/case, không parallel tools. Một assistant turn có hơn một tool call là lỗi contract. Sau tool thứ năm, request thứ sáu chỉ cho final report, không tools.
- Model được dừng sớm hoặc báo insufficient evidence. Không forced trace order, không đọc reference tool sequence để chọn tool thay model.
- Không dùng triage rule để auto-close benign ở mode SOC. Mọi kết luận thực nghiệm phải có final model response; không final thì failed/partial.
- Không `_analyze_evidence`, script risk hoặc final-text fallback ở mode SOC. Thiếu/invalid final response giữ raw output và lỗi; không render báo cáo thành công bằng nội dung tự điền.
- Tạo `SocInvestigationPolicy`, `SocCorpusContext`, adapters và schema riêng; guard mode mới không đổi semantics của R1/network/query lịch sử.
- Input alert/IOC được đăng ký là evidence loại input với ID riêng và provenance nguồn, delivered qua initial message ở cả S0/S1. EvidenceStore ghi native call ID và delivered record IDs cho phần tool. Không thêm observations khác từ raw corpus vào store nếu model chưa nhận qua tool. Không nâng source tổng hợp thành external intel thực.
- Không bật `ScriptedHumanReviewGate`; lưu final ở trạng thái `awaiting_human`. Review không gọi model lại trong release này.

## 5. Báo cáo model và biểu diễn

Final model response là JSON object theo schema `soc_investigation_report_v1`, không markdown fence. Các trường bắt buộc:

| Trường | Nội dung và kiểm tra |
|---|---|
| summary | Tóm tắt không rỗng, do model sinh |
| verdict | malicious / benign / insufficient_evidence; không tự lấy label nguồn |
| hypotheses | Description, supporting_evidence, contradicting_evidence; references phải đã delivered |
| findings | Claim, evidence_ids, kind observed/inferred; claim không rỗng, không chỉ cite ID không tồn tại |
| risk_level, risk_rationale | LOW/MEDIUM/HIGH/CRITICAL/UNKNOWN và lý do của model |
| confidence, confidence_rationale | LOW/MEDIUM/HIGH và lý do; không lấy confidence của dataset |
| limitations | Danh sách thiếu dữ liệu/phạm vi; insufficient_evidence cần ít nhất một giới hạn |
| recommended_actions | Đề xuất do model sinh, rationale và evidence_ids khi có; chỉ đề xuất, không thực thi |
| evidence_ids | Danh sách tất cả references của model, khớp union các mục trên |

Verdict khẳng định malicious/benign cần ít nhất một finding có citation hợp lệ; insufficient_evidence có thể không có evidence. Bất kỳ citation ngoài delivered set hoặc khác case làm validation fail. Kiểm ID/schema không chứng minh prose đúng; `prose_semantics_machine_verified=false` luôn hiển thị nếu chưa có kiểm nghĩa độc lập.

JSON receipt còn chứa input nguyên trạng, model raw output, parsed report, tool trace/results delivered, nguồn, timestamps, duration, model identity, usage/cost, validation errors, status và hash. Báo cáo không cần xuất nội dung suy nghĩ nội bộ của model; chỉ hiển thị các bước công cụ và lý do kết luận model đã trả.

HTML/Markdown tạo offline từ receipt bất biến, không gọi API. Không cắt summary/assessment ở 500 hay 2.000 ký tự. Trang gồm: cảnh báo/IOC; tóm tắt; bảng diễn biến; bảng evidence với source link/pointer; hypotheses/findings; risk/confidence và lý do; limitations; actions; technical status; human review; model/cost/provenance. Escape toàn bộ text nguồn/model; không dùng model HTML trực tiếp.

Không có output mới thì chỉ hiển thị trạng thái chưa chạy và input đã chọn, không dựng một báo cáo mẫu để gọi demo thành công. Sau run, có lỗi/missing/partial phải hiện ngay trong bảng tổng; không chỉ chọn các case đẹp.

## 6. Thiết kế thực nghiệm

### 6.1 Đầu vào và lựa chọn trước output

- Validation 4.984 chỉ dùng kiểm corpus/thiết kế offline; test 5.031 là candidate pool. Đã kiểm mỗi test case có ít nhất một surrounding event: malicious 4.504 thuộc 22 families, benign 527 thuộc 9 families. Đây là kiểm availability ban đầu, chưa qua sanitizer/import/eligibility đầy đủ.
- Tập chính: 64 cases, 32 malicious + 32 benign theo nhãn synthetic của tác giả. Sau import hợp lệ, chọn round-robin theo family trong từng label; families sắp lexical, candidates trong family sắp SHA-256(`20261008|scenario_id`) rồi scenario_id. Không dùng success, reference decision hoặc output model để xếp hạng.
- Nếu thiếu quota sau kiểm chất lượng, BLOCKED_DATASET_COVERAGE; không âm thầm giảm mẫu số/đổi split. Receipt selection ghi pool, exclusions, available/selected counts từng label/family và mọi hash.
- Không claim test là family holdout: splits của tác giả có chung families/templates; dữ liệu và nhãn public cũng có thể đã nằm trong model pretraining. Đây là thực nghiệm so sánh trên corpus tổng hợp có kiểm soát, không phép đo tổng quát trên SOC thật.
- Người thật audit nguồn/label/supportability trên ít nhất 12 cases chọn deterministic, mỗi label 6, trước freeze. Case không đủ căn cứ báo ambiguous; exclusions phải có receipt người thật, tái chọn theo cùng thuật toán trước output. Không agent tự tạo phiếu duyệt.
- Demo chọn bốn IDs trước model output: hai malicious thuộc families khác nhau, một benign, một có loại context tự nhiên unavailable. Nếu không có case thứ tư phù hợp, selection gate blocked; không xóa evidence để tạo thiếu dữ liệu. Các IDs là subset tập 64, không thêm lượt API cho demo.

### 6.2 Hai điều kiện so sánh

**S0 — alert-only:** Một request model, cùng allowlisted alert/context đầu vào, không tools hoặc observations bổ sung từ corpus. Cùng model/final-report schema; được cite input evidence đã đăng ký, không cite tool records chưa delivered. Insufficient evidence hợp lệ. Tool-evidence citation metrics là NA; input citation validity được báo riêng. Không gọi S0 là technical tool workflow completion.

**S1 — evidence-driven:** Cùng đầu vào và 64 IDs, qua `investigate_alert`, model tự gọi hai tools, tối đa 6 requests/case như mục 4. S0 đi qua cùng entrypoint/report validation với condition tắt tools. Không dùng fixed reference sequence hoặc copy report của tác giả.

Model đề xuất khóa cho cả hai: `gpt-4.1-mini-2025-04-14`, temperature=0, max_completion_tokens=2000, một model cho mọi turn. Đây là contract mới đề xuất, không kế thừa quyền/cap 1000 của release cũ. Max request 128.000 UTF-8 bytes, max messages 16; vượt giới hạn chặn trước transmission. SDK chính thức, max_retries=0, không fallback hoặc đổi model sau lỗi. Pricing/availability phải được xác minh lại lúc lập release; unavailable thì ghi blocked, không tự đổi model.

Tối đa 448 requests cho cả 64 S0 + 64 S1; đây là cận requests, không ngân sách đã duyệt. Không calibration/pilot paid, không thêm lượt cứu kết quả trong spec này. Chuẩn bị/kiểm protocol offline trước freeze.

### 6.3 Phép đo

| Phép đo | Quy tắc |
|---|---|
| Agreement với nhãn tổng hợp | Correct / planned 64 mỗi condition; failed/missing/insufficient không là correct. Báo riêng coverage và insufficient rate |
| Theo lớp/family | Confusion matrix ba predictions, malicious/benign precision/recall/F1; macro theo families; denominator và missing hiện rõ. Không bỏ abstentions khỏi false negatives |
| Giá trị tool | S1–S0 trên cùng 64 IDs; wins/losses/ties/incomplete, calls/tokens/latency/cost. Không gọi delta là causal proof cho toàn SOC |
| Citation/provenance | Delivered references hợp lệ / references đã cite; no citations là NA. Tách input citations với tool-evidence citations; báo case-level validity / planned64 riêng |
| Evidence coverage | Record counts delivered, loại nguồn và unavailable/truncated; không gọi reference oracle evidence là toàn gold incident |
| Technical completion | S1: final schema + source identity + citation checks + real provider/model trace + terminal state hợp lệ, trên planned64; không đồng nghĩa verdict đúng. S0 báo report completion riêng |
| Human review | reviewed/64 và approved/rejected/escalated/awaiting_human. Chỉ approved kèm technical-valid mới là approved completion; không chứng minh nhãn đúng nếu không có review ngữ nghĩa |
| Ngữ nghĩa báo cáo | Người thật rà bốn demo reports: factual support, root-cause claim, contradiction, action suitability. Technical validation không tự PASS mục này |

Paired metrics giữ record cả failures; không đo interval nếu thiếu paired coverage hoặc identities. Khoảng tin cậy nếu thêm phải nêu family clustering, seed/method và kích thước nhỏ; không bootstrap rows rồi gọi độc lập. Không lấy latency/confidence giả của bộ sinh làm số liệu mới.

## 7. Gate, trạng thái và chi phí

Gate trước paid: source/import/selection+human audit → schema/tool/policy offline checks → runtime/source/gold/scorer/prompt locks → exact-SHA CI có kiểm corpus → account/pricing/budget được người dùng cấp riêng → canonical ledger unused và cận tiền đủ toàn suite.

Release mới dùng identity SOC riêng, private canonical ledger và scope IDs không trùng cửa sổ cũ. Không sửa `RunJournal.validate_release` hiện có để giả release SOC là query. Thiết kế journal riêng hoặc generalization có review/ràng buộc hồi quy trước freeze; không chuyển tiền đã cấp cho Text-to-SQL sang SOC.

Reserve theo từng case/condition/request trước SDK; lưu raw response và usage bền vững trước parse/validate. Binding request/response/native calls/case ID phải kiểm được. Missing usage, timeout/charged failure, crash sau reserve hoặc identity mutation làm terminal; unknown cost giữ unknown, không tự ghi 0. Persist partial receipts ngay, không đợi cuối suite.

Không retry, mở output khác/window khác để chạy lại cùng scope, đổi key/model/cap hoặc sửa prompt sau output rồi giữ lock cũ. Lỗi cục bộ input/parse ghi failed; lỗi transport/budget/unknown cost dừng toàn release. Các cases chưa chạy vẫn ở denominator, status missing/not_run. Review yêu cầu thêm evidence chỉ ghi trạng thái, không mở model call mới tự động.

Technical statuses: not_run, blocked, partial, failed, completed. Review statuses độc lập: awaiting_human, approved, rejected, escalated, more_evidence_requested. Renderer không nâng trạng thái bằng cách thấy một file tồn tại.

## 8. Bàn giao và điều kiện hoàn tất

| Đầu ra | Nội dung / điều kiện kiểm |
|---|---|
| D-SOC1 | Manifest nguồn, license, digest; corpus schema/import receipt; exclusions và source pointers |
| D-SOC2 | Inventory 64, labels evaluator riêng, selection/demo locks, receipt human audit nguồn |
| D-SOC3 | Corpus adapter/tools/policy/public entrypoint, tests boundaries và real-corpus queries; không MockProvider |
| D-SOC4 | Final report schema, formatter JSON/HTML/Markdown; full content/source consistency và escaping checks |
| D-SOC5 | Release/preflight/cost bounds/account authorization/ledger identities; private raw journals không đưa lên Git public |
| D-SOC6 | 128 condition records hoặc receipt đủ completed/failed/not_run; output model mới, delivered traces, usage và errors |
| D-SOC7 | Báo cáo so sánh/coverage/class/family/cost, ghi rõ synthetic/public/template limitations |
| D-SOC8 | Bốn demo reports đã chọn và review thật; runbook nhận alert/IOC → public entrypoint → artifacts, không nút replay API |

Mỗi mốc commit/push `master`, CI đúng SHA trên Python 3.11/3.12, receipt hashes/status. Một người thực hiện, không branches/PR/subagents. Không coi skipped corpus positive tests là nghiệm thu; dữ liệu public tải ở revision/digest đã pin, không cần API key trong jobs offline. Repo-backed artifacts lưu trong repo; raw parquet/DuckDB giữ ngoài Git và có cách restore pin.

Được báo **thực nghiệm đã chạy** chỉ khi có output/trace thật và đúng scope; **báo cáo hoàn chỉnh về nội dung** cần final model report đủ fields, references và full rendering; **đã được duyệt** cần người thật. Nếu gate thiếu, bàn giao blocker và làm phần offline độc lập; không tạo số liệu hoặc demo thay thế.

## 9. Điểm tiếp tục

- [x] Người dùng chốt thiết kế luồng đầu–cuối trong hội thoại, tạm hoãn Text-to-SQL toàn diện.
- [x] Đối chiếu public HEAD, corpus audit và giới hạn orchestrator/schema hiện tại.
- [x] Viết đặc tả; tự rà preservation, gold separation, synthetic provenance, model-only report, scope/cost và partial status.
- [x] Người dùng duyệt đặc tả này ngày 08/10/2026. Các giá trị 64 cases, hai condition, model/caps và hai tools đã được duyệt về thiết kế, chưa là quyền gọi API.
- [ ] Sau khi văn bản được duyệt: dùng `superpowers:writing-plans` lập các task có files/interfaces/checks; dùng `superpowers:executing-plans` triển khai trực tiếp, giữ single writer trên master.

Không thay hoặc ghi đè kế hoạch Text-to-SQL lịch sử trong lượt lưu đặc tả. Spec này là điểm ưu tiên mới; nếu tiếp tục Text-to-SQL sau đó phải đọc cursor/gates/ledger thật tại thời điểm resume.
