# VinSOC Query Pipeline Protocol 4 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Hoàn tất một lượt chạy mới đủ 32 ca của pipeline truy vấn VinSOC mà kết quả SQL lớn không làm vỡ bước assessment, mọi dữ kiện đều được định địa chỉ chính xác và lỗi đã biết của một ca không làm mất các ca sau.

**Architecture:** Kết quả SQL đầy đủ tiếp tục là nguồn sự thật và được lưu để phát lại; một bộ chiếu thuần, xác định tạo payload assessment không quá 32.768 byte. Assessment dùng JSON Pointer trỏ vào typed full result. Runner giao thức 4 ghi trạng thái riêng cho từng ca, tiếp tục sau lỗi đã biết có chi phí rõ và dừng ngay khi chi phí không rõ hoặc lỗi hệ thống.

**Tech Stack:** Python 3.11/3.12, pytest, JSON Schema, DuckDB, OpenAI Python SDK, GitHub Actions.

**Spec:** `docs/superpowers/specs/2026-10-21-vinsoc-query-pipeline-protocol4-design.md`

## Global Constraints

- Giữ nguyên toàn bộ artifact và đường chạy giao thức 3; mọi file kết quả giao thức 4 phải tạo mới.
- Không sửa 32 câu hỏi, gold SQL, snapshot CTU, scorer Execution Accuracy, E0 selection, model hoặc tham số request.
- `NetworkQueryPolicy.MAX_RESPONSE_BYTES` giữ đúng `32768`; không thêm model call tóm tắt.
- Bản chiếu lấy tối đa 20 dòng đầu, giảm dần đến khi vừa giới hạn byte UTF-8; không chọn dòng theo nội dung.
- Mọi request dùng retry bằng 0. Chi phí không rõ hoặc request chưa đối soát phải dừng toàn bộ lượt chạy.
- Không chạy E3, R1, frozen, ThreatFox, OTRF hoặc benchmark khác trong kế hoạch này.
- Workflow trả phí chỉ có `workflow_dispatch`; không có `push`, `pull_request`, `schedule` hoặc `workflow_run`.
- Chỉ chạy đúng một lượt trả phí đủ 32 ca sau khi full CI Python 3.11/3.12 xanh trên đúng implementation SHA và preflight mới đạt.
- Không gọi một lượt có ca thiếu, unknown cost hoặc lỗi hệ thống là hoàn tất end-to-end.

## Review Focus

- Unicode nhiều byte làm payload vượt 32.768 byte: Task 1 phải đo byte UTF-8 sau serialization, không dùng `len(str)`.
- Tên cột hoặc chuỗi chứa `/` và `~`: Task 2 phải kiểm escape RFC 6901 `~1` và `~0`, đồng thời từ chối escape sai.
- `bool` bị Python xem như `int`: Task 2 phải so sánh cả `type` và giá trị.
- Tiến trình dừng sau reserve hoặc sau response nhưng trước khi ghi record: Task 4 phải dựa vào journal để chuyển `unknown_cost` hoặc phục hồi mà không gửi lại.
- Artifact giao thức 3 dùng observation `field`: Task 3 phải đọc và chấm lại được artifact cũ, nhưng runtime giao thức 4 phải từ chối shape cũ.

---

### Task 1: Bộ chiếu kết quả SQL có giới hạn

**Files:**
- Create: `agent/query_result_projection.py`
- Create: `tests/test_query_result_projection.py`

**Interfaces:**
- Consumes: evidence dictionaries từ `Evidence.to_dict()` và `max_response_bytes: int`.
- Produces: `ProjectionError(code: str)`, `project_query_evidence(evidence: list[dict], *, max_rows: int = 20) -> list[dict]`, và `serialize_assessment_payload(question: str, evidence: list[dict], *, max_bytes: int = 32768) -> str`.

- [ ] **Step 1: Viết test thất bại cho kết quả nhỏ, kết quả rỗng và tính xác định**

  Test `test_small_and_empty_results_preserve_full_projection_contract` kiểm `complete`, `included_rows`, `omitted_rows`, `row_count`, `result_sha256`; gọi hai lần phải cho byte JSON giống nhau và không sửa input.

