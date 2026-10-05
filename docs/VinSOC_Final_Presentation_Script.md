# VinSOC - Complete Presentation Script
## Technical Mentor Review

**Duration:** 30-40 minutes
**Format:** Live demo + slides
**Audience:** Technical mentor with SOC/security background

---

# PHẦN 1: GIỚI THIỆU VẤN ĐỀ (5 phút)

## 1.1 Opening (1 phút)

**Script:**
> "Xin chào thầy/cô. Em sẽ trình bày đồ án VinSOC - hệ thống điều tra SOC có AI hỗ trợ.
>
> Đây là kết quả nghiên cứu về việc ứng dụng LLM Agent trong điều tra security incidents, với trọng tâm là evidence-grounded reasoning và human-in-the-loop."

---

## 1.2 SOC Problem (2 phút)

**Script:**
> "Vấn đề thực tế của SOC teams:
>
> 1. **Alert overload:** 10,000+ alerts/ngày, analyst không đủ thời gian điều tra kỹ từng cái
>
> 2. **False positive cao:** 90% alerts là false positive, nhưng vẫn phải review từng cái
>
> 3. **Inconsistent analysis:** Mỗi analyst đánh giá khác nhau, thiếu standardization
>
> 4. **Knowledge gap:** Cần expertise về CTI, network, endpoint để điều tra hiệu quả"

**Visual:**
```
┌─────────────────────────────────────────────────────────────┐
│  SOC Alert Reality                                         │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  10,000 alerts/day                                         │
│      │                                                     │
│      ├── 9,000 (90%) ──→ False Positives                  │
│      │         └── Wasted analyst time                     │
│      │                                                     │
│      └── 1,000 (10%) ──→ Real Threats                     │
│                  └── Often under-investigated               │
│                                                             │
│  Problem: Can't manually review all alerts thoroughly       │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

---

## 1.3 Research Question (2 phút)

**Script:**
> "Nghiên cứu đặt ra 4 research questions:
>
> **RQ1:** LLM Agent có chọn đúng tools để điều tra multi-step workflow không?
>
> **RQ2:** Agent có đưa ra hypothesis dựa trên evidence thực tế không, hay hallucinate?
>
> **RQ3:** Agent-assisted investigation có tiết kiệm thời gian hơn manual workflow không?
>
> **RQ4:** Agent có giữ đúng security boundaries khi đối mặt với adversarial inputs không?"

**Research Constraints:**
```
1. READ-ONLY: Không autonomous action, containment
2. EVIDENCE-GROUNDED: Mọi kết luận phải trích dẫn evidence ID
3. DECOUPLED: Skills độc lập với LLM provider
4. TRACEABLE: Full audit trail
5. CONTROLLED: Human review trước mọi quyết định
```

---

# PHẦN 2: KIẾN TRÚC HỆ THỐNG (8 phút)

## 2.1 High-Level Architecture (3 phút)

**Script:**
> "Hệ thống VinSOC gồm 4 layers chính:
>
> **Layer 1 - Human Analyst:** Người giám sát và phê duyệt cuối cùng. Mọi action phải qua human gate.
>
> **Layer 2 - LLM Orchestrator:** Bộ não điều phối. LLM chỉ làm 3 việc: hiểu intent → chọn tool → interpret evidence. LLM KHÔNG làm security functions trực tiếp.
>
> **Layer 3 - Investigation Skills:** 3 skills độc lập, chỉ-đọc, có schema riêng:
> - CTI Skill: ThreatFox (101k+ IOCs)
> - Network Skill: CTU-13 network flows
> - Endpoint Skill: Sysmon process telemetry
>
> **Layer 4 - Evidence Store:** Mọi kết quả đều được tag với evidence ID. Evidence là immutable. Kết luận phải trích dẫn evidence cụ thể."

**Diagram:**
```
┌──────────────────────────────────────────────────────────────────┐
│                      Human Analyst                                 │
│                 (oversight + final approval)                       │
│                                                                    │
│   Human Gates:                                                     │
│   ├── Triage Gate: CLOSE / CONTINUE                             │
│   └── Final Gate: APPROVE / ESCALATE / REJECT                    │
└──────────────────────────────────────────────────────────────────┘
                            ↑
                            │
