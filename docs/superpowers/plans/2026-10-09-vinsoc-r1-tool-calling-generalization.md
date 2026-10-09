# VinSOC R1 Tool Calling Generalization Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Bổ sung split `generalization_v1` gồm 120 ca vào chính môđun R1 Tool Calling hiện có, khóa gold bằng hai người duyệt độc lập, chạy chung runner/scorer và báo kết quả có khoảng tin cậy mà không thay đổi 24 ca dev, tám ca frozen hoặc kết quả lịch sử.

**Architecture:** Candidate chưa có gold được lưu trong vùng authoring và qua kiểm tra cấu trúc, độ phủ, trùng lặp trước khi xuất hai gói duyệt mù. Chỉ sau khi hai review khớp hoặc được người thứ ba phân xử, builder mới tạo split chính thức và lock; CLI hiện có dùng chung `DecisionRunner`, matcher, metrics và provenance nhưng chặn trước khi tạo provider nếu review/lock/quyền/ngân sách chưa đạt.

**Tech Stack:** Python 3.11, dataclasses/JSON/JSONL, pytest, GitHub Actions, OpenAI provider hiện có; không thêm dependency thống kê.

**Spec:** `docs/superpowers/specs/2026-10-09-vinsoc-r1-tool-calling-generalization-design.md`

## Global Constraints

- Làm trực tiếp trên `master` theo quyền người dùng đã cấp; mỗi mốc phải commit, push và kiểm CI đúng SHA.
- Không sửa byte của `evaluation/tool_calling/benchmarks/dev/`, `evaluation/tool_calling/benchmarks/frozen/`, `results/evaluation_v1/r1/r1_a1_dev_v2_852e543.json` hoặc `evaluation/tool_calling/winner_lock.json`.
- Split mới có đúng 120 ca: 24 no-tool, 54 single-tool (18 mỗi tool), 30 two-tool (10 mỗi cặp), 12 three-tool; ít nhất 30 ca có nhãn robustness.
- Candidate không chứa final gold. Hai người duyệt tạo quyết định độc lập; agent triển khai không tự phê duyệt hoặc phân xử.
- `soc-agent-traces-100k` chỉ là nguồn gợi ý synthetic; không dùng `success`, `decision`, `decisive`, tool sequence hoặc final report của nguồn làm gold.
- Unit test được dùng fake provider để chứng minh fail-closed; không được dùng mock/replay/response viết sẵn để tạo điểm nghiệm thu.
- Không gọi API trước khi đủ 120 gold đã duyệt, lock/hash hợp lệ, preflight chi phí đạt và có quyền riêng cho đúng một suite.
- Zero retry ở SDK và runner; không giảm mẫu số, rerun hoặc mở lượt mới để cứu kết quả.
- Điểm dev `22/24` và điểm mới `x/120` luôn báo riêng; không tạo điểm `(22+x)/144`.

## Review Focus

- Candidate chứa chỉ dẫn chèn trong dữ liệu: phần này phải được giữ như dữ liệu của request và không được thay system prompt, tool schema hoặc gate.
- Review thiếu, trùng reviewer, khác schema hoặc còn bất đồng: phải dừng trước provider creation và nêu đúng case ID bị chặn.
- Cặp gần trùng trong nội bộ hoặc trùng dev/frozen: phải xuất hàng đợi xử lý; chỉ waiver có lý do và người duyệt mới cho qua.
- Split/lock bị sửa sau duyệt hoặc commit làm việc không sạch: preflight phải thất bại, không tạo provider và không ghi điểm.
- Provider lỗi hoặc artifact dở giữa suite: giữ đủ partial artifact, chấm phần chưa chạy là chưa hoàn tất, không retry và không đổi denominator.

---

## File Structure

