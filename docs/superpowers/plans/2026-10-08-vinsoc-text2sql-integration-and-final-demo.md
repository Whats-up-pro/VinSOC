# VinSOC — Kế hoạch tích hợp Text-to-SQL và bàn giao báo cáo cuối khóa

> **Dành cho người thực hiện:** Dùng superpowers:executing-plans, làm lần lượt các nhiệm vụ có checkbox. Một người ghi mã trên master; không tạo branch/PR, không tự giao thêm agent. Đây là bản thiết kế và giao việc theo yêu cầu ngày 08/10/2026, chưa phải bằng chứng đã triển khai hoặc quyền tăng ngân sách API.

**Mục tiêu:** Trước ngày 16/10/2026, bàn giao đánh giá Text-to-SQL trên nhiều cơ sở dữ liệu thật và một luồng điều tra VinSOC thực sự sử dụng chính môđun được đánh giá, có SQL, kết quả, dẫn chứng, nhận định và quyết định của người thật.

**Kiến trúc:** Một dịch vụ Text-to-SQL dùng chung cho bộ đánh giá và công cụ network_query trong public InvestigationOrchestrator. Bộ đánh giá giữ đáp án riêng; luồng vận hành chỉ nhận câu hỏi và phạm vi dữ liệu được cấp. Kết quả truy vấn đi vào EvidenceStore, kiểm chứng dữ kiện, nhận định của model và người duyệt; không dựng một demo riêng cạnh hệ thống.

**Công nghệ:** Python 3.11/3.12, DuckDB 1.5.5, SQLGlot 30.21.0, OpenAI SDK, pytest, GitHub Actions, HTML mở offline. Các phiên bản lấy từ khóa hiện có; không tự nâng thư viện.

**Thiết kế:** Mục 3–7 trong chính tài liệu này. Bản giao việc gộp thiết kế, nhiệm vụ, điều kiện nghiệm thu và danh mục giao nộp để người thực hiện không phải ghép nhiều kế hoạch.

**Mốc đã đọc:** master@c4ae3c56028b40425392e1ec779e39045c9211ef, ngày 08/10/2026. Phải đọc HEAD mới nhất khi bắt đầu; không checkout ngược về mốc này.

## 1. Quy tắc chung

- Không mock model, công cụ, DB, dẫn chứng hoặc người duyệt trong các lượt nghiệm thu và demo mới. Không thêm fake client hay dữ liệu giả để hoàn thành nhiệm vụ mới trong bản này.
- Những tests/fixture tổng hợp lịch sử được giữ nguyên và có thể chạy kiểm tra hồi quy. Chúng chỉ kiểm mã/scorer; không tính vào điểm model, thành công tích hợp hoặc bằng chứng demo.
- Đầu ra model phải có response/request identity, model thực, usage thực và nhật ký lưu trước khi parse. Thiếu bằng chứng thì ghi thiếu; không tạo dữ liệu để lấp.
- Không sửa câu hỏi, đáp án, comparator, scorer, winner_lock, snapshot đã khóa hoặc kết quả lịch sử sau khi xem model trả lời. Không ghép câu chạy lại vào một bộ cũ.
- Không mở R1 frozen, R2 S1/S4, ThreatFox hoặc OTRF bằng quyền của nhiệm vụ này. S1/S4 đã dùng và không đủ điều kiện làm tập kiểm tra độc lập mới.
- Không ghi/in/copy API key, fingerprint hoặc nội dung .env. Private account/gates/ledger không commit. Chỉ xuất các trường public-safe có trong allowlist.
- Làm trên master; mỗi mốc mã hoàn tất phải commit/push và kiểm CI đúng SHA trên cả Python 3.11/3.12. Không force push, reset --hard, git clean hoặc git add .; chỉ stage file thuộc nhiệm vụ.
- Không gọi API trước kiểm tra dữ liệu, khóa mã, CI, tài khoản, giá và ngân sách. Không retries, fallback, đổi key/model hoặc chạy thử key.
- Quyền demo network cũ giữ nguyên một lượt/tối đa bốn request/trần 0,25 USD. Quyền đó không cấp tiền cho hiệu chỉnh, đánh giá 96 câu hoặc demo tích hợp mới.
- Các lượt API mới trong bản này cần gói dự toán cụ thể và xác nhận ngân sách/phạm vi trước transmission. Không suy ra số dư hiện hành từ khoản 0,75 USD hoặc credit lịch sử.
- Không đặt mục tiêu phải đạt 100% rồi sửa để lấy điểm. Điều kiện nghiệm thu là phép đo hợp lệ, sản phẩm chạy thật và bằng chứng đầy đủ; lỗi của model vẫn phải bàn giao.

## 2. Điểm tiếp tục: giữ nguyên phần đã đạt

| Hạng mục | Bằng chứng đã có | Hành động |
|---|---|---|
| R1 dev-v2 | GPT-4.1 mini 22/24; exact-call F1 0,9508; no-tool 5/5; winner_lock.json | Giữ kết quả và phân tích lỗi; không chạy lại để tăng điểm. 11/24 gold đã được xử lý sau khi xem output nên không gọi là kiểm tra độc lập. |
| R2 lịch sử | E0 public-dev 5/8 thuộc snapshot/contract cũ; CTU GPT-5 E0 0/8; Phase-2 E3 7/8 | Tách từng điều kiện. Case006 TOOL_LIMIT/NO_FINAL_SQL vẫn sai trong bộ 7/8. |
| Kiểm lại R2 | Replay offline đã xác nhận 7/8 | Không làm lại audit đã đạt, trừ khi identity mới không khớp. |
| A1 network E2E | Public investigate(), guard/ledger, kiểm facts, renderer và khóa thật đã có | Không viết lại. Xác minh đầu vào vận hành rồi tiếp A2/A3. |
| Snapshot network E2E | 243.906 flows; S5 129.831; S7 114.075; binary 91a13ab149453ca6db6246ada3d7a21708537a12865a01e6475df18dd9a9eac3 | Dùng đúng binary; không rebuild hoặc ghi đè NETWORK_E2E_v1.lock.json. |
| Bộ mở rộng | 24 calibration + 96 evaluation; 93 evaluation families; 8 external evaluation DB/7 domain; gold và semantic audit đã khóa | Không dựng lại bộ câu hỏi. Xác minh source/snapshot thực trên môi trường chạy. |
| Mã báo cáo | reporting.py, statistics.py, release.py, live.py đã có | Dùng lại, chỉ bổ sung điểm nối runtime và kiểm chứng thiếu. |
| CI HEAD đã đọc | Run 37583051568: 1.128 passed, 2 skipped mỗi Python | Đã kiểm logs. Skip không thay cho required local-snapshot test. |
| Actions E2E | Run 37583842122: CLOUD_PRIVATE_INPUTS_MISSING; 0 attempts/0 responses/client=false | Thiếu gates, trạng thái window và URL snapshot trên cloud; chưa xác định ledger riêng của laptop. |

Nguồn trạng thái:
- docs/superpowers/plans/2026-10-07-vinsoc-e2e-closeout-and-cross-domain-next.md
- results/evaluation_v1/cross_domain_closeout/20261007/HANDOFF.md
- results/evaluation_v1/cross_domain_closeout/20261007/completion_receipt.json
- results/evaluation_v1/cross_domain_closeout/20261007/offline_status.json
- evaluation/tool_calling/winner_lock.json
- docs/evaluation/FINAL_EVALUATION_REPORT.md

