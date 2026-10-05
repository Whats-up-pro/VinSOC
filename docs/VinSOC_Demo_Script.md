# VinSOC - Demo Presentation Script
## Technical Mentor Review

> Evidence status (2026-10-05): verified R2 full-suite dev **7/8**, case006 **TOOL_LIMIT**. Post-INTEGER-hint chưa có verified full-suite score. S1/S4 đã consumed, protocol_eligible=false; chưa có independent R2 holdout. R1 frozen mới kiểm tương thích offline, chưa có model accuracy. R1 dev-v2 có11/24 gold adjudicated sau khi xem model. Các sơ đồ/output minh họa dưới đây không phải receipt E2E đã nghiệm thu. Task2 chỉ offline; mọi lệnh live cần gate riêng.

**Thời lượng:** 25-30 phút
**Mục tiêu:** Chứng minh AI-assisted SOC investigation với evidence-grounded approach

---

# SLIDE 1: Mở đầu (2 phút)

## Script
> "Xin chào thầy/cô. Em sẽ trình bày về VinSOC - hệ thống điều tra SOC có AI hỗ trợ."
>
> "Vấn đề thực tế: Một SOC trung bình nhận 10,000 alerts/ngày, trong đó 90% là false positive. Analyst kiệt sức, không đủ thời gian điều tra kỹ từng alert."
>
> "Giải pháp: VinSOC = AI copilot giúp lọc alert nhanh, điều tra có bằng chứng, human duyệt trước khi action."

## Visual
```
SOC Reality:
┌────────────────────────────────────────────────────┐
│  10,000 alerts/day                                 │
│  ├── 9,000 (90%) → False Positive → Wasted time  │
│  └── 1,000 (10%) → Real Threats → Under-investigated│
└────────────────────────────────────────────────────┘
```

---

# SLIDE 2: System Architecture (3 phút)

## Script
> "Hệ thống gồm 4 layers chính:
>
> Layer 1: Human Analyst - người giám sát và phê duyệt cuối cùng
>
> Layer 2: LLM Orchestrator - bộ não điều phối. Nhưng LLM chỉ làm 3 việc: hiểu intent, chọn tool, interpret evidence. LLM KHÔNG làm security functions.
>
> Layer 3: Skills - 3 investigation skills độc lập: CTI enrich từ ThreatFox, Network investigation từ CTU-13, Endpoint từ Sysmon. Mỗi skill chỉ-đọc, có schema riêng.
>
> Layer 4: Evidence Store - mọi kết quả đều được tag với evidence ID. Kết luận phải trích dẫn evidence cụ thể."

## Diagram
```
┌──────────────────────────────────────────────────────────┐
│                    Human Analyst                           │
│                  (review + approve)                        │
└──────────────────────────────────────────────────────────┘
                           ↓
┌──────────────────────────────────────────────────────────┐
│              LLM Orchestrator (reasoning only)             │
│  Intent → Tool Selection → Evidence Interpretation        │
└──────────────────────────────────────────────────────────┘
                           ↓
         ┌─────────────────┼─────────────────┐
         ↓                 ↓                 ↓
┌──────────────┐  ┌──────────────┐  ┌──────────────┐
│ CTI Skill    │  │ Network Skill│  │ Endpoint    │
│ (ThreatFox)  │  │ (CTU-13)    │  │ (Sysmon)   │
└──────────────┘  └──────────────┘  └──────────────┘
                           ↓
┌──────────────────────────────────────────────────────────┐
│              Evidence Store (immutable)                    │
│         Every conclusion MUST cite evidence IDs             │
└──────────────────────────────────────────────────────────┘
```

## 3 Core Principles
```
1. EVIDENCE-DRIVEN
   Hypothesis phải link đến evidence ID cụ thể
   → Không "I think" không có "because evidence X"

2. BOUNDED AUTONOMY
   AI đề xuất, human phê duyệt
   → 2 human gates: triage và final assessment

3. READ-ONLY
   Skills chỉ đọc, không action
   → Không tự containment, block, delete
```

---

# SLIDE 3: R1 - Tool Calling Evaluation (5 phút)