- Create `evaluation/tool_calling/generalization.py`: model authoring/review, audit candidate, build/verify lock, Wilson interval, exact McNemar và full-denominator coverage.
- Create `evaluation/tool_calling/authoring/generalization_v1/candidates.jsonl`: 120 request và metadata nguồn, không có `expected_calls`.
- Create `evaluation/tool_calling/authoring/generalization_v1/reviews/README.md`: quy tắc duyệt mù, schema record và quy trình phân xử.
- Create `evaluation/tool_calling/authoring/generalization_v1/reviews/reviewer_a.jsonl`: biểu mẫu trống theo 120 case ID.
- Create `evaluation/tool_calling/authoring/generalization_v1/reviews/reviewer_b.jsonl`: biểu mẫu trống theo 120 case ID.
- Create `evaluation/tool_calling/authoring/generalization_v1/near_duplicate_waivers.jsonl`: waiver trống; mỗi record cần cặp case, lý do và người duyệt.
- Create `evaluation/tool_calling/benchmarks/generalization_v1/`: chỉ được builder tạo sau human gate.
- Modify `evaluation/tool_calling/__main__.py`: thêm list/preflight/lock/run cho `generalization_v1`, cùng đường chạy hiện có.
- Modify `evaluation/tool_calling/decision_runner.py`: nhận prevalidated split contract; không đổi semantics dev/frozen.
- Modify `evaluation/tool_calling/metrics.py`: thêm full-denominator coverage và thống kê case-level.
- Modify `evaluation/tool_calling/provenance.py`: ghi lock/review/audit hashes cho split mới.
- Create `tests/test_tool_calling_generalization.py`: contract, audit, review, lock, statistics, fail-closed và bảo toàn lịch sử.
- Modify `tests/test_tool_calling_cli.py`: CLI mới và provider-construction guard.
- Create `.github/workflows/r1-generalization-v1.yml`: preflight offline và một suite có quyền riêng.
- Modify `evaluation/tool_calling/README.md`, `evaluation/tool_calling/benchmarks/README.md`, `README.md`: cách dùng và giới hạn kết luận.

### Task 1: Khóa bất biến lịch sử và hợp đồng candidate

**Files:**
- Create: `evaluation/tool_calling/generalization.py`
- Create: `tests/test_tool_calling_generalization.py`
- Test: `tests/test_tool_calling_benchmark_contract.py`

**Interfaces:**
- Consumes: `canonical_sha256(value: Any) -> str`, `get_tool_schemas() -> list[dict]`, các lock dev/frozen hiện có.
- Produces: `CandidateCase.from_dict(data: dict) -> CandidateCase`, `load_candidates(path: Path) -> list[CandidateCase]`, `historical_identity() -> dict[str, str]`.

- [ ] **Step 1: Viết test thất bại cho bất biến lịch sử và candidate không có gold**

  Thêm `test_historical_r1_bytes_match_committed_identities`, `test_candidate_rejects_expected_calls`, `test_candidate_requires_source_and_unique_identity`. Test phải khóa các giá trị hiện có: dev split `d8e68968a390a09d502a3da01319611f546a6d0189a30e0fe0c316550d0aa259`, frozen split `eb46a6d42aeced2f6f676fb5a04a670a49351d4516c5582cb61dcb39e2b61ae4`, historical result raw SHA-256 `60a87c2502ea6d664b883e147bfdfb1be014df813c001225ec0a05839f7e421b`, winner lock raw SHA-256 `dd520c4d9da7430d55d083cc66246f4de4a432aaf536108565bae070745269e9`; candidate hợp lệ phải có `case_id`, `request`, `difficulty`, `source_kind`, `source_reference`, `source_record_id`, `scenario_family`, `template_family`, `authoring_stratum`, `coverage_tags`.

- [ ] **Step 2: Chạy test để xác nhận RED**

  Run: `.venv/bin/python -m pytest -q tests/test_tool_calling_generalization.py tests/test_tool_calling_benchmark_contract.py`
  Expected: FAIL vì `evaluation.tool_calling.generalization` chưa tồn tại.

- [ ] **Step 3: Cài đặt model và loader tối thiểu**

  Trong `generalization.py`, tạo:

  ```python
  @dataclass(frozen=True)
  class CandidateCase: ...

  def load_candidates(path: Path) -> list[CandidateCase]: ...
  def historical_identity(root: Path = Path(".")) -> dict[str, str]: ...
  ```

  Loader đọc JSONL UTF-8, báo dòng lỗi, cấm `expected_calls`, `forbidden_tools`, `ordering_constraints` và mọi field gold.

- [ ] **Step 4: Chạy test GREEN và regression R1**

  Run: `.venv/bin/python -m pytest -q tests/test_tool_calling_generalization.py tests/test_tool_calling_benchmark_contract.py tests/test_tool_calling_evaluator.py`
  Expected: PASS.