**Thứ tự tài liệu:** Yêu cầu ngày 08/10 bổ sung tích hợp Text-to-SQL và cấm mock trong đầu ra nghiệm thu mới. Quy định bảo vệ lịch sử và giới hạn paid của kế hoạch 07/10 vẫn giữ. Những checkbox pending trong kế hoạch cũ không tự chứng minh mã hiện tại còn thiếu; phải đối chiếu receipts và SHA mới.

## 3. Hai câu hỏi phải trả lời trong báo cáo

### 3.1. Text-to-SQL làm việc tốt đến đâu trên nhiều schema/lĩnh vực?

Dùng bộ đã khóa, không chỉ tám câu CTU:

| Phần | Số câu | Mục đích |
|---|---:|---|
| Calibration ngoài SOC | 16 | Chọn giữa E0/E3 trước khi nhìn điểm evaluation; bốn DB riêng |
| Calibration CTU | 8 | Kiểm cấu hình trên lĩnh vực VinSOC |
| Evaluation ngoài SOC | 64 | Đo trên tám DB/bảy lĩnh vực khác SOC |
| Evaluation CTU | 32 | Đo câu hỏi network có phạm vi rộng hơn bộ tám câu lịch sử |
| CTU anchors lịch sử | 8 | Tham chiếu riêng; không cộng vào mẫu số 96 |
| Oracle subset | 12 trong 96 | Chẩn đoán theo protocol; không là 12 mẫu bổ sung |

Phải báo cáo EX ngoài SOC /64, EX CTU /32 và EX tổng /96. Có macro theo database/domain, n ở mỗi hàng, mức độ 24 cơ bản/48 trung bình/24 nâng cao và nhóm SQL: JOIN, nested query, GROUP/HAVING, DISTINCT, ORDER/LIMIT, NULL, Boolean, thời gian và window.

Cụm từ được phép: “đánh giá trên nhiều schema/lĩnh vực của tập đã chọn”. Không viết “tổng quát trên mọi dữ liệu”, “điểm Spider chính thức” hoặc “holdout độc lập với dữ liệu tiền huấn luyện”. Spider là dữ liệu công khai; chưa biết model đã thấy những gì. CTU calibration/evaluation cùng S5/S7 không tạo phân tách theo phiên nguồn.

### 3.2. Text-to-SQL có tạo ích lợi trong luồng điều tra thật không?

Một tool chọn đúng tên chưa đủ. Phải chứng minh:

1. Người dùng nhập câu hỏi network bằng ngôn ngữ tự nhiên vào CLI VinSOC.
2. Public orchestrator nhận câu hỏi, chạy triage dành cho query và model thực chọn network_query.
3. NetworkQuerySkill gọi dịch vụ Text-to-SQL dùng chung với bộ đánh giá.
4. Model sinh SQL; safety gate kiểm trước execution; worker đọc DB thật.
5. EvidenceStore lưu kết quả cùng nguồn và identity.
6. Model tạo nhận định, số liệu và dẫn chứng từ kết quả đã nhận.
7. Facts/provenance được kiểm; người thật xem nhận định và chọn approved/rejected/escalated.
8. JSON/HTML cho phép kiểm lại luồng mà không gọi API thêm.

Đánh giá đầy đủ luồng này trên **toàn bộ 32 câu CTU evaluation**, không chỉ vài ví dụ đẹp. Bốn câu để trình diễn là tập con được chọn trước khi nhìn output, không là một bộ điểm mới.

## 4. Cách tích hợp được chọn

### 4.1. Các phương án và quyết định

| Phương án | Hệ quả | Quyết định |
|---|---|---|
| Thay SQL cố định bên trong network_investigation | Schema cũ chỉ có indicator/time_range; không diễn đạt được mọi câu hỏi COUNT/GROUP/DISTINCT. Thay đổi còn làm khó đối chiếu R1/E2E cũ. | Không chọn cho đợt này |
| Thêm network_query trong một profile mới, dùng chung runtime | Diễn đạt được câu hỏi tự nhiên; vẫn dùng public orchestrator, EvidenceStore, verification và human review hiện có. | Chọn |
| Giữ một CLI Text-to-SQL ngoài orchestrator | Có điểm SQL nhưng không chứng minh tích hợp sản phẩm. | Không đủ nghiệm thu |

Giữ nguyên get_tool_schemas() mặc định và các artifact R1. Profile mới có schema/tool hash riêng. Việc schema mới không được đo bởi R1 22/24 phải ghi rõ; không đổi tên điểm R1 cũ thành điểm của profile mới.

### 4.2. Đường đi của dữ liệu

~~~mermaid
flowchart TD
    U["Câu hỏi network"] --> O["Public orchestrator"]
    O --> K["NetworkQuerySkill"]
    K --> R["Runtime Text-to-SQL dùng chung"]
    B["Bộ đánh giá: runtime DTO"] --> R
    R --> G["Kiểm SQL và worker chỉ đọc"]
    G --> D[("DB thật đã khóa")]
    D --> E["EvidenceStore và nguồn kết quả"]
    E --> A["Nhận định model và kiểm facts"]
    A --> H["Người thật duyệt"]
    G --> Q["SQL và kết quả đã lưu"]
    Q --> S["Scorer riêng: đáp án không vào runtime"]
~~~

### 4.3. Public API, không tạo IOC giả

Giữ chữ ký investigate(indicator, indicator_type, context) hiện có. Thêm:

~~~python
InvestigationOrchestrator.investigate_query(
    question: str,
    *,
    query_context: QueryContext,
) -> InvestigationCase
~~~

Hai entrypoint dùng một lifecycle nội bộ chung cho các bước investigate → verify → review. Query triage kiểm câu hỏi, phạm vi DB và giới hạn đầu vào; không dùng một IP giả để qua triage_alert(). Không gọi investigate_fixed_pipeline() hoặc private _execute_tool_call() trực tiếp từ script nghiệm thu.

**QueryContext** do ứng dụng/operator cấp, không do model tự chọn:

~~~python
@dataclass(frozen=True)
class QueryContext:
    database_id: str
    snapshot_path: Path
    snapshot_logical_sha256: str
    allowed_tables: tuple[str, ...]
    scope_id: str
~~~

Production profile chỉ cho bảng network_flows của snapshot CTU S5/S7 đã xác minh. Model không được cấp đường dẫn file, lựa chọn endpoint hoặc tên DB bất kỳ. Không áp phạm vi IOC/time ngầm khiến câu hỏi toàn dataset bị biến nghĩa. Nếu ứng dụng chỉ cấp một phần dữ liệu, catalog/tool phải dùng đúng view của phần được cấp và nêu giới hạn.

**Tool public:** network_query, schema strict chỉ có question: str. Không nhận raw SQL, database path, gold, benchmark annotation hoặc expected answer. Tool arguments.question phải giữ nguyên văn câu hỏi gốc; không chuẩn hóa làm đổi khoảng trắng bên trong literal. Đổi câu hỏi bị chặn và ghi lỗi, không tự sửa.

**Dịch vụ dùng chung:**

~~~python
@dataclass(frozen=True)
class QueryRequest:
    request_id: str
    database_id: str
    question: str

TextToSQLService.generate(
    request: QueryRequest,
    *,
    condition: Literal["E0", "E3"],
    context: DatabaseContext,
    transport: QueryTransport,
    telemetry_sink: Callable[[dict], None],
) -> dict