## Script
> "Phần đầu tiên: R1 đánh giá khả năng chọn đúng tools của model.
>
> Đặt câu hỏi: Model có chọn đúng tools để điều tra không? Cần bao nhiêu tools?"
>
> 24 test cases với các scenario: network-only, cti-only, endpoint-only, multi-skill."

## Demo Command 1
```bash
python -m evaluation.tool_calling list dev
```

## Expected Output
```
Available cases in 'dev': 24
  case_001: network_only (basic)
  case_002: cti_only (basic)
  case_003: endpoint_only (basic)
  case_004: cti_only (basic)
  case_005: cti_network_endpoint (advanced)
  case_006: cti_only (basic)
  case_007: cti_endpoint (intermediate)
  case_008: cti_network_endpoint (advanced)
  case_009: network_only (basic)
  case_010: network_endpoint (intermediate)
  ...
```

## Results Table
```
┌──────────────────────────────────────────────────────────────────┐
│  R1 Tool Calling Results (24 dev cases)                           │
├──────────────────────────────────────────────────────────────────┤
│                                                                  │
│  Model              │ Success │ F1     │ No-tool │ Cost         │
│  ──────────────────┼─────────┼────────┼─────────┼─────────────  │
│  GPT-4.1 Mini ✓    │ 22/24   │ 0.9508 │   5/5   │ $0.010       │
│  GPT-5 Mini        │ 19/24   │ 0.9355 │   4/5   │ $0.016       │
│                                                                  │
│  Winner: GPT-4.1 Mini - smaller model, better selection!         │
│                                                                  │
└──────────────────────────────────────────────────────────────────┘
```

## Key Insight
```
Observation: Smaller model (GPT-4.1 Mini) > Larger model (GPT-5 Mini)

Why?
- GPT-4.1 Mini: Chọn đúng tools, không over-engineer
- GPT-5 Mini: Thường gọi thêm endpoint_investigation không cần thiết

→ Tool selection quality > Model size
```

---

# SLIDE 4: R2 - Text-to-SQL Challenge (5 phút)

## Script
> "Phần thứ hai: R2 đánh giá khả năng generate SQL đúng từ natural language.
>
> Đây là bài toán khó hơn nhiều. Model không chỉ cần chọn tools, mà phải:
> 1. Hiểu database schema (12 columns, 4M+ rows)
> 2. Phân biệt VARCHAR vs INTEGER columns
> 3. Biết khi nào dùng aggregation vs search
>
> 8 dev cases (S5/S7); S1/S4 là historical consumed diagnostic, không phải independent holdout."

## Database Schema
```
CTU-13 Network Flows:
┌────────────────┬─────────────────────────────────────┐
│ Column         │ Type                                │
├────────────────┼─────────────────────────────────────┤
│ source_dataset │ VARCHAR (ctu13_s5, ctu13_s7)        │
│ src_ip         │ VARCHAR                             │
│ src_port       │ INTEGER ⚠️                          │
│ dst_ip         │ VARCHAR                             │
│ dst_port       │ INTEGER ⚠️                          │
│ protocol       │ VARCHAR (TCP, UDP, ICMP)            │
│ label          │ VARCHAR (From-Botnet-*, From-Norm*) │
│ bytes_out      │ BIGINT                              │
│ event_time     │ TIMESTAMP                           │
└────────────────┴─────────────────────────────────────┘
```

## Demo Command 2: List R2 Cases
```bash
python -c "from evaluation.ctu_network_public.contract import CASES; [print(f'{c.stem}: {json.loads(c.read_text())[\"question\"][:55]}...') for c in sorted(CASES.glob('ctu_sql_*.json'))]"
```

---

# SLIDE 5: DualSQL Approach (5 phút)

## Script
> "Approach: DualSQL - chia thành 2 phases.
>
> Phase 1 - Linker: Discover schema + ground values. Model gọi database_profiler để biết column types, gọi value_search để tìm catalog values. Linker trả về linked schema.
>
> Phase 2 - Generator: Generate SQL với linked schema. Model biết được column types và values, chỉ cần viết SQL đúng.
>
> Điểm mấu chốt: INTEGER columns KHÔNG có catalog values. Model phải dùng GROUP BY aggregation thay vì search."

