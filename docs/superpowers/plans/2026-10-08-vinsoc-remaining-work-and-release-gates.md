# VinSOC — Kế hoạch phần việc còn lại và gate nghiệm thu

> **Dành cho người thực hiện:** Dùng `superpowers:executing-plans`, thực hiện theo các checkbox và gate dưới đây. Một người ghi trên `master`; không branch/PR, không tự giao thêm agent. Đây là kế hoạch tiếp tục, chưa cấp quyền gọi API. Kế hoạch gốc và chỉ thị người dùng vẫn là nguồn yêu cầu; bản này đối chiếu tiến độ để không làm lại phần đã đạt.

**Mục tiêu:** Trước 16/10/2026, có phép đo Text-to-SQL nhiều schema/lĩnh vực, nghiệm thu chính runtime đó qua public orchestrator và demo/báo cáo từ kết quả thật; bàn giao đầy đủ trạng thái chưa đạt nếu gate hoặc lượt chạy bị lỗi.

**Kiến trúc:** Giữ `TextToSQLService` và `SqlExecutor` dùng chung; benchmark giữ gold ở evaluator, `network_query` chỉ nhận câu hỏi và CTU scope do ứng dụng cấp. Mọi routing/R2/assessment dùng cùng journal; kết quả vào EvidenceStore, kiểm facts/provenance và người thật duyệt. Báo cáo/HTML đọc artifacts, không tạo model output mới.

**Công nghệ:** Python 3.11/3.12, DuckDB 1.5.5, SQLGlot 30.21.0, SDK và dependencies đã pin, Linux/bubblewrap, pytest, GitHub Actions, HTML offline.

**Spec:** Đọc toàn bộ `docs/superpowers/plans/2026-10-08-vinsoc-text2sql-integration-and-final-demo.md`, nhất là mục 1, 3–7, T0–T11 và D1–D10. Đối chiếu thêm acceptance matrix 06/10, execution cursor 07/10, handoff/receipts và trạng thái triển khai 08/10. Không thay các yêu cầu đó bằng bản rút gọn này.