- [ ] **Step 5: Commit, push và kiểm CI đúng SHA**

  ```bash
  git add evaluation/tool_calling/generalization.py tests/test_tool_calling_generalization.py
  git commit -m "feat(r1): add generalization authoring contract"
  git push origin master
  ```

  Kiểm GitHub Actions gắn đúng `git rev-parse HEAD`; dừng nếu SHA hoặc CI không khớp.

### Task 2: Soạn 120 candidate và kiểm tra phân bổ

**Files:**
- Create: `evaluation/tool_calling/authoring/generalization_v1/candidates.jsonl`
- Modify: `evaluation/tool_calling/generalization.py`
- Modify: `tests/test_tool_calling_generalization.py`

**Interfaces:**
- Consumes: `CandidateCase`, `load_candidates()` từ Task 1; production tool names từ `get_tool_schemas()`.
- Produces: `audit_candidate_distribution(cases: Sequence[CandidateCase]) -> DistributionAudit` và candidate pack 120 dòng.

- [ ] **Step 1: Viết test RED cho đúng 120 ca và ma trận phân bổ**

  Test phải xác nhận ID `gen_001`…`gen_120`, 24 no-tool, 18 cho từng single tool, 10 cho từng two-tool pair, 12 three-tool, ít nhất 30 robustness, và basic/intermediate/advanced xuất hiện trong mỗi nhóm chính. `authoring_stratum` chỉ phục vụ soạn và không xuất hiện trong review pack/model input.

- [ ] **Step 2: Chạy test để xác nhận RED**

  Run: `.venv/bin/python -m pytest -q tests/test_tool_calling_generalization.py -k "distribution or candidate_pack"`
  Expected: FAIL vì chưa có candidate pack/audit.

- [ ] **Step 3: Cài đặt audit phân bổ**

  Thêm:

  ```python
  @dataclass(frozen=True)
  class DistributionAudit: ...

  def audit_candidate_distribution(cases: Sequence[CandidateCase]) -> DistributionAudit: ...
  ```

  Hàm trả `passed`, counts và errors; không tự sửa hoặc bỏ ca.

- [ ] **Step 4: Soạn 120 candidate không có gold**

  Tạo đúng một dòng JSON/case. Dùng source record riêng khi có; nếu tham khảo `soc-agent-traces-100k`, chỉ dùng alert/environment đã vệ sinh và ghi `source_kind="synthetic_auxiliary"`. Các ca contract/adversarial ghi rõ nguồn production schema hoặc tài liệu công khai. Không sao chép output/gold từ dev/frozen.

- [ ] **Step 5: Chạy test GREEN và in receipt phân bổ**

  Run: `.venv/bin/python -m pytest -q tests/test_tool_calling_generalization.py -k "distribution or candidate_pack"`
  Expected: PASS; 120/120, 24/54/30/12, robustness >=30.

- [ ] **Step 6: Commit, push và kiểm CI đúng SHA**

  ```bash
  git add evaluation/tool_calling/generalization.py evaluation/tool_calling/authoring/generalization_v1/candidates.jsonl tests/test_tool_calling_generalization.py
  git commit -m "data(r1): add 120 tool-calling candidates"
  git push origin master
  ```

### Task 3: Audit trùng lặp, lộ gold và tương thích production schema

**Files:**
- Modify: `evaluation/tool_calling/generalization.py`
- Create: `evaluation/tool_calling/authoring/generalization_v1/near_duplicate_waivers.jsonl`
- Modify: `tests/test_tool_calling_generalization.py`

**Interfaces:**
- Consumes: candidate pack từ Task 2, dev/frozen requests, production schemas.
- Produces: `audit_candidates(cases, existing_cases, schemas, waivers) -> CandidateAudit`, authoring command `audit`, và `candidate_audit.json` có thể tái tạo.

- [ ] **Step 1: Viết test RED cho exact duplicate, pivot duplicate, near duplicate, gold leakage và schema mismatch**

  Near duplicate dùng Jaccard trên token bigram sau Unicode casefold/chuẩn hóa khoảng trắng, threshold `>= 0.80`. Cặp vượt threshold phải block nếu không có waiver với `case_ids`, `reason`, `reviewed_by`. Test prompt-injection phải chứng minh nội dung candidate không thay system prompt/schema.