TextToSQLService.execute(
    generation: dict,
    *,
    context: DatabaseContext,
) -> dict
~~~

QueryTransport là interface request(payload: dict) -> dict, có counters() -> dict cho attempted/received/valid_usage/cost. Adapter của GuardedTransport hiện có và transport của query profile đều thực hiện interface này; actual-live acceptance bắt buộc verified OpenAI transport. Không gắn service với journal của riêng benchmark.

Generate không nhập reference/gold/scorer. Execute dùng safety policy và worker giống nhau trong benchmark và production. Scorer chỉ đọc SQL/kết quả đã chốt; không quay lại runtime để sửa.

Phần thuật toán hiện có trong live.py::run_live_case được chuyển thành runtime dùng chung; live adapter gọi dịch vụ thay vì giữ một bản logic thứ hai. Các prompts/tools/grounding/safety/data đã có là thư viện versioned được dùng lại, không sao chép hoặc viết lại để chạy production. Trong đợt này có thể giữ import từ namespace evaluation/r2_cross_domain_v1 cho những module thuần runtime đó; đường import phải được ghi trong dependency audit và không kéo gold vào production. Chuyển vị trí toàn bộ module là việc sau đợt này, không là điều kiện demo.

## 5. SQL, dẫn chứng và lỗi: điều kiện trước tích hợp

### 5.1. Execution boundary

- Một SELECT/WITH đọc dữ liệu thuộc allowlist; kiểm AST trước chạy.
- Chặn DDL/DML, nhiều statement, ATTACH, COPY, INSTALL/LOAD, PRAGMA/SET do model phát ra, đọc file/URL, table function không cho phép và truy cập bảng ngoài scope.
- DuckDB read_only=True, enable_external_access=False, autoload/autoinstall extensions=False, threads=1.
- DB-tool giữ các mức đã có: 12 calls/case, timeout 2 giây, 20 rows/tool và payload 8.192 bytes. Không tăng cap để cứu câu sai.
- Final result tối đa 10.000 rows; fetch 10.001 để phát hiện cắt. Kết quả cắt không đủ điều kiện EX hoặc final technical success. Payload tới assessment có giới hạn riêng; quá lớn phải báo lỗi, không lặng lẽ bỏ bớt evidence.
- SQL model chạy trong worker/container riêng, không có API key/gates/ledger, network disabled và chỉ mount snapshot cần đọc. Giới hạn tổng memory 512 MiB, một CPU và timeout final query 10 giây; cấu hình này phải được khóa và dùng giống nhau trong các điều kiện mới. Không chỉ gọi read_only là sandbox.
- Executor interface mới: SqlExecutor.query(context, sql, parameters=(), *, row_cap, timeout_seconds) -> dict. Cả profiler/value-search/SQL-probe và final SQL đều dùng executor này.
- Thiếu cơ chế cách ly tương ứng thì gate tích hợp chưa đạt. Không dùng connection mặc định trong cùng process đang giữ secrets để thay thế.

Các cap/worker mới là contract cho series dùng runtime mới, không hồi tố vào kết quả 7/8. SQL đúng nhưng vượt cận thực thi là lỗi được giữ trong phép đo vận hành; không tăng cận giữa hai điều kiện.

### 5.2. Evidence và provenance

Result receipt gồm database_id, snapshot identity, original question, SQL nguyên văn/hash, policy/executor version, result columns/typed rows/result hash, truncation, thời gian và giới hạn.

- Với kết quả row-level có source_dataset/source_row_id: giữ cặp nguồn đúng từng row; không tự thêm nguồn không có trong projection.
- Với COUNT/SUM/GROUP hoặc projection không còn source ID: ghi lineage_mode=snapshot_query, snapshot/table scope/SQL/result hash. Không gán một source_row_id mẫu làm bằng chứng cho toàn aggregate.
- OBSERVED cho identity đã kiểm và facts thực nhận từ nguồn. Kết quả aggregate là DERIVED liên kết evidence nguồn/snapshot/query execution đã quan sát; parent IDs phải tồn tại.
- Model chỉ trích evidence IDs đã được EvidenceStore cấp. Không tin self-declared witness của model.
- Đối chiếu factual claim với kết quả delivered và đọc lại SQL trên cùng snapshot khi kiểm offline. Điều này chưa chứng minh SQL trả lời đúng câu hỏi; việc đó do EX/scorer riêng đánh giá.
- Label trong CTU là trường dữ liệu có thể được hỏi trực tiếp trong query profile. Nó không là expected answer hoặc lệnh ép verdict malicious/benign; vẫn giữ quy tắc giấu nhãn chuẩn trong demo network cũ.

### 5.3. Lỗi và trạng thái

Phân biệt: lỗi hạ tầng/identity, lỗi provider, không có SQL, syntax, safety, execution, semantic mismatch, truncation, citation/fact sai và human decision.

Không có SQL hoặc SQL sai là model failure trong denominator khi run identity hợp lệ. Thiếu DB/gold/usage/identity làm phép đo chưa hợp lệ hoặc incomplete; không biến thành điểm 0 hoặc loại riêng để tăng accuracy. Unknown cost giữ riêng và chặn transmission tiếp. Người duyệt không thể biến technical-invalid thành success.

## 6. Protocol model và ngân sách

### 6.1. Hợp đồng model

| Vai trò | Model | Request contract |
|---|---|---|
| Demo network cũ | gpt-4.1-mini-2025-04-14 | temperature=0; cap 1.000; retry=0; network_investigation; tổng tối đa 4 |
| R2 E0/E3 mới | gpt-5-mini-2025-08-07 | reasoning_effort=low; không gửi temperature; cap 1.000; retry=0; endpoint chính thức |
| Orchestrator/assessment query profile | gpt-4.1-mini-2025-04-14 | temperature=0; cap 1.000; retry=0; tool_choice=auto cho routing |

E0 một request sinh SQL. E3 tối đa ba linker + ba generator requests; tối đa 12 DB-tool calls. Pipeline query tối đa một routing request + runtime + một assessment request. Không tự tạo lời nhận định khi request cuối thất bại.

### 6.2. Số lần gọi tối đa phải đặt trước

| Lượt mới | Quy mô | Cận request |
|---|---|---:|
| Calibration E0/E3 | 24 × (1 + 6) | 168 |
| Evaluation E0/E3 | 96 × (1 + 6) | 672 |
| Pipeline với cấu hình E0 đã chọn | 32 × (1 + 1 + 1) | 96 |
| Pipeline với cấu hình E3 đã chọn | 32 × (1 + 6 + 1) | 256 |
| Bốn câu demo cuối khóa | Tập con của 32 receipt pipeline | 0 mới |

Cận tối đa toàn phần mới: **1.096 request**, gồm 1.032 GPT-5-mini requests và 64 GPT-4.1-mini requests nếu triển khai E3. Nếu triển khai E0: 936 request, gồm 872 GPT-5-mini và 64 GPT-4.1-mini. Demo network cũ nếu chưa dùng còn tối đa bốn request trong quyền/window riêng; không cộng tiền cũ thành ngân sách mới.

Cận calls không phải cận tiền. Tính tiền từ toàn payload/history/schema/tool result + framing bound, output cap và giá chính thức tại lúc preflight. Không lấy chi phí trung bình bộ tám câu để suy ra trần.

