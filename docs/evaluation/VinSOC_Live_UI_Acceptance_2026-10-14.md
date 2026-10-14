# Báo cáo nghiệm thu VinSOC Live UI — 14/10/2026

## Kết luận điều hành

Giao diện Streamlit hiện chạy được một query từ đầu đến cuối qua Linux GitHub
Actions với API thật. Lượt COUNT mới đã đi qua routing, R2, SQL worker, typed
result, evidence và assessment; worker trả `459`, EX đạt và trạng thái cuối là
`technical_complete_awaiting_human`. Giao diện mở đủ tám bước và không tự điền
review.

Hai nhánh lỗi cũng được giữ nguyên. Lượt AVG mới dừng sau ba response vì SQL
probe của model sai cú pháp nhóm, nên không có final SQL hoặc assessment. Lượt
UDP mới bị chặn trước SDK vì master đổi sau preflight; giao diện hiện rõ
`REMOTE_MASTER_CHANGED`, `0/0` và chi phí lượt là `$0`. Không lượt nào được chạy
lại để đổi một kết quả xấu thành kết quả đẹp.

Chi phí query allocation đã xác minh là `$0.09061250`, gồm base `$0.08155920`
và hai live UI runs `$0.00905330`; còn `$2.90938750` trong cap dự án `$3`.
Đây không phải số dư tài khoản OpenAI. Calibration, evaluation và pipeline32
vẫn `NOT_RUN`; human approvals vẫn bằng 0.

## 1. Mốc nguồn và CI