## DualSQL Flow
```
┌─────────────────────────────────────────────────────────────────┐
│  Phase 1: Linker                                                │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  [Question] "Top 5 destination ports with most flows"           │
│      ↓                                                         │
│  ┌──────────────────────────────────────────────┐              │
│  │ database_profiler()                         │              │
│  │ → dst_port: INTEGER (no catalog values)     │              │
│  └──────────────────────────────────────────────┘              │
│      ↓                                                         │
│  ┌──────────────────────────────────────────────┐              │
│  │ value_search(label, "Botnet")                │              │
│  │ → "flow=From-Botnet-V46-TCP-Attempt"        │              │
│  └──────────────────────────────────────────────┘              │
│      ↓                                                         │
│  [Linked Schema: dst_port=INTEGER, label=VARCHAR]               │
│                                                                  │
├─────────────────────────────────────────────────────────────────┤
│  Phase 2: Generator                                             │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  Model knows: dst_port is INTEGER → use GROUP BY               │
│                                                                  │
│  [SQL]                                                          │
│  SELECT dst_port, COUNT(*) AS flow_count                        │
│  FROM network_flows                                             │
│  WHERE source_dataset = 'ctu13_s5'                              │
│  GROUP BY dst_port                                              │
│  ORDER BY count(*) DESC                                         │
│  LIMIT 5;                                                      │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

---

# SLIDE 6: Case006 - lịch sử và regression offline (5 phút)

Official suite3f9d72d giữ case006 **TOOL_LIMIT**, final_sql=null, EX=false.
Trace thật: linker turn1 database_profiler; turn2 value_search trên dst_port với query ctu13_s5;
turn3 yêu cầu batch5 search, chỉ3 call còn lại được thực thi trước cap. Tổng3 turns/5 DB calls;
generator chưa được gọi. Không thay trace này bằng ví dụ năm lượt search liên tiếp.

INTEGER hint là thay đổi code sau suite đó, chưa có verified full-suite score.
Task2 kiểm generality bằng tên cột/top-k khác trên fixture tổng hợp và real DuckDB evaluator;
fake transcript không phải kết quả model. Không nâng cap, ghép prediction hay chạy lại case để cứu điểm.

## Offline replay
```powershell
python -m scripts.audit_r2_saved_outputs --input results/evaluation_v1/ctu_network_public/r2_phase2_live/20261001_3f9d72d/suite --cases-dir evaluation/ctu_network_public/dev --snapshot data/ctu_network_public/snapshots/ctu_dev.duckdb --output .superpowers/reviewer-r2-replay-unique
```
Output phải là thư mục mới. Replay không gọi model, không overwrite nguồn và không phải lượt inference mới.
Pipeline `OK` chỉ nghĩa là có SQL; EX phải lấy từ evaluator thực thi prediction và gold trên snapshot.


# SLIDE 7: Evidence-backed results (3 phút)

R1 dev-v2 winner GPT-4.1 mini22/24, exact-call F1 0.9508, no-tool5/5;
GPT-5 mini19/24, F1 0.9355, no-tool4/5. Đây là decision-only dev, có caveat11/24 post-output adjudication.

| Điều kiện lịch sử riêng | Kết quả / giới hạn |
|---|---|
| CTU E0, run36520685612 | EX0/8, syntax/execution8/8 |
| Remediation E3 | EX1/8; contract khác Phase2 |
| Verified Phase2 suite, SHA3f9d72d | **EX7/8**, syntax/execution7/8;44 responses;$0.02085850 cho cả suite |
| Post-INTEGER-hint | **Chưa có verified full-suite score**; test riêng không thay case006 trong suite cũ |
| S1/S4 | **Consumed**, không protocol-eligible; prediction mới thiếu scoring/identity, unscored |

Các hàng khác điều kiện; không trình bày chúng thành một thí nghiệm cải tiến có đối chứng.
Chưa có independent R2 holdout hoặc bằng chứng generalization. Xem [báo cáo đính chính](evaluation/FINAL_EVALUATION_REPORT.md).


# SLIDE 8: Method Comparison (3 phút)

## Comparison Table
```
┌─────────────────────────────────────────────────────────────────────────┐
│  Method Comparison: Traditional vs VinSOC                               │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                         │
│  Aspect            │ Traditional SIEM  │ VinSOC                       │
│  ─────────────────┼───────────────────┼────────────────────────────── │
│  Alert Handling   │ Rule-based        │ LLM reasoning                 │
│  Tool Selection   │ Static rules      │ Dynamic per-case              │
│  Evidence         │ Logs separate     │ Unified store, traceable      │
│  Reasoning        │ Manual            │ Model + human review          │
│  False Positive   │ High (rules)     │ Lower (evidence-based)        │
│  Scalability      │ Limited rules     │ Not independently evaluated  │
│  Cost             │ High (analyst)    │ Low (~$0.01/investigation)  │
│                                                                         │
│  Key Difference: VinSOC reasons about evidence, not just patterns       │
│                                                                         │
└─────────────────────────────────────────────────────────────────────────┘
```

## Why Evidence Grounding Matters
```
❌ Without evidence grounding:
   "This IP is malicious because the model thinks so"
   → Hallucination risk, no traceability

