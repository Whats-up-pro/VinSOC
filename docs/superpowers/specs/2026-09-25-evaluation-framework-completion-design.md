# Đặc tả hoàn thiện khung đánh giá VinSOC R1/R2

**Ngày:** 2026-09-25 (Asia/Bangkok)
**Cơ sở kiểm tra:** `master@231f79f5192cbd5b7676460cf4c7566d71b9d262`
**Trạng thái:** Đặc tả để Agent B duyệt trước khi chia task triển khai. Không phải kết quả R2 hay lệnh mở frozen.

## 1. Mục tiêu và giới hạn phát biểu

VinSOC cần hai phép đo có đầu vào, code, chi phí và kết quả từng case tái kiểm tra được. **R1 A1** đo quyết định gọi production tool *một lượt*: benchmark `dev v2` đã có [một run model thật 22/24](../../r1_a1_dev_v2_results.md) ở commit `852e543`, không chỉnh lại artifact gốc 15/24 ở `1fd3843`. **R2** đo SQL do model sinh *offline* trên DuckDB snapshot đã xác minh: đã có 8 gold cases `dev`, runner, execution scorer và boundary SELECT/read-only, nhưng **chưa có snapshot/manifest thật hoặc điểm model**. R1 A2 MockProvider chỉ chứng minh tích hợp; end-to-end evidence/triage là thí nghiệm riêng. Không suy ra cải thiện model bằng cách trừ 15/24 khỏi 22/24, vì benchmark/gold/schema đã đổi.

Phạm vi đợt hoàn thiện: chốt provenance dữ liệu và khả năng build R2; sửa adapter theo bytes thật; xác minh 8 gold SQL; làm R2 runner có provenance, output-token cap, zero retries, budget gate; một lần chạy `dev` nếu mọi cổng đạt; sau đó phân tích lỗi và khóa cấu hình. **Không** thay R1 scorer, R1 v2 artifact, prompt/schema R1, benchmark `frozen`, production SQL boundary, hay dùng dữ liệu giả để tạo điểm official. Không tune model theo `frozen`.

## 2. Quyết định kiến trúc và phương án dự phòng

**Ưu tiên:** hoàn thành ba nguồn công khai ThreatFox + CTU-13 + OTRF theo hợp đồng snapshot hiện có; sửa điểm không tương thích và xử lý file lớn theo batch. Phương án này đo cả CTI/network/endpoint nhưng phụ thuộc full export có Auth-Key và chuyển file CTU 639.643.247 bytes. **Dự phòng chỉ khi cổng nguồn chưa qua trước 27/09/2026:** một pilot *network + endpoint* mang benchmark ID, snapshot ID, case/gold và báo cáo riêng; không gọi nó là R2 official ba nguồn và không gộp điểm với phiên bản ba nguồn. Không tự đổi source Scenario 3 sang danh sách CTU Scenario 1/4/9/10/13 từng dự kiến: cần quyết định nguồn cụ thể và version benchmark trước khi gắn gold. Phương án bỏ CTI âm thầm bị loại.

Giữ các biên sẵn có: `scripts/build_vinsoc_public_snapshot.py` xác minh file và build; `vinsoc_data/duckdb_store.py` đăng ký nguồn, ghi bảng, mở read-only; `evaluation/text_to_sql_snapshot.py` xác minh manifest; `evaluation/text_to_sql.py` gọi provider, thực thi/so gold. Không đưa raw SQL tool vào orchestrator production. Mỗi thay đổi nguồn/mapping/cases sau baseline phải có version mới và run riêng.

## 3. Cổng D0: nguồn thật và quyền sử dụng (chặn toàn bộ R2)

Danh mục bắt buộc cho mỗi nguồn: `dataset_id`, tên, URL công khai chính thức, thời điểm UTC **sau khi tải xong**, kích thước bytes, SHA-256 **tệp tải thực tế**, định dạng thực, điều khoản/attribution ở phiên bản nguồn đã dùng, local artifact path, và phép biến đổi sang normalized rows. Tải thất bại không có hash. Dữ liệu gốc giữ ngoài Git cùng metadata; chỉ manifest/probe đã loại credential được commit. Không ghi Auth-Key vào source URL trong manifest, log, command, report hoặc artifact; không dùng `threatfox_samples.json` hay recent-IOC API thay full export.