- [ ] **Step 2: Chạy test để xác nhận RED**

  Run: `.venv/bin/python -m pytest -q tests/test_tool_calling_generalization.py -k "duplicate or leakage or schema"`
  Expected: FAIL vì audit chưa tồn tại.

- [ ] **Step 3: Cài đặt audit fail-closed và receipt chuẩn hóa**

  Thêm:

  ```python
  def normalized_request(text: str) -> str: ...
  def token_bigram_jaccard(left: str, right: str) -> float: ...
  def audit_candidates(
      cases: Sequence[CandidateCase],
      existing_cases: Sequence[ToolCallCase],
      schemas: Sequence[dict[str, Any]],
      waivers: Sequence[dict[str, Any]],
  ) -> CandidateAudit: ...

  def main(argv: Sequence[str] | None = None) -> int: ...
  ```

  `main()` tại giai đoạn này chỉ có lệnh offline `audit`; nó không tạo provider hoặc chạy model.

- [ ] **Step 4: Chạy audit thật trên 120 candidate và xử lý lỗi soạn thảo**

  Run: `.venv/bin/python -m evaluation.tool_calling.generalization audit --candidates evaluation/tool_calling/authoring/generalization_v1/candidates.jsonl --output results/evaluation_v1/r1/generalization_v1/candidate_audit.json`
  Expected: command chỉ chạy offline; `passed=true`, không provider creation, không có cặp chưa xử lý.

- [ ] **Step 5: Chạy toàn bộ test Task 1–3**

  Run: `.venv/bin/python -m pytest -q tests/test_tool_calling_generalization.py tests/test_tool_calling_benchmark_contract.py tests/test_tool_calling_evaluator.py`
  Expected: PASS.

- [ ] **Step 6: Commit, push và kiểm CI đúng SHA**

  Commit message: `feat(r1): audit generalization candidates`.

### Task 4: Xuất hai gói duyệt mù và dừng tại human gate

**Files:**
- Create: `evaluation/tool_calling/authoring/generalization_v1/reviews/README.md`
- Create: `evaluation/tool_calling/authoring/generalization_v1/reviews/reviewer_a.jsonl`
- Create: `evaluation/tool_calling/authoring/generalization_v1/reviews/reviewer_b.jsonl`
- Modify: `evaluation/tool_calling/generalization.py`
- Modify: `tests/test_tool_calling_generalization.py`

**Interfaces:**
- Consumes: audited candidates từ Task 3.
- Produces: `write_blind_review_packs(cases, output_dir) -> ReviewPackReceipt`, `evaluate_review_gate(...) -> ReviewGate`, authoring command `review-gate`.

- [ ] **Step 1: Viết test RED cho review pack mù và gate hai người**

  Hai pack chỉ gồm `case_id`, `request`, `difficulty` và production schema reference; không chứa source metadata, `authoring_stratum` hoặc quyết định của reviewer còn lại. Gate cấm cùng reviewer ID, thiếu case, duplicate record, invalid tool/argument, bất đồng chưa phân xử và chữ ký rỗng.

- [ ] **Step 2: Chạy test để xác nhận RED**

  Run: `.venv/bin/python -m pytest -q tests/test_tool_calling_generalization.py -k review`
  Expected: FAIL.

- [ ] **Step 3: Cài đặt review pack/gate và tạo 240 biểu mẫu trống**

  Thêm:

  ```python
  def write_blind_review_packs(
      cases: Sequence[CandidateCase], output_dir: Path
  ) -> ReviewPackReceipt: ...

  def evaluate_review_gate(
      cases: Sequence[CandidateCase],
      review_a_path: Path,
      review_b_path: Path,
      adjudication_path: Path | None,
      schemas: Sequence[dict[str, Any]],
  ) -> ReviewGate: ...
  ```

- [ ] **Step 4: Chạy gate thật và xác nhận trạng thái chờ duyệt**

  Run: `.venv/bin/python -m evaluation.tool_calling.generalization review-gate --candidates evaluation/tool_calling/authoring/generalization_v1/candidates.jsonl --reviews evaluation/tool_calling/authoring/generalization_v1/reviews`
  Expected: exit khác 0 với `status=pending_human_review`, `reviewed_a=0/120`, `reviewed_b=0/120`, `provider_created=false`.

