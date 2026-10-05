# VinSOC

Hệ thống hỗ trợ điều tra SOC: model chọn công cụ, skill trả evidence và báo cáo dẫn chứng để analyst review. Data access chỉ đọc; quyết định xử lý thuộc người dùng.

Python 3.11/3.12 · DuckDB · Research

## Kiến trúc

`Analyst → LLM orchestrator → CTI / Network / Endpoint skills → Evidence Store → Human review`

Evidence gồm `OBSERVED`, `DERIVED`, `EXTERNAL_INTEL`; nhận định phải truy được evidence ID. Tool selection, SQL execution và demo tích hợp được đánh giá riêng.

## Trạng thái đánh giá

| Track | Bộ dữ liệu / metric | Evidence và giới hạn |
|---|---|---|
| R1 tool calling | 24 dev, trong đó 5 no-tool; 8 frozen | Winner GPT-4.1 mini 22/24, F1 0.9508, no-tool 5/5; GPT-5 mini 19/24, F1 0.9355, no-tool 4/5. 11/24 gold dev-v2 adjudicated sau khi xem model. Decision-only, không thực thi tool; frozen vẫn cần authorization riêng. |
| R2 CTU dev S5/S7 | 8 case; Execution Accuracy | [Phase-2 E3 đã chấm](results/evaluation_v1/ctu_network_public/r2_phase2_live/20261001_3f9d72d/suite/report.json): **EX 7/8**, case006 TOOL_LIMIT, 44 responses, $0.02085850. Sau INTEGER hint chưa có verified full suite; không ghép test riêng thành 8/8. [E0](results/evaluation_v1/ctu_network_public/gpt5_e0/36520685612/ctu-r2-result.json) 0/8 và [remediation E3](docs/evaluation/r2_remediation_live_results.md) 1/8 là các điều kiện lịch sử riêng. |
| R2 CTU S1/S4 lịch sử | 8 case, holdout đã consumed | Script cũ báo E0 EX 0/8, E3 EX 2/8; E3 execution success 3/8 theo flags cũ. Syntax validity đúng nghĩa chưa xác minh; cost/provenance incomplete. Không đủ frozen eligibility. |
| R2 legacy three-source | 8 dev + 6 frozen | ThreatFox/CTU/OTRF contract riêng; snapshot CTU không chứng minh bộ three-source đã hoàn tất. |

Các kết quả dev không chứng minh generalization trên holdout. Xem [đính chính frozen](docs/evaluation/frozen_comparison_results.md), [protocol audit](docs/evaluation/ctu_frozen_protocol_audit_2026-09-30.md) và [remediation status](docs/evaluation/r2_remediation_status.md).

Trạng thái: **DEV_VERIFIED / HOLDOUT_PENDING**. JSON S1/S4 mới thiếu execution-scoring và verified run identity; pipeline `OK` không phải EX. [Báo cáo đính chính](docs/evaluation/FINAL_EVALUATION_REPORT.md) và [plan Task 0+1](docs/superpowers/plans/2026-10-05-vinsoc-finalization-fix.md) giữ frozen closed và cung cấp offline scorer/audit không gọi API.

Remediation giữ adapter source metadata, một controller fail-closed, telemetry trước parse, locked scorer và output append-only. Tasks 1-7 đã nghiệm thu offline; Tasks 8-10 được duyệt riêng và đã chạy một smoke + một suite E3 trên exact-SHA CI xanh. Tổng live cost từ usage $0.02185315; [trace, lỗi từng case và hashes](docs/evaluation/r2_remediation_live_results.md). Series live đã consumed; CLI offline cũ và frozen entrypoints vẫn closed. **STOP FOR HUMAN REVIEW**, không tự chạy tiếp thí nghiệm hoặc demo.

## Setup và verification offline

```powershell
pip install -r requirements.txt
python -m pytest -q
python -m compileall -q evaluation/dualsql_lite_ctu_gpt5_v2 scripts/audit_r2_historical_reports.py
```

Tests dùng synthetic fixtures; không cần API key hoặc snapshot local để chạy unit tests. Gate full S5/S7 yêu cầu snapshot và source bytes hiện có đã verify; xem command và artifact trong remediation status.

CI kiểm Python 3.11/3.12 tại [GitHub Actions](https://github.com/Whats-up-pro/VinSOC/actions). Test count gắn với SHA và command trong status, không dùng con số cố định trên README.

## Mã nguồn và tài liệu

| Path | Nội dung |
|---|---|
| `agent/`, `skills/` | Orchestrator, CTI/network/endpoint investigation |
| `evaluation/tool_calling/` | [R1 contract](evaluation/tool_calling/README.md) |
| `evaluation/dualsql_lite_ctu_gpt5_v2/` | R2 remediation controller/tools/report; gated live entrypoint trong `scripts/` |
| `evaluation/text_to_sql.py` | Scorer được khóa, comparator execution |
| `evaluation/text_to_sql_benchmarks/` | [Legacy R2 contract](evaluation/text_to_sql_benchmarks/README.md) |
| `tests/` | Unit/integration regression |

Thiết kế: [architecture](docs/architecture.md), [evaluation protocol](docs/evaluation_protocol_v1.md), [DuckDB layer](docs/duckdb_data_layer.md), [remediation plan](docs/superpowers/plans/2026-09-30-r2-evidence-controller-remediation.md).