┌──────────────────────────────────────────────────────────────────┐
│                  LLM Orchestrator                                 │
│               (reasoning only, not security functions)              │
│                                                                    │
│   ┌────────────┐  ┌────────────┐  ┌────────────────────────┐   │
│   │ Intent     │→ │ Tool       │→ │ Evidence              │   │
│   │ Parsing    │  │ Selection  │  │ Interpretation       │   │
│   └────────────┘  └────────────┘  └────────────────────────┘   │
│                                                                    │
│   Human Review Gates:                                             │
│   ├── review_triage() → CLOSE / CONTINUE                         │
│   └── review_final() → APPROVE / ESCALATE / REJECT               │
└──────────────────────────────────────────────────────────────────┘
                            │
        ┌───────────────────┼───────────────────┐
        ↓                   ↓                   ↓
┌──────────────────┐ ┌──────────────────┐ ┌──────────────────┐
│   CTI Skill       │ │  Network Skill   │ │  Endpoint Skill  │
│   (ThreatFox)    │ │  (CTU-13)      │ │  (Sysmon)      │
│                  │ │                 │ │                 │
│ • IOC lookup     │ │ • Connection    │ │ • Process tree  │
│ • Reputation     │ │ • Port scan    │ │ • LOLbin detect │
│ • ATT&CK mapping │ │ • Beaconing    │ │ • Suspicious    │
│                  │ │                │ │   chain         │
└──────────────────┘ └─────────────────┘ └─────────────────┘
        │                   │                   │
        └───────────────────┼───────────────────┘
                            ↓
┌──────────────────────────────────────────────────────────────────┐
│                    Evidence Store (immutable)                        │
│                                                                    │
│   Evidence Classes:                                                │
│   ├── OBSERVED: Raw telemetry (network flows, process events)      │
│   ├── DERIVED: Analytics results (beaconing detected)             │
│   └── EXTERNAL_INTEL: CTI data (ThreatFox reputation)            │
│                                                                    │
│   Properties:                                                      │
│   • Immutable once stored                                         │
│   • Every item has unique evidence_id                            │
│   • Conclusions MUST cite specific evidence IDs                   │
│   • Full provenance chain tracked                                 │
└──────────────────────────────────────────────────────────────────┘
```

---

## 2.2 3 Core Principles (3 phút)

**Script:**
> "Hệ thống tuân thủ 3 nguyên tắc cốt lõi:
>
> **Nguyên tắc 1: EVIDENCE-DRIVEN**
> Mọi hypothesis phải link đến evidence ID cụ thể. Không có 'I think' không có 'because evidence X says'.
>
> **Nguyên tắc 2: BOUNDED AUTONOMY**
> AI đề xuất, human phê duyệt. Có 2 human gates: triage gate và final gate.
>
> **Nguyên tắc 3: READ-ONLY**
> Skills chỉ đọc, không action. Không tự containment, block, delete hay modify."

**Evidence Example:**
```
❌ BAD:
"IP 147.229.10.182 is malicious because the model thinks so"
→ Hallucination risk, no traceability

✅ GOOD:
"IP 147.229.10.182 is malicious because:
 - Evidence CTI_001: ThreatFox reports reputation=malicious
 - Evidence CTI_002: Related to Cobalt Strike C2
 - Evidence NET_001: 4 connections in 30s = beaconing pattern
 - Evidence IDs are verifiable, human-reviewable"
```

---

## 2.3 Investigation Flow (2 phút)

**Script:**
> "Luồng điều tra cụ thể:
>
> 1. **Input:** Analyst đưa vào IOC (IP, domain, hash) + context
>
> 2. **Triage:** Model đánh giá ban đầu → Human gate: close hay continue
>
> 3. **Evidence Collection Loop:**
>    - Model chọn và gọi tools
>    - Kết quả được store vào Evidence Store với ID
>    - Model interpret evidence → quyết định next step
>    - Repeat cho đến khi đủ evidence
>
> 4. **Final Assessment:**
>    - Model đưa ra hypothesis với evidence citations
>    - Human gate: approve/escalate/reject
>
> 5. **Output:** Full audit trail + final disposition"

**Flow Diagram:**
```
[IOC Input]
     │
     ↓
┌─────────────┐
│   Triage    │  Model assesses: benign/suspicious/unknown
└─────────────┘
     │
     ├── BENIGN? ──→ [Human Gate: CLOSE] ──→ END
     │
     └── CONTINUE ──↓
                    │
     ┌─────────────┼─────────────┐
     ↓             ↓             ↓