- [ ] **Step 2: Chạy test để xác nhận thất bại**

  Run: `python -m pytest tests/test_query_result_projection.py -q`

  Expected: FAIL vì module chưa tồn tại.

- [ ] **Step 3: Viết test biên 9.780 dòng, Unicode và schema quá lớn**

  Test phải xác nhận payload `<= 32768` byte, tối đa 20 dòng đầu đúng thứ tự, full input/hash không đổi, số dòng giảm được với Unicode và `ProjectionError.code == 'ASSESSMENT_PROJECTION_SCHEMA_LIMIT'` khi envelope bắt buộc không thể vừa.

- [ ] **Step 4: Triển khai module thuần**

  `project_query_evidence()` chỉ thay `data.rows` trong bản sao sâu và thêm `assessment_projection`; `serialize_assessment_payload()` thử từ `min(20, row_count)` xuống 0, serialize bằng `ensure_ascii=False`, compact separators và đo `len(encoded.encode('utf-8'))`.

- [ ] **Step 5: Chạy test focused và commit**

  Run: `python -m pytest tests/test_query_result_projection.py -q`

  Expected: PASS.

  Commit: `feat(pipeline): add bounded query result projection`

### Task 2: JSON Pointer và hợp đồng assessment giao thức 4

**Files:**
- Create: `evaluation/finalization/query_json_pointer.py`
- Modify: `agent/network_query_policy.py`
- Modify: `vinsoc_text2sql/provider.py`
- Modify: `tests/test_network_query_policy.py`
- Create: `tests/test_query_json_pointer.py`

**Interfaces:**
- Consumes: full `evidence.data`, projected evidence và observation `{evidence_id, json_pointer, value}`.
- Produces: `resolve_json_pointer(document: object, pointer: str) -> object`, `verify_scalar_observation(observation: dict, evidence_by_id: dict, projected_paths: dict[str, set[str]]) -> bool`, prompt/schema assessment v4.

- [ ] **Step 1: Viết test thất bại cho resolver RFC 6901**

  Bao phủ `/row_count`, `/rows/1/2`, `/columns/0/name`, `~0`, `~1`; từ chối relative pointer, escape sai, index âm, object/array target, dòng bị lược và pointer lặp.

- [ ] **Step 2: Viết test kiểu dữ liệu nghiêm ngặt**

  Kiểm `true != 1`, `null` đúng kiểu, string số không bằng number và pointer không có trong bản chiếu bị từ chối dù tồn tại trong full result.

- [ ] **Step 3: Chạy test để xác nhận thất bại rồi triển khai resolver**

  Run: `python -m pytest tests/test_query_json_pointer.py -q`

  Expected trước code: FAIL vì module chưa tồn tại; expected sau code: PASS.

- [ ] **Step 4: Đổi prompt, response schema và parser runtime sang `json_pointer`**

  `NetworkQueryPolicy.VERSION = 'network_query_policy_v2'`; `tool_response()` gọi Task 1 và lưu tập pointer đã gửi trong `self._assessment_projected_paths`; `parse_final_response()` chỉ nhận đúng ba field observation mới và dùng chung verifier Task 2. `ASSESSMENT_RESPONSE_FORMAT` thay `field` bằng `json_pointer`. Orchestrator ghi `query_policy.version = NetworkQueryPolicy.VERSION` và `query_policy.projection_manifest` gồm version, counts, result hash và các pointer đã gửi vào record để reporting chọn đúng verifier mà không sao chép dữ liệu dòng.

- [ ] **Step 5: Thêm hồi quy cho ca nhiều dòng và kết quả rỗng**

  Test assessment có `/rows/1/0` hợp lệ, `/row_count == 0` hợp lệ, `field` shape bị từ chối, payload 9.780 dòng không tạo `ASSESSMENT_EVIDENCE_PAYLOAD_LIMIT`.

- [ ] **Step 6: Chạy focused tests và commit**

  Run: `python -m pytest tests/test_query_result_projection.py tests/test_query_json_pointer.py tests/test_network_query_policy.py -q`

  Expected: PASS.

  Commit: `feat(pipeline): verify assessment facts by JSON pointer`

### Task 3: Tương thích artifact cũ và báo cáo dữ kiện mới