| Nguồn | Bằng chứng đã có | Chốt điều kiện đạt |
|---|---|---|
| OTRF | ZIP gốc 13.944.973 bytes, SHA-256 `98a073140860560d70080ace9142961be4f64b4862bae892d62d0f254d0fdbe5`; member `apt29_evals_day1_manual_2020-05-01225525.json`, 385.334.029 bytes. | Xác nhận hash ZIP lưu, member đúng JSONL, nguồn/điều khoản tại commit gốc, adapter nhận format thật. README OTRF ghi GPL-3.0 còn tệp `LICENSE` hiện ghi MIT: **giải quyết mâu thuẫn trước khi công bố/phân phối dữ liệu**; không tự chọn một nhãn license. |
| CTU-13 | HEAD HTTP 200, `Content-Length=639643247`; chưa có bytes/hệ hash. | Tải hoặc chuyển *toàn bộ* `.binetflow` Scenario 3, hash 639.643.247 bytes, kiểm header/các cột và yêu cầu ghi nguồn/tác giả MCFP. Nếu nguồn Scenario khác được chọn, phát hành version dữ liệu mới trước build. |
| ThreatFox | Export full yêu cầu Auth-Key; job probe không có `THREATFOX_AUTH_KEY`. | Nhận full `full.csv.zip` qua secret an toàn hoặc kênh file riêng. Ghi SHA-256 ZIP gốc, member name và SHA-256 CSV sau giải nén. `threatfox_csv.path` trỏ **CSV** và `file_sha256` phải là hash CSV; bảng phụ liên kết hash ZIP→member→CSV. Ghi usage/fair-use; không đưa URL chứa key vào manifest. |

[Probe và lỗi cụ thể ngày 24/09](../../r2_source_gate_2026-09-24.md) là chứng cứ của D0, không phải dataset manifest đã đạt. Đường truyền Actions có mạng đối với OTRF/CTU HEAD; runtime local timeout cả ba host. Nếu chuyển qua môi trường khác, kiểm SHA-256 ở **hai đầu**. Nếu D0 không đạt trước 27/09 (giờ Asia/Bangkok), báo rõ thiếu bytes/secret/terms và đưa pilot riêng cho Agent B quyết định; không tự dựng lịch sử hoặc snapshot một phần.

## 4. Cổng D1: mapping, khả năng build và manifest

Sửa `normalize_sysmon_zip_jsonl`/`_normalize_sysmon_lines` theo dữ liệu OTRF đã kiểm: 10.000 dòng đầu có `Hostname`, `EventID` ở cấp trên, `host` là string của collector và không có `winlog`/`Computer`. Host của endpoint phải lấy từ trường được kiểm chứng, không nhận nhầm collector host; map process parent/child/command/user khi trường có thật, còn thiếu phải để `null`, không tự sinh. Test dùng các dòng thật, đã loại thông tin không cần thiết, kiểm stable `<member>:line:<n>`, các trường host/event/time, và các dòng bị bỏ với lý do. Giữ adapter `winlog` hiện có cho các input cũ; không sửa gold để che lỗi mapping.

`normalize_ctu13_binetflow` và `normalize_sysmon_zip_jsonl` hiện trả list; `SocSnapshotBuilder.insert_rows` còn tạo bản sao list. Với 610 MiB input CTU và 385 MiB JSON member OTRF, triển khai đọc/ghi theo batch có giới hạn bộ nhớ, đếm normalized/filtered theo nguồn và bảo toàn row ID. Test so batch với semantics cũ trên fixture nhỏ, test fail giữa chừng không xuất bản snapshot/manifest. Ghi transaction/atomic publish để file hỏng không được nhận là snapshot hợp lệ. Nếu CTU có nhiều dòng bị loại do port/timestamp thực tế, thống kê lý do trước khi chấp nhận độ bao phủ.