**Mốc kiểm tra:** Ngày 08/10/2026, `HEAD = origin/master = 791184cbc0346c3c6331dab63b603facfeb4005a`; tracked tree sạch. [CI 37727034514](https://github.com/Whats-up-pro/VinSOC/actions/runs/37727034514) completed/success; logs của `test (3.11)` và `test (3.12)` đều 1.150 passed, 2 skipped. CI này kiểm mã, chưa khôi phục DB thật cho nghiệm thu mới. Khi bắt đầu thực hiện phải kiểm HEAD mới; đây không phải quyền dùng CI cũ cho SHA mới.

## 1. Quy tắc giữ nguyên

- Không mock trong nghiệm thu/demo; không fake SDK mới, DB giả, SQL viết sẵn thay SQL model, nhận định của script hoặc agent tự duyệt. Tests tổng hợp lịch sử giữ nguyên và ghi rõ phạm vi hồi quy.
- Không sửa benchmark/gold/comparator/scorer/prompts/locks/kết quả lịch sử; không chạy lại R1 22/24 hoặc audit R2 7/8 để tăng điểm. Không mở frozen, S1/S4, ThreatFox/OTRF bằng kế hoạch này.
- Không rebuild DB để giả làm exact binary đã khóa. DB dựng lại cùng nội dung chỉ là audit nguồn, không tự mở gate nghiệm thu.
- Không retry, đổi model/key/cap, fallback hoặc đổi window/output/clone để cứu lượt chạy. Calibration, evaluation và pipeline có scope riêng; không tạo scope mới cho cùng công việc đã consumed.
- Paid chỉ sau data/worker/code/CI/account/pricing/budget/ledger PASS. Quyền E2E network cũ tối đa bốn requests, 0,25 USD không cấp tiền cho phần mới.
- Không commit/in/copy `.env`, API key, fingerprint, private gates/ledger hoặc raw SDK journal vào Git public. Không force push/reset/clean; stage explicit allowlist.
- Mỗi mốc hoàn tất: commit/push, CI đúng SHA trên cả 3.11/3.12, receipt lệnh/exit/status/hash. Không đánh dấu đạt cho lệnh chưa chạy hoặc test bị skip.
- Mẫu số cố định: calibration 24×2; evaluation 96×2 gồm external64/CTU32, 93 families; pipeline 32. Bốn demo IDs đã chọn giữ nguyên kể cả khi lỗi.
- Người duyệt không nâng lỗi kỹ thuật/EX sai thành workflow success. `awaiting_human`, rejected, escalated, partial và unknown giữ nguyên nghĩa.

## 2. Đối chiếu acceptance matrix và execution cursor

| Hạng mục | Trạng thái tại mốc kiểm | Giữ / việc còn lại |
|---|---|---|
| R1 dev | VERIFIED_EXISTING: 22/24, exact-call F1 0,9508, no-tool 5/5 | Giữ winner/artifacts; báo caveat 11/24 gold adjudicated sau output, frozen pending |
| R2 lịch sử | VERIFIED_EXISTING theo từng contract: 5/8 cũ; CTU GPT-5 E0 0/8; Phase-2 E3 7/8 | Không ghép điểm hoặc chạy lại case006; audit offline 7/8 đã có |
| A1 network E2E | Mã/renderer/ledger/lock đã có; chưa là live success | Không viết lại; kiểm residual regression nếu tái hiện |
| A2/A3 network cũ / T1 | BLOCKED tại đây; canonical laptop state chưa biết | Đọc ledger/receipt thật; không suy ra unused. Có thêm content-lock mismatch ở HEAD hiện tại |
| T0 preservation/setup | Đã có receipts/hashes; phần canonical state còn thiếu | Kiểm lại identity ở HEAD tiếp tục, không dựng lại toàn bộ lịch sử |
| T2 nguồn và 120 gold | Nguồn thật đã pin; 120 gold PASS về nội dung trên bản dựng riêng | Không làm lại source acquisition/selection; cần 13 exact binaries, validator và CI restore thật |
| T3–T5 | Shared service/executor/skill/public API/accounting đã có mã | Cần kiểm positive path bằng worker/DB thật; chưa gọi là nghiệm thu tích hợp |
| T6 | Runner/scorer/coverage report đã có một phần | Thiếu chuẩn hóa records cho module/statistics, metrics pipeline, selection binding đủ mạnh, real-data CI |
| T7 | Có dự toán, `bound_verified_for_transmission=false`, account/prior unknown | Chưa có paid authorization; phải chốt cận thực và đối soát từ evidence |
| T8/T9 | NOT_RUN: chưa có calibration/evaluation/pipeline mới hợp lệ | Chỉ chạy sau release đủ gate; không biến gold replay thành model score |
| T10 | Renderer sơ bộ đọc receipt; chưa có demo/report cuối | Hoàn thiện trước freeze; điền bằng artifacts thật sau run |
| T11 | Matched tám câu cũ và independent holdout deferred | Giữ riêng; đánh giá 96 và pipeline 32 không hoàn tất protocol cũ/holdout |

Nguồn kiểm: `docs/evaluation/VinSOC_Text2SQL_Implementation_Status_2026-10-08.md`, `results/evaluation_v1/text2sql_integration_v1/{validation_receipt,worker_probe,preflight_calibration,preflight_pipeline,cost_bound,demo_selection,dependency_audit,preservation_receipt}.json`; closeout tại `results/evaluation_v1/cross_domain_closeout/20261007/`.

**Blocker mới xác minh:** `NETWORK_E2E_v1.lock.json.content_files['agent/orchestrator.py']` pin `6c815cbd55fbb6704decc0beb08a6bf1dab7db32f803f49132cfb33cb92e9a94`; portable hash hiện tại là `c75a36756d8f8e6018edbdc38d7dd8f33f5fd3e64aed2a70cfd937b6084ff4d7`. Không overwrite khóa hoặc gắn HEAD mới vào receipt cũ. T1 phải được ghi BLOCKED_CONTENT_IDENTITY nếu chưa có phương án resume phù hợp contract. Blocker này không cấm T2–T6 offline hoặc thay thế quyền riêng của pipeline mới.

**Giới hạn kiểm tra trong lượt lập kế hoạch:** Không chạy lại full suite/model. `python3 -m cli.main query --help` chưa chạy được ở Python mặc định do thiếu `dotenv`; `.venv/bin/python` hiện không dùng được. Kết luận CI lấy từ jobs/logs GitHub thực, không giả local PASS. R0 phải khôi phục môi trường dependencies đã pin, không tự nâng phiên bản.

## 3. Thứ tự và các việc có thể làm ngay

Chuỗi gate bắt buộc: **R0 xác minh trạng thái → R1 exact DB → R2 worker/real-DB checks → R3/R4/R5 hoàn thiện mã, báo cáo và CI → R6 release/budget → R7 calibration → khóa lựa chọn/CI → evaluation → R8 pipeline/human → R9 bàn giao**.

Một người thực hiện có thể làm R3/R4/R5 offline trong lúc chờ operator chuyển DB ở R1. Chưa có DB thì không đánh dấu positive real-data tests đạt. R6 có thể chuẩn bị mẫu đối soát và dự toán, nhưng xác nhận freshness/remaining/phạm vi phải làm sát lượt chạy. Không treo mọi công việc vì laptop chưa xuất ZIP.

### R0 — Khóa điểm tiếp tục và đọc canonical state (T0/T1)

**Owner:** người thực hiện kiểm repo; operator đọc private ledger trên máy giữ trạng thái authoritative. **Đầu ra:** `results/evaluation_v1/text2sql_integration_v1/resume_20261008/setup_and_gate_receipt.json`.

- [ ] Fetch `origin/master`, ghi HEAD/remote/status; chỉ fast-forward khi không mất changes. Khôi phục Python environment từ pins hiện có; ghi phiên bản thực.
- [ ] Đối chiếu protected hashes và receipts đã có; không đọc frozen gold để phân tích. Đánh dấu phần VERIFIED_EXISTING ở bảng trên.
- [ ] Operator kiểm canonical `network-finalization-20261006` và ba scope mới. Nếu có claim/attempt/receipt thì giữ nguyên, không tạo ledger rỗng; export chỉ public-safe state/cost/reference, không key.
- [ ] Ghi riêng network v1 DB thiếu và content mismatch. Nếu window đã dùng, chỉ render/review output thật đã có. Nếu chưa xác định hoặc mismatch chưa giải quyết, giữ T1 blocked/deferred; không dispatch paid trên HEAD hiện tại.
- [ ] Commit receipt/docs explicit; kiểm CI evidence SHA. Không chạy lại rehearsal synthetic cũ để gọi nghiệm thu mới đạt.

**Gate:** Repo/identity rõ; mỗi scope có trạng thái authoritative hoặc blocker cụ thể. R1 và các việc offline độc lập được tiếp tục dù private state chưa cung cấp.

### R1 — Chuyển 13 exact DB và đóng gate dữ liệu (T2)

**Owner:** operator/máy giữ DB gốc xuất bytes; người thực hiện xác minh và khôi phục. **Files:** registry/source/benchmark locks chỉ đọc; DB/sources ở ignored paths; receipt mới `real_data_validation.json`, `bundle_restore_receipt.json`.

- [ ] Trên máy giữ DB gốc chạy `export_vinsoc_db_bundle.py --repo <repo-goc> --check-only`, rồi đóng gói. Script đã giao kiểm đủ 13 hash và không lấy secrets; ZIP này chỉ chứa DB/manifest, không tự chứa toàn bộ Spider archive/sources cần validator.
- [ ] Chuyển ZIP bằng attachment hoặc URL/artifact đọc được; xác minh zip SHA, mỗi entry/path/hash, không path traversal/symlink, không overwrite file khác hash. Giữ nguyên relative paths của `runtime_registry.json`.
- [ ] Tách 13-DB runtime bundle với `VinSOC_Qualified_Network_Snapshot_20261007.zip` của network v1. Cross-domain CTU hash `0b29765b...`; network v1 CTU hash `91a13ab1...`; logical giống không cho phép tráo binary.
- [ ] Bổ sung từ archive đã tải các members `spider_data/dev.json`, `spider_data/tables.json` và 12 SQLite DB; kiểm archive/member hashes. Không tải lại nguồn đã đúng hash. Giữ hai CTU raw sources/attribution và kiểm manifest đúng protocol.
- [ ] Chạy validator bên dưới, yêu cầu exit 0/đủ 24+96 và base gold parity. Sau đó chạy `query_runtime_validation.validate_data()` qua R2 khi worker đã sẵn sàng; nó là gate runtime mới, không chỉ validator lịch sử.
- [ ] Ghi thiếu đúng database_id/path/expected/actual hash nếu thất bại. Không chỉnh registry/locks để hợp thức bản dựng riêng. Nếu không còn exact binaries, record UNRECOVERABLE_EXACT_BINARY; protocol thay thế là quyết định riêng trước output, không tự mở trong kế hoạch này.
- [ ] Pin vị trí artifact, identity/digest và retention ít nhất qua bàn giao/tái lập; chỉ receipt/manifest vào Git, không DB binary.

```bash
python -m scripts.validate_r2_cross_domain --registry evaluation/r2_cross_domain_v1/runtime_registry.json --benchmarks evaluation/r2_cross_domain_v1/benchmarks --lock evaluation/r2_cross_domain_v1/benchmark.lock.json --output .vinsoc/final-report/data-validation.json
```

**Gate / D2:** Exact binaries + source checks + schema/PK/FK/catalog/parity thực đạt. Chuyển ZIP trên laptop là bước xuất dữ liệu; không bắt buộc chạy SQL model trên Windows.

### R2 — Chứng minh worker và positive path bằng dữ liệu thật (T3/T4/T5)

**Files giữ:** `vinsoc_text2sql/{service,executor,_worker}.py`, `skills/network_query_skill.py`, `agent/network_query_policy.py`; sửa chỉ khi tái hiện lỗi. **Tests bổ sung:** `tests/test_query_real_data.py`; receipt `real_worker_validation.json`.

**Interface:** Dùng `SqlExecutor.query(context, sql, parameters=(), *, row_cap, timeout_seconds) -> dict` và receipt/schema đã có. Không thêm một executor mặc định cùng process.

- [ ] Chọn Linux host cho bubblewrap/user/network namespaces; Windows laptop chỉ xuất DB, hoặc dùng Linux/WSL2 được kiểm thực tế. Cài đúng dependencies/bwrap và chẩn đoán `WORKER_ISOLATION_OR_STARTUP_FAILED` bằng log riêng an toàn; chưa suy ra mọi lỗi đó đều do namespaces.
- [ ] Viết kiểm tra `test_saved_live_sql_runs_in_isolated_worker_on_locked_db`: lấy SQL nguyên văn từ saved live report Phase-2, dùng DB đúng khóa, assert typed result/hash/parity, snapshot bytes trước/sau không đổi. Thiếu DB/backend thì fail REAL_DATA_REQUIRED/WORKER gate, không skip để nghiệm thu.
- [ ] Viết kiểm tra `test_worker_observed_boundaries`: xác minh thực network namespace, env không secrets, mount chỉ đọc/snapshot cần thiết, memory/CPU/time bounds. Không lấy chính fields `isolation` do executor ghi để tự chứng minh. Nếu giới hạn hiện tại chưa đáp ứng tổng memory 512 MiB, bổ sung cơ chế group/container limit và khóa identity mới trước paid.
- [ ] Kiểm CTU row/aggregate/empty/null/decimal/Boolean/source-pair/truncation trên DB thật; dùng saved SQL để replay offline và trusted diagnostic SQL được ghi rõ, không tạo prediction/assessment mới. Không invent row IDs cho COUNT/GROUP.
- [ ] Kiểm syntax/safety/caps: AST reject trước worker, DB-tool 12 calls/2s/20 rows/8.192 bytes; final 10s/10.000 rows, fetch+1 phát hiện cắt; quá assessment payload bound là lỗi giữ lại.
- [ ] Chạy `python -m pytest -q tests/test_query_real_data.py tests/test_text2sql_shared_service.py tests/test_network_query_skill.py tests/test_network_query_policy.py`; chạy `validate_data()` đủ 120 trusted gold qua cùng worker trước SDK.
- [ ] Nếu cần sửa, RED đúng lỗi → sửa nhỏ → GREEN real DB → preservation/compile/diff → commit/push/CI. Chưa có authentic native query conversation thì public lifecycle live vẫn pending R8.

**Gate / D1,D2:** Có receipt positive worker/DB/source/lineage thật; benchmark và production vẫn cùng service/executor. Startup/hạ tầng fail không bị chấm thành model accuracy 0.

### R3 — Hoàn thiện runner, identity và accounting trước calibration (T5/T6)

**Files:** `scripts/run_vinsoc_query_acceptance.py`, `vinsoc_text2sql/accounting.py`, `evaluation/finalization/{query_pipeline_contract,query_runtime_validation}.py`; tests mới `tests/test_query_acceptance_preflight.py`, `tests/test_query_selection_lock.py`, `tests/test_query_journal_persistence.py`.

**Interfaces:** Giữ `run_preflight(scope, condition, private) -> dict`, `run_live(release, output) -> dict`, `RunJournal`/scoped clients. Thêm helper thuần offline `verify_selection_lock(path: Path, *, identities: dict) -> dict` trong `query_runtime_validation.py`.

- [ ] Chặn selection thiếu/sai/hash mismatch **ngay preflight trước SDK/claim**, không đợi nhánh live. Hiện runner chỉ kiểm vài fields ở `run_live`; chưa xác minh selection producer/records/digest đầy đủ.
- [ ] Selection lock phải tham chiếu đủ 48 calibration records, scoring/usage completeness, artifact hashes, implementation SHA, data/runtime/scorer/benchmark identities, quy tắc EX→cost→calls→latency→E0 và lựa chọn được recompute. Không chỉ tin `calibration_complete=true`.
- [ ] Reserve cả suite/case/request; chứng minh capacity mọi role trước routing. Gắn case_id/condition/role/request/response IDs vào events để tách cost theo case/role; counters toàn run không dùng như counts từng case.
- [ ] Lưu response/usage đã nhận bền vững trước parse/validate, kể cả usage/model/finish lỗi. Hiện `record_response()` giữ full response sau kiểm usage/model; phải kiểm và đóng khoảng hở mất response khi lỗi/crash. Unknown exposure/charged failures giữ riêng; không tự ghi 0.
- [ ] Lưu partial case checkpoint và report trong mọi nhánh lỗi/terminal; dựng metrics offline cho records đã có, không chỉ cuối full-run. SDK close thất bại không được làm mất receipt hoặc báo completed sai.
- [ ] Kiểm claim liên process/crash, consumed scope không mở lại bằng output/clone/migration; dữ liệu private mới không được tự ghi owner_verified để pass. Tests pure boundary dùng metadata/receipts thật hoặc kiểm input bị từ chối, không fake transport/paid authorization.
- [ ] Rà source-hash closure gồm dependencies public lifecycle/policy/evidence/safety/prompt/DTO, schema/scorer/benchmarks và execution limits. Source/data mutation phải fail trước client. Mọi sửa semantics nằm trước freeze/calibration.
- [ ] Viết/chạy RED guards cho missing selection, altered calibration artifact, unknown cost/terminal/crash/mutation; GREEN deterministic; commit/push/exact-SHA CI. Output mới chứng minh attempts=responses=0/client=false khi bất kỳ gate thiếu.

**Gate / D1,D3,D10:** Release thực có binding kiểm lại được; mọi lớp charge cùng journal; partial giữ đủ evidence. Không mở paid khi preflight còn dựa cờ tự khai.

### R4 — Đóng khoảng hở báo cáo/phép đo trước chạy (T6/T10)

**Files:** tạo `evaluation/finalization/query_record_normalization.py`, `query_pipeline_reporting.py`; mở rộng `query_reporting.py`; dùng lại `evaluation/r2_cross_domain_v1/{reporting,statistics,module_metrics}.py` chỉ đọc. Runner gọi adapters mới; tests `tests/test_query_reporting.py`, `tests/test_query_pipeline_reporting.py`.

**Interfaces:** `normalize_query_records(records: list[dict], inventory: list[dict], *, identities: dict, journal: dict) -> list[dict]`; `build_pipeline_report(records: list[dict], inventory: list[dict], *, reviews: list[dict], identities: dict, journal: dict) -> dict`.

- [ ] Chuẩn hóa score hiện đang nested trong `record['score']` thành records mà reporting/statistics cũ tiêu thụ; metadata từ inventory gồm DB/domain/family/difficulty/features, planned count. Gắn snapshot/scorer/benchmark/runtime identity và usage/provenance validity từ checks thật, không auto-set true.
- [ ] Nối `build_evaluation_report()` và `summarize_statistics(seed=20261007, bootstrap_replicates=10000)`; báo external64/CTU32/tổng96, macro DB/domain, difficulty 24/48/24, SQL features, schema/value metrics, calls/DB calls/tokens/latency/known/unknown cost.
- [ ] Pair theo cùng 96 IDs/identities; win/loss/tie/delta và cluster database/family. Thiếu telemetry/identity/record thì paired incomplete/interval NA, không bỏ fail để tăng EX. E0 linker/grounding NA, không ghi 0 vì stage không tồn tại.
- [ ] Báo partial planned/completed/scored/paired và đúng kết quả đã có; không suy đoán score của missing cases. Synthetic semantic fixtures chỉ phụ lục kiểm scorer; không official Spider/test-suite score.
- [ ] Pipeline report có đủ routing/shared-runtime coverage/integrated EX/provenance/facts/technical workflow/human coverage/approved completion/role overhead, tất cả denominator 32. EX chấm riêng SQL do pipeline sinh; không copy EX của R2 run.
- [ ] Join review bằng case receipt hash + decision thật; pending không approved. Technical workflow success là conjunction gồm integrated EX; policy facts pass không thay semantic correctness. Approved trên SQL sai không thành completion.
- [ ] Kiểm schema thực và chấm archived live artifacts offline trên DB thật; giữ source artifacts nguyên bytes. Không tạo 192/32 synthetic predictions để pass report. Tests missing/partial dùng inventory thật, positive aggregation dùng outputs thật khi có; tests cần outputs mới còn pending tới R7/R8.
- [ ] Chạy targeted tests/scorer replay thật; commit/push/CI. Ghi riêng phần chưa positive-tested, không gọi report hoàn tất chỉ vì các null cases pass.

**Gate / D4,D5,D10:** Các adapters/report schema sẵn sàng trước freeze; báo cáo positive cuối cùng chỉ có sau R7/R8.

### R5 — Khôi phục DB thật trong CI; hoàn thiện đường demo trước freeze (T5/T6/T10)

**Files:** `.github/workflows/ci.yml`, tạo `scripts/restore_query_data_bundle.py`, `tests/test_query_bundle_restore.py`; `cli/main.py`, `scripts/render_query_pipeline_report.py`, `scripts/review_vinsoc_query_case.py`; docs/runbook mới.

**Interfaces:** `restore_bundle(bundle: Path, *, expected_sha256: str, destination: Path) -> dict` chỉ restore allowlist/hash và không overwrite khác hash. `render_report(source, output, *, review_paths=(), demo_selection=None) -> dict` giữ tương thích positional API hiện có.

- [ ] CI tải bundle exact DB/artifact đã pin và source archive/members đã pin; `contents:read/actions:read` tối thiểu theo nơi lưu. Kiểm archive digest/path map/member hash trước đặt runtime paths; không tải DB không pin/rebuild thay binary. Giữ sources/binaries ngoài Git.
- [ ] Run 120-data validation/worker tests trên cả 3.11/3.12, không API key ở jobs dữ liệu/worker. Thiếu artifact/backend thì fail required gate, không skip. Việc availability job hiện có thấy key không chứng minh paid được phép.
- [ ] Full suite + required real-data checks/compile/diff/preservation; ghi jobs/logs/artifact IDs/digest đúng implementation SHA. CI green với hai skips hiện tại không đóng gate này.
- [ ] CLI hiện chỉ nhận inventory batch, chưa có đầu vào câu hỏi tự nhập. Bổ sung `query --case-id <locked-id> --question <exact-original-question>` ở chế độ chọn/xem câu cho lượt pipeline đã cấp, không tạo lượt paid ngoài scope hoặc retry riêng case. Transcript chứng minh câu hỏi do người nhập khớp inventory, route qua public API khi batch thực hiện.
- [ ] Demo mặc định là viewer của bốn receipts đã chọn; không nút gọi API lại. Nếu cần arbitrary-question product/live demo, thiết kế scope/ledger/budget riêng trước run; không suy ra quyền từ bộ 32. Ghi đây là scope mở rộng, không tự chạy.
- [ ] Review UI hiện in assessment/evidence; bổ sung hiển thị rõ question, native call, SQL, typed result, technical checks, EX nếu có và limitations. Người thật nhập identity/decision/rationale/UTC; không auto-input/approve. Base receipt bất biến.
- [ ] HTML hiện là JSON trong details; bổ sung bảng toàn 32 IDs/status/coverage và bốn demo IDs cố định, trace đủ từng stage, review join có hash, costs unknown và lỗi hiện rõ, escape nội dung. Thiếu case hiện missing, không dựng trace để lấp.
- [ ] Viết tests offline từ inventory/selection/artifacts thật cho escaping, missing/partial/duplicate, review hash sai và status không nâng. Full positive trace/JSON–HTML equality là gate hậu R8; không fake một trace đẹp để gọi pass.
- [ ] Commit/push/CI, rồi freeze toàn runtime/source hash set. CLI/renderer cũng nằm trong hash set hiện hành nên hoàn thiện trước calibration; không đổi sau output rồi giữ identity cũ.

**Gate / D1,D7,D9:** Môi trường thực chạy được; CLI/demo đường dùng rõ ràng; exact-SHA real-data CI PASS, không API calls.

### R6 — Chốt release và tiền từng scope (T7)

**Owner:** người thực hiện tính/kiểm; owner tài khoản xác nhận allocation/phạm vi từ evidence thật. **Files:** private release/gates/journal ngoài repo; public-safe `preflight_*.json`, `public_cost_bound.json` mới, append-only.

- [ ] Chốt implementation SHA/schema/runtime/executor/source/split/scorer/caps; exact clean master = remote, CI SHA khớp, data/worker PASS. Không sửa `benchmark.lock.json.paid_authorized=false` lịch sử.
- [ ] Kiểm framing/token bound thật cho toàn serialized payload/history/schema/results; reserve uncached. Không chỉ đổi `input_bound_verified=true`; giữ evidence phương pháp và giới hạn đã kiểm.
- [ ] Reconcile prior cost/account allocation/remaining/unknown exposure trên tất cả scopes cùng allocation; migration laptop/cloud giữ authoritative consumed state và chặn host cũ.
- [ ] Kiểm giá chính thức và account confirmation tối đa 6 giờ tuổi sát run, refresh ở mỗi scope dài/ngày khác. Không dựa chi phí 8 cases hoặc credit lịch sử.
- [ ] Trình gói ngân sách cụ thể: calibration tối đa 168 GPT-5-mini requests; evaluation 672; pipeline E0 32 R2+64 outer, hoặc E3 192 R2+64 outer. Tổng mới tối đa 936 hoặc 1.096 requests; bốn câu viewer 0 requests mới.
- [ ] Dự toán lưu ngày 08/10: 1,73376 + 6,93504 + pipeline 1,7040384/3,3552384 USD, tổng 10,3728384/12,0240384 USD. **Chỉ là planning bound cũ, chưa xác minh transmission, chưa cộng prior unknown, không là tiền được cấp hoặc giá xác nhận lúc chạy.** Tính lại từ gate evidence hiện hành.
- [ ] Owner quyết định ngân sách/phạm vi mới trước transmission; thiếu quyết định thì BLOCKED_PAID_AUTHORIZATION. Không hỏi lại quyền network cũ và không mượn budget đó.
- [ ] Preflight mỗi scope phải exit 0/status preflight_pass, 0 attempts/responses/client=false, selection binding đầy đủ khi cần. Thiếu bất kỳ gate: lưu public-safe blocker, không tạo SDK/claim/call thử.

**Gate / D10:** Full-suite reserve trong allocation thực, không unknown chưa đối soát; có authorization riêng phù hợp scope. Thiếu tiền/nguồn/worker trước 11/10 phải báo nguy cơ trễ, vẫn tiếp tục phần offline.

### R7 — Calibration, chốt lựa chọn, đánh giá 96 (T8)

**Files output:** `results/evaluation_v1/text2sql_integration_v1/calibration/<run-id>/`, `evaluation/<run-id>/`; raw SDK/ledger private. Dùng runner đã freeze, không viết runtime mới.

- [ ] Một calibration invocation E0 rồi E3 trên đủ 24 IDs; giữ 48 records hoặc partial thật, tối đa 168 requests. Không tuning prompt sau output.
- [ ] Chấm bằng scorer riêng, kiểm identity/usage/completeness. Chỉ chọn khi 48 records hợp lệ; tie-break đã pin. Chốt selection lock tham chiếu artifacts/producer SHA/runtime/data/scorer và commit/push/CI selection SHA, không đổi semantic source bytes.
- [ ] Gate evaluation mới xác minh selection/hash/CI/account/pricing/budget. Một invocation đủ 96 IDs E0 rồi E3, 192 records hoặc partial thật, tối đa 672 requests. Không sửa/commit code giữa conditions.
- [ ] Model sai/syntax/TOOL_LIMIT/no-final-SQL giữ trong denominator hợp lệ; infrastructure/provider/identity/unknown-cost chặn paid tiếp và ghi incomplete theo contract. Không ghép retry vào run.
- [ ] Xuất module/statistics/error/cost report R4 từ saved records; đối chiếu journal events và record/score/result hashes. Chưa đủ records thì không công bố full EX/paired result.
- [ ] Sanitize public exports, manifest artifacts và commit/push/CI evidence SHA. Producer/selection/evidence SHA phân biệt; không hash future commit hoặc chính lock gây vòng lặp.

**Gate / D3,D4:** Phép đo đầy đủ/hợp lệ hoặc partial được bàn giao đúng; điểm không bắt buộc cao. Chỉ selection hợp lệ mới mở pipeline paid.

### R8 — Nghiệm thu public pipeline và người thật (T9)

- [ ] Xác minh selected condition, CTU scope, runtime/service/executor/source hashes khớp bản được chấm; fresh preflight và scope budget riêng. Runtime semantic bytes thay đổi thì gate dừng, không gọi là cùng môđun.
- [ ] Một invocation 32 original questions qua `InvestigationOrchestrator.investigate_query`; native model call, SQL model, DB worker, assessment model thật. Không private dispatcher, IOC giả, tool forced hay script assessment.
- [ ] Ghi native tool-call ID, exact question, runtime invocation/version, SQL/typed result/hash, evidence/parents, lifecycle/verification, từng role usage/cost/latency. Giữ đủ trace khi failed/partial.
- [ ] Chấm integrated EX độc lập cho SQL trong pipeline; đối chiếu facts/provenance; R4 report đủ mẫu số 32. Routing/profile mới không thừa hưởng R1 22/24.
- [ ] Người thật xem và duyệt technical-valid cases; decision/rationale/UTC/base hash. Reject/escalate là workflow decision thật, không ép approved. Technical-invalid không được approve để thành success; pending giữ pending.
- [ ] Xuất human coverage/approved completion và overhead, join review có hash; commit/push/public-safe evidence, CI evidence SHA. Không gọi API thêm cho người duyệt hoặc chọn lại bốn demo IDs.

**Gate / D5,D6:** Có authentic traces đủ điểm nối; completed technical/human tách riêng. Chưa có trace pass vẫn giao failed/incomplete, không giả demo thành công.

### R9 — Báo cáo, demo và kiểm tái lập (T10/T11)

**Files:** `docs/evaluation/VinSOC_Final_Report_2026-10-15.md`, `docs/VinSOC_Text2SQL_Demo_Runbook_2026-10-15.md`; `artifact_manifest.json`, `delivery_receipt.json`, `remaining_work.md` mới trong integration output.

- [ ] Render bảng toàn 32 và bốn IDs đã chọn: `ctu_cross_708b66575657429a`, `ctu_cross_66b8e92a76c3359b`, `ctu_cross_3f659571f998adb0`, `ctu_cross_bce6d3679ade4cd6`. Giữ trạng thái failed/missing; không đổi câu cho đẹp.
- [ ] Kịch bản 5–7 phút: kiến trúc dùng chung → một trace đủ → lỗi thật nếu có → external64/CTU32/96 + integration32 → limitations/human/cost. Ghi “xem lại lượt thật”; không gọi viewer là một live run mới.
- [ ] Demo thành công chỉ khi ít nhất một trong bốn trace technical-success và người thật approved, đồng thời hiển thị cả bốn. Nếu không có thì giao demo failed/incomplete với evidence; không tăng cap/request để cứu.
- [ ] Báo R1/R2 lịch sử tách contract; bộ mới nhiều schema/lĩnh vực của tập đã chọn, không mọi dữ liệu/official Spider/pretraining-independent holdout. CTU S5/S7 không tạo source-session holdout.
- [ ] Ghi matched tám câu cũ/deferred, A2/A3 network v1 blocked/partial/awaiting_human theo evidence thật, R1 frozen/independent R2 holdout pending. Không dùng 96/32 để xóa mục tiêu lịch sử.
- [ ] Checkout sạch exact code, restore artifacts pinned, chạy validator/scorer/report/renderer offline; đối chiếu JSON–HTML/status/cost/hashes, không gửi model requests. Ghi commands/exits; không sửa history khi tái lập.
- [ ] Kiểm preservation toàn bộ và manifest từng artifact; cost register giữ attempted/received/usage/known/unknown/exposure và failure charged. Bàn giao public package + private source/journal package có quyền truy cập riêng.
- [ ] Commit/push final docs/results, CI exact final SHA; `delivery_receipt.json` đánh trạng thái từng D1–D10, thiếu gì/gate nào/owner nào; không một nhãn COMPLETE phủ hết các phần pending.

## 4. Ma trận giao nộp D1–D10

| Đầu ra | Phần còn làm | Gate nghiệm thu | Owner |
|---|---|---|---|
| D1 code/pins/locks | R2/R3/R5 freeze, positive real DB + CI | Benchmark/production cùng service/executor, clean checkout chạy được | Người thực hiện |
| D2 sources/data | R1 exact bundle + R2 validation | Exact hashes/schema/parity/120 gold/scope, artifact truy được | Operator + người thực hiện |
| D3 calibration/selection | R7 | 48 records hợp lệ, lựa chọn trước evaluation và có artifact binding | Người thực hiện |
| D4 evaluation/report | R4/R7 | 192 records hoặc partial rõ; EX64/32/96/modules/paired/costs đúng | Người thực hiện |
| D5 pipeline32 | R4/R8 | Public native/model/DB/assessment traces thật, integrated score riêng | Người thực hiện |
| D6 human review | R8 | Người thật/decision/rationale/UTC/hash; không auto-approve | Analyst |
| D7 HTML/CLI | R5/R9 | Offline full traces/4 fixed IDs/32 statuses; không API khi render | Người thực hiện |
| D8 báo cáo cuối | R9 | Lịch sử/mới/pipeline/deferred tách rõ, giới hạn nguồn/phép đo đúng | Người thực hiện |
| D9 reproduction | R1/R5/R9 | Source/artifact pin + offline commands/exits + CI/producer identities | Người thực hiện |
| D10 money/blockers | R0/R3/R6–R9 | Journal mọi role, charged failure/unknown/remaining/state thật | Operator + người thực hiện |

## 5. Review Focus — năm rủi ro phải chặn

1. **Đổi binary/content lock mà vẫn gọi bản cũ:** R0/R1/R3 kiểm exact hashes/source/selection/CI trước SDK; sai identity fail, không relabel.
2. **Record từng case lấy counters toàn journal hoặc mất response khi usage lỗi:** R3 gắn IDs/role và durable checkpoint; R4/R6 đối soát không cộng nested calls hai lần.
3. **Paired/module reports đọc sai nested score hoặc thiếu identities:** R4 chuẩn hóa schema và coverage, giữ NA/incomplete; R7 replay report từ records thật.
4. **Facts đúng với query sai hoặc review pending bị gọi complete:** R4/R8 conjunction integrated EX/provenance/facts + actual review; R5/R9 renderer không nâng status.
5. **Worker receipt chỉ tự khai isolation, CI skip/missing DB vẫn xanh:** R2 quan sát boundary thực; R5 required real-data jobs fail thiếu input/backend, không fake fallback.

## 6. Lịch mục tiêu và điểm báo trễ

| Ngày | Việc / kết quả cần có |
|---|---|
| 08/10 | R0 xác minh state + R1 xuất bundle; bắt đầu R3/R4/R5 độc lập, lưu blocker content-lock cũ |
| 09–10/10 | R1/R2 data/worker PASS; hoàn tất R3/R4/R5 và real-data CI cả hai Python |
| 11/10 | R6 freeze/release/cận tiền/authorization; nếu thiếu DB/worker/account/budget, báo nguy cơ trễ cụ thể |
| 12–13/10 | R7 calibration/selection CI/evaluation; giữ partial nếu lỗi, không chạy cứu |
| 14/10 | R8 pipeline32 + người thật; R9 đối chiếu report/HTML |
| 15/10 | R9 final report/demo/reproduction/D1–D10/CI; hoàn tất trước 16/10 |

Lịch phụ thuộc đầu vào thực, không phải cam kết các gate đã có. Nếu chặn, tiếp tục report/CLI/guards/sanitize/reproduction scaffold offline; giữ score và human decision thiếu là thiếu. Không giảm denominator hoặc dùng mock để giữ lịch.

## 7. Tự rà và bàn giao cho người thực hiện

- [x] Đọc kế hoạch gốc và đối chiếu acceptance matrix/cursor mới với HEAD/CI thực.
- [x] Mỗi T0–T11 và D1–D10 có việc tiếp tục/gate/trạng thái trong bản này.
- [x] Không yêu cầu viết lại shared runtime/skill/orchestrator đã có; chỉ xác minh positive path và đóng phần thiếu.
- [x] Tách source audit khỏi exact-binary acceptance, mã/CI khỏi live measurement, facts khỏi EX, human pending khỏi approved.
- [x] Interface/paths nối đúng mã hiện có; interfaces mới là kế hoạch, không tuyên bố đã tồn tại. Không có tác vụ tạo synthetic predictions cho nghiệm thu.
- [x] Scope/money/window/frozen restrictions không được mở thêm bởi bản plan.

Khi tiếp tục dùng mode đã được chỉ thị: inline, một người ghi trên master. Không bắt người dùng chọn lại branch/PR/subagent mode. Mỗi checkbox thực thi chỉ đánh dấu khi có lệnh/exit/evidence/CI của chính mốc đó.