Có ba record riêng: calibration, evaluation và pipeline integration. Chúng đại diện ba công việc khác nhau; không dùng window mới để chạy lại một công việc đã claimed/consumed. Migration laptop/cloud phải giữ trạng thái authoritative và chặn host cũ; không tạo bản ledger rỗng.

### 6.3. Interface accounting chung

RunJournal.claim(release: dict, *, ledger_path: Path) -> RunJournal thực hiện atomic claim ở canonical root đã khai báo trong release. RunJournal.reserve(role: str, payload: dict) -> dict ghi reservation trước SDK; RunJournal.record_response(reservation_id: str, response: object) -> dict ghi actual model/usage/cost trước parse; RunJournal.fail(reservation_id: str, safe_code: str) -> None giữ exposure và terminal state.

ScopedOpenAIClient(client: object, *, role: str, contract: dict, journal: RunJournal) có giao diện chat.completions.create tương thích SDK. Ba role routing/r2/assessment có model contracts riêng; mọi role cùng RunJournal. QueryTransport adapter r2 gọi scoped client r2; OpenAIProvider nhận scoped client routing/assessment, không tạo client không có guard.

Reserve toàn suite trước claim; reserve mỗi case gồm mọi role còn lại; reserve từng request trước transmission. Không trừ nested request hai lần khi tổng hợp, không xóa costs lúc provider.reset_tracking(). Implementation/selection/evidence SHA ghi ở receipts, không hash future commit hoặc chính lock vào nội dung lock gây vòng lặp.

### 6.4. Chọn cấu hình trước evaluation

Chạy E0/E3 trên 24 calibration, cùng model/data/runtime/scorer. Chọn theo:
1. EX cao hơn.
2. Chi phí usage thấp hơn.
3. Ít model calls hơn.
4. Latency thấp hơn.
5. Nếu vẫn bằng nhau, chọn E0.

Khóa cấu hình triển khai sau calibration. Không chỉnh prompt/tool/schema sau khi đọc evaluation. Evaluation vẫn chạy cả E0/E3 để có đối chứng cùng 96 IDs; kết quả này không thay cấu hình đã chọn trong cùng protocol. Nếu evaluation cho thấy lựa chọn calibration kém, ghi finding; cải tiến thuộc series sau, không chạy lại.

Calibration có thể không chọn được nếu provider/identity không hợp lệ hoặc thiếu đủ records. Khi đó không mở evaluation/pipeline paid; bàn giao trạng thái incomplete và ngân sách thật.

## 7. Các chỉ số phải giao

### 7.1. R2 trên nhiều DB

- EX base: correct/n cho /64 ngoài SOC, /32 CTU, /96 tổng; đủ hai conditions.
- Macro database/domain; difficulty và SQL feature, n/coverage ở từng hàng.
- Syntax validity, execution success, no-final-SQL, safety rejection, provider errors.
- Schema linking: tables/columns/relationships precision/recall/F1, exact-set và valid join path.
- Value grounding: typed literal/operator, DB witness precision, unsupported literal rate; thiếu context là NA.
- Model calls, DB calls, tokens, latency và known/unknown cost.
- Win/loss/tie E0/E3 và paired delta; cluster bootstrap theo database/family đã pin, 10.000 lần, seed 20261007. Wilson cấp câu chỉ là diagnostic có giả định độc lập.
- Giữ nguyên denominator dự kiến khi partial, đồng thời ghi completed/scored/paired counts. 96 câu thuộc 93 families, không giả định 96 quan sát độc lập.
- Existing two-instance semantic fixtures chỉ nằm ở phụ lục kiểm scorer/độ bền. Ghi synthetic; không thay EX trên DB nguồn thật, không gọi là official Spider Test Suite Accuracy.

### 7.2. Pipeline trên 32 câu CTU thật

| Chỉ số | Mẫu số và ý nghĩa |
|---|---|
| Routing success | Số câu model thực chọn đúng network_query và giữ câu hỏi /32 trong query profile; không là R1 chọn ba tools |
| Runtime invocation coverage | Số câu thật gọi shared TextToSQLService /32 |
| Integrated EX | SQL cuối tạo trong pipeline trả kết quả đúng câu hỏi gốc /32 |
| Provenance validity | Row/source hoặc snapshot-query identity kiểm được /32 |
| Factual/citation validity | Nhận định có facts/citations hợp lệ; số được kiểm và coverage /32 |
| Technical workflow success | Routing, runtime, SQL execution, đúng kết quả, evidence và facts cùng đạt /32 |
| Human review coverage | Approved/rejected/escalated/pending; không coi pending là approved |
| Human-approved completion | Approved sau technical success /32; đây là kết quả workflow, không thay EX |
| Overhead | Calls, latency, token/cost routing/runtime/assessment tách riêng |

Điểm đúng dữ kiện không thay EX; SQL sai câu hỏi vẫn có thể cho facts tự nhất quán. Người duyệt phải xem cả câu hỏi, SQL, kết quả và nhận định. Không nhờ model tự chấm nhận định làm human decision.

## 8. File và trách nhiệm dự kiến

Các đường dẫn “mới” dưới đây là quyết định thiết kế, chưa tồn tại tại SHA đã đọc.

| File | Việc cần làm |
|---|---|
| vinsoc_text2sql/service.py — mới | QueryRequest; dịch vụ generate/execute dùng chung; không gold |
| vinsoc_text2sql/accounting.py — mới | RunJournal và scoped clients cho routing/R2/assessment, tổng chi phí một allocation |
| vinsoc_text2sql/executor.py — mới | SqlExecutor/worker, caps, kết quả typed và isolation receipt |
| skills/network_query_skill.py — mới | NetworkQuerySkill, QueryContext, chuyển query result thành evidence_items |
| agent/network_query_policy.py — mới | Profile tool/schema, giữ câu hỏi gốc, facts/citations và validation |
| agent/orchestrator.py | Thêm investigate_query; dùng lifecycle/EvidenceStore/review hiện có |
| cli/main.py | Lệnh query/preflight/review/render; không mặc định MockProvider |
| evaluation/r2_cross_domain_v1/live.py | Adapter gọi shared service; không hai logic sinh SQL |
| evaluation/r2_cross_domain_v1/tools.py | Inject executor thay vì DB connection có quyền rộng; giữ semantic contract/caps |
| evaluation/r2_cross_domain_v1/release.py | Gate runtime mới, scope calibration/evaluation và budget riêng |
| evaluation/r2_cross_domain_v1/reporting.py, statistics.py | Dùng lại; bổ sung external64/CTU32 và gắn runtime identity nếu thiếu |
| evaluation/finalization/query_pipeline_contract.py — mới | Khóa profile/runtime/scope/caps/model và toàn request budget |
| scripts/run_vinsoc_query_acceptance.py — mới | Batch 32 qua public API; preflight-only, journal và partial |
| scripts/render_query_pipeline_report.py — mới | HTML đọc receipt thật, không API/DB query |
| tests/test_text2sql_shared_service.py — mới | Quyết định deterministic trên real DB/saved live artifacts |
| tests/test_network_query_skill.py — mới | Source lineage/aggregate/scope trên CTU thật |
| tests/test_network_query_lifecycle.py — mới | Public entrypoint và lifecycle receipt; actual live bằng acceptance runner |
| .github/workflows/ci.yml | Khôi phục bundle DB nguồn thật đã pin trước new real-DB tests; không gọi model |
| tests/test_query_pipeline_contract.py — mới | Khóa, budgets, scope và cấu hình deterministic |
| docs/evaluation/VinSOC_Final_Report_2026-10-15.md — mới | Báo cáo từ artifacts |
| results/evaluation_v1/text2sql_integration_v1/ | Calibration/evaluation/pipeline receipts và bảng điểm |