Đóng `dataset_manifest.json` chỉ sau khi đủ ba file thật và hash. Bảo toàn hợp đồng `source_url`, `retrieved_at`, `file_sha256`, `license_note`, `format`, `path`, `archive_member`; ThreatFox cần ledger phụ ZIP→CSV vì manifest hiện chỉ ghi CSV. Build vào đường dẫn mới, không ghi đè; tạo snapshot manifest bằng SHA-256 của **DuckDB file vừa tạo**, mở read-only lại, kiểm đúng ba bảng khác rỗng, không có hàng thiếu `source_dataset/source_row_id`, số nguồn provenance đúng và mã định danh row không trùng trong từng nguồn. Lưu snapshot binary/hồ sơ nguồn ngoài Git nhưng có vị trí tải và retention thực tế; đường dẫn manifest dùng được trong runtime chạy model. Không coi checksum của archive Actions là checksum nguồn.

## 5. Cổng D2: gold SQL, semantics và nguồn/split

Trước mọi provider call, chạy cả **8 `sql_dev_001`–`sql_dev_008`** và tất cả gold variants trên chính snapshot hash đã đóng, qua cùng read-only `DuckDBSnapshot.query`. Ghi case ID, SQL hash, comparator, row count/result digest, trạng thái và snapshot SHA; lỗi SQL hoặc bảng trống khiến D2 FAIL. Reviewer đối chiếu nội dung câu hỏi/gold với bảng thật, nhất là `DISTINCT`, cận thời gian, filter, aggregation và top-k có ordering; các counterexample SQL sai nghĩa mà tình cờ trả cùng rows phải có semantic-trap fixture riêng trong tests. Một snapshot không bảo đảm SQL tương đương mọi dữ liệu: ghi giới hạn đó trong report. Snapshot dev/frozen dùng chung phiên bản nguồn hiện chưa chứng minh tổng quát hóa sang nguồn/session mới; chưa gọi `frozen` là holdout độc lập về dữ liệu. Không đọc kết quả `frozen` để sửa dev.

## 6. Cổng M0: chuẩn bị R2 provider và tính điểm an toàn

Giữ Execution Accuracy làm headline; báo Syntax Validity, Execution Success, Safety Rejection Rate, provider error, latency/tokens/cost và category/difficulty. Provider/execution error được chấm thất bại và phân loại rõ; không được thành một success do kết quả rỗng. Dùng provider `openai`, **exact** model ID `gpt-4.1-mini-2025-04-14`, temperature `0` như baseline R1 để đơn giản hóa theo dõi chi phí; đó là lựa chọn thiết kế **chưa tạo R2 result**. Khóa provider/model trước run, không fallback/routed. Không dùng default `gpt-4o` hiện tại để lấp chỗ trống.

Thêm `max_completion_tokens=1000` vào request OpenAI thực sự (cả tên provider khác chữ hoa và provider injection đều phải gắn cap hoặc fail trước request); `max_retries=0` ở client thực, không chỉ ghi report. Unit test bắt request Chat Completions qua client giả, cap sai kiểu/≤0 fail fast, provider/actual model/fallback lệch fail; fake provider không được nhận nhầm cap. Ghi cap, retries và exact prompt+schema/hashes, benchmark split/case hashes, scorer SHA, Git SHA/dirty flag, snapshot/source SHA và actual provider/model cùng per-case SQL, error, usage. Trường eligibility chỉ `true` nếu full 8 IDs, Git sạch, snapshot/gold hợp lệ, cap thực áp dụng, actual provider/model đúng, usage đủ và không có provider error; thiếu thông tin thì report partial + lý do, không có điểm official.

Trước call đầu, preflight payload **thật của cả 8 case** (prompt, schema, model, max output) bằng giá hiện hành từ trang OpenAI chính thức, tính cả trần input theo cách bảo thủ, 8×1000 output và **zero retries**. Giới hạn kinh phí đề xuất **$1.00 cho toàn bộ task R2 dev**, cần chốt với controller trước khi dùng secret; nếu không chứng minh được cận trên/cơ chế dừng thì không gọi API. Sau mỗi case, kiểm usage trả về, actual model, số call, cộng cost từ input/output token thật; trước call kế tiếp kiểm `spent + bound_remaining < budget`. Mọi lỗi/thiếu usage/mismatch hoặc nguy cơ vượt trần phải dừng, ghi artifact từng phần, không gọi tiếp, không báo `$0` khi cost chưa biết. Kiểm giá từ nguồn chính thức lại tại ngày run, không lấy cost field `0` khi `cost_complete=false`.

