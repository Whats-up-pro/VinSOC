# NEXT TASK FOR AGENT A - TRIỂN KHAI DUALSQL-LITE NHƯ PHƯƠNG ÁN SO SÁNH VỚI E0

Làm trực tiếp trên `master` của repo `Whats-up-pro/VinSOC`. Trước khi sửa:

1. Chạy `git fetch origin` và đồng bộ với `origin/master`.
2. Ghi initial SHA và `git status --short`.
3. HEAD được audit gần nhất là `2715c9537da7da38a527582e16f918503365751c`; nếu origin đã mới hơn thì dùng HEAD mới.
4. Giữ nguyên `.env`, file untracked và artifact lịch sử.
5. Không dùng `git clean`, `git reset --hard`, `git add .`, branch hoặc PR.
6. Chỉ stage các file thuộc task.
7. Đọc:
   - `docs/superpowers/specs/2026-09-28-vinsoc-r1-r2-finalization-design.md`
   - `docs/superpowers/plans/2026-09-29-vinsoc-r1-r2-finalization.md`

Chỉ thị này làm rõ và thay thế nội dung triển khai ở Task 6-8 và Task 12 của plan hiện tại khi có điểm khác nhau.

## Mục tiêu

Giữ E0 one-shot Text-to-SQL làm baseline. DualSQL-Lite là kiến trúc bổ sung để so sánh, chưa thay thế E0.

Tạo series mới:

`dualsql_lite_ctu_gpt5_v1`

Series phải đo bốn điều kiện:

- E0: one-shot generator, không linker, không DB tool.
- E1: Schema Linker có DB tools, sau đó generator one-shot không có DB tools.
- E2: không linker, generator có DB tools.
- E3: Schema Linker có DB tools và generator cũng có DB tools.

Execution Accuracy là metric chính. Không mặc định E3 là winner.

## Evidence hiện có

R2 GPT-5 Mini E0 đã chạy:

- Actions run: `36520685612`
- Model: `gpt-5-mini-2025-08-07`
- Kết quả: EX 0/8
- Syntax Validity: 8/8
- Execution Success: 8/8
- Report:
  `results/evaluation_v1/ctu_network_public/gpt5_e0/36520685612/ctu-r2-result.json`
- Report SHA-256:
  `33b35678171309c1a8958c1d9818499915986942e6936a03428df8fa0544bc15`

Lỗi E0 chủ yếu là sai stored representation của `source_dataset`, `label`; case 008 chọn projection/grouping rộng hơn yêu cầu.

DualSQL GPT-4.1 Mini lịch sử có E0/E2 5/8 và E1/E3 1/8, nhưng dùng snapshot, model và request contract khác. Giữ nguyên toàn bộ:

- `evaluation/dualsql_lite/`
- `evaluation/dualsql_lite/SELECTED_CONFIG.lock`
- `results/evaluation_v1/public_pilot/dualsql_lite/`

Không sửa hoặc dùng các điểm cũ làm baseline trực tiếp cho series mới.

## Phase 0 - Khép snapshot builder đang làm dở

Rà:

- `scripts/build_ctu_network_frozen_snapshot.py`
- `tests/test_ctu_network_frozen_builder.py`

CSV staging và DuckDB COPY phải có contract tường minh:

- delimiter `,`
- quotechar `"`
- doublequote `True`
- quoting `csv.QUOTE_MINIMAL`
- lineterminator `\n`
- `AUTO_DETECT FALSE`
- `DELIMITER ','`
- `QUOTE '"'`
- `ESCAPE '"'`
- `NULL ''`

Viết regression test cho VARCHAR chứa dấu phẩy và nullable values. Build S1/S4 hai lần offline, xác nhận logical hash giống nhau, row counts đúng và không có model call.

Chưa chạy frozen model ở phase này.

## Phase 1 - Khóa E0 compatibility

Tạo:

- `evaluation/dualsql_lite_ctu_gpt5/__init__.py`
- `evaluation/dualsql_lite_ctu_gpt5/contract.py`
- `evaluation/dualsql_lite_ctu_gpt5/SERIES.lock`
- `tests/test_dualsql_ctu_gpt5.py`

Implement:

```python
verify_e0_baseline(
    report_path: Path,
    series_lock_path: Path,
) -> BaselineEvidence
```

Kiểm tra đồng thời:

- đúng 8 case và đủ case ID;
- run complete và usage hợp lệ;
- requested/actual model đúng;
- `reasoning_effort=low`;
- không có `temperature`;
- cap 1000;
- retries 0;
- split hash;
- logical snapshot hash;
- source hashes;
- scorer/builder hashes;
- system prompt hash;
- schema context hash;
- report SHA cố định.

Chỉ tái sử dụng E0 nếu toàn bộ identity phù hợp với E0 condition của series mới. Nếu có mismatch, STOP và báo cụ thể. Không tự rerun E0.

## Phase 2 - CTU-only database tools

Tạo:

`evaluation/dualsql_lite_ctu_gpt5/tools.py`

Cung cấp đúng ba tools:

1. `database_profiler`
2. `value_search`
3. `sql_probe`

Phạm vi chỉ gồm `network_flows`.

`value_search` phải tìm được stored values thật của:

- `source_dataset`
- `label`
- `protocol`

Không tạo alias theo case ID hoặc literal benchmark. Catalog phải dựng trực tiếp từ verified CTU snapshot và có deterministic SHA-256.

Tool output phải có controller-owned `evidence_id`. Mỗi output bị giới hạn byte; SQL Probe tối đa 20 rows. Chặn write SQL, multi-statement, external files, URLs, extension loading, provenance/internal tables và remote scans.

Không serialize raw DuckDB exception. Chỉ trả safe error category.

## Phase 3 - GPT-5 agent controller

Tạo:

- `evaluation/dualsql_lite_ctu_gpt5/prompts.py`
- `evaluation/dualsql_lite_ctu_gpt5/agents.py`

Cả hai role dùng:

```text
model = gpt-5-mini-2025-08-07
reasoning_effort = low
temperature = absent
max_completion_tokens = 1000
SDK retries = 0
```

Schema Linker chỉ trả bảng và cột. Controller tự gắn grounded values cùng evidence ID từ tool trajectory. Không bắt model tự chứng nhận provenance.

Cho phép nhiều native tool calls trong một turn nếu tổng call chưa vượt giới hạn.

Giới hạn cho mỗi role:

- tối đa 5 model turns;
- tối đa 5 DB tool calls;
- một final submission.

E1 generator chạy one-shot, không tools. E2 generator có tools. E3 linker và generator đều có tools.

Usage, response ID và actual model phải được ghi trước khi parse tool arguments. Malformed arguments là model-level failure và vẫn giữ charged usage.

Gold SQL, gold result, scorer verdict và benchmark annotations không được xuất hiện trong model messages, tool arguments, tool results hoặc linked schema.

## Phase 4 - Một runner cho một condition

Tạo:

- `evaluation/dualsql_lite_ctu_gpt5/runner.py`
- `.github/workflows/r2-dualsql-ctu-gpt5.yml`

Interface:

```python
run_condition(
    condition: Literal["E1", "E2", "E3"],
    snapshot_path: Path,
    output_path: Path,
    client: Any,
    series_lock: SeriesLock,
) -> ConditionReport
```

Workflow chỉ có `workflow_dispatch`, không có `push`.

Workflow chỉ chấp nhận `E1`, `E2`, `E3`. E0 được lấy từ artifact đã khóa sau khi compatibility gate đạt.

Mỗi condition tạo artifact riêng dưới:

`results/evaluation_v1/ctu_network_public/dualsql_lite_ctu_gpt5_v1/<run-id>/`

Report phải append-only và có partial evidence sau mỗi charged response.

## Phase 5 - Budget và provenance

Preflight tính từ serialized request thật và bounded tool context.

Cận call tối đa:

- E1: 48 model calls cho 8 case.
- E2: 40 model calls cho 8 case.
- E3: 80 model calls cho 8 case.

Trước từng call:

```text
known_spend + conservative_remaining_bound < suite_budget
```

Tổng conservative ceiling đề xuất cho E1-E3 không vượt `$0.75`. Nếu cận tính thật vượt mức này, STOP trước khi tạo client và báo breakdown.

Không tự mua credit, tăng limit hoặc đổi model.

Report phải ghi:

- git SHA;
- condition;
- benchmark/split hash;
- snapshot logical hash;
- scorer hash;
- model config hash;
- prompt hashes;
- tool schema và implementation hashes;
- catalog hash;
- requested/actual model;
- calls, tokens, calculated cost và latency;
- per-case SQL, trajectory và score;
- partial state khi dừng.

## Phase 6 - Tests và CI

Test tối thiểu:

- E0 identity mismatch bị chặn offline.
- GPT-5 request không chứa `temperature`.
- Hai valid tool calls trong một turn đều được xử lý.
- Tool call thứ sáu bị chặn.
- Turn thứ sáu bị chặn.
- Question literal được dùng mà không cần DB provenance.
- Giá trị nhận từ DB phải có controller provenance.
- Invented grounded value bị từ chối.
- Gold sentinel không xuất hiện trong inference inputs.
- `source_dataset`, `label`, `protocol` tìm được từ snapshot thật.
- Read-only safety và external access gate.
- Raw database exception không leak.
- Usage được lưu trước parse failure.
- Budget bị chặn trước provider creation.
- Partial report được giữ sau charged failure.
- Selection từ chối report khác identity.

Chạy:

```bash
python -m pytest tests/test_dualsql_ctu_gpt5.py -q
python -m pytest tests/test_dualsql_tools.py tests/test_dualsql_experiments.py -q
python -m pytest -q
python -m py_compile evaluation/dualsql_lite_ctu_gpt5/*.py
git diff --check
```

Nếu local thiếu dependency, báo đúng command và lỗi. Không gọi test chưa chạy là pass.

Commit/push code, test và workflow lên `master`. Chờ CI Python 3.11/3.12 xanh trên đúng final implementation SHA.

## Phase 7 - Paid development series

E1, E2 và E3 phải chạy từ cùng một git SHA, prompt version, tool implementation và catalog identity.

Thứ tự:

1. Preflight E1, chạy E1 đúng một lần.
2. Preflight E2, chạy E2 đúng một lần.
3. Preflight E3, chạy E3 đúng một lần.

Không sửa code, prompt hoặc tools giữa ba condition.

Không retry case vì SQL sai. Provider/model/snapshot identity failure làm run invalid và phải STOP. Không tự dispatch lần thứ hai.

## Phase 8 - Selection và báo cáo

Tạo:

- `evaluation/dualsql_lite_ctu_gpt5/selection.py`
- `evaluation/dualsql_lite_ctu_gpt5/SELECTED_CONFIG.lock`
- `docs/evaluation/r2_dualsql_ctu_gpt5_dev.md`

Headline metric:

```text
Execution Accuracy = correct execution results / 8
```

Báo thêm:

- raw correct count;
- Syntax Validity;
- Execution Success;
- Safety Rejection;
- linker completion;
- model calls;
- DB tool calls;
- input/output tokens;
- cost;
- latency;
- per-case error class.

Selection order:

1. Execution Accuracy cao hơn.
2. Cost thấp hơn.
3. Model calls ít hơn.
4. Latency thấp hơn.
5. Kiến trúc đơn giản hơn theo E0, E1, E2, E3.

Với 8 case, mỗi case tương đương 12.5 điểm phần trăm. Chỉ claim "strong pilot signal" nếu hơn E0 ít nhất 2/8 case. Không claim statistical significance.

Nếu E0 thắng, giữ E0 làm final configuration và ghi DualSQL không chứng minh được cải thiện. Nếu E1/E2/E3 thắng, đó là candidate cho frozen; E0 vẫn được giữ làm baseline trong báo cáo.

## Phase 9 - Frozen comparison gate

Chưa chạy frozen trước khi `SELECTED_CONFIG.lock` được commit và CI xanh.

Nếu E0 thắng dev, chạy E0 frozen đúng một lần.

Nếu E1/E2/E3 thắng dev, trước frozen phải cập nhật spec/plan để khóa một trong hai protocol:

1. Selected-only frozen: chạy winner một lần, comparison với E0 chỉ được claim trên dev.
2. Paired frozen: một workflow nguyên khối chạy E0 và winner, mỗi condition đúng một lần, không hiển thị kết quả trung gian và không tuning sau đó.

Mục tiêu hiện tại là so sánh DualSQL với baseline nên ưu tiên paired frozen, nhưng không tự chạy cho đến khi protocol được ghi vào spec và lock.

## Báo cáo sau mỗi checkpoint

Báo:

- initial/final SHA;
- files changed;
- tests thật đã chạy;
- CI URL;
- Actions run URL nếu có;
- artifact ID/digest;
- condition và count;
- EX, syntax, execution success, safety;
- calls, usage, cost và latency;
- blocker hoặc deviation.

Không chạy demo, R1 paid suite, ThreatFox, OTRF hoặc bất kỳ model/snapshot nào ngoài phạm vi task này.