**Files:**
- Modify: `evaluation/finalization/query_pipeline_reporting.py`
- Modify: `scripts/review_vinsoc_query_case.py`
- Modify: `scripts/render_query_pipeline_report.py`
- Modify: `tests/test_query_pipeline_reporting.py`
- Modify: `tests/test_query_cli_viewer.py`

**Interfaces:**
- Consumes: protocol 4 observations và immutable protocol 3 observations.
- Produces: `query_observations_verified(assessment: dict, evidence: list[dict], *, policy_version: str | None, projected_paths: dict[str, set[str]] | None = None) -> bool`; `network_query_policy_v2` dùng Task 2, record legacy không có version dùng adapter cũ chỉ đọc.

- [ ] **Step 1: Viết test phân tách hai giao thức**

  Artifact đã lưu `query_run_38041048027_assessment.json` vẫn được đọc/chấm như trước. Record v4 dùng `field` phải fail; record v4 dùng pointer đúng phải pass.

- [ ] **Step 2: Viết test chống nhầm full result và projection**

  Pointer tới dòng không có trong `query_policy.projection_manifest` phải fail; thay cell trong full result nhưng giữ hash cũ phải làm provenance và technical workflow fail. Manifest bị sửa hoặc không khớp `result_sha256` cũng phải fail.

- [ ] **Step 3: Triển khai adapter và cập nhật HTML/CLI**

  HTML hiển thị `json_pointer`, trạng thái projection, `included_rows`, `omitted_rows`; không dựng lại full result từ projection và không sửa artifact nguồn.

- [ ] **Step 4: Chạy focused tests và commit**

  Run: `python -m pytest tests/test_query_pipeline_reporting.py tests/test_query_cli_viewer.py -q`

  Expected: PASS, gồm hồi quy protocol 3.

  Commit: `feat(reporting): support protocol 4 fact verification`

### Task 4: Trạng thái từng ca và tiếp tục an toàn

**Files:**
- Create: `evaluation/finalization/query_case_lifecycle.py`
- Create: `tests/test_query_case_lifecycle.py`
- Create: `tests/test_query_pipeline_protocol4_live.py`
- Modify: `scripts/run_vinsoc_query_acceptance.py`
- Modify: `tests/test_query_journal_persistence.py`

**Interfaces:**
- Produces: `CaseState` với `not_started|running|completed|known_error|unknown_cost|fatal_error`; `classify_case_failure(error, *, stage: str, journal: RunJournal) -> CaseFailure`; `load_protocol4_checkpoint(path, release_sha256) -> dict`.
- Runner ghi `failure_stage`, `failure_category`, `cost_events`, `cost_unknown` và trạng thái bằng persist nguyên tử hiện có.

- [ ] **Step 1: Viết test ma trận chuyển trạng thái và danh mục lỗi**

  Chỉ cho phép `not_started -> running -> completed|known_error|unknown_cost|fatal_error`; terminal case không quay lại `running`. Danh mục known error gồm mã sinh SQL/thực thi đã có, `ASSESSMENT_PROJECTION_SCHEMA_LIMIT`, assessment contract và fact mismatch; exception ngoài danh mục là `fatal_error`.

- [ ] **Step 2: Viết test tiếp tục và dừng**

  Fake 3-case run: ca 1 completed, ca 2 assessment known error có usage hợp lệ, ca 3 vẫn chạy. Fixture missing usage dừng ngay ở ca 2 và không gọi ca 3. Unexpected exception cũng dừng.

- [ ] **Step 3: Viết test phục hồi không gửi trùng**

  Cùng `execution_id` bỏ qua `completed`/`known_error`; `running` chỉ tiếp tục khi journal không có request chưa đối soát; ngược lại chuyển `unknown_cost`. Release hash khác hoặc checkpoint v3 bị từ chối.

- [ ] **Step 4: Triển khai state machine và tích hợp runner**

  Không catch rộng để tiếp tục. Runner chỉ tiếp tục từ `CaseFailure.continue_allowed is True`; mọi artifact lỗi chỉ chứa mã an toàn, không chứa raw exception/response/key/traceback.

- [ ] **Step 5: Chạy focused tests và commit**

  Run: `python -m pytest tests/test_query_case_lifecycle.py tests/test_query_journal_persistence.py tests/test_query_pipeline_protocol4_live.py -q`

  Expected: PASS.

  Commit: `feat(pipeline): isolate known per-case failures`

