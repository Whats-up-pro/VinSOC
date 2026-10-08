# VinSOC — Thực nghiệm SOC từ đầu vào đến báo cáo

Nguồn `alirezaaminzadeh/soc-agent-traces-100k` là **dữ liệu tổng hợp**, revision `fe94a95dadbd188c2bf137a9785b82cb5f7865c2`, Apache-2.0. Kết quả mới chỉ tồn tại khi SDK chính thức trả response trong cửa sổ SOC đã cấp. Không phát lại transcript nguồn hoặc dùng mock để demo.

Text-to-SQL toàn diện đang hoãn. Bộ SOC có DB, release và ngân sách riêng; không cần dùng DB CTU cũ để kiểm ngoại tuyến SOC. Snapshot CTU thiếu trên môi trường này vẫn là gate lịch sử chưa xác minh.

## 1. Môi trường và phục hồi dữ liệu

Dùng Python 3.11/3.12, môi trường riêng, requirements của repository; ghim DuckDB 1.5.5. Journal cần filesystem POSIX hỗ trợ khóa/fsync; trên Windows dùng WSL2. Không phụ thuộc việc phải chạy riêng trên laptop: CI/cloud kiểm corpus ngoại tuyến được; lượt live cần cùng source/runtime/release và private state hợp lệ ở nơi thực chạy.

```bash
python -m pip install -r requirements.txt
python -m pip install duckdb==1.5.5
python scripts/prepare_soc_traces.py --fetch --source-dir data/soc_traces_v1/source --output-dir data/soc_traces_v1/corpus
```

Hai parquet có tổng khoảng24MB; importer không execute builder của tác giả. CLI kiểm digest và ghi receipt cho DB mới. Không đưa raw parquet/DuckDB/private state/API key lên Git. DB nhị phân phục hồi phải được gắn với receipt của lần phục hồi đó; logical digest/importer/source identity phải khớp. Không coi DB này thay thế các exact DB lịch sử.

```bash
VINSOC_SOC_REQUIRED=1 VINSOC_SOC_SOURCE_DIR=data/soc_traces_v1/source VINSOC_SOC_CORPUS_PATH=data/soc_traces_v1/corpus/corpus.duckdb python -m pytest tests/test_soc_corpus_acceptance.py tests/test_soc_corpus_tools.py -q
```

Full suite trên laptop còn cần `VINSOC_LOCAL_SNAPSHOT` đúng CTU. CI dùng điều kiện skip lịch sử cho snapshot riêng; các tests SOC required không skip.

## 2. Kiểm nguồn, chưa gọi model

Artifacts ở `results/evaluation_v1/soc_traces_v1/`:

- `inventory.json`: 64 IDs, 32 malicious +32 benign, round-robin family/seed đã khóa.
- `gold.json`: nhãn tổng hợp evaluator riêng, không đưa vào requests/tools.
- `source_audit_queue.json`:12 IDs deterministic,6/label.
- `source_audit_pack.json`: input/observations/source pointers của12 hồ sơ để người thật kiểm; đây là tài liệu evaluator, không phải output model.
- `demo_selection.json`: bốn ID được chọn trước output.

Người thật đọc nguồn/bằng chứng và ghi12 phiếu vào `~/.vinsoc/live-windows/soc-traces-20261008-v1/source_reviews.json` (JSON array). Mỗi phiếu cần `analyst`, `reviewed_at` UTC có timezone, `scenario_id`, `source_sha256` bằng payload hash trong queue, `inventory_sha256`, `label_supportability`, `decision`, `rationale`. Được include chỉ khi người duyệt xác nhận `label_supportability=supported`, `decision=include`. Nếu nguồn/nhãn ambiguous, ghi đánh giá thật và quay lại selection trước output; không đổi nhãn hoặc giảm quota để pass. Audit final inventory phải đủ6/label. Agent không ký thay người duyệt.

Bốn demo hiện chọn: `SCT-087094`, `SCT-017066`, `SCT-004523`, `SCT-096313`. Chúng là subset64; không xóa context để tạo ca thiếu dữ liệu và không thêm request demo ngoài suite.

## 3. Preflight và quyền SOC riêng

```bash
python scripts/run_soc_traces.py --preflight --source-dir data/soc_traces_v1/source --corpus data/soc_traces_v1/corpus/corpus.duckdb
```

Preflight không claim scope, không tạo SDK client, attempts/responses=0. Exit2 là blocked; đọc `blockers`, không đổi window/output để vượt gate.

Private directory cố định: `~/.vinsoc/live-windows/soc-traces-20261008-v1/`. Cần các files sau do operator cung cấp, có chứng cứ thật:

| File | Nội dung cần có |
|---|---|
| `source_reviews.json` |12 phiếu nguồn như mục2 |
| `account.json` |operator,approved_at ngày chạy,window,account_id,authorization_statement,allowed_model,api_key_sha256; không đưa key vào JSON |
| `pricing.json` |operator,checked_at ngày chạy,model,source URL OpenAI pricing chính thức,input/output_usd_per_million,model_available,source_evidence_path/sha256; giữ chứng cứ giá đã đọc |
| `budget.json` |operator,approved_at ngày chạy,window,limit_usd cụ thể,calls_limit448; không dùng tiền/quyền R1/R2 |
| `request_bound.json` |operator,checked_at,method=utf8_bytes_plus_verified_framing,max_utf8_bytes128000,framing_token_reserve integer dương,verification_evidence_path/sha256,verification_rationale; thiếu chứng minh bound thì blocked |
| `ci.json` |operator,checked_at ngày chạy,implementation_sha,run_id; preflight kiểm lại GitHub success đúng SHA, cả3.11/3.12 và bước restore corpus required |

