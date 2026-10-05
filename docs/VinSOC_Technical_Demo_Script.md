# VinSOC - Technical Demo Script for Mentor

> Evidence status (2026-10-05): verified R2 full-suite dev **7/8**, case006 **TOOL_LIMIT**. Post-INTEGER-hint chưa có verified full-suite score. S1/S4 đã consumed, protocol_eligible=false; chưa có independent R2 holdout. R1 frozen mới kiểm tương thích offline, chưa có model accuracy. R1 dev-v2 có11/24 gold adjudicated sau khi xem model. Các sơ đồ/output minh họa dưới đây không phải receipt E2E đã nghiệm thu. Task2 chỉ offline; mọi lệnh live cần gate riêng.

**Duration:** 20-30 minutes
**Audience:** Technical mentor with SOC/security background
**Goal:** Demonstrate AI-assisted SOC investigation with evidence-grounded approach

---

## Part 1: Problem Statement (3 phút)

### Slide: SOC Challenge
```
Problem:
- 10,000+ alerts/day, 90% false positives
- SOC analysts overwhelmed, inconsistent analysis
- Manual investigation: slow, error-prone

Opportunity:
- LLMs can reason across CTI, network, endpoint data
- But: hallucinations, missing evidence, no traceability

Solution:
- VinSOC: AI copilot with bounded autonomy
- Evidence-driven: every conclusion must cite evidence
- Human-in-the-loop: analyst reviews before action
```

### Key Insight
```
SOC Investigation = Multi-step reasoning + Evidence correlation

Traditional: SIEM rules → alert → human analysis
VinSOC: Alert → LLM agent → Tools → Evidence Store → Human review
```

---

## Part 2: Architecture Overview (5 phút)

### System Architecture
```
┌─────────────────────────────────────────────────────────────────┐
│                        Human Analyst                              │
│                   (oversight + final approval)                     │
└─────────────────────────────────────────────────────────────────┘
                                  │
                                  ▼
┌─────────────────────────────────────────────────────────────────┐
│              Investigation Orchestrator (LLM)                     │
│   ┌──────────────┐  ┌──────────────┐  ┌──────────────────────┐ │
│   │ Intent       │→ │ Tool         │→ │ Evidence             │ │
│   │ Parsing      │  │ Selection    │  │ Interpretation       │ │
│   └──────────────┘  └──────────────┘  └──────────────────────┘ │
└─────────────────────────────────────────────────────────────────┘
                                  │
              ┌───────────────────┼───────────────────┐
              ▼                   ▼                   ▼
┌──────────────────┐  ┌──────────────────┐  ┌──────────────────┐
│   CTI Skill      │  │  Network Skill   │  │  Endpoint Skill  │
│   (ThreatFox)    │  │  (CTU-13)        │  │  (Sysmon)       │
└──────────────────┘  └──────────────────┘  └──────────────────┘
              │                   │                   │
              ▼                   ▼                   ▼
┌─────────────────────────────────────────────────────────────────┐
│                    Evidence Store (immutable)                      │
│  - Every result tagged with evidence ID                           │
│  - Conclusions MUST cite specific evidence IDs                    │
│  - No hallucination: conclusions are traceable                   │
└─────────────────────────────────────────────────────────────────┘
```

### 3 Core Principles
```
1. EVIDENCE-DRIVEN
   - Every hypothesis must link to specific evidence IDs
   - No "I think" without "because evidence X says..."

2. BOUNDED AUTONOMY
   - AI proposes, human approves
   - Investigation is READ-ONLY (no containment actions)
   - Human gates at triage and final assessment

3. DECOUPLED ARCHITECTURE
   - Skills are independent of LLM provider
   - LLM only for orchestration (tool selection, reasoning)
   - Easy to swap models or add new data sources
```

---

## Part 3: R1 - Tool Calling Evaluation (5 phút)

### Demo Command 1: List R1 Cases
```bash
python -m evaluation.tool_calling list dev
```

Output:
```
Available cases in 'dev': 24
  case_001: network_only (basic)
  case_002: cti_only (basic)
  case_003: endpoint_only (basic)
  ...
  case_005: cti_network_endpoint (advanced)
  ...
```

### Demo Command 2: Run Single Case
```bash
python -m evaluation.tool_calling run case_005 --provider openai --model gpt-4.1-mini-2025-04-14
```