### Task 5: Hợp đồng, danh tính và cửa sổ giao thức 4

**Files:**
- Create: `evaluation/finalization/query_pipeline_protocol4.py`
- Modify: `evaluation/finalization/query_runtime_validation.py`
- Modify: `evaluation/finalization/query_pipeline_contract.py`
- Modify: `scripts/vinsoc_live_protocol.py`
- Modify: `scripts/run_query_live_ui_cloud.py`
- Modify: `tests/test_query_pipeline_contract.py`
- Modify: `tests/test_query_acceptance_preflight.py`
- Modify: `tests/test_query_cloud.py`

**Interfaces:**
- Produces: `PROTOCOL4_VERSION`, `protocol4_window_id(execution_id: str) -> str`, `protocol4_identities() -> dict`, `preflight_protocol4(*, inventory: list[dict], identities: dict, account: dict, pricing: dict, budget: dict, execution_id: str) -> dict`, và `create_protocol4_request(*, head_sha: str, ci_run_id: int, execution_id: str, live_consent: bool) -> dict`.
- `protocol4_identities()` khóa prompt SHA, projection SHA, JSON Pointer verifier SHA, scorer, benchmark, runtime và snapshot identities.

- [ ] **Step 1: Viết test cửa sổ và release riêng**

  Window có dạng `text2sql-integration-20261021-protocol4-pipeline-<execution_id>`; release v3 không validate như v4; v4 không nhận checkpoint/window v3.

- [ ] **Step 2: Viết test đầy đủ chuỗi danh tính**

  Thiếu hoặc đổi prompt/projection/verifier/scorer/snapshot/case order phải chặn trước client; đủ đúng 32 ID, E0 lock và SHA hợp lệ mới qua gate identity.

- [ ] **Step 3: Triển khai contract và cập nhật source closure**

  Giữ API v3 mặc định cho artifact lịch sử. Chỉ đường protocol 4 mới gọi `preflight_protocol4`; `create_protocol4_request()` khóa `scope='pipeline'`, `condition='E0'`, 32 ca và không nhận `case_id`/`question`. Không đổi models, retry, caps hoặc pricing rules.

- [ ] **Step 4: Chạy focused tests và commit**

  Run: `python -m pytest tests/test_query_pipeline_contract.py tests/test_query_acceptance_preflight.py tests/test_query_cloud.py -q`

  Expected: PASS.

  Commit: `feat(pipeline): lock protocol 4 release identities`

### Task 6: Workflow thủ công và artifact giao thức 4

**Files:**
- Create: `.github/workflows/query-pipeline-protocol4.yml`
- Create: `scripts/run_query_pipeline_protocol4_cloud.py`
- Create: `tests/test_query_pipeline_protocol4_workflow.py`
- Modify: `evaluation/finalization/query_pipeline_reporting.py`
- Modify: `scripts/render_query_pipeline_report.py`

**Interfaces:**
- Workflow nhận `mode: preflight|live`, `execution_id`, `ci_run_id`, `request_json`; runner cloud dùng Task 5 và gọi public pipeline lifecycle hiện có.
- Artifact công khai gồm preflight, report, 32 case receipts hoặc trạng thái dừng, cost summary, hash manifest, HTML và human-review queue; private artifact giữ canonical ledger theo cơ chế hiện có.

- [ ] **Step 1: Viết test cấu trúc workflow**

  Assert manual-only, `contents: write`, concurrency không hủy, exact-SHA CI input, key chỉ ở live step, retry 0 qua contract, cleanup/artifact upload chạy `if: always()` và không có trigger tự động.

- [ ] **Step 2: Viết test artifact/report đủ và partial**

  32 terminal case cho rate mẫu số 32; known error có stage metrics đã đo và false cho bước không hoàn tất; fatal/unknown giữa lượt giữ headline `null`, missing đúng số. JSON và HTML phải khớp.

- [ ] **Step 3: Triển khai workflow, cloud runner và manifest**

  Không ghi raw journal vào public artifact. `live` phải từ chối nếu preflight identity khác, CI không xanh hoặc output đã tồn tại.