Mã chức năng Live UI được phát hành tại
`3c9e44a68d887f90b7ef23c8f64fcf2fc7f39fe6`. CI đúng SHA là
[run 38440995847](https://github.com/Whats-up-pro/VinSOC/actions/runs/38440995847):
full suite 1.431 passed/7 skipped trên cả Python 3.11 và 3.12; required offline
135 passed/0 skipped mỗi phiên bản; real-data 13 passed/0 skipped mỗi phiên bản.

Trong lúc nghiệm thu, master tiến thêm commit tài liệu `e14beb7`. Lượt UDP dùng
SHA cũ đã bị backend chặn an toàn. Workspace được fast-forward lên
`e14beb7782230bb818016317bdb951612cdfd907`; CI đúng SHA
[38496517640](https://github.com/Whats-up-pro/VinSOC/actions/runs/38496517640)
đạt trên hai phiên bản Python. Commit `3573496a165876f36116b2716ca737d17091aaf7`
vẫn là ancestor.

Bản sửa để UI hiện category của lượt blocked nằm tại
`e6504d594715e685eb539d534b1a514f7cfe8192`; CI đúng SHA
[38498145776](https://github.com/Whats-up-pro/VinSOC/actions/runs/38498145776)
đạt: full suite 1.432 passed/7 skipped, required offline 136 passed/0 skipped
và real-data 13 passed/0 skipped trên mỗi Python 3.11/3.12.

Các lệnh chính:

```powershell
git fetch origin master
git rev-list --left-right --count HEAD...origin/master
git merge --ff-only origin/master
git merge-base --is-ancestor 3573496a165876f36116b2716ca737d17091aaf7 HEAD
gh run view 38496517640 --repo Whats-up-pro/VinSOC --json status,conclusion,headSha,jobs
```

Nhận xét: source binding đã làm đúng nhiệm vụ. Khi remote master đổi, runner
không dùng quyền preflight cũ để gọi model.

## 2. Preflight và API thật

### AVG — lỗi thật được giữ nguyên

- Preflight: [38442148674](https://github.com/Whats-up-pro/VinSOC/actions/runs/38442148674),
  `attempted=0`, `received=0`, `client_created=false`.
- Live: [38442744166](https://github.com/Whats-up-pro/VinSOC/actions/runs/38442744166),
  3/3 responses, chi phí `$0.00139010`.
- Routing gọi `network_query`; R2 gọi `value_search`, sau đó `sql_probe`.
- SQL probe dùng `overall.overall_avg` trong `HAVING` nhưng không nhóm/aggregate
  biểu thức đó. Worker trả `SQL_EXECUTION_FAILED`; record giữ `TOOL_FAILURE`,
  `NO_FINAL_SQL`, EX false và không có assessment giả.

### COUNT — luồng end-to-end đạt kỹ thuật

- Preflight: [38444046451](https://github.com/Whats-up-pro/VinSOC/actions/runs/38444046451),
  0/0 calls, không tạo SDK client.
- Live: [38444497641](https://github.com/Whats-up-pro/VinSOC/actions/runs/38444497641),
  8/8 responses, chi phí `$0.00766320`.
- Vai trò: 1 routing, 6 R2, 1 assessment.
- Usage: 13.408 input tokens, 2.536 output tokens, 4.352 cached tokens.
- SQL tìm giao tập IP đích TCP của CTU S5 và S7 sau hai mốc thời gian nghiêm
  ngặt; worker cách ly trả một cột `BIGINT`, một hàng, giá trị `459`.
- `execution_success=true`, `execution_accurate=true`, category `OK`.
- Assessment dẫn về evidence đã lưu. Human review vẫn pending.

### UDP — gate nguồn chặn trước SDK

- Preflight: [38496130495](https://github.com/Whats-up-pro/VinSOC/actions/runs/38496130495),
  đạt với 0/0 calls.
- Live: [38496491276](https://github.com/Whats-up-pro/VinSOC/actions/runs/38496491276),
  bị chặn `REMOTE_MASTER_CHANGED` do master đã tiến thêm commit.
- `attempted=0`, `received=0`, `client_created=false`, `window_claimed=false`,
  chi phí mới `$0`.

Thao tác thật được thực hiện qua trang **Chạy pipeline thật**. Các helper browser
chỉ tự động hóa đúng thao tác người dùng: chọn case, dán câu gốc, chạy preflight,
tick consent và nhấn live một lần. Marker `live.dispatch` và remote run inventory
được kiểm trước mọi thao tác tiếp theo, nên không có double dispatch.

## 3. Đối soát artifact và chi phí

Sáu Actions artifacts được tải độc lập bằng endpoint đã xác thực. SHA-256 archive
khớp hoàn toàn với digest Actions API. Hash public files và hash private ledger
được ghi trong `artifact_hashes.json`; raw private request/journal không được đưa
vào Git.

Lệnh kiểm:

```powershell
gh run list --repo Whats-up-pro/VinSOC --workflow query-live-ui.yml --limit 50 `
  --json databaseId,displayTitle,headSha,status,conclusion,url
gh api repos/Whats-up-pro/VinSOC/git/matching-refs/tags/vinsoc-ui-allocation-
Get-FileHash .vinsoc/live-ui-acceptance-zips/*.zip -Algorithm SHA256
```

Remote allocation registry chỉ có hai cặp begin/end:

| Execution | Calls | Cost | End receipt |
|---|---:|---:|---|
| AVG `liveui-5ccddb…` | 3 | $0.00139010 | verified |
| COUNT `liveui-9d9844…` | 8 | $0.00766320 | verified |

UDP không có begin claim. Tổng hai UI runs là 11 calls và `$0.00905330`. Cộng
base 80 calls/`$0.08155920` thành 91 calls/`$0.09061250`. Không có open claim,
unknown usage hoặc unknown cost.

## 4. Nghiệm thu giao diện

Khởi động:

```powershell
Set-Location D:\VINUNI_AI2026\Phase3_VinSOC
.\.venv\Scripts\python.exe -m pip install -r requirements-demo.txt
.\.venv\Scripts\python.exe -m streamlit run scripts/vinsoc_demo_app.py `
  --server.address=127.0.0.1 --server.port=8501
```

Browser QA mở lại COUNT và đi đủ tám màn hình:

1. câu hỏi gốc;
2. native tool call;
3. schema và value trajectory;
4. SQL của model;
5. typed result `459`;
6. evidence, provenance và hashes;
7. assessment cùng các gate độc lập;
8. form review trống identity/decision/rationale/UTC.

Các ảnh thật nằm ở
`results/evaluation_v1/text2sql_integration_v1/live_ui_acceptance_20261014/screenshots/`.
`ui_checks.json` liên kết SHA-256 của từng ảnh. Việc mở và refresh saved session
không tạo workflow mới.

Browser cũng mở AVG stage 4 và 7: UI hiện “Chưa có final SQL” và “Chưa có
assessment hợp lệ”, không mượn kết quả AVG lịch sử. UDP blocked hiện category
`REMOTE_MASTER_CHANGED`, 0/0 và `$0.00000000`. Lỗi hiển thị category bị thiếu
ban đầu đã được tái hiện, viết test RED, sửa nhỏ rồi test GREEN.

## 5. Kịch bản demo mentor 15–20 phút

1. Mở **Tổng quan** và nói rõ có bốn saved demo records, không phải một suite
   pipeline32. Hai record đạt kỹ thuật, một incomplete, một failed.
2. Mở **Chạy pipeline thật**, chọn saved COUNT `liveui-9d9844…`. Cho mentor xem
   run ID, 8/8 responses, cost và số dư trước khi vào kết quả.
3. Đi tám stage của COUNT. Ở SQL, giải thích hai subquery S5/S7 và phép giao bằng
   hai điều kiện `IN`. Ở typed result, chỉ ra `459`, type `BIGINT`, row_count 1,
   `truncated=false`.
4. Ở evidence, chỉ ra database ID, snapshot hash, SQL hash, result hash và worker
   version. Nhấn mạnh SQL chạy trong worker Linux cách ly, không trong Streamlit.
5. Ở assessment, giải thích `459` là kết quả truy vấn; nó chưa tự chứng minh hành
   vi độc hại. Analyst vẫn phải xét CTI/endpoint context.
6. Ở review, để trống form và giải thích người duyệt thật phải tự nhập identity,
   decision, rationale và UTC. Không tự approve trong demo.
7. Mở AVG UI run mới để minh họa lỗi model thật: đã tốn 3 calls nhưng không có
   final SQL. Đây là lý do workflow success/failure không đồng nghĩa chất lượng.
8. Mở saved NULL để giải thích edge case SQL chạy được nhưng sai: `WHERE` trước
   `GROUP BY` làm mất nhóm có count 0, nên EX false.
9. Mở saved UDP để giải thích edge case payload: 9.780 rows được giữ đầy đủ,
   assessment dừng do payload vượt policy; không loại rows để làm đẹp.
10. Kết thúc bằng bảng chi phí và gates còn mở.

Để chạy một query mới trong buổi demo, phải dùng HEAD đã có CI success, chạy
preflight mới, kiểm 0/0/client false, rồi người vận hành tự tick consent. Không
dùng lại execution đã consumed và không chạy lại chỉ vì output xấu.

## 6. Phạm vi hình thức còn mở

| Scope | Records thật | Trạng thái | Cận bảo thủ |
|---|---:|---|---:|
| Calibration | 0/48 | NOT_RUN | $19.9680000 |
| Selection lock | 0/48 đầu vào | PENDING | — |
| Evaluation | 0/192 | NOT_RUN | $79.8720000 |
| Pipeline | 0/32 cùng producer | NOT_RUN | $53.5443456 |

Tổng cận ba scope là `$153.3843456`, cao hơn allocation còn lại. Các số này là
reserve bound theo payload/model hiện hành, không phải chi phí đã phát sinh.
Không được giảm reserve, tạo records giả hoặc dùng saved SQL làm điểm model.

## 7. Receipts bàn giao

- `run_inventory.json`: sáu preflight/live workflows và outcome.
- `artifact_hashes.json`: archive/public file hashes; private chỉ lưu ledger hash.
- `cost_reconciliation.json`: calls, tokens, costs, cap và formal bounds.
- `acceptance_receipt.json`: chức năng đã quan sát và gates còn mở.
- `ui_checks.json`: browser checks cùng screenshot hashes.

Hai ZIP pin vẫn giữ nguyên:

- `VinSOC_Runtime_DB_20261010.zip`:
  `7cc72e34d50b5533ae44d23abcf1b68aa949a8fed972ccce73c932bd6c67114e`.
- `VinSOC_CTU_20261010.zip`:
  `2847ba055dee714195898251e686ad62f0856c721eda84af8782c77a33293dc4`.

Nhận định chung: giao diện đã chứng minh được cả happy path và failure path bằng
artifacts/API thật, đồng thời giữ chặt source, budget và human-review gates. Phần
còn thiếu là chạy các formal suites với ngân sách riêng và hoàn tất human review;
không có cơ sở để ghi COMPLETE cho các phần đó ở mốc này.