Không sửa frozen gold, benchmark reference hoặc old winner lock. Nếu thay file được khóa runtime lịch sử: giữ khóa cũ để nó mô tả version cũ; lập execution lock mới, không gắn mã mới vào identity cũ.

## 9. Nhiệm vụ thực hiện

### T0 — Xác minh HEAD, nguồn sự thật và preservation

**Đầu vào:** master hiện hành và receipts mục 2. **Đầu ra:** setup_receipt.json. **Owner:** người thực hiện; không API.

- [ ] Đọc toàn tài liệu này và closeout 07/10; ghi git branch/status/staged paths/HEAD/origin/master. Chỉ fast-forward khi không mất thay đổi.
- [ ] Lập protected hashes cho R1/R2 benchmark, prompts/locks/scorers và kết quả lịch sử; không đọc frozen gold để phân tích.
- [ ] Đọc canonical ledger/technical receipts trên laptop trước khi kết luận chưa chạy. Nếu cloud migration đã có, đối chiếu authoritative state; không dispatch Actions thử.
- [ ] Đánh dấu VERIFIED_EXISTING cho phần có bằng chứng; nêu chính xác phần thiếu. Không dùng tên checkbox cũ để làm lại.
- [ ] Ghi receipt public-safe: SHA, lệnh/exit code, file identity đã kiểm và blockers. Không đưa personal paths/key/private gates vào Git.

**Gate:** đúng repo/master, không divergence chưa xử lý, có ledger state hoặc báo đúng đầu vào thiếu.

### T1 — Đóng A2/A3 của demo network cũ trước khi đổi orchestrator

**Files:** runner/renderer/lock hiện có; output mới dưới network_e2e_v1, không overwrite.

- [ ] Xác minh đúng binary snapshot đã khóa và CI HEAD hiện chạy. Không sửa A1 nếu không có regression được tái hiện.
- [ ] Nếu canonical window chưa dùng: xác minh .env/account/pricing/reconciliation rồi chạy preflight-only.
- [ ] Chỉ khi PASS, dùng quyền đã cấp để chạy đúng một invocation, hai scenario, tối đa bốn request; không hỏi lại quyền demo cũ.
- [ ] Nếu đã used/claimed hoặc có receipt live, không gửi request mới. Render và bàn giao receipt hiện có.
- [ ] Render JSON thực; người thật duyệt hoặc giữ awaiting_human. Partial thì giữ partial, chốt lý do/cost thật.
- [ ] Commit/push sanitized evidence/runbook; kiểm CI evidence SHA. Bàn giao A trước thay đổi T3–T5 có thể làm old content lock hết hiệu lực.

**Gate:** A2/A3 đã kết thúc bằng receipt thật hoặc blocked/partial có bằng chứng. Blocker private-input không ngăn T2–T6 làm offline; không trì hoãn toàn dự án.

### T2 — Khôi phục các DB đã khóa và xác minh 120 câu bằng dữ liệu thật

**Files:** runtime_registry.json/source manifest/benchmark lock hiện có chỉ đọc; ignored DB/source paths.

- [ ] Kiểm bytes/source member hashes, schema/PK/FK/catalog và snapshot logical identity. Tìm file đã có trên laptop trước; không rebuild chỉ vì runtime khác thiếu file.
- [ ] Bản network E2E binary mới không tự thay được CTU binary đã pin trong cross-domain registry. Giữ riêng hai identity và đúng path của từng protocol.
- [ ] Chạy validator hiện có:
~~~powershell
python -m scripts.validate_r2_cross_domain --registry evaluation/r2_cross_domain_v1/runtime_registry.json --benchmarks evaluation/r2_cross_domain_v1/benchmarks --lock evaluation/r2_cross_domain_v1/benchmark.lock.json --output .vinsoc/final-report/data-validation.json
~~~
- [ ] Yêu cầu exit 0 và đủ 24/96, source/snapshot checks, base gold parity; các fixture tổng hợp lịch sử chỉ là phụ lục.
- [ ] Nếu thiếu nguồn, ghi database_id/path/hash mong đợi. Việc tải/chuyển đổi bổ sung phải dùng nguồn đã pin và giữ lỗi; không dùng fixture thay DB.
- [ ] Đóng gói chính các binary runtime đã xác minh thành bundle real-data dùng cho CI/acceptance, kèm relative path map, hashes, source attribution/license. Binary không commit vào Git. Tải lên artifact có retention đủ qua đợt bàn giao; khóa artifact/run identity và digest trong receipt. Không rebuild để thay exact binary.
- [ ] Cho CI tải đúng bundle đã pin với quyền đọc artifact, kiểm digest/manifest và đặt VINSOC_LOCAL_SNAPSHOT/registry paths trước real-DB tests. Không cấp API key cho job kiểm dữ liệu hoặc worker. Nếu bundle chưa có, CI của các tasks phụ thuộc chưa được gọi full real-data PASS.
- [ ] Chọn trước bốn demo IDs từ 32 CTU theo bốn nhóm: filter/time, DISTINCT, GROUP/HAVING, Boolean hoặc ORDER/LIMIT. Chọn hash-order seed 20261008 trong từng nhóm, không trùng; khóa selection trước model calls.

**Đầu ra:** real_data_validation.json, source/snapshot manifest, real-data bundle/CI restore receipt, demo_selection.json. **Gate:** validation thực đạt; không chỉ dựa receipt cũ.

### T3 — Dịch vụ Text-to-SQL dùng chung và execution worker

**Files:** service.py/executor.py/accounting.py mới; live.py/tools.py adapter; tests shared service.

**Interfaces:** dùng đúng QueryRequest, QueryTransport, TextToSQLService.generate/execute, SqlExecutor.query tại mục 4–5; RunJournal/ScopedOpenAIClient tại mục 6.3.

- [ ] Viết kiểm tra chưa đạt cho shared interface, không nhận gold, context sai DB, blocked SQL không đến worker và SQL lấy từ saved live artifact. Dùng DB nguồn thật; không fake transport.
- [ ] Chạy kiểm tra để ghi FAIL rõ; tests yêu cầu DB thật phải fail với REAL_DATA_REQUIRED nếu thiếu, không tự skip để nghiệm thu.
- [ ] Chuyển orchestration thuật toán từ run_live_case vào service và để benchmark adapter gọi service. Không chỉnh prompt/case-specific rules.
- [ ] Inject SqlExecutor cho mọi query DB-tool/final SQL; đưa worker vào môi trường cách ly mục 5, không secrets/network.
- [ ] Dùng SQL/predictions live đã lưu từ dev để xác minh read-only, syntax/execution/result hash và type handling; không sửa archived artifact.
- [ ] Kiểm hash source/DB trước/sau, targeted/full tests, compile/diff; commit/push và CI đúng SHA.

**Đầu ra:** mã chung, real-DB regression receipt, worker isolation receipt, execution identity mới. **Gate:** benchmark/production import cùng service và SQL executor; không còn hai vòng sinh SQL.

### T4 — NetworkQuerySkill và nguồn evidence thật