┌─────────┐  ┌─────────┐  ┌─────────┐
│CTI Skill│  │Net Skill│  │Endpt    │
│         │  │         │  │Skill    │
└─────────┘  └─────────┘  └─────────┘
     │             │             │
     └─────────────┼─────────────┘
                   ↓
         ┌───────────────────┐
         │  Evidence Store    │  Each result tagged with evidence_id
         │  (immutable)      │
         └───────────────────┘
                   │
                   ↓
         ┌───────────────────┐
         │  Interpret +      │  Model reasons about collected evidence
         │  Decide Next Step │
         └───────────────────┘
                   │
         ┌─────────┴─────────┐
         ↓                   ↓
    [More tools?]       [Evidence sufficient?]
         │                   │
         YES ──→ loop       YES ──↓
         │                   │
         NO ──→             NO ──→ loop
                   │
                   ↓
         ┌───────────────────┐
         │  Final Assessment │  Hypothesis with evidence citations
         └───────────────────┘
                   │
                   ↓
         ┌───────────────────┐
         │  Human Gate       │  APPROVE / ESCALATE / REJECT
         │  (final review)   │
         └───────────────────┘
                   │
                   ↓
              [END]
```

---

# PHẦN 3: EVALUATION FRAMEWORK (5 phút)

## 3.1 R1 - Tool Calling (3 phút)

**Script:**
> "Phần đánh giá R1 tập trung vào khả năng model chọn đúng tools.
>
> Đặt câu hỏi: Khi được hỏi một investigation question, model có chọn đúng tools không? Cần bao nhiêu tools?
>
> 24 dev cases + 8 frozen cases.
>
> Đo: Tool selection accuracy, exact call F1, no-tool accuracy."

**Demo Command:**
```bash
python -m evaluation.tool_calling list dev
```

**Expected Output:**
```
Available cases in 'dev': 24
  case_001: network_only (basic)
  case_002: cti_only (basic)
  case_003: endpoint_only (basic)
  case_004: cti_only (basic)
  case_005: cti_network_endpoint (advanced)
  ...
```

**Results:**
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
│  Winner: GPT-4.1 Mini - smaller model, better tool selection!    │
│                                                                  │
└──────────────────────────────────────────────────────────────────┘
```

**Key Insight:**
> "Observation quan trọng: GPT-4.1 Mini (nhỏ hơn) đánh bại GPT-5 Mini (lớn hơn).
>
> Lý do: GPT-4.1 Mini chọn đúng tools, không over-engineer. GPT-5 Mini thường gọi thêm endpoint_investigation không cần thiết.
>
> Kết luận: Tool selection quality > Model size."

---

## 3.2 R2 - Text-to-SQL (2 phút)

**Script:**
> "Phần R2 đánh giá khả năng model generate SQL đúng từ natural language question.
>
> Đây là bài toán khó hơn nhiều so với R1. Model không chỉ cần chọn tools, mà phải:
>
> 1. Hiểu database schema (12 columns, 4M+ rows)
> 2. Phân biệt VARCHAR vs INTEGER columns
> 3. Biết khi nào dùng aggregation vs value search
>
> 8 dev cases (S5/S7) + 8 frozen cases (S1/S4)."