### Results Table
```
┌─────────────────────────────────────────────────────────┐
│  R1 Tool Calling Results (24 dev cases)                  │
├─────────────────────────────────────────────────────────┤
│                                                         │
│  Model              │ EX     │ F1     │ No-tool │ Cost  │
│  ───────────────────┼────────┼────────┼─────────┼──────│
│  GPT-4.1 Mini       │ 22/24  │ 0.9508 │   5/5   │$0.010 │  ← Winner
│  GPT-5 Mini         │ 19/24  │ 0.9355 │   4/5   │$0.016 │
│                                                         │
│  Key insight: Smaller model + better tool selection >     │
│              larger model with worse selection            │
│                                                         │
└─────────────────────────────────────────────────────────┘
```

### Tool Selection Example
```
Case: "Check if IP is malicious AND get network connections"

GPT-4.1 Mini selection:
  1. cti_enrichment(IP)     ← correct
  2. network_investigation() ← correct

GPT-5 Mini selection:
  1. cti_enrichment(IP)
  2. network_investigation()
  3. endpoint_investigation() ← unnecessary (no host provided)
```

---

## Part 4: R2 - Text-to-SQL Evaluation (10 phút)

### The Challenge
```
CTU-13 Network Flows Database:
- 4M+ rows, 12 columns
- Types: VARCHAR, INTEGER, BIGINT, TIMESTAMP
- 8 dev cases (S5/S7); S1/S4 đã consumed, không độc lập/protocol-eligible

Example Question:
  "Return the five scenario 5 destination ports with most flows"

Model needs to know:
1. Column names → use database_profiler tool
2. Column types → INTEGER vs VARCHAR
3. Catalog values → use value_search tool
4. When to aggregate → GROUP BY for INTEGER columns
```

### DualSQL Architecture
```
┌─────────────────────────────────────────────────────────────────┐
│  Phase 2: Linker → Generator Pipeline                           │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  [Natural Language Question]                                     │
│       │                                                         │
│       ▼                                                         │
│  ┌──────────────┐                                               │
│  │   Linker     │  Schema Discovery + Value Grounding           │
│  │  (4 turns)   │  • database_profiler → column types          │
│  └──────────────┘  • value_search → catalog values             │
│       │             • sql_probe → lineage verification          │
│       ▼                                                         │
│  ┌──────────────┐                                               │
│  │  Generator   │  SQL Generation with Linked Schema          │
│  │  (2 turns)   │  • COUNT, GROUP BY, WHERE                   │
│  └──────────────┘  • Aggregations for INTEGER columns          │
│       │                                                         │
│       ▼                                                         │
│  [Final SQL with Provenance]                                     │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

### Demo Command3: Offline R2 scoring

```powershell
python -m scripts.audit_r2_saved_outputs --input results/evaluation_v1/ctu_network_public/r2_phase2_live/20261001_3f9d72d/suite --cases-dir evaluation/ctu_network_public/dev --snapshot data/ctu_network_public/snapshots/ctu_dev.duckdb --output .superpowers/reviewer-r2-replay-unique
```
Output phải là thư mục mới. Replay không gọi model, không overwrite nguồn và không phải lượt inference mới.
Pipeline `OK` chỉ nghĩa là có SQL; EX phải lấy từ evaluator thực thi prediction và gold trên snapshot.

### Case006: preserved failure

Official suite:3 linker turns,5 DB calls, TOOL_LIMIT, generator không chạy, final_sql=null, EX=false.
Post-INTEGER hint là code change, chưa có verified full-suite model score.

### R2 results

| Điều kiện lịch sử riêng | Kết quả / giới hạn |
|---|---|
| CTU E0, run36520685612 | EX0/8, syntax/execution8/8 |
| Remediation E3 | EX1/8; contract khác Phase2 |
| Verified Phase2 suite, SHA3f9d72d | **EX7/8**, syntax/execution7/8;44 responses;$0.02085850 cho cả suite |
| Post-INTEGER-hint | **Chưa có verified full-suite score**; test riêng không thay case006 trong suite cũ |
| S1/S4 | **Consumed**, không protocol-eligible; prediction mới thiếu scoring/identity, unscored |

Các hàng khác điều kiện; không trình bày chúng thành một thí nghiệm cải tiến có đối chứng.
Chưa có independent R2 holdout hoặc bằng chứng generalization. Xem [báo cáo đính chính](evaluation/FINAL_EVALUATION_REPORT.md).

---

## Part 5: Evidence Grounding Demo (5 phút)

### Demo Command 4: Show Evidence Flow
```bash
# Run investigation with trace
python -m cli.main investigate 185.220.101.45 --provider openai --model gpt-4.1-mini-2025-04-14
```

### Output Example
```
┌─────────────────────────────────────────────────────────┐
│  Investigation: 185.220.101.45 (Tor exit node)         │
├─────────────────────────────────────────────────────────┤
│                                                         │
│  [1] CTI Enrichment                                    │
│      Tool: cti_enrichment                              │
│      Evidence: CTI_001 (threatfox), CTI_002 (tags)     │
│      Result: malicious, confidence=high                │
│                                                         │
│  [2] Network Investigation                             │
│      Tool: network_investigation                       │
│      Evidence: NET_001 (connections), NET_002 (ports)  │
│      Result: 4 connections, beaconing pattern          │
│                                                         │
│  Final Assessment:                                     │
│  ├─ Risk: HIGH                                         │
│  ├─ Confidence: HIGH                                   │
│  ├─ Supporting Evidence: CTI_001, CTI_002, NET_001     │
│  └─ Assessment: C2 communication confirmed            │
│                                                         │
└─────────────────────────────────────────────────────────┘
```

### Key Point: Traceability
```
Every conclusion links to specific evidence:

❌ Bad: "This IP is malicious because I think so"
✅ Good: "This IP is malicious because CTI_001 (ThreatFox) 
         reports reputation=malicious and NET_001 shows
         beaconing pattern (4 connections in 30s)"
```

---

## Part 6: Summary (2 phút)

### Results Summary

| Track | Verified development evidence | Holdout status |
|---|---|---|
| R1 | GPT-4.1 mini22/24; F1 0.9508; no-tool5/5;11/24 post-output adjudication caveat | Compatibility only; frozen inference chưa được mở |
| R2 | Phase2 full suite7/8; case006 TOOL_LIMIT; post-INTEGER hint chưa có full-suite score | S1/S4 consumed; chưa có independent R2 holdout |

### Limits

- Synthetic typed-grounding/counterexample tests kiểm code/evaluator, không đo model accuracy.
- IDs hợp lệ không tự chứng minh factual claims đúng; demo E2E cần receipt/evidence/fact checks riêng.
- R1 và R2 là hai metric khác nhau; demo không vào accuracy benchmark.
- Dev score, offline compatibility và green CI không phải proof of generalization.


### Demo Commands Reference
```bash
# R1 Tool Calling
python -m evaluation.tool_calling list dev
python -m evaluation.tool_calling run case_005 --provider openai --model gpt-4.1-mini-2025-04-14

# R2 Text-to-SQL
python -c "from evaluation.ctu_network_public.contract import CASES; [print(c.stem) for c in sorted(CASES.glob('ctu_sql_*.json'))]"

# CLI Investigation
python -m cli.main investigate 185.220.101.45 --provider openai
python -m cli.main list

# Tests
python -m pytest tests/test_r2_phase2_grounding.py -q
python -m pytest tests/test_r2_phase2_safety.py -q
```

---

## Q&A Preparation

### "AI miss threat thì sao?"
→ HITL gate: human duyệt trước mọi action. AI chỉ đề xuất, không tự quyết định.

### "Chi phí?"
→ ~$0.01-0.02/investigation (GPT-4.1 mini)
→ GPT-5 mini: ~$0.016/investigation

### "Dùng data source nào?"
→ CTI: ThreatFox (101k+ IOCs)
→ Network: CTU-13 (4M+ flows)
→ Endpoint: Sysmon traces (future)

### "So với SOAR?"
→ SOAR: rule-based automation
→ VinSOC: LLM reasoning + evidence grounding
→ Complementary, not replacement

### "Security concerns?"
→ Read-only enforcement
→ Evidence immutability
→ No autonomous containment
→ Full audit trail

---

## Files Reference

| File | Description |
|------|-------------|
| `docs/architecture.md` | Full architecture documentation |
| `docs/problem.md` | Problem statement and research questions |
| `docs/evaluation_protocol_v1.md` | R1/R2 evaluation protocol |
| `evaluation/tool_calling/` | R1 tool calling benchmark |
| `evaluation/r2_phase2/` | R2 text-to-SQL Phase 2 implementation |
| `agent/orchestrator.py` | Main investigation orchestrator |
| `skills/` | CTI, Network, Endpoint skills |
| `cli/main.py` | CLI for live investigations |