- [ ] **Step 4: Chạy focused tests và commit**

  Run: `python -m pytest tests/test_query_pipeline_protocol4_workflow.py tests/test_query_pipeline_reporting.py tests/test_query_cli_viewer.py -q`

  Expected: PASS.

  Commit: `feat(pipeline): add guarded protocol 4 execution workflow`

### Task 7: Kiểm chứng ngoại tuyến và CI đúng SHA

**Files:**
- Modify only if a test reveals a protocol 4 regression; no result artifact in this task.

- [ ] **Step 1: Chạy toàn bộ focused suite**

  Run: `python -m pytest tests/test_query_result_projection.py tests/test_query_json_pointer.py tests/test_network_query_policy.py tests/test_query_pipeline_reporting.py tests/test_query_cli_viewer.py tests/test_query_case_lifecycle.py tests/test_query_journal_persistence.py tests/test_query_pipeline_protocol4_live.py tests/test_query_pipeline_contract.py tests/test_query_acceptance_preflight.py tests/test_query_cloud.py tests/test_query_pipeline_protocol4_workflow.py -q`

  Expected: PASS, 0 skip trong các test gate protocol 4.

- [ ] **Step 2: Chạy full suite và kiểm tra tĩnh**

  Run:

  ```bash
  python -m pytest -q
  python -m compileall agent evaluation skills vinsoc_text2sql scripts tests
  git diff --check
  python -m scripts.verify_query_preservation
  ```

  Expected: tất cả đạt; preservation xác nhận artifact lịch sử không đổi.

- [ ] **Step 3: Kiểm staged diff và commit mốc implementation**

  Assert không có `.env`, database, raw source, artifact lịch sử hoặc credential trong staged files.

  Commit: `feat(pipeline): complete protocol 4 offline gates`

- [ ] **Step 4: Push `master` và chờ CI đúng SHA**

  Xác nhận Python 3.11/3.12, real-data isolation và test workflow đều xanh trên đúng final SHA. Không dispatch preflight trước khi đạt.

### Task 8: Preflight, một lượt chạy 32 ca và bàn giao

**Files:**
- Create after authentic run: `results/evaluation_v1/text2sql_integration_v1/pipeline_protocol4_<execution-id>/` containing `report.json`, `case_receipts/`, `public_cost_summary.json`, `artifact_manifest.json`, `offline_pipeline_viewer.html` and `human_review_queue.json`.
- Create: `docs/evaluation/VinSOC_Query_Pipeline_Protocol4_Report_2026-10-21.md`

- [ ] **Step 1: Dispatch preflight manual trên exact implementation SHA**

  Kiểm đủ 32 ID theo thứ tự, E0 selection, snapshot/hash, source closure, CI, pricing, account reconciliation, unknown exposure bằng 0 và cost ceiling nằm trong hạn mức đã duyệt. Preflight phải có `attempted=0`, `received=0`, `client_created=false`.

- [ ] **Step 2: Kiểm preflight artifact và quyết định live**

  Chỉ tiếp tục nếu `authorized=true`, không có reason, window protocol 4 chưa dùng và `release_sha256` khớp. Nếu không đạt, dừng; không gọi API.

- [ ] **Step 3: Dispatch đúng một lượt `live` đủ 32 ca**

  Không đổi commit, request, prompt, benchmark hoặc snapshot giữa preflight và live. Không retry ca sai và không dispatch lượt hai nếu run dừng.

- [ ] **Step 4: Kiểm toán artifact thật**

  Chạy verifier ngoại tuyến; đối chiếu 32 case states, request/response/usage, known cost, zero unknown cost, result/projection hashes, independent replay, JSON–HTML equality và manifest. Xác nhận case tương ứng lỗi cũ 9.780 dòng đã qua projection mà full result hash không đổi.

- [ ] **Step 5: Commit evidence và báo cáo nếu lượt chạy đủ điều kiện**

  Báo số completed/known_error, routing, integrated EX, provenance, fact verification, technical workflow, projection counts, per-stage errors, token/cost và human-review coverage. Giữ `official_eligible=false` cho đến khi audit và người thật duyệt hoàn tất.

  Commit: `results(pipeline): publish protocol 4 execution evidence`

- [ ] **Step 6: STOP FOR HUMAN REVIEW**

  Không tự duyệt assessment, không chạy lại API, không mở frozen và không suy rộng CTU32 thành holdout độc lập.