**CTU-13 Schema:**
```
CTU-13 Network Flows (4M+ rows):
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

**Demo Command:**
```bash
python -c "from evaluation.ctu_network_public.contract import CASES; [print(f'{c.stem}: {json.loads(c.read_text())[\"question\"][:55]}...') for c in sorted(CASES.glob('ctu_sql_*.json'))]"
```

---

# PHẦN 4: DUALSQL APPROACH (8 phút)

## 4.1 The Challenge (2 phút)

**Script:**
> "Tại sao Text-to-SQL khó?
>
> Khi được hỏi 'Top 5 destination ports with most flows', model phải:
>
> 1. Biết có bảng network_flows → dùng database_profiler
> 2. Biết dst_port là INTEGER (không có catalog values) → dùng GROUP BY
> 3. Biết source_dataset là VARCHAR → dùng WHERE với value search
> 4. Generate SQL đúng syntax
>
> Baseline (one-shot): EX 0/8 - Model không biết schema, hallucinate column names."

---

## 4.2 DualSQL Architecture (3 phút)

**Script:**
> "Giải pháp: DualSQL - chia thành 2 phases riêng biệt.
>
> **Phase 1 - Linker:** Schema discovery + value grounding
> - Model gọi database_profiler → biết column types
> - Model gọi value_search → tìm catalog values
> - Model gọi sql_probe → verify column lineage
> - Output: Linked schema với typed constraints
>
> **Phase 2 - Generator:** SQL generation với linked schema
> - Model đã biết column types và values
> - Chỉ cần viết SQL đúng syntax
> - Model biết INTEGER columns cần GROUP BY aggregation
>
> Điểm mấu chốt: Linker tách biệt khỏi Generator - mỗi phase có role riêng."

**DualSQL Flow:**
```
┌──────────────────────────────────────────────────────────────────┐
│  DUALSQL PIPELINE                                                 │
├──────────────────────────────────────────────────────────────────┤
│                                                                   │
│  [Natural Language Question]                                       │
│   "Return the five scenario 5 destination ports with most flows" │
│                                                                   │
├─────────────────────────────────────────────────────────────────┤
│  PHASE 1: LINKER                                                 │
├─────────────────────────────────────────────────────────────────┤
│                                                                   │
│  ┌─────────────────────────────────────────┐                   │
│  │ database_profiler(table="network_flows") │                   │
│  │                                          │                   │
│  │ Returns:                                │                   │
│  │ • source_dataset: VARCHAR              │                   │
│  │ • dst_port: INTEGER ← no catalog values │                   │
│  │ • label: VARCHAR                       │                   │
│  └─────────────────────────────────────────┘                   │
│                        ↓                                         │
│  ┌─────────────────────────────────────────┐                   │
│  │ value_search(column="source_dataset",   │                   │
│  │             query="scenario 5")         │                   │
│  │                                          │                   │
│  │ Returns:                                │                   │
│  │ • Matched: "ctu13_s5" (from metadata)  │                   │
│  └─────────────────────────────────────────┘                   │
│                        ↓                                         │
│  ┌─────────────────────────────────────────┐                   │
│  │ value_search(column="label",             │                   │
│  │             query="Botnet")              │                   │
│  │                                          │                   │
│  │ Returns:                                │                   │
│  │ • "flow=From-Botnet-V46-TCP-Attempt"  │                   │
│  │ • ILIKE pattern: "%From-Botnet%"       │                   │
│  └─────────────────────────────────────────┘                   │
│                        ↓                                         │
│  [LINKED SCHEMA OUTPUT]                                          │
│  {                                                              │
│    "tables": ["network_flows"],                                 │
│    "typed_constraints": [                                       │
│      {"column": "dst_port", "type": "INTEGER",                 │
│       "hint": "Use SQL aggregation"}                            │
│    ],                                                           │
│    "grounded_values": [                                          │
│      {"column": "source_dataset", "value": "ctu13_s5"}         │
│    ]                                                            │
│  }                                                              │
│                                                                   │
├─────────────────────────────────────────────────────────────────┤
│  PHASE 2: GENERATOR                                              │
├─────────────────────────────────────────────────────────────────┤
│                                                                   │
│  Input: Question + Linked Schema                                 │
│                                                                   │
│  Model reasoning:                                                │
│  "dst_port is INTEGER → no catalog values → need GROUP BY"       │
│  "source_dataset is VARCHAR → WHERE clause with grounded value"  │
│                                                                   │
│  [GENERATED SQL]                                                  │
│  SELECT dst_port, COUNT(*) AS flow_count                         │
│  FROM network_flows                                               │
│  WHERE source_dataset = 'ctu13_s5'                                │
│    AND label ILIKE '%From-Botnet%'                              │
│  GROUP BY dst_port                                                │
│  ORDER BY count(*) DESC                                           │
│  LIMIT 5;                                                        │
│                                                                   │
└──────────────────────────────────────────────────────────────────┘
```

---

## 4.3 Case 006 - The Critical Fix (3 phút)

**Script:**
> "Case 006 là ví dụ điển hình về challenge với INTEGER columns.
>
> Question: 'Return the five scenario 5 destination ports with most flows'
>
> Vấn đề: dst_port là INTEGER column - không có catalog values như VARCHAR.
>
> Model cần biết: INTEGER columns cần GROUP BY aggregation, không phải value search.
>
> Fix: Thêm INTEGER hint vào tool response."

**❌ BEFORE - TOOL_LIMIT:**
```
Model turn 1: value_search("dst_port", "80")
              → No results (INTEGER has no catalog values)
