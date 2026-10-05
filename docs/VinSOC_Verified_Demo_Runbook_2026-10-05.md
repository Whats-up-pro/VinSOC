# VinSOC: kịch bản demo sau phần kết quả

**Đối tượng:** hội đồng kỹ thuật / reviewer. **Thời lượng:** 15–20 phút.
**Mốc code đã kiểm:** Task2 `422ba0beeda0fa8f7dce2bfefc4296c151287695`; closure `1ea74db1a838d9f28535cf017eca0a1937c07e81`; sửa CLI `46f5a27723b880e39d593f5a25f769afad57308e`.

Đây là kịch bản trình bày và hướng dẫn thao tác. Việc viết tài liệu này không tạo lượt model mới, không tạo score mới và không mở frozen. Các lệnh rehearsal/replay dưới đây là đề xuất cho người trình diễn; chúng chưa được chạy để tạo artifact demo trong checkpoint viết tài liệu này. CLI/flags được đối chiếu với code hiện tại.

## 1. Thông điệp xuyên suốt

> “VinSOC đã có kết quả dev được lưu và chấm lại được. Sau phần số liệu, tôi sẽ mở trace để xem SQL và evidence thực sự đến từ đâu. Kết quả model, execution scoring và demo được trình bày riêng. Hiện dự án chưa có R2 holdout độc lập hợp lệ.”

Trên màn hình luôn đặt một trong ba nhãn:

| Nhãn | Nội dung | API mới |
|---|---|---:|
| **REPLAY ARTIFACT** | Mở response/SQL/tool calls của lượt lịch sử, hoặc chấm lại prediction đã lưu | 0 |
| **OFFLINE REHEARSAL** | Tool production truy vấn snapshot thật; arguments cố định từ scenario; assessment của script | 0 |
| **LIVE MODEL CALL — GATED** | Model sinh arguments rồi assessment; chỉ thực hiện sau release/budget/identity/CI gates | Chỉ khi được mở gate |

Fake transport trong unit tests là kiểm thử code. Nó không thuộc ba loại kết quả model/demo có dữ liệu trên và không được xuất thành accuracy.

## 2. Kịch bản theo thời gian

| Phút | Màn hình / thao tác | Điểm cần nói |
|---:|---|---|
| 0–2 | Bảng R1/R2 và link artifact | Metric đo gì, mẫu bao nhiêu, kết quả còn thiếu gì |
| 2–4 | Git SHA, CI, winner lock, snapshot hashes | Code được kiểm; dữ liệu và lịch sử được bảo toàn |
| 4–7 | R2 case008 và case006 từ report | Một query đã chấm đúng và một TOOL_LIMIT được giữ nguyên |
| 7–9 | Replay scorer offline | Người khác có thể chấm lại mà không trả phí model |
| 9–13 | Botnet + Normal network rehearsal | Production tool, evidence ID, source row và thời gian CTU thật |
| 13–16 | Trace live nếu đã mở gate; nếu chưa, trình bày contract và trạng thái | Arguments/assessment phải do model; citations chưa tự chứng minh mọi claim |
| 16–20 | Q&A, lỗi CLI vừa sửa, các bước còn lại | DEV_VERIFIED / HOLDOUT_PENDING; không tuyên bố hoàn tất generalization |

## 3. Mở đầu: show kết quả trước

### Lời dẫn

> “R1 đo quyết định chọn tool, không thực thi tool trong suite này. R2 đo kết quả thực thi SQL so với gold trên snapshot đã khóa. CI xanh kiểm chứng code; nó không thay thế artifact accuracy.”

| Track / điều kiện | Metric đã có | Cost từ usage của lượt đó | Giới hạn |
|---|---|---:|---|
| R1 dev v2, GPT‑4.1 mini | 22/24 = 91.67%; exact-call F1 0.9508; no-tool 5/5 | $0.0101312 | Winner dev; 11/24 gold adjudicated sau khi xem output gốc |
| R1 dev v2, GPT‑5 mini | 19/24 = 79.17%; F1 0.9355; no-tool 4/5 | $0.01595 | Model/request contract khác; không là frozen |
| R2 CTU E0, run36520685612 | EX0/8; response/syntax/execution8/8 | Xem usage/cost trong artifact E0 | Điều kiện lịch sử riêng; immutable |
| R2 remediation live lịch sử | EX1/8 | Xem artifact riêng | Không ghép với public pilot hoặc Phase2 thành đường cải tiến nhân quả |
| R2 Phase2, SHA3f9d72d | EX7/8 = 87.5%; syntax7/8; execution7/8 | $0.02085850 | 8 dev cases; case006 TOOL_LIMIT giữ nguyên |
| Post-INTEGER hint / Task2 v4 | Chưa có verified full-suite model score mới | Task2 inference mới $0 | 820 tests là code verification, không phải EX model |
| Holdout | R1 chưa mở inference; R2 chưa có holdout độc lập hợp lệ | Chưa chạy trong checkpoint này | S1/S4 consumed, protocol-ineligible |

