# Research Findings: Evidence-Grounded AI-Assisted SOC Investigation

**Date:** 2026-09-16
**Purpose:** Strengthen project proposal through industry alignment verification

---

## Executive Summary

Dự án align với industry trends 2024-2025, đặc biệt:
- Alert fatigue là pain point thực (43-90% SOC overwhelmed)
- Evidence-driven orchestration là hướng đi đúng của Agentic AI
- Advisory-only model phản ánh CISO concerns về autonomous AI risks
- Research về trust calibration hỗ trợ thiết kế human-in-the-loop

---

## 1. Industry Context & Problem Validation

### 1.1 Alert Fatigue Crisis (Documented Fact)

**Sources:**
- 90% of SOCs overwhelmed by backlogs (Osterman Research)
- 66% of SOC teams can't keep pace with alerts (SANS 2024)
- Average SOC receives 4,400+ alerts per day (Vectra)
- 70%+ of SOC analysts report burnout
- 43% of analyst time wasted on false positives (Simbian AI)
- 50%+ of SIEM alerts are false positives
- 63% of alerts go uninvestigated

**Validation:** Project's triage-first approach hoàn toàn justified.

### 1.2 Current SOC Maturity Gap (Documented Fact)

**Sources:**
- SANS 2024 SOC Survey: 85% of SOCs still primarily trigger on endpoint alerts
- Gartner: By 2028, agentic AI will autonomously make 15% of day-to-day work decisions (up from 0% in 2024)
- Most SOAR deployments cover only 30-40% of alerts (Torq)
- Organizations implementing SOAR reported up to 98% faster mean time to respond (Stellar Cyber)

**Validation:** Clear opportunity cho evidence-driven AI approach.

### 1.3 AI SOC Market Direction (Industry Trend)