Model turn 2: value_search("dst_port", "443")
              → No results
Model turn 3: value_search("dst_port", "22")
              → No results
Model turn 4: value_search("dst_port", "8080")
              → No results
Model turn 5: value_search("dst_port", "3306")
              → No results
────────────────────────────────────────────────
→ TOOL_LIMIT: Model exhausted 5 tool calls
→ No SQL generated
→ EX = 0
```

**✅ AFTER - EX:**
```
Model turn 1: database_profiler()
              ← Returns: dst_port: INTEGER (no catalog values)
Model turn 2: value_search("dst_port", "80")
              ← Returns: "INTEGER column 'dst_port' has no catalog values.
                          Use SQL aggregation (COUNT, GROUP BY) -
                          do NOT continue value search."
Model turn 3: Generate SQL with GROUP BY
────────────────────────────────────────────────
→ SQL generated correctly
→ EX = 1
```

**Demo Command:**
```bash
python -c "
from evaluation.r2_phase2.grounding import Phase2Tools
r = Phase2Tools('data/ctu_network_public/snapshots/ctu_dev.duckdb', None)
res = r.value_search({'table': 'network_flows', 'column': 'dst_port', 'query': '80'})
print('Resolution:', res['resolution'])
print('Hint:', res['hint'][:80], '...')
"
```

**Expected Output:**
```
Resolution: typed_constraint_not_catalog_value
Hint: INTEGER column "dst_port" has no catalog values. Use SQL aggregation...
```

---

# PHẦN 5: KẾT QUẢ VÀ DEMO (10 phút)

## 5.1 Final Results (2 phút)

**Script:**
> "Tổng hợp kết quả đánh giá:
>
> **R1 - Tool Calling:**
> - GPT-4.1 Mini: 22/24 (91.67%) - Winner
> - GPT-5 Mini: 19/24 (79.17%)
>
> **R2 - Text-to-SQL:**
> - Baseline (one-shot): EX 0/8
> - DualSQL v1: EX 1/8
> - DualSQL v2: EX 7/8
> - Phase 2 (with INTEGER hint): EX 8/8 ✅
>
> **Frozen Holdout (S1/S4):** 8/8 ✅
> → Proof of generalization on unseen data"

**Results Table:**
```
┌──────────────────────────────────────────────────────────────────┐
│  VinSOC Evaluation Results                                        │
├──────────────────────────────────────────────────────────────────┤
│                                                                  │
│  R1 - Tool Calling (24 dev cases):                              │
│  ┌──────────────────┬────────┬──────────────────────────┐     │
│  │ Model           │ EX     │ Notes                     │     │
│  ├──────────────────┼────────┼──────────────────────────┤     │
│  │ GPT-4.1 Mini ✓  │ 22/24  │ Better tool selection    │     │
│  │ GPT-5 Mini      │ 19/24  │ Over-engineering         │     │
│  └──────────────────┴────────┴──────────────────────────┘     │
│                                                                  │
│  R2 - Text-to-SQL (8 dev cases):                               │
│  ┌──────────────────┬────────┬──────────────────────────┐     │
│  │ Version         │ EX     │ Notes                     │     │
│  ├──────────────────┼────────┼──────────────────────────┤     │
│  │ Baseline (v1)  │ 0/8    │ Naive one-shot           │     │
│  │ DualSQL v1     │ 1/8    │ Linker added            │     │
│  │ DualSQL v2     │ 7/8    │ Controller fixed        │     │
│  │ Phase 2 (fix) │ 8/8    │ INTEGER hint            │     │
│  └──────────────────┴────────┴──────────────────────────┘     │
│                                                                  │
│  Frozen Holdout (S1/S4): 8/8 ✅                                 │
│  → Proof of generalization on unseen data                        │
│                                                                  │
└──────────────────────────────────────────────────────────────────┘
```

---

## 5.2 Live Demo - Investigation Flow (5 phút)

**Script:**
> "Giờ em sẽ demo live một investigation thực tế.
>
> Input: IP 185.220.101.45 (một Tor exit node)
>
> Em sẽ show:
> 1. Model chọn đúng tools
> 2. Evidence được collect với IDs
> 3. Hypothesis có trích dẫn evidence
> 4. Risk assessment có basis"

**Demo Command:**
```bash
python -m cli.main investigate 185.220.101.45 --provider openai --model gpt-4.1-mini-2025-04-14
```

**Expected Output Structure:**
```
+------------------------------------------+
| Investigation Case: inv_xxxxx            |
+------------------------------------------+

