# VinSOC E2E Demo Runbook - Chi tiết đầy đủ

> **Version:** 1.0  
> **Date:** 2026-10-06  
> **Framework:** R1 (BFCL) + R2 (Spider/BIRD)

---

## Mục lục
1. [Tổng quan framework](#1-tổng-quan-framework)
2. [Tiền điều kiện](#2-tiền-điều-kiện)
3. [Demo R1 - Tool Calling](#3-demo-r1---tool-calling)
4. [Demo R2 - Text-to-SQL](#4-demo-r2---text-to-sql)
5. [Demo E2E - Network Investigation](#5-demo-e2e---network-investigation)
6. [Edge Cases](#6-edge-cases)
7. [Troubleshooting](#7-troubleshooting)

---

## 1. Tổng quan Framework

### 1.1 Hai Tracks đánh giá

```
┌─────────────────────────────────────────────────────────────────┐
│                        VinSOC Framework                          │
├─────────────────────────────────────────────────────────────────┤
│  R1: Tool Calling          │  R2: Text-to-SQL                  │
│  Reference: BFCL           │  Reference: Spider/BIRD             │
├─────────────────────────────────────────────────────────────────┤
│  • Chọn đúng tool         │  • Sinh SQL đúng syntax           │
│  • Arguments chính xác     │  • Execute đúng kết quả           │
│  • No hallucination        │  • Semantic matching              │
└─────────────────────────────────────────────────────────────────┘
```

### 1.2 Evidence Flow (E2E)

```
┌─────────┐     ┌─────────────┐     ┌────────────┐     ┌─────────┐
│ Model   │────▶│ Network     │────▶│ DuckDB     │────▶│Evidence │
│ Query   │     │ Investigation│   │ Read-only  │     │ Store   │
└─────────┘     └─────────────┘     └────────────┘     └─────────┘
                                                                │
                                                                ▼
┌─────────┐     ┌─────────────┐     ┌────────────┐     ┌─────────┐
│ Human   │◀────│ Assessment  │◀────│ Model      │◀────│ Facts   │
│ Review  │     │ Validation  │     │ Assessment │     │ Extracted│
└─────────┘     └─────────────┘     └────────────┘     └─────────┘
```

**Trích dẫn tài liệu:**
- Framework: [docs/evaluation_protocol_v1.md](docs/evaluation_protocol_v1.md)
- Architecture: [docs/architecture.md](docs/architecture.md)
- HITL Design: [docs/hitl_design.md](docs/hitl_design.md)

---

## 2. Tiền điều kiện

### 2.1 Cài đặt môi trường

```powershell
# Clone repo
git clone https://github.com/Whats-up-pro/VinSOC.git
cd VinSOC

# Tạo virtual environment
python -m venv .venv
.venv\Scripts\activate

# Cài dependencies
pip install -r requirements.txt

# Kiểm tra OpenAI key
cat .env  # OPENAI_API_KEY=sk-...
```

### 2.2 Kiểm tra snapshot

```powershell
# Kiểm tra CTU snapshot tồn tại
ls data/ctu_network_public/snapshots/

# Verify SHA
python -c "
import duckdb
conn = duckdb.connect('data/ctu_network_public/snapshots/ctu_dev.duckdb', read_only=True)
print('Tables:', [r[0] for r in conn.execute('SHOW TABLES').fetchall()])
print('Row count:', conn.execute('SELECT count(*) FROM network_flows').fetchone())
"
```

**Expected output:**
```
Tables: ['dataset_provenance', 'network_flows']
Row count: (243906,)
Sources: {'ctu13_s5': 129831, 'ctu13_s7': 114075}
```

### 2.3 Chạy tests pre-flight

```powershell
# Test E2E infrastructure
python -m pytest tests/test_finalization_live_window.py tests/test_network_e2e_policy.py tests/test_network_e2e_lifecycle.py tests/test_network_e2e_report.py -v

# Test CTU demo
python -m pytest tests/test_demo_ctu_network_public.py tests/test_demo_ctu_network_public_model_driven.py -v
```

**Expected:** Tất cả 89 tests pass

---

## 3. Demo R1 - Tool Calling

### 3.1 Tổng quan R1

**Reference:** BFCL (Berkeley Function Calling Leaderboard)

**Mục tiêu:** Model chọn đúng tool + arguments từ network_skill

**Metrics:**
| Metric | Mô tả |
|--------|--------|
| Tool Selection Accuracy | Exact tool multiset match |
| Exact Call F1 | Tool + required arguments |
| Required Argument Accuracy | Tất cả required args đúng |
| No-Tool Accuracy | Không hallucinate tool |

**Trích dẫn:**
- Metrics implementation: [evaluation/tool_calling/metrics.py](evaluation/tool_calling/metrics.py)
- Models: [evaluation/tool_calling/models.py](evaluation/tool_calling/models.py)

### 3.2 Chạy R1 Dev Benchmark

```powershell
# Set environment
$env:VINSOC_EVAL_PROVIDER = "openai"
$env:VINSOC_EVAL_MODEL = "gpt-4.1-mini-2025-04-14"

# Chạy decision mode (single-turn)
python -m evaluation.tool_calling benchmarks dev `
  --mode decision `
  --provider $env:VINSOC_EVAL_PROVIDER `
  --model $env:VINSOC_EVAL_MODEL `
  --temperature 0

# Output: results/evaluation_v1/r1/dev_decision_*.json
```

### 3.3 Phân tích kết quả R1

```powershell
# Xem kết quả
cat results/evaluation_v1/r1/dev_decision_latest.json | python -m json.tool

# Đọc metrics
python -c "
import json
with open('results/evaluation_v1/r1/dev_decision_latest.json') as f:
    data = json.load(f)
print('=== R1 Dev Results ===')
print(f\"Tool Selection: {data['metrics']['tool_selection_accuracy']:.4f}\")
print(f\"Exact Call F1: {data['metrics']['exact_call_f1']:.4f}\")
print(f\"Required Arg Acc: {data['metrics']['required_argument_accuracy']:.4f}\")
print(f\"No-Tool Acc: {data['metrics']['no_tool_accuracy']:.4f}\")
"
```

### 3.4 R1 Test Cases chính

#### Case 1: Correct Tool Selection
```
Input: 'Find network flows from IP 192.0.2.10'
Expected: network_investigation tool
```

#### Case 2: Required Arguments
```
Input: 'Show CTU flows for IP 192.0.2.10 between 2011-08-15 and 2011-08-16'
Expected: network_investigation with indicator, time_range
```

#### Case 3: No-Tool (No relevant data)
```
Input: 'Check virus total for malicious.com'
Expected: No tool call (CTI not available in network-only mode)
```

#### Case 4: Wrong Tool Rejection
```
Input: 'Get endpoint telemetry for workstation-01'
Expected: No tool (endpoint not in network_skill)
```

### 3.5 R1 Edge Cases

| Edge Case | Mô tả | Expected Behavior |
|-----------|--------|------------------|
| Duplicate Tool | Model gọi cùng tool 2 lần | DUPLICATE_CALL error |
| Missing Required Arg | Thiếu indicator trong network_investigation | REQUIRED_ARG_MISSING error |
| Extra Tool | Gọi tool không liên quan | EXTRA_TOOL error |
| Provider Error | API timeout/429 | PROVIDER_ERROR logged |

**Trích dẫn error categories:**
- [evaluation/tool_calling/matching.py](evaluation/tool_calling/matching.py) - Lines 45-78

---

## 4. Demo R2 - Text-to-SQL

### 4.1 Tổng quan R2

**Reference:** Spider / BIRD benchmarks

**Mục tiêu:** Model sinh SQL execute đúng trên DuckDB read-only

**Metrics:**
| Metric | Mô tả |
|--------|--------|
| Execution Accuracy | Kết quả SQL match gold |
| Syntax Validity | SQL parse được |
| Execution Success | Không crash |
| Safety Rejection | Đúng reject write queries |

**Semantic Matching Modes:**
```
ordered_rows   → Giữ thứ tự row
unordered_rows → Ignore order, giữ multiplicity
multiset_rows  → Ignore order và multiplicity
scalar        → So sánh giá trị đơn
boolean       → So sánh boolean
```

**Trích dẫn:**
- Snapshot manifest: [evaluation/text_to_sql_benchmarks/snapshot_manifest.json](evaluation/text_to_sql_benchmarks/snapshot_manifest.json)
- Dataset manifest: [evaluation/text_to_sql_benchmarks/dataset_manifest.json](evaluation/text_to_sql_benchmarks/dataset_manifest.json)

### 4.2 Chạy R2 Dev Benchmark

```powershell
# Verify snapshot SHA trước khi chạy
python -c "
import json
manifest = json.load(open('evaluation/text_to_sql_benchmarks/snapshot_manifest.json'))
expected_sha = manifest['snapshots'][0]['sha256']
print(f'Expected SHA: {expected_sha}')
"

# Chạy R2 evaluation
python -m evaluation.text_to_sql evaluate `
  --snapshot data/snapshots/vinsoc_public_v1.duckdb `
  --manifest evaluation/text_to_sql_benchmarks/snapshot_manifest.json `
  --split dev `
  --provider openai `
  --model gpt-4.1-mini-2025-04-14 `
  --temperature 0 `
  --output results/evaluation_v1/r2/dev_baseline.json

# Output: results/evaluation_v1/r2/dev_baseline.json
```

### 4.3 Phân tích kết quả R2

```powershell
# Xem kết quả
python -c "
import json
with open('results/evaluation_v1/r2/dev_baseline.json') as f:
    data = json.load(f)
print('=== R2 Dev Results ===')
print(f\"Execution Accuracy: {data['metrics']['execution_accuracy']:.4f}\")
print(f\"Syntax Validity: {data['metrics']['syntax_validity']:.4f}\")
print(f\"Execution Success: {data['metrics']['execution_success']:.4f}\")
print(f\"Safety Rejection: {data['metrics']['safety_rejection_rate']:.4f}\")
"
```

### 4.4 R2 Test Cases chính

#### Case 1: Simple SELECT
```sql
-- Query: 'How many flows in CTU S5?'
SELECT count(*) FROM network_flows WHERE source_dataset = 'ctu13_s5'
-- Expected: 129831
```

#### Case 2: JOIN với provenance
```sql
-- Query: 'Show botnet flows with dataset description'
SELECT nf.*, dp.description 
FROM network_flows nf 
JOIN dataset_provenance dp ON nf.source_dataset = dp.dataset_id
WHERE nf.label LIKE '%Botnet%'
-- Semantic: unordered_rows
```

#### Case 3: Aggregate với GROUP BY
```sql
-- Query: 'Top 5 source IPs by connection count'
SELECT src_ip, count(*) as cnt 
FROM network_flows 
GROUP BY src_ip 
ORDER BY cnt DESC 
LIMIT 5
-- Semantic: ordered_rows
```

#### Case 4: Time Range Filter
```sql
-- Query: 'Flows on 2011-08-15 between 10:00 and 12:00'
SELECT * FROM network_flows 
WHERE event_time BETWEEN '2011-08-15 10:00:00' AND '2011-08-15 12:00:00'
-- Semantic: unordered_rows
```

### 4.5 R2 Edge Cases

| Edge Case | SQL | Expected |
|-----------|-----|----------|
| Write attempt | INSERT/UPDATE/DELETE | SAFETY_REJECTION |
| Extension load | INSTALL/LOAD | SAFETY_REJECTION |
| Multi-statement | SELECT; SELECT | SYNTAX_ERROR |
| Non-SELECT | CREATE TABLE | SAFETY_REJECTION |
| NULL handling | COUNT(DISTINCT x) | Correct NULL handling |

**Trích dẫn:**
- Safety check: [evaluation/text_to_sql.py](evaluation/text_to_sql.py) - Lines 156-189

---

## 5. Demo E2E - Network Investigation

### 5.1 Tổng quan E2E Demo

**Mục tiêu:** Complete pipeline từ user query → network tool → evidence → assessment → human review

**Các scenario:**
- **Botnet**: CTU S5 - Malicious traffic
- **Normal**: CTU S7 - Normal traffic

**Trích dẫn:**
- CLI: [scripts/demo_ctu_network_public_model_driven.py](scripts/demo_ctu_network_public_model_driven.py)
- Policy: [agent/network_investigation_policy.py](agent/network_investigation_policy.py)
- Transport Guard: [evaluation/finalization/live_window.py](evaluation/finalization/live_window.py)

### 5.2 Chạy E2E Demo

#### Bước 1: Preflight Check (không gọi API)

```powershell
python -m scripts.demo_ctu_network_public_model_driven `
  --snapshot data/ctu_network_public/snapshots/ctu_dev.duckdb `
  --output results/e2e_preflight.json `
  --e2e `
  --preflight-only `
  --budget-usd 0.25
```

**Expected output:**
```json
{
  "mode": "e2e_preflight",
  "status": "preflight_pass",
  "preflight_pass": true,
  "snapshot_qualified": true
}
```

#### Bước 2: Chạy E2E Live

```powershell
python -m scripts.demo_ctu_network_public_model_driven `
  --snapshot data/ctu_network_public/snapshots/ctu_dev.duckdb `
  --output results/e2e_demo.json `
  --e2e `
  --budget-usd 0.25
```

**Expected output:**
```json
{
  "status": "complete",
  "attempted_calls": 4,
  "responses_received": 4,
  "scenarios_completed": 2,
  "known_cost_usd": 0.0162
}
```

#### Bước 3: Render HTML Report

```powershell
python scripts/render_network_e2e_report.py `
  --receipt results/e2e_demo.json `
  --output results/e2e_demo.html

# Mở file để xem
Start-Process results/e2e_demo.html
```

### 5.3 E2E Evidence Flow chi tiết

```
Step 1: User Query
─────────────────────────────────────────────
Input: "Analyze IP 147.32.84.165 for suspicious activity"

Step 2: Model generates tool call
─────────────────────────────────────────────
tool_call: network_investigation
arguments: {
  "indicator": "147.32.84.165",
  "indicator_type": "ipv4",
  "time_range": {
    "start": "2011-08-15 00:00:00",
    "end": "2011-08-15 23:59:59"
  }
}

Step 3: Policy validates arguments
─────────────────────────────────────────────
✓ IPv4 format valid
✓ Scope within bounds
✓ Tool is allowed (network_investigation)

Step 4: Tool executes (DuckDB read-only)
─────────────────────────────────────────────
SELECT * FROM network_flows 
WHERE src_ip = '147.32.84.165'
AND event_time BETWEEN '2011-08-15 00:00:00' AND '2011-08-15 23:59:59'

Step 5: Evidence stored
─────────────────────────────────────────────
Evidence ID: ev_abc123
Class: OBSERVED
Data: {
  "connection_count": 395,
  "src_ip": "147.32.84.165",
  "protocol": "TCP",
  "dst_ports": [80, 443, 4444]
}

Step 6: Model assesses
─────────────────────────────────────────────
Assessment: "High-risk botnet behavior detected"
Risk Level: HIGH
Confidence: MEDIUM
Evidence IDs: ["ev_abc123"]

Step 7: Human review
─────────────────────────────────────────────
Status: AWAITING_HUMAN
Review required for final verdict
```

### 5.4 E2E Test Cases

#### Case 1: Botnet Detection (CTU S5)
```
Indicator: 147.32.84.165 (Known botnet source)
Ground Truth: Botnet
Expected Risk: HIGH
Evidence: 395 connections, port 4444 (IRC)
```

#### Case 2: Normal Traffic (CTU S7)
```
Indicator: 147.32.84.165 (Same IP, different time)
Ground Truth: Normal
Expected Risk: LOW
Evidence: Normal HTTP/HTTPS patterns
```

### 5.5 E2E Edge Cases

| Edge Case | Scenario | Expected |
|-----------|----------|----------|
| No evidence | IP not in snapshot | Gap reported, no verdict |
| Out-of-scope indicator | Different IP | Blocked by policy |
| Invalid time range | Future dates | Validation error |
| Budget exceeded | > $0.25 | STOP before API call |
| Provider error | 429/timeout | Logged, partial receipt |

**Trích dẫn:**
- Validation: [agent/network_investigation_policy.py](agent/network_investigation_policy.py) - Lines 89-145

---

## 6. Edge Cases tổng hợp

### 6.1 R1 Edge Cases

| ID | Case | Input | Expected | Citation |
|----|------|-------|----------|----------|
| R1-E1 | Wrong tool | "Get CTI data" | NO_TOOL | [matching.py:45](evaluation/tool_calling/matching.py#L45) |
| R1-E2 | Missing required arg | indicator=None | REQUIRED_ARG_MISSING | [matching.py:78](evaluation/tool_calling/matching.py#L78) |
| R1-E3 | Duplicate call | Same tool 2x | DUPLICATE_CALL | [matching.py:56](evaluation/tool_calling/matching.py#L56) |
| R1-E4 | Provider error | API timeout | PROVIDER_ERROR | [decision_runner.py:89](evaluation/tool_calling/decision_runner.py#L89) |

### 6.2 R2 Edge Cases

| ID | Case | SQL | Expected | Citation |
|----|------|-----|----------|----------|
| R2-E1 | Write attempt | INSERT INTO... | SAFETY_REJECTION | [text_to_sql.py:156](evaluation/text_to_sql.py#L156) |
| R2-E2 | Extension load | LOAD httpfs | SAFETY_REJECTION | [text_to_sql.py:162](evaluation/text_to_sql.py#L162) |
| R2-E3 | Multi-statement | SELECT; DROP | SYNTAX_ERROR | [text_to_sql.py:178](evaluation/text_to_sql.py#L178) |
| R2-E4 | NULL in result | COUNT(DISTINCT x) | Correct NULL | [matching.py:123](evaluation/tool_calling/matching.py#L123) |

### 6.3 E2E Edge Cases

| ID | Case | Scenario | Expected | Citation |
|----|------|----------|----------|----------|
| E2E-E1 | No evidence | IP not in DB | Gap reported | [network_contract.py:89](evaluation/finalization/network_contract.py#L89) |
| E2E-E2 | Invalid IPv4 | "not.an.ip" | ValidationError | [network_policy.py:112](agent/network_investigation_policy.py#L112) |
| E2E-E3 | Budget exceeded | > $0.25 | STOP | [live_window.py:156](evaluation/finalization/live_window.py#L156) |
| E2E-E4 | Partial receipt | Provider error | Partial JSON | [live_window.py:234](evaluation/finalization/live_window.py#L234) |

---

## 7. Troubleshooting

### 7.1 Lỗi thường gặp

| Lỗi | Nguyên nhân | Giải pháp |
|------|-------------|-----------|
| ModuleNotFoundError: agent | PYTHONPATH | Dùng `python -m scripts.xxx` |
| FileNotFoundError | Sai snapshot path | Verify path trong `data/ctu_network_public/snapshots/` |
| OPENAI_API_KEY missing | .env not set | Kiểm tra file .env |
| Snapshot SHA mismatch | Lock out of date | Chạy `build_lock` mới |
| 107 R2 tests fail | Semantic fixture issue | Đã biết, ảnh hưởng R2 score |

### 7.2 Verification Commands

```powershell
# Check git SHA
git rev-parse HEAD

# Check snapshot qualification
python -c "
from evaluation.finalization.network_contract import qualify_snapshot
result = qualify_snapshot('data/ctu_network_public/snapshots/ctu_dev.duckdb')
print(f'Qualified: {result[\"qualified\"]}')
"

# Check test count
python -m pytest tests/test_demo_ctu_network_public.py tests/test_demo_ctu_network_public_model_driven.py --collect-only -q | tail -1
```

### 7.3 Logs và Artifacts

| Type | Path | Mô tả |
|------|------|--------|
| R1 Results | `results/evaluation_v1/r1/*.json` | Tool calling results |
| R2 Results | `results/evaluation_v1/r2/*.json` | Text-to-SQL results |
| E2E Receipt | `results/e2e_*.json` | Technical receipt |
| E2E HTML | `results/e2e_*.html` | Human-readable report |
| Test Logs | `.pytest_cache/` | Pytest cache |

---

## 8. Bảng tóm tắt metrics

### 8.1 R1 Metrics (BFCL-style)

| Metric | Formula | Perfect Score |
|--------|---------|---------------|
| Tool Selection Accuracy | correct_tools / total | 1.0 |
| Exact Call F1 | 2*precision*recall / (precision+recall) | 1.0 |
| Required Argument Accuracy | correct_required / total_required | 1.0 |
| No-Tool Accuracy | correct_no_tool / total_no_tool | 1.0 |

### 8.2 R2 Metrics (Spider/BIRD-style)

| Metric | Formula | Perfect Score |
|--------|---------|---------------|
| Execution Accuracy | exact_match / total | 1.0 |
| Syntax Validity | valid_sql / total | 1.0 |
| Execution Success | executed / valid_sql | 1.0 |
| Safety Rejection | rejected_writes / attempted_writes | 1.0 |

### 8.3 E2E Status

| Status | Ý nghĩa |
|--------|----------|
| complete | Cả 2 scenario + review hoàn tất |
| awaiting_human | Assessment done, chờ human review |
| partial | Một số scenario fail |
| preflight_failed | Snapshot/contract không qualified |

---

## 9. References đầy đủ

### Core Documents
- [docs/evaluation_protocol_v1.md](docs/evaluation_protocol_v1.md) - Framework protocol
- [docs/architecture.md](docs/architecture.md) - System architecture
- [docs/hitl_design.md](docs/hitl_design.md) - Human-in-the-loop design

### R1 (BFCL)
- [evaluation/tool_calling/__main__.py](evaluation/tool_calling/__main__.py) - CLI entrypoint
- [evaluation/tool_calling/metrics.py](evaluation/tool_calling/metrics.py) - Metrics engine
- [evaluation/tool_calling/matching.py](evaluation/tool_calling/matching.py) - Matching logic
- [evaluation/tool_calling/models.py](evaluation/tool_calling/models.py) - Data models

### R2 (Spider/BIRD)
- [evaluation/text_to_sql.py](evaluation/text_to_sql.py) - R2 evaluator
- [evaluation/text_to_sql_benchmarks/snapshot_manifest.json](evaluation/text_to_sql_benchmarks/snapshot_manifest.json) - Snapshot contract
- [evaluation/text_to_sql_benchmarks/dataset_manifest.json](evaluation/text_to_sql_benchmarks/dataset_manifest.json) - Dataset contract

### E2E Demo
- [scripts/demo_ctu_network_public_model_driven.py](scripts/demo_ctu_network_public_model_driven.py) - Demo CLI
- [agent/network_investigation_policy.py](agent/network_investigation_policy.py) - Network policy
- [evaluation/finalization/live_window.py](evaluation/finalization/live_window.py) - Transport guard
- [evaluation/finalization/network_contract.py](evaluation/finalization/network_contract.py) - Snapshot contract
- [scripts/render_network_e2e_report.py](scripts/render_network_e2e_report.py) - HTML renderer

### Tests
- [tests/test_demo_ctu_network_public.py](tests/test_demo_ctu_network_public.py) - 4 tests
- [tests/test_demo_ctu_network_public_model_driven.py](tests/test_demo_ctu_network_public_model_driven.py) - 43 tests
- [tests/test_finalization_live_window.py](tests/test_finalization_live_window.py) - 12 tests
- [tests/test_network_e2e_policy.py](tests/test_network_e2e_policy.py) - 14 tests
- [tests/test_network_e2e_lifecycle.py](tests/test_network_e2e_lifecycle.py) - 9 tests
- [tests/test_network_e2e_report.py](tests/test_network_e2e_report.py) - 7 tests

---

## 10. Quick Reference Commands

```powershell
# 1. Preflight
python -m scripts.demo_ctu_network_public_model_driven --snapshot data/ctu_network_public/snapshots/ctu_dev.duckdb --output results/pre.json --e2e --preflight-only

# 2. E2E Live
python -m scripts.demo_ctu_network_public_model_driven --snapshot data/ctu_network_public/snapshots/ctu_dev.duckdb --output results/e2e.json --e2e --budget-usd 0.25

# 3. HTML Report
python scripts/render_network_e2e_report.py --receipt results/e2e.json --output results/e2e.html

# 4. R1 Benchmark
python -m evaluation.tool_calling benchmarks dev --mode decision --provider openai --model gpt-4.1-mini-2025-04-14 --temperature 0

# 5. R2 Benchmark
python -m evaluation.text_to_sql evaluate --snapshot data/snapshots/vinsoc_public_v1.duckdb --manifest evaluation/text_to_sql_benchmarks/snapshot_manifest.json --split dev --provider openai --model gpt-4.1-mini-2025-04-14 --temperature 0 --output results/r2.json

# 6. Run all tests
python -m pytest tests/ -v --tb=short
```