**Files:** network_query_skill.py; tests; schema query receipt mới nếu cần.

- [ ] Viết/chạy kiểm tra FAIL cho row-result, aggregate-result, kết quả rỗng đúng nghĩa, truncation, source không tồn tại và DB sai scope trên CTU thật.
- [ ] Implement QueryContext và skill; generate bằng service rồi execute; không đưa gold/case annotation vào skill.
- [ ] Row-level dùng đúng cặp nguồn; COUNT/GROUP dùng snapshot_query lineage, không bịa row lineage. Failed-query không thành “không tìm thấy sự kiện”.
- [ ] Khóa result hash/type/columns/truncation; trả evidence_items vào EvidenceStore theo contract hiện có.
- [ ] Kiểm exact query replay từ saved live SQL trên DB thật, đóng mọi handle, snapshot bytes không đổi; targeted/full/compile/diff, commit/push/CI.

**Đầu ra:** skill, provenance contract, real-DB lineage receipt. **Gate:** mọi returned fact có identity đủ kiểm lại.

### T5 — Public orchestrator, CLI và guard cho mọi tầng gọi model

**Files:** agent/orchestrator.py, network_query_policy.py mới, cli/main.py, query_pipeline_contract.py.

- [ ] Thêm investigate_query và lifecycle chung; giữ investigate cũ. Không IOC giả; query profile không tự tạo MockProvider.
- [ ] Tool network_query strict question-only, validate câu hỏi gốc/scope; model tự chọn native call. Không ép tool_choice=required hoặc tạo arguments trong script.
- [ ] Dùng EvidenceStore/tool response hiện có; không cắt evidence ở nhánh 4.000 ký tự mặc định. Quá payload bound là lỗi thật.
- [ ] Ghi metadata riêng query_policy; không để đọc nhầm network_policy và approve do fallback.
- [ ] Trước routing, reserve đủ runtime + assessment của cả case; mọi tầng dùng một journal có role budgets/model contracts. Ghi usage trước parse; không chỉ đo provider tầng ngoài.
- [ ] Giữ technical-invalid blocked trước người duyệt. Deferred review lưu receipt gốc; quyết định thật ở receipt liên kết hash, không gọi model thêm.
- [ ] Tests deterministic dùng real DB/saved artifacts kiểm scope/bounds/facts/metadata; actual calls và lifecycle sẽ nghiệm thu ở T9.
- [ ] Full regression cho profile cũ, compile/diff/preservation; commit/push/CI đúng SHA.

**Đầu ra:** CLI query/preflight/review, runtime/profile lock builder, toàn bộ accounting path. **Gate:** luồng sản phẩm đủ điểm nối; chưa gọi đây là live success.

### T6 — Khóa protocol mới, bộ chấm và reporting

**Files:** release.py/live.py/reporting.py/statistics.py; runner acceptance mới; .github/workflows/ci.yml; tests contract.

- [ ] Khóa source SHA của shared runtime/executor/skill/profile, model configs, dataset/split/scorer identities và cap tại implementation SHA.
- [ ] Giữ benchmark.lock.json dữ liệu và paid_authorized=false nguyên bytes. Execution release mới cấp scope riêng; không sửa false thành true trong khóa lịch sử.
- [ ] Benchmark adapter gọi generate/execute; scorer đọc output đã chốt và gold riêng sau đó. Pipeline runner gọi investigate_query cho 32 IDs, không private dispatcher.
- [ ] Chạy offline chấm saved live outputs trên DB thật: SQL đúng, sai và không có SQL; pipeline OK không đồng nghĩa EX. Không tạo prediction mới từ script.
- [ ] Kiểm report có external64/CTU32, per-module coverage, paired IDs và planned/completed counts; missing usage/provenance không bị loại riêng để tăng điểm.
- [ ] Khóa thứ tự calibration/evaluation theo danh sách runtime đã lock; điều kiện E0 trước E3, cùng code trong mỗi cặp. Không commit/sửa mã giữa hai conditions.
- [ ] Cập nhật job CI kiểm mã để restore bundle DB nguồn thật T2 trước các new real-DB tests; chạy cả Python 3.11/3.12, không fake fallback hoặc skip missing source. CI không gọi API. Ghi riêng những synthetic tests lịch sử vẫn đang chạy.
- [ ] Commit/push và full CI đúng SHA. Nếu dữ liệu runtime bị thiếu, gate local chưa đạt dù CI xanh.

**Đầu ra:** release lock, runner, reporting commands, xác minh gold isolation và source hashes. **Gate:** protocol mới đủ để chạy T8/T9; không synthetic metric trong report chính.

### T7 — Dự toán cụ thể và quyền paid cho phần mới

**Files:** private gates/release records; sanitized preflight receipts.

- [ ] Tính cận money cho 168/672 và pipeline 96 hoặc 256 requests theo giá chính thức mới kiểm. Bao gồm framing/history/schema/tool result, phí từng model và prior costs thuộc cùng allocation.
- [ ] Kiểm token bound, output cap, payload/schema metadata và rủi ro usage thiếu; cached discount không dùng để giảm conservative reserve.
- [ ] Xác minh tài khoản/project/allocation còn lại, source và UTC; account/pricing tối đa sáu giờ tuổi.
- [ ] Bàn giao gói rõ: calls tối đa theo model, tiền calibration, tiền evaluation, tiền pipeline, tổng, remaining và các khoản chưa rõ.
- [ ] Xin quyết định ngân sách/phạm vi mới dựa trên gói đã tính; không hỏi lại quyền demo cũ, không tự nâng budget hoặc cắt case.
- [ ] Preflight-only phải 0 attempts/0 responses/client=false và fail trước SDK khi thiếu một gate.
- [ ] Nếu ngân sách không đủ: ghi chính xác số thiếu. Nếu cần scope nhỏ hơn, lập protocol mới được quyết định trước run; không gọi một phần 96 là hoàn tất 96.

**Đầu ra:** preflight theo scope, bảng cost bound, quyết định ngân sách và authoritative windows. **Gate:** quyền + tiền + identity thật, không chỉ cờ authorized=true.

### T8 — Calibration và đối chứng E0/E3 trên 96 câu thật

**Files:** results/evaluation_v1/text2sql_integration_v1/calibration/ và evaluation/; không overwrite.

- [ ] Một lượt calibration gồm đủ 24 IDs cho E0 và E3; 48 records, tối đa 168 requests. Không tuning prompt trong đợt này.
- [ ] Chấm EX bằng scorer riêng; chọn cấu hình theo mục 6.4 và khóa selected configuration trước evaluation.
- [ ] Bảo đảm selection-lock commit có CI đúng SHA; các source/runtime bytes không thay đổi so với calibration. Receipt giữ SHA producer từng lượt.
- [ ] Một lượt evaluation cùng 96 IDs cho E0/E3; 192 records, tối đa 672 requests; cùng model/data/scorer/runtime và caps.
- [ ] Wrong SQL/TOOL_LIMIT/parse failure được giữ; không retry. Provider/identity/unknown-cost failure chặn paid tiếp, lưu partial, không mở window khác để cứu run.
- [ ] Chấm raw flags/cost theo từng case; báo micro/macro/external64/CTU32, module metrics và paired statistics.
- [ ] Mọi raw response/request/usage giữ trong bản riêng an toàn; public outputs loại secrets/error bodies/đường dẫn cá nhân nhưng giữ model-authored SQL/trace cần kiểm.
- [ ] Commit/push artifacts/report/manifest; CI evidence SHA. Không sửa implementation sau output rồi gán điểm cũ cho bản mới.