R1 GPT‑4.1 mini dùng temperature0; GPT‑5 mini bỏ temperature và dùng reasoning_effort low. Public-dev pilot5/8 thuộc snapshot/điều kiện riêng; không đặt cùng một đường tiến bộ với CTU E0, remediation và Phase2. Các cost trên không phải tổng hóa đơn hoặc số dư credit.

### Mở artifact, không nhập số bằng tay

```powershell
Set-Location D:\VINUNI_AI2026\Phase3_VinSOC
$r1 = Get-Content -Raw -Encoding UTF8 evaluation/tool_calling/winner_lock.json | ConvertFrom-Json
$r1.winner | Select-Object case_success_count, case_count, config, cost_usd
$r1.winner.aggregate | Select-Object exact_call_f1, no_tool_accuracy
$r1.other_candidate | Select-Object case_success_count, case_count, config, cost_usd
$r1.caveats

$suitePath = 'results/evaluation_v1/ctu_network_public/r2_phase2_live/20261001_3f9d72d/suite/report.json'
$suite = Get-Content -Raw -Encoding UTF8 $suitePath | ConvertFrom-Json
$suite.counts
$suite | Select-Object actual_models, attempted_calls, response_count, db_calls, input_tokens, cached_input_tokens, output_tokens, observed_cost_usd, cost_complete
$suite.case_results | Select-Object case_id, error_category, syntax_valid, execution_success, execution_accurate
```

Nguồn: [R1 winner lock](../evaluation/tool_calling/winner_lock.json), [Phase2 suite](../results/evaluation_v1/ctu_network_public/r2_phase2_live/20261001_3f9d72d/suite/report.json), [E0 receipt](../results/evaluation_v1/ctu_network_public/gpt5_e0/36520685612/receipt.json), [governance](evaluation/r2_phase2_governance.md).

## 4. Kiểm dữ liệu và code trước phần thao tác

> “Tôi đang dùng CTU S5/S7 lịch sử, không dùng telemetry 24 giờ gần đây. Snapshot có243906flows: S5=129831, S7=114075. Hash binary này là của snapshot gốc trên checkout; logical hash là định danh nội dung đã khóa. Binary rebuild khác không được tự gán lại thành binary identity của run cũ.”

```powershell
git status --short
git rev-parse HEAD
git rev-parse origin/master
$demoSnapshot = 'data/ctu_network_public/snapshots/ctu_dev.duckdb'
$snapshotHash = (Get-FileHash -LiteralPath $demoSnapshot -Algorithm SHA256).Hash.ToLowerInvariant()
if ($snapshotHash -ne '0b29765b9a175d00e0a193039a1b058691406e28a434e10030ae78265cfa67b9') {
    throw 'Snapshot binary khác bản đã kiểm; dừng để đối chiếu identity.'
}
python -m evaluation.ctu_network_public.contract --snapshot $demoSnapshot
if ($LASTEXITCODE -ne 0) { throw 'CTU validation chưa pass.' }
```

Logical S5/S7: `42c8e0a62441295cc5d95329a65dc22409c37de5b26a1e37dd56fbf0164a758c`.
Không dùng `--write-lock`, không rebuild/download trong buổi demo. Nếu dữ liệu thiếu hoặc validator fail, mở receipt lịch sử và trình bày blocker; không đổi nguồn để có màn hình đẹp.

CI đã kiểm:

