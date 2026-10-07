# VinSOC: kịch bản 11 slide và demo có kiểm chứng

**Đối tượng:** mentor, hội đồng kỹ thuật / reviewer. **Thời lượng:** 15–20 phút, gồm khoảng 9 phút nói theo slide, 5 phút mở artifact/rehearsal và thời gian Q&A.
**Deck:** [VinSOC Evaluation Progress — 2026-10-05](https://www.canva.com/d/H14i_CJTqqk8VMm), 11 trang. Kịch bản dưới đây bám đúng thứ tự trang, không yêu cầu đổi bố cục deck.

**Mốc đối chiếu tài liệu:** `master@f544d9dc637e93a489218cb05918439cb1cb2c61`.
**Mốc code:** audit Task 0+1 `bb462f30b30f29d1bba6207b4a96b2ad579875a9`; Task 2 `422ba0beeda0fa8f7dce2bfefc4296c151287695`; closure `1ea74db1a838d9f28535cf017eca0a1937c07e81`; sửa CLI `46f5a27723b880e39d593f5a25f769afad57308e`.

**Đính chính tiến độ khi nói:** deck đang giữ checkpoint `bb462f3`, nên trang 1/9/11 ghi **774 tests**, trang 10 còn đặt typed grounding trong lộ trình. Đến mốc runbook này, Task 2 đã implement và CI **820 tests** trên mỗi Python 3.11/3.12; sửa CLI đã có CI **823 tests** trên mỗi phiên bản. Các số là checkpoints khác nhau, không ghi đè lịch sử. Task 2 không gọi model mới, chưa tạo lock v4 và chưa tạo full-suite score mới. R1 vẫn **22/24**, R2 CTU dev vẫn **7/8**. Khi trình bày trang 2 và 10 phải nói cập nhật này, không mô tả Task 2 vẫn chưa bắt đầu.

Chỉ thay đổi kịch bản tài liệu. Các lệnh rehearsal/replay dưới đây dành cho người trình diễn, chưa được thực hiện trong lượt sửa runbook này. Không gọi API, mở frozen, tạo demo receipt hoặc tự mở gate paid. Giữ cách phân biệt kết quả model, replay offline, rehearsal và kiểm thử code.

## 1. Thông điệp xuyên suốt

> “VinSOC đã có kết quả dev được lưu và chấm lại được. Sau phần số liệu, tôi sẽ mở trace để xem SQL và evidence thực sự đến từ đâu. Kết quả model, execution scoring và demo được trình bày riêng. Hiện dự án chưa có R2 holdout độc lập hợp lệ.”

Trên màn hình luôn đặt một trong ba nhãn:

| Nhãn | Nội dung | API mới |
|---|---|---:|
| **REPLAY ARTIFACT** | Mở response/SQL/tool calls của lượt lịch sử, hoặc chấm lại prediction đã lưu | 0 |
| **OFFLINE REHEARSAL** | Tool production truy vấn snapshot thật; arguments cố định từ scenario; assessment của script | 0 |
| **LIVE MODEL CALL — GATED** | Model sinh arguments rồi assessment; chỉ thực hiện sau release/budget/identity/CI gates | Chỉ khi được mở gate |

Fake transport trong unit tests là kiểm thử code. Nó không thuộc ba loại kết quả model/demo có dữ liệu trên và không được xuất thành accuracy.

## 2. Thứ tự slide và thời gian

| Phút | Trang / màn hình | Thao tác |
|---:|---|---|
| 0–2 | 1–2: bìa, tóm tắt | Chốt hai kết quả dev, phạm vi CTU-only và trạng thái còn thiếu |
| 2–4 | 3–4: phương pháp, kiến trúc | Phân biệt model run với audit; production tools với SQL evaluator |
| 4–6 | 5–6: R1 | Giải thích case success, F1, no-tool; chọn cấu hình theo dev |
| 6–9 | 7–8: R2 | Giải thích execution scoring, 7/8, case006 và usage/cost |
| 9–14 | Tạm rời trang 8, mở artifact và rehearsal | Mở case008/case006 theo mục 5; replay mục 6; Botnet/Normal mục 7 nếu đã rehearsal trước |
| 14–17 | Quay lại 9–11 | Đọc bảng lịch sử có caveat; cập nhật Task 2; chốt bước tiếp theo và nguồn |
| 17–20 | Q&A | Dùng mục 10; không rerun model hoặc mở holdout để trả lời |

Nếu thiếu snapshot hợp lệ hoặc chưa rehearsal, chỉ mở artifact đã lưu rồi quay lại trang 9. Nói rõ phần thao tác chưa thực hiện; không dùng output mẫu để giả một lần chạy. Phần live ở mục 8 chưa được mở, không chen vào thời lượng này để gọi API.

## 3. Lời thoại theo từng trang

Các đoạn trích là lời có thể đọc trực tiếp. Ghi chú “Chỉ vào” và “Thao tác” dành cho người trình diễn, không đọc thành lời. Không đọc hết các ô bảng khi một câu đã nêu kết luận.

### Trang 1 — Kết quả development đến 05/10/2026

**Chỉ vào:** 22/24, 7/8, 243.906 flows, 774 tests.

> “VinSOC đang đo hai năng lực: model chọn tool và arguments ở R1, và sinh SQL trả đúng kết quả ở R2. Trên development, R1 đạt 22 trong 24 case; R2 CTU đạt 7 trong 8 case. Dữ liệu R2 gồm 243.906 network flows thật từ CTU Scenario 5 và 7. Đây là kết quả dev có artifact để kiểm tra. Đánh giá holdout độc lập và demo end-to-end hoàn chỉnh vẫn còn gate.”

**Ghi chú số CI:** 774 trên slide thuộc `bb462f3`. Nếu hỏi mốc mới nhất, dẫn CI 823 ở mục 4, không đổi 774 thành số của một SHA khác.

### Trang 2 — Tiến độ cụ thể

**Chỉ vào:** Benchmark, Model run, Audit, Fix / E2E.

> “Ba phần đã có bằng chứng là benchmark development, các lượt model thật đã lưu và audit lại cách chấm. Chữ Audit đã xong chỉ nói về Task 0+1 tại checkpoint của slide. Sau checkpoint đó, Task 2 đã bổ sung typed grounding và fixture phản ví dụ, CI đạt 820 tests. Chưa có lượt model mới để đo tác động của bản sửa. Bước tiếp theo là review, khóa contract cùng guard ngân sách, rồi mới mở đánh giá đối chứng và demo.”

> “R1 đã chọn cấu hình dev. R2 còn case006 không tạo được SQL cuối trong lượt 7/8. S1/S4 đã consumed và chưa có execution score được xác minh, nên không dùng chúng làm bằng chứng holdout độc lập.”

**Không nói:** “toàn bộ dự án xong”, “frozen đạt 100%”, hoặc “test tăng nên accuracy tăng”.

### Trang 3 — Phương pháp và bằng chứng

**Chỉ vào:** kiểm tra tích hợp, model thật + audit, replay 7/8 và 188 hashes.

> “Mock được dùng để kiểm thử code, còn accuracy lấy từ response model thật đã lưu. Với R1, evaluator ghép prediction và gold một-một rồi kiểm tool cùng arguments. Với R2, evaluator chạy SQL trên snapshot khóa và so kết quả với gold. Audit Task 0+1 giữ nguyên 188 hashes lịch sử và chấm lại dev vẫn 7/8, không gọi model mới.”

> “Task 2 bổ sung dữ liệu fixture để một query sai nhưng chạy được phải bị chấm sai: thiếu source filter, nhầm DISTINCT, biên thời gian, Boolean, wildcard hoặc top-k. Các fixture này kiểm độ phân biệt của scorer; chúng chưa tạo một accuracy mới của model.”

**Giới hạn:** EX=true trên một snapshot chưa chứng minh query đúng trên mọi dữ liệu có thể có. Mở Task 2 receipt nếu hỏi chi tiết, không gộp 188 hashes của Task 0+1 với 287 protected files của checkpoint sau.

### Trang 4 — Kiến trúc và ranh giới thực thi

**Chỉ vào:** production domain tools, R1, R2, evidence và assessment.

> “Production agent gọi domain tools bằng arguments có cấu trúc. R1 chỉ đo một lượt quyết định chọn tool và điền arguments; suite A1 không thực thi tool. R2 là evaluator riêng: model sinh SQL, safety gate kiểm query, DuckDB mở read-only và comparator chấm kết quả. Chúng tôi không đưa đường raw SQL của evaluator vào production agent.”

> “Demo network sẽ kiểm luồng tool trả evidence có source row rồi assessment sử dụng evidence đó. Đây là phép kiểm end-to-end riêng, không suy ra từ hai điểm R1/R2.”

### Trang 5 — R1: cách đo Tool Calling

**Chỉ vào:** Request, Provider, Tool Calls, Matcher, Report.

> “Evaluator đọc native tool-call objects thay vì đoán tool từ văn bản trả lời. Gold quy định tool và arguments cần có. Call thừa, thiếu, bị cấm hoặc sai argument đều có thể làm case thất bại. Report giữ predictions, arguments, match trace, provider telemetry và provenance để reviewer xem lại mà không gọi model.”

> “Cấu hình thắng trên dev là gpt-4.1-mini-2025-04-14, temperature 0, cap 1.000 completion tokens và không retry. Một lượt dev v2 có usage-derived cost 0,0101312 đô.”

**Lưu ý ô Argument Accuracy 100%:** đây là field accuracy theo denominator của evaluator. Nó không có nghĩa mọi case đều đúng; call thiếu/thừa vẫn bị phạt ở call metrics và case success.

### Trang 6 — R1: đọc bảng kết quả dev v2

**Chỉ vào:** từng hàng theo thứ tự bảng, sau đó dòng GPT-5 mini và caveat v1/v2.

| Điều kiện dev v2 | Model / request contract | Case success | Exact-call F1 | No-tool | Usage (input / output) | Cost từ usage |
|---|---|---:|---:|---:|---:|---:|
| Winner | `gpt-4.1-mini-2025-04-14`; temperature=0; cap=1000; retries=0 | 22/24 (91,67%) | 0,9508 | 5/5 | 18.088 / 1.810 | $0,0101312 |
| Comparator lịch sử | `gpt-5-mini-2025-08-07`; reasoning=low; không gửi temperature; cap=1000; retries=0 | 19/24 (79,17%) | 0,9355 | 4/5 | 20.104 / 5.462 | $0,0159500 |

| Winner case-level | Giá trị |
|---|---:|
| Tool-set exact match | 22/24 (91,67%) |
| Precision / recall | 0,9667 / 0,9355 |
| Case không đạt | `case_002`, `case_015` |

> “Case Success 22/24 nghĩa là 22 yêu cầu có quyết định hoàn toàn đúng theo gold và contract. Exact Call F1 là 95,08%, với precision 96,67% và recall 93,55%. F1 chấm từng call; case success chấm cả yêu cầu, nên một case có vài call đúng vẫn trượt nếu còn call sai hoặc thiếu.”

> “No-tool 5/5 nghĩa là model xử lý đúng năm case không nên gọi tool. Tool Set Exact Match 22/24 kiểm tên tool và số lượng call, còn Exact Call F1 có thêm required argument values. Hai con số case-level trùng nhau trong run này, nhưng hai metric có định nghĩa khác nhau.”

> “GPT-5 mini đạt 19/24, nên rule chọn theo dev case success giữ GPT-4.1 mini. Đây là lựa chọn giữa hai request contracts: GPT-4.1 mini dùng temperature 0, GPT-5 mini bỏ temperature và dùng reasoning low. Chưa kết luận một model tốt hơn trên mọi tác vụ.”

**Caveat phải giữ:** v1 15/24 và v2 22/24 khác gold/schema; 11/24 gold cases đã adjudicate sau khi thấy output gốc. Dev v2 phục vụ phát triển và chọn cấu hình, không là holdout độc lập. R1 frozen chưa được cấp phép inference. Hai lỗi winner còn lại là `case_002`, `case_015`; chỉ mở trace dev đã lưu nếu được hỏi.

### Trang 7 — R2: cách đo Text-to-SQL

**Chỉ vào:** schema + values, safety, DuckDB, comparator.

> “R2 đo query có trả đúng dữ liệu mà câu hỏi yêu cầu hay không. Query parse được là syntax validity; chạy được là execution success; trả accepted result mới là execution accuracy. Comparator xử lý scalar, hàng không có thứ tự và hàng có thứ tự theo contract của case. Safety rejection là trạng thái riêng.”

> “Model cần hiểu cả kiểu cột và giá trị lưu trong DB. DualSQL-Lite dùng database tools để grounding trước khi sinh SQL. Bản Task 2 tách schema type khỏi chứng cứ literal trong DB: biết một cột là INTEGER không tự chứng minh một giá trị đã xuất hiện trong cột đó.”

**Phạm vi phương pháp:** VinSOC sử dụng ý tưởng inference và DB grounding từ DualSQL, chưa train hoặc reproduce multi-agent RL của paper. Không gọi mọi run lịch sử E0 là cùng một cấu hình E0.

### Trang 8 — R2: live result và audit cùng là 7/8

**Chỉ vào:** hai cột Run 3f9d72d / Audit bb462f3, hàng case006, usage/cost.

| Case | Pipeline error | Syntax | Execution | EX | Diễn giải |
|---|---|---:|---:|---:|---|
| `ctu_sql_001` | `OK` | ✓ | ✓ | ✓ | Đã chấm bằng snapshot S5/S7 đã khóa |
| `ctu_sql_002` | `OK` | ✓ | ✓ | ✓ | Đã chấm bằng snapshot S5/S7 đã khóa |
| `ctu_sql_003` | `OK` | ✓ | ✓ | ✓ | Đã chấm bằng snapshot S5/S7 đã khóa |
| `ctu_sql_004` | `OK` | ✓ | ✓ | ✓ | Đã chấm bằng snapshot S5/S7 đã khóa |
| `ctu_sql_005` | `OK` | ✓ | ✓ | ✓ | Đã chấm bằng snapshot S5/S7 đã khóa |
| `ctu_sql_006` | `TOOL_LIMIT` | ✗ | ✗ | ✗ | Không có final SQL; offline scorer: `NO_FINAL_SQL` |
| `ctu_sql_007` | `OK` | ✓ | ✓ | ✓ | Đã chấm bằng snapshot S5/S7 đã khóa |
| `ctu_sql_008` | `OK` | ✓ | ✓ | ✓ | Group/count theo `source_dataset`, có thứ tự |

| R2 Phase2 suite lịch sử | Giá trị |
|---|---:|
| Implementation SHA | `3f9d72ddc840d368b15b161881a94335c42eb03e` |
| Syntax / execution success / execution accuracy | 7/8 / 7/8 / 7/8 |
| Safety rejection | 0/8 |
| Attempted / received model calls; DB calls | 44 / 44; 34 |
| Input / cached input / output tokens | 47.802 / 8.960 / 5.462 |
| Usage-derived cost | $0,02085850 (complete) |

| Lượt hoặc kết quả chưa có | Trạng thái trình bày |
|---|---|
| Post-INTEGER / typed-grounding full suite | Chưa chạy; không suy ra score từ unit tests |
| R2 v4 E0 và E3 paired dev | Chưa mở: cần Task3 contract, identity, budget và exact-SHA CI |
| Network demo model-driven | Chưa mở: cần shared ledger và factual validator |
| R1 frozen; R2 holdout độc lập | Chưa được authorize; S1/S4 đã consumed |

> “Cột trái là kết quả full dev Phase2 đã lưu tại implementation 3f9d72d. Cột phải là offline audit ở checkpoint bb462f3. Cả hai đều 7/8, tức 87,5% execution accuracy; syntax và execution success cũng 7/8. Safety rejection là 0/8. Audit giữ nguyên kết quả model, không sinh prediction mới.”

> “Case006 kết thúc TOOL_LIMIT, không có final SQL và vẫn nằm trong mẫu số tám. Trong scorer, nó là NO_FINAL_SQL với EX=false. Chúng tôi không thay một case rerun vào suite cũ để công bố 8/8.”

> “Lượt live có 44 attempted calls và 44 responses, cùng 34 database tool calls. Usage là 47.802 input tokens, gồm 8.960 cached input, và 5.462 output tokens. Chi phí tính từ usage là 0,0208585 đô. Đây là chi phí của run đó, không là tổng hóa đơn hoặc credit balance. Replay thêm zero model calls.”

**Thao tác tiếp theo:** tạm rời slide, dùng mục 5 mở `ctu_sql_008` và `ctu_sql_006`. Case008 query nhóm theo dataset và ORDER BY, kết quả S5=129.831, S7=114.075. Đây là response SQL đã lưu, không phải gold được dán vào để diễn live. Các sample 001/004 trên slide là điểm dữ liệu của run, không chứng minh semantic correctness trên mọi snapshot.

Nếu snapshot/outputs đã chuẩn bị và gate offline pass, chạy mục 6 replay rồi mục 7 rehearsal Botnet/Normal. Nếu chưa, chỉ trình bày report/trace và quay lại trang 9. Không gọi model tại đoạn này.

### Trang 9 — So sánh lịch sử có kiểm soát

**Chỉ vào:** từng hàng trước/sau và cột ý nghĩa.

> “Bảng này ghi tiến độ theo phiên bản, không phải một đường cải thiện model duy nhất. R1 từ 15/24 sang 22/24 có thay gold và schema. Public pilot R2 từ 2/8 lên 5/8 là replay cùng SQL sau sửa scorer. CTU từ 0/8 lịch sử đến 7/8 Phase2 đã đổi model hoặc kiến trúc/request contract. Vì thế chưa dùng các delta này để chứng minh tác động riêng của một cải tiến.”

> “Hàng audit dev 7/8 sang 7/8 cho thấy việc kiểm lại không nâng điểm. S1/S4 có tám saved predictions nhưng chưa qua snapshot identity gate, nên unscored. Đồng thời chúng đã consumed, không được tái sử dụng làm holdout độc lập.”

**Đính chính số tests:** 774 thuộc audit `bb462f3`; Task 2 820 và CLI 823 là checkpoints mới đã có CI. Tăng số test không thay đổi điểm R2 7/8.

### Trang 10 — Các gate còn lại

**Chỉ vào:** typed grounding, contract v4, paired dev, demo E2E.

> “Trang này giữ roadmap tại checkpoint slide. Đến runbook hiện tại, mục typed grounding và semantic counterexamples đã implement và qua CI 820 tests. Bản sửa chưa có lock v4 hoặc paid result mới. Gate tiếp theo là review và khóa release contract, attempt/cost guards cùng snapshot identities.”

> “Sau khi mở gate, mới chạy một cặp E0/E3 trên cùng tám dev cases và cùng implementation SHA để đo tác động có control. Sau đó là demo network: model sinh arguments, production tool lấy evidence thật, model sinh assessment và factual checks kiểm claim. Hiện chưa gọi trạng thái đó là E2E COMPLETE.”

> “Final track là CTU-only network. Ba nguồn ThreatFox/CTU/OTRF vẫn blocked, không nằm trên đường bắt buộc để hoàn tất demo này. Holdout độc lập cần authorization và ngân sách riêng; S1/S4 cũ không thay thế gate ấy.”

**Không thao tác:** không tạo lock, rerun suite, smoke, retry hoặc dispatch paid workflow ngay trong bài trình bày. Kịch bản này không cấp quyền mở các gate tiếp theo.

### Trang 11 — Nguồn và kết luận

**Chỉ vào:** nguồn phương pháp, repo, CI.

> “Nguồn phương pháp gồm native function calling, BFCL cho tool/no-tool evaluation, DualSQL cho hướng grounding và Zhong cùng cộng sự về semantic evaluation bằng test suites. Các nguồn này là cơ sở thiết kế; điểm VinSOC lấy từ artifact riêng của dự án, không phải điểm của các benchmark đó.”

> “Hiện có R1 dev 22/24 và R2 CTU dev 7/8 có trace, usage và provenance. Task 0+1 đã kiểm lại cách chấm; Task 2 đã bổ sung typed grounding và phản ví dụ offline. Các bước còn lại là release gate v4, đánh giá đối chứng, demo model-driven có factual checks và holdout độc lập. Tôi giữ kết quả sai cùng giới hạn của chúng để reviewer có thể kiểm lại.”

**Nếu kết thúc sau rehearsal:** nói rõ production tool đã chạy trên snapshot thật khi có receipt thực tế, nhưng arguments/assessment do script; không gọi đó là live model-driven E2E. Nếu chưa rehearsal, chỉ nói đã trình bày artifact và kế hoạch thao tác.

### Mở artifact để đối chiếu lời nói

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
- [CLI46f5a27](https://github.com/Whats-up-pro/VinSOC/actions/runs/37274201577): Python 3.11/3.12, **823 pass mỗi job** (log: 51.43s / 55.92s).
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

**Cập nhật implementation:** canonical `--e2e` đã đi qua public `InvestigationOrchestrator.investigate()`, dùng một guarded client, một native network call và một assessment request/scenario. `--preflight-only`, `--env-file`, deferred review và offline HTML đã có; preflight không tạo SDK client. Đây là trạng thái code, chưa phải bằng chứng live thành công. R1/R2 và các kết quả lịch sử ở những mục trước không được cập nhật bằng unit tests.

**Release/live vẫn đóng nếu thiếu snapshot hoặc private gates.** Không có snapshot đủ điều kiện thì không tạo `NETWORK_E2E_v1.lock.json` từ số liệu lịch sử. Local acceptance bắt buộc dùng đúng CTU S5/S7, logical SHA `42c8e0a62441295cc5d95329a65dc22409c37de5b26a1e37dd56fbf0164a758c`, 243906 flows và 243906 source pairs. CI skip bài test local không thay thế bước này. Không tải lại nguồn, tạo dữ liệu giả hoặc chạy API để thử gate.

Các lệnh sau là quy trình trên laptop **sau khi xác minh file có thật**, không phải receipt cho một live run đã diễn ra:

```powershell
$Snapshot = (Resolve-Path "data/ctu_network_public/snapshots/ctu_dev.duckdb").Path
$env:VINSOC_LOCAL_SNAPSHOT = $Snapshot
python -m pytest tests/test_network_e2e_lifecycle.py -k local_verified_snapshot_two_scenario_rehearsal -q
python -m evaluation.finalization.network_contract --snapshot "$Snapshot" --output "evaluation/finalization/NETWORK_E2E_v1.lock.json"
```

Rehearsal dùng production tool và snapshot thật nhưng model/reviewer synthetic, nhãn `OFFLINE_REHEARSAL`, không API. Lock mới chỉ được tạo một lần; không overwrite lock khi hash khác. Sau lock, commit/push và đợi full CI Python 3.11/3.12 đúng implementation SHA trước preflight.

Private `gates.json` phải là bằng chứng thật, không commit: exact implementation/CI SHA và URLs/jobs; account/project cùng allocation hiện hành được owner/platform xác nhận; giá hiện hành; receipt hashes/known prior cost/unresolved unknown-cost. Account/pricing tối đa sáu giờ tuổi. Không tự điền `true` hoặc coi credit cũ là balance hiện tại. Một allocation unknown chưa reconcile phải block.

```powershell
$WindowRoot = Join-Path $env:USERPROFILE ".vinsoc/live-windows/network-finalization-20261006"
$Ledger = Join-Path $WindowRoot "ledger.json"
$Gates = Join-Path $WindowRoot "gates.json"
$Out = "results/evaluation_v1/network_e2e_v1/20261006/technical_receipt.json"
python -m scripts.check_env --check
python -m scripts.demo_ctu_network_public_model_driven --e2e --preflight-only --scenario all --snapshot "$Snapshot" --output "$Out" --budget-usd 0.25 --ledger "$Ledger" --gates "$Gates" --review-mode deferred
```

Nếu dùng checkout riêng, thêm `--env-file` trỏ tới `.env` gốc; không copy/ghi đè `.env`. Key-source conflict/custom base URL/missing gate dừng trước client. Preflight PASS phải có attempted0, responses0, client_created=false; output nằm cạnh technical output với hậu tố `_preflight.json`. Chỉ sau tất cả gate PASS mới chạy **một invocation**:

```powershell
python -m scripts.demo_ctu_network_public_model_driven --e2e --scenario all --snapshot "$Snapshot" --output "$Out" --budget-usd 0.25 --ledger "$Ledger" --gates "$Gates" --review-mode deferred
```

Model pin `gpt-4.1-mini-2025-04-14`, temperature0, cap1000, retry0, network-only `tool_choice=auto`; tối đa bốn attempts cả window. Application reserve 50000 input +1000 output/request, conditional ceiling $0.0864 tại giá $0.40/$0.10/$1.60 mỗi triệu input/cached/output; không phải invoice/billing hard cap. Payload đầy đủ được kiểm lại trước assessment, quá giới hạn dừng thay vì cắt evidence. Đổi output/checkout/ledger không cấp lượt mới; legacy/diagnostic CLI bị chặn khi canonical window đã claimed/consumed. Không smoke hay retry bổ sung.

Facts/source pairs và aggregate được kiểm độc lập trước human approval. Bounded retrieval và source-reference sampling giữ metadata, không được gọi là full population. Model assessment giữ nguyên; prose causal claims vẫn cần human review. Deferred receipt là `TECHNICAL_COMPLETE / AWAITING_HUMAN`, **không COMPLETE**.

```powershell
python -m scripts.render_network_e2e_report --receipt "$Out" --output ".vinsoc/demo/network-e2e.html"
Start-Process ".vinsoc/demo/network-e2e.html"
python -m scripts.demo_ctu_network_public_model_driven --review-receipt "$Out" --output "results/evaluation_v1/network_e2e_v1/20261006/human_review_receipt.json"
python -m scripts.render_network_e2e_report --receipt "$Out" --review-receipt "results/evaluation_v1/network_e2e_v1/20261006/human_review_receipt.json" --output ".vinsoc/demo/network-e2e-reviewed.html"
```

Các lệnh render/review hoàn toàn offline; review chỉ cho technical receipt hợp lệ của đủ hai scenario, người thật chọn decision/rationale và xem toàn bộ assessment/evidence. Linked review không overwrite technical receipt; HTML reviewed phải khớp hash/run/SHA và hai quyết định với receipt gốc. Không ghi đè review output đã có. Partial/preflight-failed JSON vẫn render được, không nâng thành live success.

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

## 11. Kết thúc sau phần thao tác / Q&A

> “Kết quả dev, prediction lỗi và chi phí đã được giữ trong artifact. Reviewer có thể chấm lại SQL offline và truy vết evidence. Task 2 đã implement và kiểm thử offline, chưa tạo score model mới. Những bước còn lại là khóa release v4, lượt dev có control, demo model-driven đã kiểm factual claims và holdout độc lập được human authorize. Trạng thái hiện tại là DEV_VERIFIED / HOLDOUT_PENDING.”

### Chuẩn bị trước buổi trình diễn

- [ ] Dùng đúng checkout đã có CI xanh; `.env` không mở lên màn hình; không thay key hoặc mua credit.
- [ ] Chuẩn bị artifact/receipts và snapshot gốc; validator/hashes pass, output namespace mới.
- [ ] Chạy rehearsal offline trước buổi trình diễn nếu được giao; giữ receipt và thời gian thực tế, không nhập output mẫu vào slide.
- [ ] Màn hình có nhãn replay/rehearsal/live, nguồn/timeframe và limitations.
- [ ] Phần live chỉ có sau review/cost/identity/CI/attempt gates; không rerun suite hoặc case fail.
- [ ] Nếu một bước fail: giữ artifact, trình bày lỗi và blocker, không đổi dữ liệu/model/gold/scorer để hoàn tất màn hình.

Các checkbox trên dành cho người trình diễn. Việc tạo kịch bản không đánh dấu chúng đã hoàn thành.