**Đầu ra:** 48 calibration records, selection lock, 192 evaluation records hoặc partial thật, báo cáo module/thống kê và cost journal. **Gate:** full result chỉ khi mọi ID có record hợp lệ; điểm model không cần 100%.

### T9 — Đo pipeline thật trên toàn bộ 32 câu CTU

**Files:** run_vinsoc_query_acceptance.py, output pipeline/, technical/human receipts.

- [ ] Xác minh selected config, snapshot/scope và runtime source hash đúng bản được đánh giá T8. Nếu runtime semantic bytes đã đổi, không gọi là cùng môđun đã chấm; dừng/release mới.
- [ ] Preflight toàn bộ 32 câu gồm outer routing, inner SQL và final assessment; tổng tối đa 96 nếu E0 hoặc 256 nếu E3. Không mượn 4-request window cũ.
- [ ] Chạy một lượt 32 qua public investigate_query; câu hỏi nguyên gốc, model native tool call, model SQL thật, DB thật, model assessment thật. Không đưa đáp án vào prompt.
- [ ] Nhật ký từng case chứng minh invocation của service bằng implementation/config hash; ghi toàn nested calls, DB calls, SQL, result hash, evidence IDs và lifecycle.
- [ ] Scorer offline chấm SQL từ pipeline trên original question/gold; không lấy score của T8 để điền vào T9.
- [ ] Kiểm evidence/result/facts; người thật duyệt từng technical-valid case, giữ rationale/UTC/hash. Technical-invalid không đưa vào approve; pending được giữ rõ.
- [ ] Báo đủ các chỉ số mục 7.2 với denominator 32; ngắt giữa chừng vẫn ghi planned=32/completed/scored thật.
- [ ] Commit/push public-safe JSON/HTML/report và CI evidence SHA; không thêm run để chọn câu đẹp.

**Đầu ra:** 32 case traces hoặc partial thật, integrated EX, routing/runtime/provenance/factual/review metrics và chi phí cả luồng. **Gate:** có trace sống đủ điểm nối; không chỉ service trả SQL trong script riêng.

### T10 — Demo và gói giao nộp cuối khóa

**Files:** render_query_pipeline_report.py; report/runbook/manifest; không API mới.

- [ ] Dựng HTML standalone từ bốn demo IDs đã chọn ở T2 và bảng đủ 32 cases; ID thất bại phải hiện thất bại. Không thay ID bằng câu thành công khác.
- [ ] Đối chiếu JSON–HTML: câu hỏi → native call → SQL → result → evidence → assessment → verification → human review; cost/status/counts khớp.
- [ ] Chuẩn bị kịch bản 5–7 phút: kiến trúc, một trace đầy đủ, một lỗi thật nếu có, bảng external64/CTU32 và giới hạn. Mở output model thật đã lưu phải ghi “xem lại lượt thật”, không “live mới”.
- [ ] Nếu trình diễn lại live được yêu cầu, cần scope/window/budget riêng đã quyết định; không tự gọi lại từ nút demo.
- [ ] Bàn giao R1 từ artifact hiện có: 22/24, đầy đủ metrics/failed IDs/config, caveat và frozen pending. Không chạy R1 để lấp báo cáo.
- [ ] Kiểm toàn bộ protected hashes; final report có SHA implementation/evidence, CI links, producer config/dataset/scorer hashes và command reproduction.
- [ ] Manifest SHA-256 cho từng artifact; giữ source/raw SDK/private ledger ngoài public Git. Có source bundle/model journal riêng được kiểm soát truy cập để tái lập.
- [ ] Chạy commands offline trong checkout sạch với đúng sources đã khóa, ghi lệnh/exit code/hash. Tests xanh một mình không thay successful acceptance.
- [ ] Commit/push docs/results; CI final SHA; bàn giao tất cả trạng thái đạt/chưa đạt và blocker thực.

**Đầu ra:** gói trong mục 10. **Gate:** người xem mở được báo cáo/demo và tự lần theo evidence mà không gọi API.

### T11 — Ghi nhận phần deferred, không tự mở thêm thí nghiệm

- [ ] Matched E0/E3 tám câu trong ma trận 06/10 vẫn chưa có R2_MATCHED_v1.lock/report. Báo riêng là deferred; bộ 96 có 32 CTU không tự hoàn tất đúng protocol tám câu đó.
- [ ] Không chạy thêm bộ tám câu chỉ để lặp bằng chứng đã có ở phạm vi rộng hơn, trừ khi hội đồng yêu cầu đối chứng chính xác protocol cũ và có gate riêng.
- [ ] R1 frozen cần quyền riêng. R2 cần một tập kiểm tra độc lập mới nếu muốn claim ngoài development; không đổi tên S1/S4 đã consumed thành fresh holdout.
- [ ] Nếu không có điểm độc lập trước deadline, kết luận DEV_VERIFIED / HOLDOUT_PENDING. Các phần đo rộng/integration có trạng thái riêng.
- [ ] Khi module thiếu function không được bịa trace, script-authored assessment, hardcoded SQL hoặc auto-approval để “kịp demo”.

**Đầu ra:** remaining_work.md với quyết định scope, không xóa mục tiêu cũ khỏi lịch sử.

## 10. Danh mục giao nộp và điều kiện nghiệm thu

| Mã | Phải giao | Đạt khi |
|---|---|---|
| D1 | Source code, dependency pins, runtime/profile/execution locks | Checkout sạch cài/chạy được; benchmark và production gọi cùng service/executor |
| D2 | Data/source/snapshot manifests và real-data validation | Đúng bytes/schema/parity/scope; không dữ liệu giả thay thế |
| D3 | Calibration records, bảng E0/E3 và selected config | 24 IDs/condition, selection trước evaluation, usage và identity đủ |
| D4 | Evaluation records và report | 96 IDs/condition, EX ngoài SOC64/CTU32/tổng96, paired/modules/statistics và costs |
| D5 | Pipeline acceptance | 32 câu CTU qua public orchestrator, SQL/evidence/assessment thật, integrated score riêng |
| D6 | Human review receipts | Decision/rationale/UTC/technical hash từ người thật; pending không thành approved |
| D7 | Standalone HTML và CLI runbook | Xem lại offline từ receipt thật; không gọi API/DB để render |
| D8 | Báo cáo cuối khóa và bảng R1/R2 | R1 lịch sử/cấu hình/giới hạn rõ; kết quả R2 lịch sử, mới và tích hợp tách riêng |
| D9 | Reproduction package | Commands offline, expected hashes, manifest, implementation/evidence CI, dữ liệu truy được |
| D10 | Cost/partial/blocker register | Attempts/received/usage/known/unknown/exposure đúng, không bỏ charged failure |

**Hoàn tất phép đo** không có nghĩa model trả đúng mọi câu. Một bộ đo hợp lệ có thể có EX thấp; phải bàn giao lỗi đó. Nhưng bộ chặn trước API hoặc trace mock không đủ thay model evaluation.

**Hoàn tất demo tích hợp** cần ít nhất một trace thành công kỹ thuật được người thật duyệt trong bốn câu đã chọn, và trình bày đầy đủ trạng thái cả bốn. Nếu không câu nào đạt, sản phẩm được bàn giao với status failed/incomplete, không tuyên bố demo thành công. Không tăng request hoặc đổi câu để ép đạt.

