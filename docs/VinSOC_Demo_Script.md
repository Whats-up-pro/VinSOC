# VinSOC - Demo Presentation Script
## Technical Mentor Review

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
> 8 dev cases (S5/S7) + 8 frozen cases (S1/S4)."

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

# SLIDE 6: Case 006 - The Critical Fix (5 phút)

## Script
> "Case 006 là ví dụ điển hình về challenge này.
>
> Question: 'Return the five scenario 5 destination ports with most flows'
>
> Trước fix: Model gọi value_search trên dst_port (INTEGER). Không có results vì INTEGER không có catalog values. Model cố gọi lại... 5 lần → TOOL_LIMIT."

## ❌ Before Fix (TOOL_LIMIT)
```
Model turn 1: value_search("dst_port", "80")
Model turn 2: value_search("dst_port", "443")
Model turn 3: value_search("dst_port", "22")
Model turn 4: value_search("dst_port", "8080")
Model turn 5: value_search("dst_port", "3306")
→ TOOL_LIMIT: Model exhausted 5 tool calls

❌ Final SQL: NONE (no generation)
❌ Result: EX = 0
```

## Solution: INTEGER Hint
```python
# evaluation/r2_phase2/grounding.py - line 83
'hint': col_type + ' column "' + col_name + '" has no catalog values. 
         Use SQL aggregation (COUNT, GROUP BY) for analysis - 
         do NOT continue value search.'
```

## ✅ After Fix (EX)
```
Model turn 1: database_profiler()
             ← "dst_port: INTEGER (no catalog values)"
             
Model turn 2: value_search("dst_port", "80")
             ← "INTEGER column 'dst_port' has no catalog values.
                 Use SQL aggregation (COUNT, GROUP BY)"
             
Model turn 3: [Generate SQL with GROUP BY]

✅ Final SQL:
SELECT dst_port, COUNT(*) AS flow_count
FROM network_flows
WHERE source_dataset = 'ctu13_s5'
GROUP BY dst_port
ORDER BY count(*) DESC
LIMIT 5;

✅ Result: EX = 1
```

## Demo Command 3: Verify Fix
```bash
python -c "
from evaluation.r2_phase2.grounding import Phase2Tools
tools = Phase2Tools('data/ctu_network_public/snapshots/ctu_dev.duckdb', None)
result = tools.value_search({'table': 'network_flows', 'column': 'dst_port', 'query': '80'})
print('Resolution:', result['resolution'])
print('Hint:', result['hint'][:80], '...')
"
```

---

# SLIDE 7: Final Results (3 phút)

## Results Summary
```
┌──────────────────────────────────────────────────────────────────┐
│  VinSOC Evaluation Results                                        │
├──────────────────────────────────────────────────────────────────┤
│                                                                  │
│  R1 - Tool Calling (24 cases):                                  │
│  ┌──────────────────┬────────┬──────────────────────────┐       │
│  │ Model           │ EX     │ Notes                   │       │
│  ├──────────────────┼────────┼──────────────────────────┤       │
│  │ GPT-4.1 Mini ✓  │ 22/24  │ Winner: better select   │       │
│  │ GPT-5 Mini      │ 19/24  │ Over-engineering        │       │
│  └──────────────────┴────────┴──────────────────────────┘       │
│                                                                  │
│  R2 - Text-to-SQL (8 cases):                                    │
│  ┌──────────────────┬────────┬──────────────────────────┐       │
│  │ Version         │ EX     │ Notes                   │       │
│  ├──────────────────┼────────┼──────────────────────────┤       │
│  │ Baseline (v1)   │ 0/8    │ Naive one-shot         │       │
│  │ DualSQL v1     │ 1/8    │ Linker added           │       │
│  │ DualSQL v2     │ 7/8    │ Controller fixed       │       │
│  │ Phase 2 (fix)  │ 8/8    │ INTEGER hint           │       │
│  └──────────────────┴────────┴──────────────────────────┘       │
│                                                                  │
│  Frozen Holdout (S1/S4): 8/8 ✅                                 │
│  → Proof of generalization on unseen data                       │
│                                                                  │
└──────────────────────────────────────────────────────────────────┘
```

## Key Metrics
```
Cost per investigation:
- R1: ~$0.01 (GPT-4.1 Mini)
- R2: ~$0.02-0.03 (GPT-5 Mini, more turns)

Accuracy:
- R1 Tool Calling: 91.67%
- R2 Text-to-SQL: 100% (dev + frozen)
```

---

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
│  Scalability      │ Limited rules     │ Generalizes                  │
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
→ Frozen holdout: 8/8 trên unseen data (S1/S4)
→ Model học được pattern, không phải memorize
→ INTEGER hint = transferrable knowledge
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
r = Phase2Tools('data/ctu_network_public/snapshots/ctu_dev.duckdb', None)
res = r.value_search({'table': 'network_flows', 'column': 'dst_port', 'query': '80'})
print('Hint:', res['hint'][:60], '...')
"
```

## Full Investigation (requires API key)
```bash
# Run R1 case
python -m evaluation.tool_calling run case_005 --provider openai --model gpt-4.1-mini-2025-04-14

# Run R2 case
python -c "
from evaluation.r2_phase2.grounding import Phase2Tools
from evaluation.r2_phase2.runner import run_case
from evaluation.ctu_network_public.contract import MANIFEST, CASES
from openai import OpenAI
import json, os
from dotenv import load_dotenv
load_dotenv()

client = OpenAI(api_key=os.getenv('OPENAI_API_KEY'))
case = json.loads((CASES / 'ctu_sql_006.json').read_text())
tools = Phase2Tools('data/ctu_network_public/snapshots/ctu_dev.duckdb', MANIFEST)
result = run_case(case=type('Case', (), case)(), condition='E3', tools=tools, client=client, schema_context=tools.schema_context())
print('EX:', result.get('error_category') == 'OK')
"
```

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