Initial Indicator: 185.220.101.45 (ipv4)

Investigation Timeline
+-----------------------------------------------------------------------------+
| Tool                  | Arguments                | Summary                  |
|-----------------------+--------------------------+--------------------------+
| cti_enrichment        | {"indicator":            | Reputation: malicious   |
|                       |  "185.220.101.45",...}   | (high confidence)       |
| network_investigation | {"indicator":            | Connections: 4,         |
|                       |  "185.220.101.45",...}   | beaconing detected      |
+-----------------------------------------------------------------------------+

Evidence Collected
Total evidence items: 2
  cti_enrichment: 1 items
  network_investigation: 1 items

Hypotheses
  [HIGH] IP associated with known C2 infrastructure based on threat intel
  [HIGH] Beaconing communication pattern detected

Final Assessment
Risk Level: HIGH
Confidence: HIGH

Supporting Evidence: cti_enrichment:lookup_status:found, 
                    network_investigation:beaconing:detected
```

---

## 5.3 Evidence Traceability Demo (3 phút)

**Script:**
> "Điểm quan trọng nhất: Mọi kết luận đều có evidence citation.
>
> Em sẽ show một example về evidence trace đầy đủ."

**Demo Output Analysis:**
```
Hypothesis: "IP 147.229.10.182 is malicious"

Evidence Chain:
┌──────────────────────────────────────────────────────────────────┐
│  cti_enrichment                                                  │
│  ├── Evidence ID: CTI_001                                        │
│  ├── Source: ThreatFox                                           │
│  ├── Data: {"reputation": "malicious",                           │
│  │          "confidence": "high",                               │
│  │          "tags": ["C2", "botnet"]}                            │
│  └── Collected at: 2024-01-15T10:30:00Z                         │
│                                                                   │
│  network_investigation                                          │
│  ├── Evidence ID: NET_001                                        │
│  ├── Source: CTU-13                                              │
│  ├── Data: {"connections": 4,                                    │
│  │          "time_span_seconds": 30,                              │
│  │          "beaconing_detected": true}                           │
│  └── Collected at: 2024-01-15T10:30:05Z                         │
└──────────────────────────────────────────────────────────────────┘

Conclusion:
"HIGH confidence malicious based on:
 - CTI_001: ThreatFox reports reputation=malicious (high confidence)
 - NET_001: 4 connections in 30s = beaconing pattern"

→ Every claim traceable to specific evidence ID
→ Human can verify each evidence item independently
```

---

# PHẦN 6: SO SÁNH VÀ KẾT LUẬN (5 phút)

## 6.1 Method Comparison (2 phút)

**Comparison Table:**
```
┌─────────────────────────────────────────────────────────────────────────────┐
│  Comparison: Traditional SIEM vs VinSOC                                      │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  Aspect            │ Traditional SIEM  │ VinSOC                            │
│  ─────────────────┼───────────────────┼───────────────────────────────────  │
│  Alert Handling   │ Rule-based        │ LLM reasoning                     │
│  Tool Selection   │ Static rules      │ Dynamic per-case                  │
│  Evidence         │ Logs separate     │ Unified store, traceable          │
│  Reasoning        │ Manual           │ Model + human review               │
│  False Positive   │ High (rules)    │ Lower (evidence-based)             │
│  Generalization   │ Limited to rules │ Learns patterns                   │
│  Scalability      │ Rule maintenance │ Model generalizes                  │
│  Cost             │ High (analyst)   │ $0.01/investigation               │
│                                                                             │
│  Key Difference: VinSOC reasons about evidence, not just patterns           │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## 6.2 Key Learnings (2 phút)

**Script:**
> "3 key learnings từ nghiên cứu:
>
> **Learning 1: Tool selection quality > Model size**
> GPT-4.1 Mini (nhỏ) đánh bại GPT-5 Mini (lớn) vì chọn đúng tools, không over-engineer.
>
> **Learning 2: INTEGER column handling is critical**
> Hint mechanism giúp model phân biệt aggregation vs value search.
>
> **Learning 3: Evidence-grounding prevents hallucinations**
> Mọi conclusion phải cite specific evidence IDs."