## 7. Cổng M1 và H: chỉ một baseline, rồi review

Sau D0–D2 và M0 cùng CI xanh Python 3.11/3.12: preflight 8 IDs/đúng snapshot/chi phí; chạy **một lượt `dev`** bằng pinned SHA/config; lưu JSON ngay sau từng case và artifact toàn bộ hoặc phần đã hoàn tất khi fail. Kiểm 8 model calls, 8 IDs, metadata, actual model, usage/cost, kết quả theo category/difficulty, `official_eligible` và lý do. Chỉ nếu report qua gate mới ghi official R2 dev score; nếu không, ghi diagnostic run kèm lỗi cụ thể. Chưa chạy frozen hoặc R2 lặp lại để tune trong cùng task.

Sau baseline, gắn một lý do chính cho mỗi R2 failure (syntax, safety, execution, wrong result, provider); thay một biến mỗi thử nghiệm dev, so chi phí/latency. R1 case `002`/`015` có thể phân tích riêng, không sửa R1 benchmark hay baseline 22/24 trong quá trình R2. Chỉ sau review từng track mới pre-register hashes của model/prompt/schema/gold/scorer/snapshot, kiểm hợp đồng frozen và cân nhắc một holdout run; không claim independent source/session generalization khi vẫn dùng một snapshot.

## 8. Tiêu chí nghiệm thu và thứ tự giao task

1. **D0:** đủ 3 file gốc/hash và quyền sử dụng đã giải quyết. Nếu không, STOP official R2; trước 27/09 báo blocker và quyết định pilot có version riêng. Không dùng samples.
2. **D1:** mapping OTRF từ bytes thật + batch build, số dòng/identity/provenance kiểm được; manifest, snapshot SHA và read-only reopen đạt.
3. **D2:** 8/8 dev gold chạy và reviewer duyệt semantics/counterexamples; snapshot cố định.
4. **M0:** request cap/zero retries/cost ceiling, report provenance và regression tests đạt; CI 3.11/3.12 xanh.
5. **M1:** duy nhất một run dev, đủ 8 cases/calls, usage đầy đủ, cost dưới trần, report official eligible và review; frozen vẫn đóng.

Agent A chỉ nhận **một task nhỏ mỗi vòng**, commit/push trực tiếp `master`, đưa initial/final SHA, diff, tests và artifact cho Agent B review trước task sau. Không push file chứa key, không thay scorer hay gold để cứu điểm, không mô tả unit-test/fake-provider là real-model accuracy. Các cổng phía sau tuyệt đối không được bắt đầu khi cổng trước còn FAIL.

## Nguồn tham khảo kiểm chứng

- [VinSOC evaluation protocol](../../evaluation_protocol_v1.md), [R2 source probe](../../r2_source_gate_2026-09-24.md), [R1 dev v2 report](../../r1_a1_dev_v2_results.md).
- [ThreatFox full export/Auth-Key](https://threatfox.abuse.ch/export/), [ThreatFox FAQ/terms](https://threatfox.abuse.ch/faq/); [CTU-13 selected file](https://mcfp.felk.cvut.cz/publicDatasets/CTU-Malware-Capture-Botnet-44/detailed-bidirectional-flow-labels/) và [MCFP attribution](https://mcfp.felk.cvut.cz/publicDatasets/CTU-Malware-Capture-Botnet-4/README.html).
- [OTRF archive](https://github.com/OTRF/Security-Datasets/blob/master/datasets/compound/apt29/day1/apt29_evals_day1_manual.zip), [README](https://github.com/OTRF/Security-Datasets/blob/master/README.md), [LICENSE](https://github.com/OTRF/Security-Datasets/blob/master/LICENSE); cần giải quyết nhãn license khác nhau trước phát hành dữ liệu.
- [OpenAI GPT-4.1 mini pricing](https://developers.openai.com/api/docs/models/gpt-4.1-mini); [DuckDB read-only connections](https://duckdb.org/docs/stable/connect/overview).