- [ ] **Step 5: Commit/push review pack và kiểm CI**

  Commit message: `feat(r1): add blind gold review gate`.

- [ ] **Step 6: STOP bắt buộc**

  Bàn giao review pack cho hai người thật. Không đi sang Task 5 nếu chưa nhận lại đủ hai file review có định danh/chữ ký và biên bản phân xử mọi bất đồng. Agent không được điền thay.

### Task 5: Tạo split đã duyệt và khóa hash

**Files:**
- Create: `evaluation/tool_calling/authoring/generalization_v1/reviews/adjudication.jsonl`
- Create: `evaluation/tool_calling/benchmarks/generalization_v1/gen_001.json` … `gen_120.json`
- Create: `evaluation/tool_calling/benchmarks/generalization_v1/GENERALIZATION.lock`
- Modify: `evaluation/tool_calling/generalization.py`
- Modify: `tests/test_tool_calling_generalization.py`

**Interfaces:**
- Consumes: `ReviewGate(status="approved")` từ Task 4.
- Produces: `build_locked_split(...) -> GeneralizationLock`, `verify_generalization_lock(...) -> LockVerification`, authoring command `build-lock`.

- [ ] **Step 1: Viết test RED cho builder và lock**

  Test fixture đã duyệt phải tạo `ToolCallCase` đúng production schema; review pending phải không tạo directory. Lock ghi case hashes, split hash, candidate/review/adjudication hashes, scorer files/hashes, prompt hash, schema hash, 120 IDs và distribution theo final gold.

- [ ] **Step 2: Chạy test RED**

  Run: `.venv/bin/python -m pytest -q tests/test_tool_calling_generalization.py -k "locked_split or lock_verification"`
  Expected: FAIL.

- [ ] **Step 3: Cài đặt builder/lock verifier**

  ```python
  def build_locked_split(
      cases: Sequence[CandidateCase], review_gate: ReviewGate,
      output_dir: Path, scorer_files: Sequence[Path], schemas: Sequence[dict[str, Any]],
  ) -> GeneralizationLock: ...

  def verify_generalization_lock(split_dir: Path, lock_path: Path) -> LockVerification: ...
  ```

- [ ] **Step 4: Build split thật sau human approval và kiểm 120/120**

  Run: `.venv/bin/python -m evaluation.tool_calling.generalization build-lock --candidates evaluation/tool_calling/authoring/generalization_v1/candidates.jsonl --reviews evaluation/tool_calling/authoring/generalization_v1/reviews --output evaluation/tool_calling/benchmarks/generalization_v1`
  Expected: 120 JSON, distribution final đúng 24/54/30/12, tất cả review approved, lock verification PASS.

- [ ] **Step 5: Regression và commit/push/CI**

  Run: `.venv/bin/python -m pytest -q tests/test_tool_calling_generalization.py tests/test_tool_calling_benchmark_contract.py tests/test_tool_calling_decision_runner.py tests/test_tool_calling_evaluator.py`
  Expected: PASS.
  Commit message: `data(r1): lock reviewed generalization split`.

### Task 6: Tích hợp CLI/runner/provenance và chặn trước provider

**Files:**
- Modify: `evaluation/tool_calling/__main__.py`
- Modify: `evaluation/tool_calling/decision_runner.py`
- Modify: `evaluation/tool_calling/provenance.py`
- Modify: `tests/test_tool_calling_cli.py`
- Modify: `tests/test_tool_calling_generalization.py`

**Interfaces:**
- Consumes: verified lock từ Task 5.
- Produces: `validate_generalization_run_gate(...) -> RunGateReceipt`; CLI `list`, `preflight`, `run` dùng chung R1 path.

- [ ] **Step 1: Viết test RED cho CLI và provider guard**

  Monkeypatch `create_provider` để raise nếu bị gọi. Mọi trường hợp review/lock/hash/dirty-tree/wrong-branch/missing authorization/budget fail phải trả lỗi trước provider. `dev` và `frozen` giữ hành vi cũ.

- [ ] **Step 2: Chạy test RED**

  Run: `.venv/bin/python -m pytest -q tests/test_tool_calling_cli.py tests/test_tool_calling_generalization.py -k "cli or provider or run_gate"`
  Expected: FAIL.

