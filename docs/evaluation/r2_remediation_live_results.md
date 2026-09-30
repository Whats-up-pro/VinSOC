# R2 remediation live dev — 2026-09-30

## Kết quả và phạm vi

Đã chạy đúng một E3 smoke `ctu_sql_001`, rồi một suite E3 đủ 8 dev cases S5/S7. Smoke qua gate pipeline dù SQL sai gold. Không commit giữa hai lượt, không retry, không đổi prompt/cap/model để cứu điểm. Tất cả 41 response là live OpenAI calls; tests dùng HTTP giả, còn E0 được đọc từ artifact lịch sử, không gọi lại.

**Suite EX 1/8 (12.5%)**, syntax 4/8, execution success 3/8, safety rejection 1/8. Đây là kết quả public-dev diagnostic của controller đã remediation, không phải holdout hay demo SOC hoàn chỉnh. `official_eligible=true` trong suite chỉ là eligibility theo locked CTU dev contract; không chứng minh generalization hoặc hiệu quả nhân quả của remediation. Smoke luôn `official_eligible=false` và không nằm trong mẫu số suite.

**STOP FOR HUMAN REVIEW.** Frozen S1/S4 vẫn consumed/closed; không chạy E0/E1/E2/E0', R1, frozen hoặc demo mới.

## Checkout, implementation và CI

