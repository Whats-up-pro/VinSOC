# VinSOC — báo cáo ba demo có API thật ngày 13/10/2026

## Kết quả cho mentor

Đã thực hiện một attempt thật cho từng case còn thiếu, nhận **23/23 responses**.
Chi phí mới **$0.02040420**, cumulative query-demo allocation **$0.08155920**,
còn **$2.91844080** trong cap $3; unknown exposure false. Scope đã consumed và
authorization secret đã được xóa. Không gọi model lại hoặc nâng cap để cứu điểm.

| Case | Calls | Chi phí | Kết quả thực tế |
|---|---:|---:|---|
| UDP ở S5, không ở S7 — `ctu_cross_66b8e92a76c3359b` | 7 | $0.00529475 | SQL/worker trả 9.780 hàng; pipeline partial trước assessment/scorer |
| Hai byte fields NULL — `ctu_cross_3f659571f998adb0` | 8 | $0.00703140 | SQL chạy được, EX false; assessment observations rỗng bị từ chối |
| AVG theo protocol lớn hơn AVG toàn S7 — `ctu_cross_bce6d3679ade4cd6` | 8 | $0.00807805 | Trả TCP, EX/facts/provenance/technical đạt; awaiting_human |

Case đếm IP chung `ctu_cross_708b66575657429a` từ run trước trả **459**, cũng
awaiting_human theo reporter đã sửa. Viewer mới giữ 4/4 records: **2 awaiting_human,
1 incomplete, 1 technical_failed**, không missing trong bốn ID đã chọn.

Live workflow exit 1 vì aggregate technical_incomplete, không phải vì không có
API response hoặc thiếu ngân sách. Calibration/evaluation/pipeline32 vẫn NOT_RUN.

## Mốc nguồn và bằng chứng