- [ ] **Step 3: Cài đặt gate trước `DecisionRunner(...)`**

  ```python
  def validate_generalization_run_gate(
      split_dir: Path,
      lock_path: Path,
      authorization: Mapping[str, Any],
      requested_model: str,
      budget_limit_usd: Decimal,
      git_identity: Mapping[str, Any],
  ) -> RunGateReceipt: ...
  ```

  CLI thêm `generalization_v1` cho `list`; thêm `preflight` và `lock`; `run --split generalization_v1` bắt buộc `--authorization` và `--budget-usd` trước khi khởi tạo runner/provider.

- [ ] **Step 4: Mở rộng provenance mà không đổi hash lịch sử**

  Với split mới, ghi `generalization_lock_sha256`, candidate/review/audit hashes, authorization identity và `provider_created_after_gate=true`. Dev/frozen serialization giữ nguyên.

- [ ] **Step 5: Chạy regression GREEN**

  Run: `.venv/bin/python -m pytest -q tests/test_tool_calling_cli.py tests/test_tool_calling_generalization.py tests/test_tool_calling_decision_runner.py tests/test_tool_calling_benchmark_contract.py`
  Expected: PASS.

- [ ] **Step 6: Commit, push và kiểm CI đúng SHA**

  Commit message: `feat(r1): gate generalization runs before provider creation`.

### Task 7: Thống kê, báo cáo chung và partial artifact

**Files:**
- Modify: `evaluation/tool_calling/generalization.py`
- Modify: `evaluation/tool_calling/metrics.py`
- Modify: `evaluation/tool_calling/__main__.py`
- Modify: `tests/test_tool_calling_generalization.py`

**Interfaces:**
- Consumes: `CaseResult`, locked manifest metadata và provider telemetry.
- Produces: `wilson_interval`, `exact_mcnemar`, `full_denominator_argument_coverage`, `build_generalization_report`.

- [ ] **Step 1: Viết test RED cho các giá trị thống kê đã khóa**

  Test Wilson 22/24 phải xấp xỉ `[0.7415, 0.9768]`; 5/5 xấp xỉ `[0.5655, 1.0]`. McNemar với discordant 4–1 phải cho two-sided exact `p=0.375`. Full-denominator coverage của artifact dev lịch sử phải là required `37/41`, critical `29/31` mà không sửa artifact.

- [ ] **Step 2: Viết test RED cho báo cáo tách mẫu số và partial failure**

  Báo cáo phải có hai hàng `22/24` và `x/120`, không có `/144`. Provider lỗi giữa suite phải lưu `run_status=partial_failure`, expected 120 IDs, completed IDs, failed/current ID, usage/cost đã phát sinh và `official_eligible=false`; không retry.

- [ ] **Step 3: Chạy test RED**

  Run: `.venv/bin/python -m pytest -q tests/test_tool_calling_generalization.py -k "wilson or mcnemar or coverage or report or partial"`
  Expected: FAIL.

- [ ] **Step 4: Cài đặt thống kê bằng standard library**

  ```python
  def wilson_interval(successes: int, total: int, confidence: float = 0.95) -> tuple[float, float]: ...
  def exact_mcnemar(left: Mapping[str, bool], right: Mapping[str, bool]) -> McNemarResult: ...
  def full_denominator_argument_coverage(results: Sequence[CaseResult]) -> ArgumentCoverage: ...
  def build_generalization_report(...) -> dict[str, Any]: ...
  ```

- [ ] **Step 5: Chạy GREEN và regression metrics**

  Run: `.venv/bin/python -m pytest -q tests/test_tool_calling_generalization.py tests/test_tool_calling_evaluator.py tests/test_tool_calling_decision_runner.py`
  Expected: PASS.

- [ ] **Step 6: Commit, push và kiểm CI đúng SHA**

  Commit message: `feat(r1): report statistical uncertainty and full coverage`.

### Task 8: Workflow, tài liệu và preflight offline cuối

**Files:**
- Create: `.github/workflows/r1-generalization-v1.yml`
- Modify: `evaluation/tool_calling/README.md`
- Modify: `evaluation/tool_calling/benchmarks/README.md`
- Modify: `README.md`
- Modify: `tests/test_tool_calling_generalization.py`