- Initial SHA `0973d5a6e3a02af40a8a7e31b1bf5f39d487fffe`, master bằng origin/master sau fetch/fast-forward; tracked status rỗng. Untracked ban đầu được giữ, `.env` chỉ được đọc trong memory để resolve key, không sửa/stage.
- Implementation checkpoint `4a84aa634a080b8d07d1c3bd1678e9c476fdebfc` thêm live entrypoint/tests. [CI 36699860358](https://github.com/Whats-up-pro/VinSOC/actions/runs/36699860358) lỗi collection: dependency không khóa đã cài SDK 3.22.1/httpx2, thiếu `httpx` mà transport tests cần. Không gọi API tại SHA này, không skip tests.
- **LIVE_IMPLEMENTATION_SHA `90acf451c264d98c3cc35662670b3b772366136a`** khóa SDK 2.8.1/httpx 0.28.1 đã kiểm chứng, ghi runtime versions. [CI implementation 36700628921](https://github.com/Whats-up-pro/VinSOC/actions/runs/36700628921) xanh đúng SHA: Python 3.11 `704 passed in 37.90s`; Python 3.12 `704 passed, 1609 warnings in 45.63s`.
- Fetch lại trước live: HEAD và origin/master đều bằng implementation SHA, tracked status rỗng. Smoke và suite đều ghi SHA này; execution code không thay đổi sau live.
- Evidence được commit sau cả hai lượt. CI của evidence commit được ghi ở checkpoint phía cuối; không tạo SHA tương lai hay provenance hồi tố.

## Contract và cost gates

Model requested và mọi actual response: **`gpt-5-mini-2025-08-07`**. Chat Completions, reasoning `low`, cap 1000, không key `temperature`, SDK retries 0, service tier `default`. E3 dùng actual `run_case`, recovered `V2DatabaseTools`, fail-closed controller, snapshot-only safety boundary và locked `evaluate_sql_case`; không fake provider/fallback trong live.

Mỗi role tối đa 5 model turns và 5 tool calls; chỉ `database_profiler`, `value_search`, `sql_probe`. Request UTF-8 serialize tối đa 20,000 bytes, cộng reserve 512 framing tokens. Bound dùng input không cached và full output cap cho mọi slot còn lại: $0.007128/call; smoke 10 slots $0.07128; suite 80 slots $0.57024; tổng 90 slots **$0.64152 < $0.75**. Request vượt context bị chặn trước SDK, không tăng cap hoặc sửa prompt.

Giá được đọc lại từ [OpenAI GPT-5 Mini](https://developers.openai.com/api/docs/models/gpt-5-mini.md) lúc `2026-09-30T10:12:42.675299+00:00`: input $0.25, cached input $0.025, output $2/1M tokens; source SHA-256 `3f3228b22ff8f4d6235158bb70ce1206a521724beb2b0dd814f0f38d0d897800`. Trước client creation đã pass snapshot/split/hash, clean SHA/origin, exact-SHA CI, key-source, pricing, account, budget và exclusive-output gates.

Account gate dựa trên xác nhận trực tiếp của owner rằng credit và hard spend limit của đúng project đều đủ $0.75; **không truy vấn Billing độc lập**. Key source `dotenv`, không endpoint override; key không vào request/artifact. Tổng ngân sách được giữ ở $2; owner duyệt allocation live mới $0.75 trong phần còn lại. Historical cost vẫn incomplete, recorded lower bound $0.06508150, không coi là zero và không suy ra remaining total budget từ lower bound.

Cost tính từ usage từng response:

```text
((input_tokens - cached_tokens) * 0.25 + cached_tokens * 0.025 + output_tokens * 2) / 1,000,000
```

Đây là usage-derived cost theo giá đã verify, không phải invoice Billing. Tổng mới **$0.02185315**, mọi response có usage hợp lệ; `cost_complete=true`, `cost_unknown=false`. Recorded historical lower bound cộng live mới là $0.08693465; tổng spend lịch sử thực vẫn chưa xác định đầy đủ.

## Metrics, calls và usage

| Metric | Smoke, riêng khỏi benchmark | Suite E3 dev |
|---|---:|---:|
| Completed cases | 1/1; pipeline PASS | 8/8; complete |
| Execution Accuracy | 0/1; không dùng làm benchmark | **1/8 (12.5%)** |
| Syntax validity | 1/1 | 4/8 |
| Execution success | 1/1 | 3/8 |
| Safety rejection | 0/1 | 1/8 |
| Attempted / response API calls | 5/5 | 36/36 |
| DB tool calls | 3 | 27 |
| Input / cached input tokens | 4,908 / 0 | 30,751 / 4,736 |
| Output tokens, gồm reasoning | 890 | 6,112 |
| Cost USD | 0.00300700 | 0.01884615 |
| Tổng latency API đo được | 14,913.20 ms | 77,932.99 ms |

Tổng live: 41 attempted/41 responses, 30 tool calls, 35,659 input (4,736 cached), 7,002 output, cost $0.02185315. Latency là tổng thời gian API đo được, không phải toàn bộ wall time.

`db_calls` của report đếm actual controller tool invocations: suite gồm profiler 8, value_search 17, sql_probe 2. Profiler/value_search đọc catalog đã có trong memory; không gọi chúng là 27 physical SELECT queries. Hai probes có result `ok=true`; locked evaluator thực thi 3 predicted queries và 3 gold queries thành công. Vì vậy 8 successful SELECT queries trong pha inference/scoring của suite là số **derived từ trace và code path**, loại metadata/preflight/lock-validation; smoke tương ứng 2. Không có instrumentation tổng số mọi DuckDB statement.

## Lỗi từng case — giữ nguyên mọi case trong mẫu số 8

| Case | Syntax / execution / EX | Error | API / tool calls | Cost USD | Quan sát từ artifact |
|---|---|---|---:|---:|---|
| 001 | 1 / 1 / 0 | RESULT_MISMATCH | 5 / 3 | 0.00379580 | Source S5 grounded; generator dùng IN trên danh sách label bị truncate thay vì phủ toàn bộ prefix From-Botnet. |
| 002 | 1 / 1 / 0 | RESULT_MISMATCH | 5 / 3 | 0.00296725 | Source S7 grounded; IN trên label Normal bị truncate không tương đương gold substring. |
| 003 | 0 / 0 / 0 | TURN_LIMIT | 5 / 5 | 0.00157350 | Linker vẫn gọi search sau 5 turns; không có handoff, generator không được gọi. |
| 004 | 1 / 1 / 1 | OK | 5 / 3 | 0.00232425 | Source S5, >= inclusive và < exclusive tại microsecond; locked comparator khớp. |
| 005 | 0 / 0 / 0 | TURN_LIMIT | 5 / 5 | 0.00134210 | Linker tìm value trên numeric bytes_out, hết turns; generator không được gọi. |
| 006 | 0 / 0 / 0 | INVALID_TOOL_PROVENANCE | 3 / 2 | 0.00165525 | Probe trả dst_port/count; submitted source value không được chấp nhận từ observed matches/domains. Guard chặn generator. |
| 007 | 0 / 0 / 0 | INVALID_TOOL_PROVENANCE | 3 / 3 | 0.00285900 | Probe trả protocol/count; grounded values linker nộp không khớp observed set mà gate chấp nhận. Guard chặn generator. |
| 008 | 1 / 0 / 0 | SAFETY_REJECTION | 5 / 3 | 0.00232900 | SQL mở bằng SELECT rồi newline, boundary đã khóa yêu cầu `select `; đồng thời model dùng SUM bytes thay vì flow counts. Không sửa validator/scorer để cứu điểm. |

Các mô tả là phân tích offline trace dev sau lượt live, không chứng minh nguyên nhân nhân quả. Không tiếp tục chỉnh controller/prompt trong task này. Bốn case linker fail không có generator call; usage đã tính phí của mọi turn vẫn nằm trong report/journal.

## Đối chiếu E0 bất biến

[E0 run 36520685612](../../results/evaluation_v1/ctu_network_public/gpt5_e0/36520685612/ctu-r2-result.json) giữ nguyên SHA-256 `33b35678171309c1a8958c1d9818499915986942e6936a03428df8fa0544bc15`, EX 0/8, syntax/execution 8/8. [Compatibility receipt](../../results/evaluation_v1/ctu_network_public/dualsql_v2_remediation_live/20260930_90acf451/e0_compatibility_receipt.json) xác nhận cùng logical snapshot, source hashes, split, case IDs, bốn scorer/builder hashes và model/cap/reasoning/retry/no-temperature contract.

| Điều kiện | EX | Syntax | Execution success | Cost USD |
|---|---:|---:|---:|---:|
| E0 one-shot, immutable | 0/8 | 8/8 | 8/8 | 0.00384725 |
| E3 remediation live dev | 1/8 | 4/8 | 3/8 | 0.01884615 |

Đây chỉ là so sánh mô tả trên cùng dev contract. E3 thay controller, prompt/schema/tool context, call budget, context guard và explicit service tier; SDK/runtime cũ chưa được attested. Không gán SHA/SDK hiện tại vào E0. Không dùng public-dev 5/8 trên snapshot khác hoặc S1/S4 historical 2/8 làm đối chứng. Không claim token saving hoặc causal accuracy improvement.

## Verification thực tế và review

| Lệnh / gate | Kết quả |
|---|---|
| `python -m pytest tests/test_r2_v2_dev_live.py -q` | RED 17 errors vì chưa có module; GREEN 23 passed in 7.18s sau fixes |
| Targeted live + historical + report + scorer tests | 49 passed in 12.13s |
| `python -m pytest -q` trên implementation cuối | 704 passed, 1612 warnings in 194.48s |
| `python -m py_compile scripts/run_r2_v2_dev_live.py tests/test_r2_v2_dev_live.py` | exit 0 |
| `python -m compileall -q evaluation/dualsql_lite_ctu_gpt5_v2` | exit 0 |
| `git diff --check`, staged diff check | exit 0 trước implementation commit |
| Verified S5/S7 contract | Đúng 8 locked IDs, source/snapshot/gold/scorer locks pass; không download/rebuild |
| Live `--preflight-only` | PASS trước client creation |
| Audit JSON/usage/identity sau live | PASS; không model/API hoặc DB query trong auditor |
| Historical inventory | 45 files trước/sau cùng byte hashes |

Targeted command:

```powershell
python -m pytest tests/test_r2_v2_dev_live.py tests/test_r2_historical_entrypoints.py tests/test_r2_v2_report_contract.py tests/test_r2_v2_scoring_contract.py -q
```

Lệnh live duy nhất, không chạy lại:

```powershell
python -m scripts.run_r2_v2_dev_live --mode smoke-and-suite --output-root results/evaluation_v1/ctu_network_public/dualsql_v2_remediation_live/20260930_90acf451
```

Fresh reviewer tìm 3 Important, không Critical/Minor: journal sync có thể làm thiếu charged cost; tool infrastructure failure có thể cho thêm API calls; synthetic smoke có thể mở production suite. Ba regression tests RED 3 failed/20 passed → GREEN 23 passed. Đã sửa trước live, full/CI sau fix xanh. Không re-review hoặc sửa execution code sau live.

### Rulings đã chốt

- Dùng context bound 20,000 bytes + framing reserve 512, giữ cap/turns/prompt; vượt bound dừng. Rủi ro nếu không phù hợp: partial/negative result, không retry.
- Account theo owner confirmation, không độc lập Billing; history cost chưa đầy đủ. Rủi ro nếu xác nhận sai: paid attempt fail rồi dừng, không tự mua credit.
- Tool execution exception bị legacy boundary gom chung: live gate dừng `TOOL_EXECUTION_UNCLASSIFIED`, không đoán lỗi model hay hạ tầng. Rủi ro: có thể dừng suite ở SQL probe error của model; báo partial, không loại case.
- SDK/transport khóa đúng phiên bản đã test để xử lý CI regression, không đổi model. Rủi ro: maintenance dependency cần task sau.
- Scoped `.gitattributes -text` cho artifact live mới giữ bytes qua Git, không đổi lịch sử hoặc execution code. Rủi ro: readers cần giữ đúng bytes khi verify checksum.
- Reviewer không thể xác minh account, giá, CI, actual provider và future evidence; parent đã tự kiểm gates/response/artifact, không suy chúng từ review verdict. True historical cost/provenance chưa có và frozen vẫn closed; không claim đủ holdout evidence.

Deferred minors: không có.

## Artifact và hashes

Artifact ID trong repository: **`20260930_90acf451`**; đây là local live run, không có GitHub model-workflow artifact ID hoặc model dispatch URL.

- [Smoke report](../../results/evaluation_v1/ctu_network_public/dualsql_v2_remediation_live/20260930_90acf451/smoke/report.json), SHA-256 `8c3c6c87f62631b9beff870a2dc6579434fcf45c9ef921d50633e946c893c6e1`.
- [Suite report](../../results/evaluation_v1/ctu_network_public/dualsql_v2_remediation_live/20260930_90acf451/suite/report.json), SHA-256 `1bdc6a20c4c402445719642c17d3d9f8cd3bc85e4d6fa40b5ba32c67f5023c25`.
- [Suite partial journal](../../results/evaluation_v1/ctu_network_public/dualsql_v2_remediation_live/20260930_90acf451/suite/partial.jsonl): serialized requests, raw SDK responses, actual model/IDs/usage, tool calls/results/evidence IDs, controller telemetry, final SQL và score flags. Per-case JSON nằm cùng folder.
- [Acceptance receipt](../../results/evaluation_v1/ctu_network_public/dualsql_v2_remediation_live/20260930_90acf451/acceptance_receipt.json) và [historical inventory](../../results/evaluation_v1/ctu_network_public/dualsql_v2_remediation_live/20260930_90acf451/historical_inventory_receipt.json).
- [Artifact digests](../../results/evaluation_v1/ctu_network_public/dualsql_v2_remediation_live/20260930_90acf451/ARTIFACT_DIGESTS.json), SHA-256 `c09e11bb311d216ad917940ae2420d71c5d1694d0aa73a67f30e0d2f41ba299c`; 19 file digests, manifest tự loại khỏi inventory. Claims/receipt trong sibling `r2_remediation_live_e3_v1/` chặn lượt thứ hai.
- Snapshot binary SHA-256 `0b29765b9a175d00e0a193039a1b058691406e28a434e10030ae78265cfa67b9`, logical SHA `42c8e0a62441295cc5d95329a65dc22409c37de5b26a1e37dd56fbf0164a758c`, trước/sau không đổi.
- S5 source SHA `ef5c9ed6895d4ca5aec723449dae30054ccd1f6b091713a52ffcb681ff78a02c`; S7 `df0b5338190b967bd340a0d6c1bb3c34d1bbfb4b7ffa764c2dd26f77f1a26680`.
- v1 selection lock giữ SHA `8be5cc4d9b677c794e6987b965a31dd77e61747b0bbcb4be0a93172014f90b00`; 45 historical file hashes cùng trước/sau, bao gồm E0/v1/frozen/receipts cũ.

## Files và recovery

Giữ toàn bộ recovery/source adapter, frozen pre-client guards, consumed lock, prompts, benchmarks/gold, comparator/core scorer, snapshot và historical artifacts. Sửa thêm live entrypoint/tests, dependency pins; cập nhật plan/status/README từ evidence; thêm scoped `.gitattributes` và namespace artifacts/receipts mới. Không stage `.env`, credential, raw dataset hay untracked user files. Verification ledger/logs local được giữ, không stage, theo yêu cầu không xóa untracked.

Không còn blocker đối với việc ghi nhận lượt live đã hoàn tất. Kết quả 1/8 là kết quả âm về chất lượng dev, không mở frozen hoặc cho phép tuning/rerun trong task này.

## Evidence checkpoint đã xác minh

Evidence commit **`82598875d2b415508a69fa86e8290a5656702444`** đã push master. [CI evidence 36703577420](https://github.com/Whats-up-pro/VinSOC/actions/runs/36703577420) success trên đúng SHA, Python 3.11 `704 passed in 40.10s`, Python 3.12 `704 passed, 1609 warnings in 38.92s`. Trước commit: staged 26 allowed paths; 20 artifact hashes bằng cả checkout và Git blob; credential scan, compile và staged diff check pass; 45 historical hashes không đổi.

Checkbox Task 10 được chốt sau khi đọc kết quả CI này. Commit tài liệu closure kế tiếp chỉ ghi verification đã xảy ra; SHA và CI của chính closure commit được xác nhận trong thông báo cuối. Không sửa execution code hoặc artifact sau live. **STOP FOR HUMAN REVIEW**, không thí nghiệm/E2E mới.