**Hoàn tất toàn bộ mục tiêu ban đầu** còn phụ thuộc independent holdout riêng. Đánh giá rộng trên public dev và integration không tự mở hoặc hoàn tất gate đó.

Cấu trúc output đề nghị:
~~~text
results/evaluation_v1/text2sql_integration_v1/
  setup_receipt.json
  real_data_validation.json
  demo_selection.json
  calibration/
  evaluation/
  pipeline/
  public_cost_summary.json
  artifact_manifest.json
  delivery_receipt.json
docs/evaluation/VinSOC_Final_Report_2026-10-15.md
docs/VinSOC_Text2SQL_Demo_Runbook_2026-10-15.md
~~~
Các folder paid phải append-only và có run identity. Chọn output khác không cấp quyền chạy lại.

## 11. Lịch ưu tiên trước 16/10

Đây là lịch mục tiêu cho người thực hiện, không phải cam kết đã có nguồn/key/ngân sách.

| Ngày | Việc ưu tiên | Điều kiện chuyển |
|---|---|---|
| 08/10 | T0, chốt trạng thái A2/A3 ở T1, xác minh data T2 | Blocker cụ thể; phần offline không bị treo vì thiếu key |
| 09–10/10 | T3–T5: shared runtime, executor, skill, public lifecycle và guards | Real-DB tests và exact-SHA CI đạt |
| 11/10 | T6–T7: khóa protocol, reporting, đủ cost bound và quyền mới | Data/CI/account/pricing/budget đều đạt |
| 12–13/10 | T8: calibration và evaluation 96 E0/E3 | Không đổi code/prompt giữa conditions; đủ records hoặc partial thật |
| 14/10 | T9: 32-case pipeline và người thật duyệt | Runtime hash khớp cấu hình đã chấm |
| 15/10 | T10: báo cáo, demo offline, reproduction và CI bàn giao | D1–D10 có evidence/status; T11 ghi deferred |

Nếu ngày 11/10 vẫn thiếu data/ngân sách hoặc worker/isolation: báo khả năng trễ ngay bằng các gate cụ thể, tiếp tục mã/report offline hợp lệ. Không thay output thật bằng mock để giữ lịch.

## 12. Mẫu bàn giao bắt buộc cho từng nhiệm vụ

~~~text
Nhiệm vụ:
Trạng thái: verified / blocked / partial / failed / awaiting_human
Initial / implementation / evidence SHA:
Files thực đổi:
Lệnh đã chạy, exit code, passed/failed/skipped:
Exact CI URLs, job names, SHA:
Data/runtime/prompt/schema/scorer hashes:
Attempts / responses / valid usage:
Known cost / unknown exposure / remaining allocation:
Đầu ra, manifest/hash:
Phần nghiệm thu chưa đạt và nguyên nhân:
Nhiệm vụ tiếp theo:
~~~

Không ghi “PASS” cho command chưa chạy. Một failure được lưu đầy đủ là kết quả trung thực; nó không phải acceptance success.

## 13. Trọng tâm rà soát trước giao

1. **Mã được đánh giá khác mã production:** T3/T6/T9 kiểm cùng service/executor/source/config hash. Không dùng một adapter chấm tốt và một pipeline giả lập khác.
2. **Bỏ sót chi phí inner calls:** T5/T7/T9 dùng toàn journal routing/linker/generator/assessment; không chỉ provider reset_tracking tầng ngoài.
3. **Aggregate có lineage giả hoặc số đúng từ query sai:** T4/T6/T9 tách snapshot-query provenance, EX và factual checks.
4. **Triage tự đóng, IOC giả hoặc default MockProvider:** T5/T9 chặn cho query profile; public API có receipt từng stage.
5. **Kết quả thiếu bị biến thành thành công:** T6/T8/T10 giữ denominator/planned coverage, partial/unknown và human pending; HTML không nâng trạng thái.

Kiểm thêm: không có case-specific alias/rules; không gold vào prompt; không thay scope schema bằng model argument; profile mới không được thừa hưởng điểm R1; CI skip không phải real-DB acceptance; HTML escape model text và không cắt mất nội dung.

## 14. Cơ sở phương pháp và nguồn đọc

Nguồn kho mã tại SHA đã đọc:
- [Closeout 07/10](https://github.com/Whats-up-pro/VinSOC/blob/c4ae3c56028b40425392e1ec779e39045c9211ef/docs/superpowers/plans/2026-10-07-vinsoc-e2e-closeout-and-cross-domain-next.md)
- [Ma trận nghiệm thu 06/10](https://github.com/Whats-up-pro/VinSOC/blob/c4ae3c56028b40425392e1ec779e39045c9211ef/docs/superpowers/plans/2026-10-06-network-e2e-completion.md)
- [Handoff 07/10](https://github.com/Whats-up-pro/VinSOC/blob/c4ae3c56028b40425392e1ec779e39045c9211ef/results/evaluation_v1/cross_domain_closeout/20261007/HANDOFF.md)
- [Benchmark đã khóa](https://github.com/Whats-up-pro/VinSOC/blob/c4ae3c56028b40425392e1ec779e39045c9211ef/evaluation/r2_cross_domain_v1/benchmark.lock.json)
- [Public orchestrator](https://github.com/Whats-up-pro/VinSOC/blob/c4ae3c56028b40425392e1ec779e39045c9211ef/agent/orchestrator.py)
- [SQL cố định hiện có](https://github.com/Whats-up-pro/VinSOC/blob/c4ae3c56028b40425392e1ec779e39045c9211ef/vinsoc_data/domain_queries.py)
- [Live R2 adapter](https://github.com/Whats-up-pro/VinSOC/blob/c4ae3c56028b40425392e1ec779e39045c9211ef/evaluation/r2_cross_domain_v1/live.py)
- [CI HEAD](https://github.com/Whats-up-pro/VinSOC/actions/runs/37583051568)
- [Actions E2E bị chặn trước API](https://github.com/Whats-up-pro/VinSOC/actions/runs/37583842122)

Nguồn phương pháp:
- [Spider — Yale](https://yale-lily.github.io/spider): đánh giá nhiều schema cần phân biệt DB ở các phần hiệu chỉnh/đánh giá. Đây là cơ sở cho báo cáo theo DB; không gán subset VinSOC thành điểm Spider chính thức.
- [Zhong, Yu, Klein, EMNLP 2020](https://aclanthology.org/2020.emnlp-main.29/): test-suite accuracy nhằm xấp xỉ đúng ngữ nghĩa trên nhiều DB instances. Hai fixture hữu hạn trong VinSOC chỉ là diagnostic, không chứng minh tương đương SQL trên mọi dữ liệu.
- [DuckDB — Securing DuckDB](https://duckdb.org/docs/current/operations_manual/securing_duckdb/overview): SQL không tin cậy có thể đọc file/network/extension và dùng tài nguyên. Read-only và AST checks là các lớp kiểm tra; worker cách ly vẫn cần cho đường thực thi SQL model.

**Ranh giới lượt soạn tài liệu:** Chỉ tạo bản giao việc; không sửa mã sản phẩm, không dispatch workflow paid, không tạo model prediction hoặc human decision. Mọi nhiệm vụ mới ở mục 9 còn unchecked cho đến khi người thực hiện có đúng bằng chứng.