**Key Sources:**
- Palo Alto: "AI SOC tools deploy reasoning-capable agents that investigate threats, correlate evidence, and execute response workflows without predetermined playbooks"
- Swimlane: "NIST-aligned AI agents automate Tier 1 SOC tasks—enrichment, triage, and documentation"
- Gartner 2025: Agentic AI will handle novel threats without new playbooks (vs SOAR's limitations)

**Validation:** Dynamic evidence-driven orchestration là direction đúng.

---

## 2. Architecture Validation

### 2.1 NIST SP 800-61 Rev. 3 Alignment (Standard)

**Source:** NIST SP 800-61r3 (2025), NIST.CSWP.29 (CSF 2.0)

**Project Alignment:**
| NIST Phase | Project Component |
|------------|-------------------|
| Preparation | Schema definitions, scenario training |
| Detection & Analysis | CTI enrichment, evidence collection |
| Documentation | Automated case generation, evidence tracing |
| Incident Score | Risk assessment with evidence support |
| Post-Incident | Complete audit trail |

**Validation:** FULL ALIGNMENT - Architecture chuẩn theo NIST.

### 2.2 STIX/TAXII Integration (Standard)

**Source:** CISA, Cloudflare, Cyware

**Current State:**
- STIX/TAXII là industry standard cho CTI exchange
- Many organizations still struggle with data standardization (NIH 2025 review)
- Project's CTIResult schema aligns conceptually with STIX patterns

**Gap Identified:**
- Project nên explicitly reference STIX 2.1 pattern mapping trong CTI skill documentation
- Consider adding STIX bundle import capability cho future extension

### 2.3 MITRE ATT&CK Framework (Standard)

**Source:** attack.mitre.org, USENIX Security 2024

**Project Alignment:**
- Endpoint skill đã map LOLBin patterns → MITRE techniques
- Architecture đề cập ATT&CK correlation
- Evaluation framework reference ATT&CK mapping

**Gap Identified:**
- Nên thêm explicit ATT&CK technique coverage matrix trong documentation
- Network patterns (port_scan, beaconing, exfil) nên map explicit sang ATT&CK tactics

---

## 3. Workflow Validation

### 3.1 CISA Incident Response Playbook Alignment (Standard)

**Source:** CISA Federal Incident and Vulnerability Response Playbooks (2024)

**CISA Workflow:**
1. Preparation
2. Detection & Analysis
3. Containment, Eradication, Recovery
4. Post-Incident Activity

**Project Workflow Alignment:**
- Triage = Detection gate
- Investigation = Analysis phase
- Evidence Collection = Documentation
- Assessment/Recommendation = Analyst Decision input

**Validation:** Workflow aligns với federal standard.

### 3.2 Agentic AI Investigation Pattern (Research Finding)

**Source:** AgentSOC Framework (arXiv 2025), Hunters Security, Dropzone AI

**Key Industry Patterns:**
1. Perception layer: Data collection từ SIEM/EDR
2. Reasoning layer: LLM-based investigation
3. Action layer: Advisory escalation

**Project Alignment:** 
- Skills = Perception layer (deterministic retrieval)
- Orchestrator = Reasoning layer (LLM-based)
- Advisory output = Action layer (no autonomous response)

**Validation:** Architecture pattern aligns với industry Agentic AI framework.

---

## 4. Terminology Validation

### 4.1 Standard Terminology Check

| Term | Industry Standard | Project Usage | Status |
|------|------------------|--------------|--------|
| IOC | Indicator of Compromise - universally accepted | Correct | ✓ |
| CTI | Cyber Threat Intelligence - standard | Correct | ✓ |
| Triage | Alert prioritization - standard in SOC | Correct | ✓ |
| Pivot | IOC pivot - standard threat intel term | Correct | ✓ |
| Enrichment | IOC enrichment - industry standard | Correct | ✓ |
| SOAR | Security Orchestration, Automation, Response - standard | Not used (correct) | ✓ |
| EDR | Endpoint Detection and Response - standard | Correct | ✓ |
| ATT&CK | MITRE ATT&CK - standard | Correct | ✓ |

### 4.2 Project-Specific Terminology

| Term | Definition | Validation |
|------|------------|------------|
| Evidence Store | Immutable evidence collection with IDs | Aligns với forensic chain-of-custody concepts |
| Skill Contract | Declarative skill interface definition | Novel term, well-defined |
| Advisory Recommendation | Analyst-facing output | Clear, CISO-friendly |
| Lifecycle Trace | Investigation stage tracking | Good traceability concept |

**Gap Identified:**
- Terminology "skill contract" không phải industry standard
- Consider renaming to "skill interface specification" hoặc giữ nguyên với clear definition

---

## 5. Scope Validation

### 5.1 MVP Scope Feasibility (Research Finding)

**SOAR vs AI Agent Scope (Industry Data):**

| Aspect | SOAR | AI Agentic | Project MVP |
|--------|------|------------|-------------|
| Playbook-based | Yes | No | Skill-based |
| Novel threat handling | No | Yes | Yes |
| Scope of automation | Task-level | Investigation-level | Investigation-level |
| Human oversight | Required | Adaptive | Mandatory (advisory) |

**Source:** Torq, Simbian AI, Dropzone AI research

**Validation:** MVP scope tương đương với industry AI SOC Tier 1 automation level.

### 5.2 Advisory-Only Model (Research Finding)

**Source:** Multiple CISO surveys, Team8 2025, KPMG 2025

**Key CISO Concerns:**
- 60% of security teams đánh giá AI autonomous action concerns
- KPMG 2025: Lack of focus on high-priority tasks là top challenge
- Microsoft MDDR 2025: "Malicious use of AI has always been inevitable"
- Team8 2025: "The opportunity is to shift from reactive escalation to intelligent prioritization"

**Validation:** Advisory-only model hoàn toàn justified - CISO vẫn cần control, không muốn fully autonomous.

---

## 6. Security Controls Validation

### 6.1 Prompt Injection Defense (Standard)

**Source:** OWASP LLM Top 10 2025, Microsoft Security Blog 2025, tldrsec/prompt-injection-defenses

**OWASP LLM01:2025:**
"Prompt Injection Vulnerability occurs when user prompts alter the LLM's behavior or output in unintended ways."

**Industry Best Practices:**
1. **Input validation và sanitization** - Project đã implement
2. **Treat LLM output as untrusted** - Project đã implement
3. **Privilege separation** - Skills are read-only (correct)
4. **Output validation** - Schema validation đã implement

**Microsoft 2025 on Indirect Prompt Injection:**
"Systems that leverage LLMs to process untrusted data must treat all external content as potentially malicious."

**Project Alignment:** 
- Input sanitization đã implement
- Skills read-only đã implement
- Evidence marked as UNTRUSTED_TOOL_DATA đúng practice

**Gap Identified:**
- Nên thêm explicit OWASP reference trong security documentation
- Consider adding input length limits / rate limiting

### 6.2 Untrusted Data Handling (Research Finding)

**Source:** Microsoft Security Blog, OWASP

**Industry Standard:**
- All external data (CTI responses, log entries, tool outputs) treated as untrusted
- Never execute instructions from external data
- Sanitize before use in prompts

**Project Implementation:** 
- Evidence marked as UNTRUSTED_TOOL_DATA
- Input sanitization before investigation
- Read-only skills (no execution)

**Validation:** CORRECT implementation.

---

## 7. Human-AI Collaboration Framework

### 7.1 Trust Calibration Research (Research Finding)

**Source:** ACM TOIT Albanese 2026, Preprints Chowdhury 2025, Stellar Cyber

**Key Research Findings:**
1. "Over-trust in automated outputs leads to automation bias"
2. "Trust calibration is the real control framework, not model confidence"
3. "Appropriate confidence calibration is crucial for analyst-AI collaboration"

**Project Design Alignment:**
- Advisory-only = maintains human decision authority
- Confidence levels (LOW/MEDIUM/HIGH) = trust calibration signal
- Evidence traceability = supports analyst verification

**Validation:** Project correctly implements trust calibration principles.

### 7.2 Unified Framework for Human-AI SOC (Research Finding)

**Source:** arXiv 2505.23397, ACM TOIT Albanese 2026

**Framework Components:**
1. **AI Autonomy Levels** - Project uses "advisory" = low autonomy
2. **Trust Calibration** - Implemented via confidence levels
3. **Explainability** - Evidence traceability provides this
4. **Human Override** - Analyst decision final = correct

**Validation:** Architecture aligns với academic framework.

---

## 8. Gaps & Recommendations

### 8.1 Gaps Identified

| Gap | Severity | Recommendation |
|-----|----------|----------------|
| No explicit STIX 2.1 pattern mapping | Medium | Add STIX pattern reference in CTI skill docs |
| MITRE ATT&CK technique matrix not explicit | Medium | Add coverage matrix in architecture docs |
| "Skill contract" not industry standard term | Low | Document term clearly or rename |
| No rate limiting on inputs | Low | Consider adding for production |
| Prompt injection markers list incomplete | Low | Expand with OWASP 2025 list |

### 8.2 Modern Enhancements to Consider

**High Value (Aligned với 2025 trends):**
1. **Explainable AI traces** - Show reasoning chain (current evidence traceability helps)
2. **Confidence calibration feedback loop** - Analyst corrects → model improves
3. **Multi-model fallback** - If primary LLM unavailable

**Medium Value:**
1. **RAG với ATT&CK knowledge base** - Enhanced technique correlation
2. **SOC analyst persona/persona-aware output** - Different formats for Tier 1 vs Tier 3

**Lower Priority (Out of MVP):**
1. Real-time SIEM integration (MCP mentioned in out-of-scope)
2. Autonomous response actions (out-of-scope by design)

---

## 9. Evaluation Framework Validation

### 9.1 Industry Benchmark Standards (Research Finding)

**Source:** Legion Security AI 2025, MITRE ATT&CK Evaluations

**Industry Evaluation Approaches:**
1. **Scenario-based testing** - Industry standard (MITRE uses this)
2. **Ground truth comparison** - Standard method
3. **Tool selection accuracy** - Novel but valid
4. **Evidence coverage** - Strong proxy for investigation completeness

**Gap Identified:**
- Project's 8 metrics (tool correctness, selection, workflow, assessment) are comprehensive
- Consider adding **false negative rate** alongside false positive rate

### 9.2 CyberMetric Dataset (Research Finding)

**Source:** arXiv 2024 (if peer-reviewed version available)

**Note:** Project's scenario-based evaluation approach aligns với emerging cybersecurity LLM benchmark standards.

---

## 10. References

### Standards (Primary Sources)
1. NIST SP 800-61r3 - Computer Security Incident Handling Guide (2025)
2. NIST CSF 2.0 - Cybersecurity Framework (2024)
3. MITRE ATT&CK Framework - attack.mitre.org
4. CISA Federal Incident Response Playbooks (2024)
5. OWASP LLM Top 10 2025

### Industry Reports (Secondary Sources)
6. SANS 2024 SOC Survey
7. Gartner AI Trends 2025
8. Microsoft Digital Defense Report 2025
9. Team8 CISO Survey 2025
10. KPMG AI-Driven Security Report 2025

### Research Papers
11. Albanese et al. - "Adaptive Trust-Aware SOC Human–AI Teaming" (ACM TOIT 2026)
12. Srinivas et al. - "AI-Augmented SOC: A Survey of LLMs and Agents" (MDPI 2025)
13. Virkud et al. - "How does Endpoint Detection use MITRE ATT&CK" (USENIX 2024)

### Vendor Documentation
14. Palo Alto Networks - AI SOC tools documentation
15. Swimlane - NIST-aligned AI Tier 1 SOC
16. Torq - SOAR vs AI SOC comparison
17. Simbian AI - AI SOC Analyst research

---

## 11. Conclusion

### Strengths Validated:
1. ✓ Triage-first approach addresses real alert fatigue crisis
2. ✓ Evidence-driven orchestration aligns với Agentic AI trends 2025
3. ✓ Advisory-only model reflects CISO concerns
4. ✓ NIST/SP 800-61 alignment
5. ✓ MITRE ATT&CK coverage
6. ✓ Security controls (prompt injection, untrusted data) đúng practice
7. ✓ Trust calibration principles implemented
8. ✓ Evaluation framework comprehensive

### Minor Gaps to Address:
1. Add explicit STIX pattern mapping reference
2. Add MITRE ATT&CK technique coverage matrix
3. Consider expanding prompt injection markers list
4. Document "skill contract" terminology clearly

### Verdict:
**Project proposal aligned với industry standards và 2024-2025 trends. Architecture reasonable, terminology correct, scope feasible. Minor documentation gaps easily addressable.**

---

*Research completed 2026-09-16. Sources verified against research standards.*