Model khóa `gpt-4.1-mini-2025-04-14`, temperature0, max_completion_tokens2000, official OpenAI SDK2.8.1/httpx0.28.1, max_retries0. Budget phải đủ toàn suite theo bound đã kiểm; 448 requests là cận số lượt, chưa phải tiền đã cấp. Giá/availability không kế thừa constants của provider cũ.

Sau khi đủ gates và CI của runtime frozen:

```bash
python scripts/run_soc_traces.py --preflight --source-dir data/soc_traces_v1/source --corpus data/soc_traces_v1/corpus/corpus.duckdb --write-release ~/.vinsoc/live-windows/soc-traces-20261008-v1/release.json
```

Không sửa importer/tools/prompts/schema/scorer/provider/runner/CLI sau freeze. Nếu artifact-only commit làm HEAD thay đổi, CI receipt vẫn phải bind đúng implementation SHA có cùng toàn bộ runtime hashes. Trước live runner kiểm key hash và model availability bằng API metadata; đó không phải inference.

## 4. Đầu vào và lượt E2E

Alert intake là `{"kind":"alert","alert":<đúng allowlisted alert của locked scenario>}`. IOC intake là `{"kind":"ioc","value":<literal có trong imported observations/input>,"indicator_type":"ipv4|domain|hash|url"}`. IOC không có hoặc khớp nhiều scenarios bị blocked trước SDK; không tự chọn theo ground truth. Đây không phải tra IOC internet tùy ý.

`python cli/main.py soc --input <input.json> --case-id <locked-id> --condition S1 --release <private-release.json>` chỉ xác minh scope/input của suite. Không mở một lượt paid khác để demo.

Đặt `OPENAI_API_KEY` bằng cơ chế private phù hợp, không truyền key vào lệnh/receipt public. Chạy **một lần**:

```bash
python scripts/run_soc_traces.py --live --release ~/.vinsoc/live-windows/soc-traces-20261008-v1/release.json --output-dir results/evaluation_v1/soc_traces_v1/live
```

Thứ tự64 IDs cố định, mỗi ID S0 rồi S1. S0: một request alert-only; S1: model tự chọn tối đa5 tools/6 requests. Luồng public `investigate_alert`: nhận/kiểm scope → model → tools thật đọc DB → evidence IDs thực delivered → final JSON model → validation → receipt → awaiting_human. Không triage auto-close hoặc script verdict/risk. Request6 final-only. Không tool SQL/scenario argument. UTC half-open,20rows/20000UTF8bytes mỗi tool,128000bytes/16messages mỗi request.

Journal reserve trước transmission, lưu raw HTTP body và usage trước parse. Private raw responses/requests/ledger không public. Checkpoint sau response/case; receipt cuối không sửa. Timeout/crash/unknown usage/identity mutation/budget dừng toàn release; giữ partial và unknown cost. Không retry/key/window/output mới để cứu lượt. Review more-evidence chỉ ghi yêu cầu, không mở API.

## 5. Đọc báo cáo và review

```bash
python scripts/render_soc_report.py --suite results/evaluation_v1/soc_traces_v1/live --output results/evaluation_v1/soc_traces_v1/views
python cli/main.py soc-report --receipt results/evaluation_v1/soc_traces_v1/live/cases/SCT-087094_S1.json --output results/evaluation_v1/soc_traces_v1/views
```

JSON/HTML/Markdown giữ đầy đủ summary, verdict, hypotheses/support/contradictions, findings observed/inferred, risk/confidence và lý do, limitations, actions, evidence, nguồn, tools/native IDs, usage/cost/errors. Không cắt500/2000 ký tự. Không có final thì chỉ hiện input/status/errors; không điền báo cáo mẫu.

Mở bốn pages demo, trình bày cảnh báo → tool choices/delivered observations → nhận định model và citations → giới hạn/hành động → trạng thái duyệt. Case lỗi/thiếu vẫn xuất hiện trong bảng tổng.

Người thật kiểm factual support, root-cause/contradiction và action suitability rồi ghi quyết định:

```bash
python scripts/review_soc_case.py --receipt <case-receipt.json> --output <live/reviews/id_S1.json> --analyst <tên-người-thật> --decision approved --rationale <nhận-xét-thực>
```

Các decisions: approved/rejected/escalated/more_evidence_requested. Review bind scenario/condition/receipt hash/UTC; receipt gốc bất biến. Render lại với `--review <review.json>`. Không tự approve; approved completion cần technical-valid. Kiểm schema/citation không tự chứng minh prose đúng.

## 6. Phép đo và bàn giao

Luôn64 mẫu số/condition và64 cặp. Failed/missing/abstain không correct; abstain và missing là FN trong recall. Báo coverage, confusion, class/family metrics, paired win/loss/tie/incomplete, input/tool citations riêng, tokens/latency/cost known/unknown và reviewed/approved. S0 tool metrics NA. Khi chưa chạy, accuracy/delta chưa có số; không biến not_run thành benchmark0%.

Agreement chỉ với nhãn synthetic public; không kết luận khả năng SOC tổng quát, family holdout hoặc causal proof. Families/templates overlap và pretraining exposure có thể xảy ra. Chưa có outputs/reviews thật thì D-SOC6–8 chưa nghiệm thu; bàn giao readiness/blockers, không dựng demo thay thế.