**Interfaces:**
- Consumes: CLI/gates/report từ Tasks 5–7.
- Produces: workflow có `preflight` không secret và job model cần manual authorization; tài liệu tái lập.

- [ ] **Step 1: Viết test RED kiểm workflow contract**

  Test YAML/text phải khóa Python 3.11, branch `master`, exact 120, model input, budget input, zero retries, artifact upload ngay cả khi partial failure, và không có `pull_request`/`push` trigger cho paid job. Job model không chạy nếu preflight/review/lock/authorization chưa đạt.

- [ ] **Step 2: Chạy test RED**

  Run: `.venv/bin/python -m pytest -q tests/test_tool_calling_generalization.py -k workflow`
  Expected: FAIL.

- [ ] **Step 3: Tạo workflow và cập nhật tài liệu**

  `workflow_dispatch` nhận exact model, budget và xác nhận split SHA. Receipt ghi `github.actor`, run ID/attempt, commit SHA và inputs; không chứa secret. README nêu rõ 22/24 là dev, `x/120` là split mở rộng, tám frozen vẫn riêng và decision-only không phải E2E.

- [ ] **Step 4: Chạy toàn bộ kiểm thử offline và preflight**

  Run: `.venv/bin/python -m pytest -q`
  Expected: PASS, 0 failed.

  Run: `.venv/bin/python -m evaluation.tool_calling preflight generalization_v1 --output results/evaluation_v1/r1/generalization_v1/preflight.json`
  Expected: PASS chỉ khi human review/lock đã đạt; nếu chưa đạt, fail-closed đúng gate và không tạo provider.

- [ ] **Step 5: Commit, push và kiểm CI đúng SHA**

  Commit message: `ci(r1): add guarded generalization workflow`.

### Task 9: Một suite model thật và bàn giao kết quả

**Files:**
- Create: `results/evaluation_v1/r1/generalization_v1/<run-id>/report.json`
- Create: `results/evaluation_v1/r1/generalization_v1/<run-id>/REPORT.md`
- Create: `results/evaluation_v1/r1/generalization_v1/<run-id>/receipt.json`
- Modify: `README.md`

**Interfaces:**
- Consumes: green CI đúng SHA, approved human gate, verified lock, exact model/budget authorization riêng.
- Produces: một authentic suite artifact 120 ca hoặc partial failure artifact; không retry.

- [ ] **Step 1: Xác minh lại gate ngay trước lượt trả phí**

  Kiểm exact HEAD/origin/master/CI SHA, clean tree, 120 lock, review identities, zero unresolved, model, giá, worst-case cost, secret presence và authorization. Nếu thiếu bất kỳ mục nào: ghi blocker receipt và STOP paid run.

- [ ] **Step 2: Chạy đúng một workflow dispatch**

  Không rerun job/workflow. Runner lưu artifact sau từng ca bằng atomic replace. Provider/telemetry error làm suite dừng và giữ partial artifact.

- [ ] **Step 3: Tải artifact, xác minh hash và tính báo cáo**

  Báo case success + Wilson 95%, call metrics, no-tool, forbidden/extra/duplicate, full-denominator argument coverage, nhóm, latency, tokens, cost và limitations. Lower bound <80% vẫn bàn giao nguyên kết quả và không sửa benchmark/prompt.

- [ ] **Step 4: Chạy verification cuối**

  Run: `.venv/bin/python -m pytest -q`
  Expected: PASS.

  Kiểm artifact count/hash và GitHub Actions status cho đúng SHA. Không claim hoàn tất nếu receipt thiếu hoặc CI khác SHA.

- [ ] **Step 5: Commit/push báo cáo và kiểm CI đúng SHA**

  Commit message: `docs(r1): publish generalization v1 results`.

## Completion Contract

- Dev/frozen/historical identities không đổi.
- Candidate 120 ca và audit receipt đạt; không có final gold do agent tự duyệt.
- Hai reviewer độc lập và mọi adjudication có receipt.
- Split/lock được tạo sau review, xác minh đúng 120 và đúng phân bổ final.
- CLI dùng chung runner/scorer, fail-closed trước provider.
- Toàn bộ pytest và CI đúng SHA đạt.
- Tối đa một suite model thật khi có quyền riêng; không rerun.
- Báo cáo tách 22/24 và x/120, có Wilson interval và giới hạn decision-only.

