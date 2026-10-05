# VinSOC - Technical Demo Script for Mentor

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
- 8 dev cases (S5/S7), 8 frozen cases (S1/S4)

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

### Demo Command 3: Run R2 Phase2 Cases
```bash
# List Phase2 cases
python -c "
from evaluation.ctu_network_public.contract import CASES
for c in sorted(CASES.glob('ctu_sql_*.json'))[:3]:
    import json
    d = json.loads(c.read_text())
    print(f'{d[\"case_id\"]}: {d[\"question\"][:60]}...')
"

# Run one case
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

tools = Phase2Tools(
    snapshot='data/ctu_network_public/snapshots/ctu_dev.duckdb',
    manifest=MANIFEST
)

result = run_case(
    case=type('Case', (), case)(),
    condition='E3',
    tools=tools,
    client=client,
    schema_context=tools.schema_context(),
)

print(f'EX: {result.get(\"error_category\") == \"OK\"}')
print(f'SQL: {result.get(\"final_sql\", \"N/A\")[:100]}')
"
```

### Case 006: The Critical Fix

**❌ BEFORE (TOOL_LIMIT - before fix):**
```
Model called: value_search("dst_port", "80")
→ No results (INTEGER column has no catalog values)
→ Model tried again... 5 times → TOOL_LIMIT
```

**✅ AFTER (EX - after fix):**
```
Model called: value_search("dst_port", "80")
← Received hint: "INTEGER column 'dst_port' has no catalog values. 
                 Use SQL aggregation (COUNT, GROUP BY)"
Model switched to: GROUP BY dst_port ORDER BY count(*) DESC LIMIT 5
```

### Final R2 Results
```
┌─────────────────────────────────────────────────────────┐
│  R2 Text-to-SQL Results                                │
├─────────────────────────────────────────────────────────┤
│                                                         │
│  Baseline (one-shot):     EX 0/8  ← naive approach     │
│  DualSQL v1:             EX 1/8  ← linker added       │
│  DualSQL v2:             EX 7/8  ← controller fixed    │
│  DualSQL Phase 2:        EX 8/8  ← INTEGER hint fix    │
│                                                         │
│  Frozen Holdout (S1/S4): EX 8/8  ← generalization!     │
│                                                         │
└─────────────────────────────────────────────────────────┘
```

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
```
┌─────────────────────────────────────────────────────────┐
│  VinSOC Evaluation Results                              │
├─────────────────────────────────────────────────────────┤
│                                                         │
│  R1 - Tool Calling:                                     │
│  ┌──────────────┬────────┬─────────────────┐           │
│  │ Dev (24)    │ 91.67% │ GPT-4.1 Mini ✓  │           │
│  │ Frozen (8)  │ 100%   │ Compatible      │           │
│  └──────────────┴────────┴─────────────────┘           │
│                                                         │
│  R2 - Text-to-SQL:                                     │
│  ┌──────────────┬────────┬─────────────────┐           │
│  │ Dev (8)     │ 8/8    │ EX ✓            │           │
│  │ Frozen (8)  │ 8/8    │ EX ✓            │           │
│  └──────────────┴────────┴─────────────────┘           │
│                                                         │
│  Proof of generalization: 8/8 on unseen frozen data     │
│                                                         │
└─────────────────────────────────────────────────────────┘
```

### Key Learnings
```
1. Smaller model + better tool selection > larger model
   → GPT-4.1 Mini (91.67%) > GPT-5 Mini (79.17%)

2. INTEGER column handling is critical
   → Hint mechanism prevents TOOL_LIMIT failures

3. Evidence-grounding prevents hallucinations
   → Every conclusion must cite specific evidence IDs

4. Frozen holdout validates generalization
   → 8/8 on unseen data proves real improvement
```

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