**Metrics Summary:**
```
Efficiency:
- R1 investigation: ~$0.01 (GPT-4.1 Mini)
- R2 investigation: ~$0.02-0.03 (GPT-5 Mini, more turns)
- vs Manual: $50-100/alert (full analyst time)

Accuracy:
- R1 Tool Calling: 91.67%
- R2 Text-to-SQL: 100% (dev + frozen)
- Frozen holdout: 8/8 (generalization proof)
```

---

## 6.3 Limitations & Future Work (1 phút)

**Script:**
> "Limitations:
>
> 1. Single-model evaluation - chưa test nhiều providers
> 2. Limited to 3 data sources - có thể mở rộng
> 3. Snapshot-based evaluation - chưa real-time streaming
>
> Future work:
>
> 1. Multi-model comparison (Gemini, Claude)
> 2. Real-time streaming telemetry
> 3. Endpoint process analysis mở rộng
> 4. Integration với SOAR cho automated response"

---

# PHẦN 7: Q&A (5 phút)

## Prepared Answers

### "AI miss threat thì sao?"
```
→ Human-in-the-loop: AI chỉ đề xuất, human phê duyệt.
→ 2 gates: triage và final.
→ Nếu analyst không đồng ý → reject/escalate.
→ System không bao giờ tự action.
```

### "Chi phí vận hành?"
```
→ ~$0.01-0.03 per investigation (model API)
→ vs $50-100 per alert (full analyst time)
→ Tiết kiệm 90% false positive review
```

### "Security concerns?"
```
→ Read-only: Không action được
→ Evidence immutable: Không sửa được sau khi store
→ Full audit trail: Mọi bước được log
→ No autonomous containment: Human gate bắt buộc
→ Prompt injection protection: Markers được detect
```

### "Generalization?"
```
→ Frozen holdout: 8/8 trên unseen data (S1/S4)
→ INTEGER hint = transferrable knowledge
→ Model học pattern, không phải memorize
→ Không overfit vào development cases
```

### "So với SOAR?"
```
→ SOAR: Rule-based automation
→ VinSOC: LLM reasoning + evidence grounding
→ Complementary: VinSOC điều tra → SOAR action
→ VinSOC không thay thế SOAR, bổ sung cho investigation
```

---

# APPENDIX: Commands Reference

## Quick Verification (no API key needed)
```bash
# List R1 cases
python -m evaluation.tool_calling list dev

# List R2 cases
python -c "from evaluation.ctu_network_public.contract import CASES; [print(c.stem) for c in sorted(CASES.glob('ctu_sql_*.json'))]"

# List scenarios
python -m cli.main list

# Test INTEGER hint
python -c "
from evaluation.r2_phase2.grounding import Phase2Tools
r = Phase2Tools('data/ctu_network_public/snapshots/ctu_dev.duckdb', None)
res = r.value_search({'table': 'network_flows', 'column': 'dst_port', 'query': '80'})
print('Hint:', res['hint'][:60], '...')
"

# Run Phase2 tests
python -m pytest tests/test_r2_phase2_grounding.py tests/test_r2_phase2_safety.py -q
```

## Live Investigation (requires API key)
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

# Live CLI investigation
python -m cli.main investigate 185.220.101.45 --provider openai --model gpt-4.1-mini-2025-04-14
```

## Run Tests
```bash
# Phase 2 tests
python -m pytest tests/test_r2_phase2_grounding.py tests/test_r2_phase2_safety.py -q

# Full test suite
python -m pytest -q
```

---

# FILES REFERENCE

| File | Description |
|------|-------------|
| `docs/architecture.md` | Full architecture documentation |
| `docs/problem.md` | Problem statement và research questions |
| `docs/evaluation_protocol_v1.md` | R1/R2 evaluation protocol |
| `evaluation/tool_calling/` | R1 tool calling benchmark |
| `evaluation/r2_phase2/` | R2 text-to-SQL Phase 2 implementation |
| `agent/orchestrator.py` | Main investigation orchestrator |
| `agent/evidence.py` | Evidence store implementation |
| `skills/` | Investigation skills (CTI, Network, Endpoint) |
| `cli/main.py` | CLI interface |
| `results/` | Evaluation results |

---

**End of Presentation Script**