✅ With evidence grounding:
   "This IP is malicious because:
    - CTI_001: ThreatFox reports reputation=malicious
    - NET_001: 4 connections in 30s = beaconing pattern
    - Evidence IDs are verifiable"
   → Traceable, verifiable, human-reviewable
```

---

# SLIDE 9: Q&A (5 phút)

## Prepared Answers

### "AI miss threat thì sao?"
```
→ HITL gates: Human duyệt trước mọi action.
  AI chỉ đề xuất, không tự quyết định.
  Nếu analyst không đồng ý → reject/escallate.
```

### "Chi phí vận hành?"
```
→ ~$0.01-0.03 per investigation (model API)
→ So với analyst: $50-100/alert (nếu điều tra kỹ)
→ Tiết kiệm 90% false positive review
```

### "Security concerns?"
```
→ Read-only: Không action được
→ Evidence immutable: Không sửa được
→ Full audit trail: Mọi bước được log
→ No autonomous containment: Human gate
```

### "So với SOAR?"
```
→ SOAR: Rule-based automation
→ VinSOC: LLM reasoning + evidence grounding
→ Complementary: VinSOC điều tra → SOAR action
```

### "Generalization?"
```
→ S1/S4 đã consumed; chưa có independent R2 holdout
→ INTEGER hint được kiểm offline trên synthetic fixtures, chưa có full-suite post-hint score
→ Dev7/8 và demo không chứng minh generalization
```

---

# Demo Commands Reference

## Quick Verification
```bash
# List scenarios
python -m cli.main list

# List R1 cases
python -m evaluation.tool_calling list dev

# List R2 cases
python -c "from evaluation.ctu_network_public.contract import CASES; [print(c.stem) for c in sorted(CASES.glob('ctu_sql_*.json'))]"

# Test INTEGER hint
python -c "
from evaluation.r2_phase2.grounding import Phase2Tools
from evaluation.ctu_network_public.contract import MANIFEST
r = Phase2Tools('data/ctu_network_public/snapshots/ctu_dev.duckdb', MANIFEST)
res = r.value_search({'table': 'network_flows', 'column': 'dst_port', 'query': '80'})
print('Hint:', res['hint'][:60], '...')
"
```

## Gated live investigation

Không gọi OpenAI trực tiếp từ tài liệu để rerun case006 hoặc suy EX từ pipeline OK.
Lượt live/dev/demo phải dùng runner đã khóa, CI/identity/budget/attempt gate và authorization tương ứng.
Task2 không cho phép live. Dùng offline replay ở Slide6 để tái chấm kết quả cũ.

## Run Tests
```bash
# Phase 2 tests
python -m pytest tests/test_r2_phase2_grounding.py tests/test_r2_phase2_safety.py -q

# Full test suite
python -m pytest -q
```

---

# Files Reference

| File | Description |
|------|-------------|
| `docs/architecture.md` | Full architecture |
| `docs/problem.md` | Problem statement |
| `evaluation/tool_calling/` | R1 benchmark |
| `evaluation/r2_phase2/` | R2 implementation |
| `agent/orchestrator.py` | Main orchestrator |
| `skills/` | Investigation skills |
| `cli/main.py` | CLI interface |

---

**End of Demo Script**