| Mốc | SHA | CI / workflow |
|---|---|---|
| Runner ba case, guards ngân sách riêng từng case | `89409ea4d3f55b818948a7ffa3214326ffb67589` | [CI 38365972443](https://github.com/Whats-up-pro/VinSOC/actions/runs/38365972443) success |
| Restore đúng source bytes từ mirror pin | `1263308b05f06defa48ee4b1ab6712d16e15850c` | [CI 38368039406](https://github.com/Whats-up-pro/VinSOC/actions/runs/38368039406) success |
| Source upstream bị quota trước runner | `89409ea...` | [38366545085](https://github.com/Whats-up-pro/VinSOC/actions/runs/38366545085): 0 model calls |
| Cloud preflight cả ba | `1263308...` | [38368861277](https://github.com/Whats-up-pro/VinSOC/actions/runs/38368861277): 0 attempts/responses/client=false |
| Live API | `1263308...` | [38369416643](https://github.com/Whats-up-pro/VinSOC/actions/runs/38369416643): 23/23, technical_incomplete |

Producer CI mỗi Python 3.11/3.12: **1398 passed, 7 regression skips**; required
offline **102 passed, 0 skipped**; required real-data **13 passed, 0 skipped**.
13 DB/120 gold được giữ nguyên. 3640 protected files không đổi; hai ZIP pin không đổi.

Local full suite bị dừng vì chậm; hai failures đã tái hiện riêng: thiếu snapshot
legacy network qua VINSOC_LOCAL_SNAPSHOT và Windows thiếu quyền symlink (1314).
Không ghi local full suite PASS, không sửa hoặc skip tests để lấy nghiệm thu.

Kiểm handoff cuối trong `.venv`: reporter/viewer **45 passed, 0 skipped**;
đối chiếu bytes public artifact và bốn projections đạt. Lệnh `python` mặc định
trỏ Python 3.13 thiếu sqlglot, nên lần collection đầu lỗi; đã chạy lại bằng
`.\.venv\Scripts\python.exe`, không thay dependencies toàn máy.
Receipt chi tiết: `mentor_four_case_demo_20261013/verification_receipt.json`.

## Các bước, lệnh và nhận xét

### 1. Đối soát phạm vi và tiền

Đọc selection cố định và 10 prior receipts thật, xác minh chi phí $0.06115500.
Fetch official model documents của đúng hai snapshots; giá giữ GPT-5 mini
$0.25/$0.025/$2 và GPT-4.1 mini $0.40/$0.10/$1.60 input/cached/output mỗi triệu.

```powershell
git fetch origin master
git rev-parse HEAD
git rev-parse origin/master
gh secret list --repo Whats-up-pro/VinSOC
```

Cận theo full context window là $1.6732608/case. Tổng ba worst-case bounds lớn
hơn $3; thực thi conditional sequential với full-case preflight trước mỗi case,
đối soát actual usage của case trước. Không giảm reserve hoặc cap để cho qua gate.
Receipt: `remaining_demo3_20261013/release_preparation.json`.

### 2. Runner và TDD

Thêm selection_mode=remaining3 cho ba IDs chưa chạy; immutable batch claim và
per-case claims/checkpoints; reject scope đã dùng, unknown cost và altered source.
New guards được quan sát RED trước implementation, GREEN sau đó. Required tests
được thêm vào CI, skip ở required job làm fail.

```powershell
py -m pytest tests/test_query_remaining_demo.py tests/test_query_cloud.py tests/test_query_acceptance_preflight.py tests/test_query_pipeline_contract.py tests/test_query_journal_persistence.py tests/test_query_pipeline_reporting.py tests/test_query_cli_viewer.py tests/test_network_query_policy.py -q
py -m compileall -q scripts/run_query_demo_cloud.py scripts/run_query_remaining_demo_cloud.py evaluation/finalization/query_runtime_validation.py
py scripts/verify_query_preservation.py
git diff --check
```

Targeted trước cập nhật remote: 105 passed; sau đồng bộ guard mới, required 101
passed. Mirror guard RED rồi GREEN nâng required lên 102; producer CI xác nhận.

### 3. Source blocker và khôi phục đúng archive

```powershell
gh workflow run query-demo-once.yml --repo Whats-up-pro/VinSOC --ref master -f ci_run_id=38365972443 -f run_mode=preflight -f selection_mode=remaining3
gh run download 38366545085 --repo Whats-up-pro/VinSOC --dir .vinsoc/remaining-demo3-preflight-38366545085
```

GDrive trả HTML quota, existing SOURCE_CHECKSUM_MISMATCH chặn trước SDK. Lưu
`source_blocker_receipt.json`; không đổi lock, không rebuild hoặc export DB.

Mirror public `HAL-9001/spider-databases@4a01bbac6520cd35b216db9e1724e5e1ada60aa4`
được tải và kiểm **205800266 bytes**, SHA-256
`00636695dabed6b5f4b8328a16b13e069a2f16591d5efcce57660669c85b121b` đúng pin gốc.
Workflow dùng `validate_original_query_data --restore-sources --archive` để kiểm
toàn archive và pinned members; source/DB identity không thay đổi.

### 4. CI và preflight thật trên Linux

```powershell
gh run watch 38368039406 --repo Whats-up-pro/VinSOC --exit-status
gh workflow run query-demo-once.yml --repo Whats-up-pro/VinSOC --ref master -f ci_run_id=38368039406 -f run_mode=preflight -f selection_mode=remaining3
gh run watch 38368861277 --repo Whats-up-pro/VinSOC --exit-status
gh run download 38368861277 --repo Whats-up-pro/VinSOC --dir .vinsoc/remaining-demo3-preflight-38368861277
```

Cả ba release authorized, attempted=received=0, client_created=false; chưa claim
paid windows. Mirror source đã đóng blocker; worker giữ namespace/mount/memory/CPU.

### 5. Live dispatch và lưu response trước parse

Authorization JSON riêng được gửi vào repository secret qua stdin; không log key.
Đây là quyền mới cho ba demos trong original $3 cap, không mượn window network cũ.

```powershell
gh workflow run query-demo-once.yml --repo Whats-up-pro/VinSOC --ref master -f ci_run_id=38368039406 -f run_mode=live -f selection_mode=remaining3
gh run watch 38369416643 --repo Whats-up-pro/VinSOC --exit-status
gh secret delete VINSOC_QUERY_DEMO_AUTH_JSON --repo Whats-up-pro/VinSOC
gh run download 38369416643 --repo Whats-up-pro/VinSOC --dir .vinsoc/remaining-demo3-live-38369416643
```

Real model roles: routing 3, R2 18, assessment 2. Private journals giữ raw request,
response và usage trước parse; public exports giữ cost/request/response/provider IDs.
Không commit private journals. UDP chưa gọi assessment; invalid NULL assessment
vẫn được tính tiền. Không có thêm paid attempt sau khi batch kết thúc.

### 6. Phân tích UDP partial

Checkpoint giữ cả SQL và execution thật, row_count=9780, truncated=false,
result hash hợp lệ. Rows JSON riêng có 186810 bytes, vượt cap tool_response
32768 bytes. Cloud chỉ lưu exception class ValueError; category payload-limit
là chẩn đoán từ retained execution và guard hiện hành, không giả là literal log.

Không tạo EX posthoc: scorer chưa chạy trong pipeline. Một gold-cardinality
diagnostic offline trên DB gốc xác nhận 9780 rows; đó không phải model score hay
demo run mới. Không sửa SQL/giảm rows để nâng record thành pass.

### 7. Phân tích NULL failed

SQL model thực sự chạy:

```sql
SELECT protocol, COUNT(*) AS flow_count
FROM network_flows
WHERE source_dataset = 'ctu13_s7'
  AND bytes_out IS NULL
  AND bytes_in IS NULL
GROUP BY protocol
ORDER BY protocol ASC;
```

DB trả empty rows. Gold contract đếm có điều kiện trên toàn bộ protocol domain:
SUM(CASE WHEN ... THEN 1 ELSE 0 END), giữ các nhóm 0. Vì vậy EX=false với
RESULT_MISMATCH; execution_success=true không thay EX. Raw assessment dẫn IDs
nhưng observations=[]; contract chặn MISSING_QUERY_OBSERVATION. Stored validation
sau rejection cũng ghi QUERY_RESULT_NOT_CITED vì không có accepted assessment.
Không sửa gold hoặc model response để gọi case thành công.

### 8. Luồng AVG thành công để show mentor

Original question → native network_query → value/schema grounding → SQL model
so sánh AVG của mỗi protocol với AVG toàn S7 → worker read-only → typed result
`TCP` → evidence `ev_f03ff2ae_2`/`ev_9c0fcad4_3` → assessment → independent replay
và evaluator EX=true → awaiting_human.

Assessment quan sát `protocol=TCP` và cite đúng IDs; risk UNKNOWN, nêu thiếu
CTI/endpoint context. Prose semantics vẫn cần người thật review. Không auto-approve.

### 9. Viewer và preservation

[Viewer bốn case](../../results/evaluation_v1/text2sql_integration_v1/mentor_four_case_demo_20261013/index.html)
và [runbook mentor](../../results/evaluation_v1/text2sql_integration_v1/mentor_four_case_demo_20261013/README.md)
đọc record thật, escape HTML và giữ producer riêng. Summary không fake 192/32
predictions hoặc thay identities để ghép các runs khác SHA thành một suite.

Mỗi viewer inventory riêng giữ mẫu số 32. Landing page demo chỉ báo coverage của
bốn ID được chọn và ghi các suite chính thức chưa chạy. HTML preview UDP tám
hàng là preview màn hình, không thay full rows trong immutable JSON.

## Artifacts và gate còn mở

- Live artifact `11798712801`, digest
  `sha256:f8646fbb512d7de14a5b694c1afafe84ee3daaf580537da71cf71aa620e38cfe`.
- Preflight artifact `11798596416`, digest
  `sha256:795dc07699f2240e5d53276be50e39085c8fe7085004501b2bca9da26cd74536`.
- Chi tiết expiry/file hashes/request IDs: `source_artifacts.json`,
  `artifact_manifest.json`, `demo_summary.json` và public source reports.
- Closed: source archive transport, real-data/worker CI, paid authorization cho
  ba scopes, 23 responses/usage/cost reconciliation, AVG technical path.
- Open: UDP payload envelope/partial lifecycle; NULL zero-group semantics và
  empty-observation model output; human review của hai valid traces; diagnostic
  module grounding; 48 calibration, 192 evaluation và pipeline32 chính thức.
- Old source audit manifest mismatch 8/9 đã được ghi ở handoff trước, không sửa
  lại lịch sử để biến thành exact artifact acceptance.

Nhận định: đã có luồng end-to-end mới có thể trình bày và hai edge cases thật.
Kết quả phản ánh đúng năng lực hiện tại: có truy vấn đúng, có lỗi nghiệp vụ và
có giới hạn context/payload. Gates phát hiện lỗi, giữ receipts và chi phí thay vì
lấp bằng output đẹp. Calibration, evaluation và pipeline chưa COMPLETE.