- [Task2 implementation422ba0b](https://github.com/Whats-up-pro/VinSOC/actions/runs/37265105043): Python3.11/3.12,820 pass mỗi job.
- [Task2 closure1ea74db](https://github.com/Whats-up-pro/VinSOC/actions/runs/37265511965): hai job xanh.
- [CLI46f5a27](https://github.com/Whats-up-pro/VinSOC/actions/runs/37274201577): hai job xanh; lấy số pass từ log CI khi trình bày.
- [Task2 completion receipt](../results/evaluation_v1/finalization_audit/20261005/task2/completion_receipt.json), [CLI offline receipt](../results/evaluation_v1/finalization_audit/20261005/cli_context/verification_receipt.json).

## 5. R2: mở một case đúng và một case lỗi

**Nhãn màn hình: REPLAY ARTIFACT — không gọi model mới.**

```powershell
$good = $suite.case_results | Where-Object case_id -eq 'ctu_sql_008'
$good.final_sql
$good | Select-Object syntax_valid, execution_success, execution_accurate
$good.trajectory | Select-Object tool, arguments, result

$failed = $suite.case_results | Where-Object case_id -eq 'ctu_sql_006'
$failed | Select-Object case_id, error_category, final_sql, db_calls, observed_cost_usd
$failed.roles.linker | Select-Object turns, tool_count, error
$failed.trajectory | Select-Object tool, arguments, result
```

SQL008 thực trong artifact:

```sql
SELECT source_dataset, COUNT(*) AS flow_count
FROM network_flows
GROUP BY source_dataset
ORDER BY source_dataset;
```

> “Query này đã được execution-score trên snapshot khóa. Case006 không có final SQL: linker3turns,5DBcalls, TOOL_LIMIT. Chúng tôi giữ nó trong denominator8. Việc sửa typed hint chưa cho phép thay case006 bằng một prediction mới rồi gọi suite cũ là8/8.”

Hiển thị pipeline lịch sử `model → SQL validator → DuckDB → comparator → EX`. Raw SQL thuộc evaluator R2; production network tool có arguments có cấu trúc, không nhận SQL từ LLM.

## 6. Chấm lại prediction mà không gọi API

```powershell
$demoStamp = Get-Date -Format 'yyyyMMdd_HHmmss_fff'
$demoRoot = Join-Path '.vinsoc' ('demo_rehearsal_' + $demoStamp)
if (Test-Path -LiteralPath $demoRoot) { throw 'Output đã tồn tại; dùng namespace mới.' }
New-Item -ItemType Directory -Path $demoRoot | Out-Null
$replayOutput = Join-Path $demoRoot 'r2_saved_outputs'
python -m scripts.audit_r2_saved_outputs --input results/evaluation_v1/ctu_network_public/r2_phase2_live/20261001_3f9d72d/suite --snapshot $demoSnapshot --output $replayOutput
if ($LASTEXITCODE -ne 0) { throw 'Replay chưa qua identity/scoring gate; giữ receipt và dừng.' }
$replay = Get-Content -Raw -Encoding UTF8 (Join-Path $replayOutput 'report.json') | ConvertFrom-Json
$replay | Select-Object scope, is_new_model_run, model_calls, new_cost_usd, case_count, scored_case_count, status
$replay.counts
```

> “Đây là current offline replay của prediction đã lưu. Scorer phân biệt pipeline OK với execution accuracy; SQL chạy được nhưng sai kết quả vẫn RESULT_MISMATCH. Replay không bổ sung provenance hồi tố cho run cũ.”

Giữ input report/8caseJSON nguyên bytes. Không chạy lại E0/E1/E2/E3, không gọi script case006 để sinh prediction; wrapper case006 hiện chỉ chấm input có sẵn offline.

## 7. Hai tình huống production network tool

**Nhãn màn hình: OFFLINE REHEARSAL — data thật, arguments cố định, assessment của script.**

Đây là rehearsal có thể dùng trước khi live gate được mở. Nó chưa chứng minh model chọn đúng tool, chưa có assessment do model và không phải benchmark accuracy.

### 7.1 Botnet

```powershell
$botnetOutput = Join-Path $demoRoot 'botnet_rehearsal.json'
if (Test-Path -LiteralPath $botnetOutput) { throw 'Không ghi đè receipt Botnet.' }
python -m scripts.demo_ctu_network_public --snapshot $demoSnapshot --scenario botnet --output $botnetOutput
if ($LASTEXITCODE -ne 0) { throw 'Botnet rehearsal fail; giữ output/diagnostic.' }
$botnet = Get-Content -Raw -Encoding UTF8 $botnetOutput | ConvertFrom-Json
$botnet | Select-Object demo_mode, snapshot_logical_sha256, evidence_ids, usage, cost_usd
$botnet.scenario | Select-Object indicator, time_range
$botnet.tool_trace
$botnet.evidence | Select-Object evidence_id, data, provenance
$botnet.limitations
```

Lời dẫn:

> “Scenario được chọn từ CTU label ở bước chuẩn bị. Tool nhận IP và thời gian lịch sử, trả evidence kèm nguồn. Label chỉ dùng đối chiếu ngoài request; không dùng nó để bảo model kết luận malicious. Với rehearsal, arguments và lời assessment này là của script.”

### 7.2 Normal

```powershell
$normalOutput = Join-Path $demoRoot 'normal_rehearsal.json'
if (Test-Path -LiteralPath $normalOutput) { throw 'Không ghi đè receipt Normal.' }
python -m scripts.demo_ctu_network_public --snapshot $demoSnapshot --scenario normal --output $normalOutput
if ($LASTEXITCODE -ne 0) { throw 'Normal rehearsal fail; không gọi toàn demo success.' }
$normal = Get-Content -Raw -Encoding UTF8 $normalOutput | ConvertFrom-Json
$normal.scenario | Select-Object indicator, time_range
$normal.evidence | Select-Object evidence_id, data, provenance
$normal.limitations
```

> “Normal là nhãn dataset của scenario. Nó không buộc assessment trả benign. Kết luận phụ thuộc evidence quan sát được và phải giữ uncertainty khi thiếu CTI/endpoint hoặc thiếu coverage.”

### 7.3 Chứng minh evidence nối tới hàng nguồn

Mở `evidence_id`, `data` và `provenance.source_records` trong JSON. Helper `_verify_evidence_pairs()` đối chiếu từng `(source_dataset, source_row_id)` bằng readonly query và yêu cầu đúng1hàng. Nếu cặp nguồn không tồn tại, rehearsal phải fail.

```powershell
$botnet.evidence | ForEach-Object {
    $_.evidence_id
    $_.provenance.source_records | Select-Object source_dataset, source_row_id
}
```

> “ID tồn tại chứng minh khả năng truy vết record. Nó chưa tự chứng minh mọi câu prose đúng. Connection counts, protocol, timestamps, IP/port phải đối chiếu với payload tương ứng; claim CTI hoặc endpoint cần nguồn riêng.”

CTU-only có network flows, không có CTI/endpoint tables. Giữ các limitations này trên màn hình. Không gọi ThreatFox/OTRF trong critical path.

## 8. Phần live model-driven: chỉ mở sau các gate tiếp theo

**Trạng thái tại ngày viết: chưa mở cho final demonstration.** Task3 contract/guard, paired dev và Task5 factual validator/shared ledger còn cần review/implementation. Entrypoint `scripts.demo_ctu_network_public_model_driven.py` hiện tạo client trước phần run preflight, chưa có CLI `--preflight-only`/shared ledger theo finalization plan; vì vậy tài liệu này không cung cấp lệnh paid để vượt qua release gate. `--diagnostic-first-request` là lượt paid riêng, không là preflight miễn phí.

Sau khi release đó được review, người trình diễn mới dùng lệnh CLI đã được kiểm ở implementation SHA ấy. Không tự thêm flags chưa có trong code hiện tại.

Lời dẫn dự kiến cho live:

> “Bây giờ mới là live API. Request chỉ gửi analyst question và dữ liệu được phép. Model đầu sinh arguments cho production network_investigation; validator kiểm arguments rồi DuckDB trả evidence. Model thứ hai đọc evidence và sinh assessment. Botnet và Normal tối đa2requests mỗi scenario; chúng tôi giữ partial nếu một scenario fail.”

Receipt live cần hiển thị:

1. Implementation SHA với CI-before-inference, snapshot/manifest/prompt/schema identities; account headroom, pricing receipt, preflight reserve và ledger chung.
2. Actual model `gpt-4.1-mini-2025-04-14`, temperature0, cap1000, retries0; attempted/received calls, response IDs, request hashes và usage journal trước parsing.
3. Model arguments thực, validator outcome, production tool trace, evidence ID + source pair; không thay bằng arguments của script.
4. Assessment model thực, required citations/limitations và structured factual observations khớp payload. Prose review scope riêng; ID hợp lệ chưa là factual correctness.
5. Flags từng scenario; aggregate chỉ true khi cả hai pass. Thiếu usage/identity/budget hoặc provider failure dừng paid window; câu trả lời sai được giữ, không retry để lấy kết quả đẹp.

Nếu live chưa mở, kết thúc ở rehearsal và nói đúng trạng thái. Nếu live fail, mở partial artifact và lỗi; không chuyển rehearsal thành “model-generated success”. Hai scenario demo không cho headline accuracy.

## 9. Giải thích output CLI IP185.220.101.45 đã gửi

Lệnh đã gửi không có `--duckdb-snapshot`; nó không chứng minh đã tra snapshot CTU. “Connections0” chỉ mô tả kết quả nguồn/tool trong invocation đó; `UNKNOWN/LOW` không phải xác nhận IP benign. Thời gian24giờ gần đây cũng không phải thời gian CTU2011.

Lỗi `context=None` đã được tái hiện bằng fake provider và sửa trong shared case serialization: field optional bị bỏ khi không có context; string rỗng và context được cung cấp vẫn giữ. Schema production không đổi. Local regression20pass; full823pass. Không gọi lại model để xác nhận sửa lỗi serialization. Usage/cost của lượt CLI do người dùng chạy chưa được cung cấp và không nằm trong accuracy benchmark hay chi phí offline$0 này.

## 10. Câu hỏi hội đồng và câu trả lời ngắn

**“Có đạt100% không?”** — Full-suite R2 đã chấm là7/8. Post-hint chưa có full-suite verified score mới; tests xanh không nâng điểm model.

**“Có generalize không?”** — Chưa có R2 holdout độc lập hợp lệ. S1/S4 consumed, không chạy lại hoặc đổi tên để gọi frozen mới. R1 frozen cũng chưa mở inference.

**“Tại sao R1 chọn GPT‑4.1 mini?”** — Rule hiện hành chọn dev case success22/24 so với19/24; tool-selection contract và11/24 post-output adjudication caveat được công bố. Không mở vòng tuning để cứu điểm.

**“Token tiết kiệm bao nhiêu?”** — Trình bày usage và cost từng artifact. Chưa có bằng chứng cho claim tiết kiệm60%, không suy từ giá/model size hoặc hai run khác contract.

**“Demo chứng minh điều gì?”** — Rehearsal chứng minh production tool đọc network snapshot và evidence có nguồn. Live receipt đạt gate mới chứng minh model sinh arguments/assessment cho hai scenario cụ thể. Cả hai không thay thế accuracy suite hoặc full SOC CTI/endpoint evaluation.

**“Có reproduce DualSQL RL không?”** — Đây là inference-inspired architecture. Không tuyên bố đã train hoặc reproduce multi-agent RL.

## 11. Kết thúc

> “Kết quả dev, prediction lỗi và chi phí đã được giữ trong artifact. Reviewer có thể chấm lại SQL offline và truy vết evidence. Những bước còn lại là khóa release v4, lượt dev có control, demo model-driven đã kiểm factual claims và holdout độc lập được human authorize. Trạng thái hiện tại là DEV_VERIFIED / HOLDOUT_PENDING.”

### Chuẩn bị trước buổi trình diễn

- [ ] Dùng đúng checkout đã có CI xanh; `.env` không mở lên màn hình; không thay key hoặc mua credit.
- [ ] Chuẩn bị artifact/receipts và snapshot gốc; validator/hashes pass, output namespace mới.
- [ ] Chạy rehearsal offline trước buổi trình diễn nếu được giao; giữ receipt và thời gian thực tế, không nhập output mẫu vào slide.
- [ ] Màn hình có nhãn replay/rehearsal/live, nguồn/timeframe và limitations.
- [ ] Phần live chỉ có sau review/cost/identity/CI/attempt gates; không rerun suite hoặc case fail.
- [ ] Nếu một bước fail: giữ artifact, trình bày lỗi và blocker, không đổi dữ liệu/model/gold/scorer để hoàn tất màn hình.

Các checkbox trên dành cho người trình diễn. Việc tạo kịch bản không đánh dấu chúng đã hoàn thành.
