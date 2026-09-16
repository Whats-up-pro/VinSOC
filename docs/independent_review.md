# Independent Project Review: AI-Assisted SOC Investigation System

**Review Date:** 2026-09-16
**Reviewer:** Independent Technical Review
**Purpose:** Critical evaluation against project direction, industry practice, and research standards

---

## A. Current Project Understanding

### A.1 Project Summary

**Name:** Evidence-Grounded AI-Assisted SOC Investigation System
**Goal:** AI augmentation for SOC analysts, not AI replacement
**Approach:** Tool-calling LLM agent with 3 read-only investigation skills

### A.2 Project Direction (as stated)

```
Alert → Alert Triage → Investigation Agent → Evidence Collection/Pivot → 
Evidence Correlation → Assessment → Recommendation → Analyst Decision
```

**Core Principles:**
1. Triage-first
2. Evidence-driven orchestration
3. No hard pipeline (CTI→Network→Endpoint)
4. Evidence và Inference tách biệt
5. Assessment trace về evidence IDs
6. LLM = orchestration/reasoning; Skills = deterministic retrieval
7. Read-only investigation
8. Advisory-only (no auto-close, no response)
9. Insufficient Evidence là outcome hợp lệ
10. Security data = untrusted input

### A.3 MVP Scope

**In Scope (5 weeks):**
- Alert triage
- CTI / Network / Endpoint skills
- Dynamic orchestration
- Evidence traceability
- Advisory recommendation
- Scenario benchmark
- Security testing

**Out of Scope:**
- Autonomous response
- Production SIEM integration
- Full MCP implementation
- Fine-tuning
- Large-scale infrastructure

---

## B. Code Audit Findings

### B.1 Implementation Status Matrix

| Component | Status | Evidence |
|-----------|--------|----------|
| **Triage Gate** | [IMPLEMENTED] | `triage.py` - deterministic keyword matching |
| **CTI Skill** | [IMPLEMENTED] | `cti_skill.py` - full schema validation |
| **Network Skill** | [IMPLEMENTED] | `network_skill.py` - pattern detection logic |
| **Endpoint Skill** | [IMPLEMENTED] | `endpoint_skill.py` - LOLBin patterns |
| **Evidence Store** | [IMPLEMENTED] | `evidence.py` - append-only, validated |
| **LLM Orchestrator** | [IMPLEMENTED] | `orchestrator.py` - tool selection loop |
| **Schema Validation** | [IMPLEMENTED] | `validators.py` - all 4 schemas |
| **Input Sanitization** | [IMPLEMENTED] | `_sanitize_investigation_input()` |
| **Lifecycle Trace** | [IMPLEMENTED] | `lifecycle_trace` field in metadata |
| **Security Tests** | [IMPLEMENTED] | `test_security_attack_vectors.py` |
| **20 Scenarios** | [IMPLEMENTED] | `scenarios/case_001-020.json` |
| **Benchmark Runner** | [IMPLEMENTED] | `benchmark_runner.py` |
| **LLM Provider Adapter** | [IMPLEMENTED] | `provider.py` - OpenAI + Mock |
| **CLI Interface** | [IMPLEMENTED] | `cli/main.py` |
| **Integrations** | [PARTIAL] | `integrations.py` - all stubs return `[]` |
| **Runbooks** | [PARTIAL] | `runbooks.py` - defined but not integrated |
| **Fixed Pipeline Method** | [IMPLEMENTED] | `investigate_fixed_pipeline()` |

### B.2 Critical Code-Architecture Mismatch

**[ISSUE #1] MockProvider không mô phỏng LLM thực**

**Code Evidence** (`provider.py`, lines 187-213):
```python
def _next_tool_call(self, messages: List[Dict[str, str]]) -> List[Dict[str, Any]]:
    """Select the next read-only tool from observed evidence, not a fixed pipeline."""
    called = []
    for message in messages:
        if message.get("role") == "assistant" and message.get("tool_calls"):
            called.extend(call["function"]["name"] for call in message["tool_calls"])
    
    tool_messages = [message["content"].lower() for message in messages if message.get("role") == "tool"]
    context = " ".join(message.get("content", "").lower() for message in messages)
    network_markers = ("scan", "beacon", "exfil", "traffic", "connection", "dns", "c2")
    endpoint_markers = ("edr", "process", "workstation", "endpoint", "macro", "powershell")
    # ...
    if not called:
        return [{"id": "mock_cti_1", "name": "cti_enrichment", ...}]
```

**Problem:** MockProvider sử dụng heuristic rule-based logic thay vì mô phỏng LLM reasoning. Điều này có nghĩa:
- Benchmark không test được "dynamic evidence-driven orchestration" thực sự
- So sánh "evidence-driven vs fixed pipeline" không có ý nghĩa vì cả hai đều dùng heuristic

**Impact:** Proposal claims "LLM là orchestration/reasoning" nhưng MockProvider không test được điều này.

**[ISSUE #2] Triage quá đơn giản**

**Code Evidence** (`triage.py`):
```python
def triage_alert(indicator: str, context: Optional[str] = None) -> TriageResult:
    text = f"{indicator} {context or ''}".lower()
    benign_markers = ("known infrastructure", "expected", "allowlisted", "benign")
    suspicious_markers = ("malicious", "suspicious", "beacon", "exfil", "scan", "anomaly")
    
    if any(marker in text for marker in suspicious_markers):
        return TriageResult("SUSPICIOUS", ...)
    if any(marker in text for marker in benign_markers):
        return TriageResult("BENIGN", ...)
    return TriageResult("NEEDS_INVESTIGATION", ...)
```

**Problem:** Chỉ là keyword matching trên lowercase text. Dễ bypass:
- "beaconing" → suspicious
- "BEACON" → không match (case-sensitive vì đã lowercase)
- "Suspicious Activity Detected" → suspicious
- "Detected suspicious activity" → không match (word order)

**Impact:** Triage-first principle không đáng tin cậy với triển khai hiện tại.

**[ISSUE #3] Evidence-Traceability enforcement yếu**

**Code Evidence** (`orchestrator.py`, lines 808-829):
```python
def _verify_case_quality(self, evidence, tool_calls, hypotheses) -> List[str]:
    """QA gate enforcing evidence-grounding and traceability."""
    limitations = []
    evidence_ids = {ev.evidence_id for ev in evidence}
    
    for hypothesis in hypotheses:
        unknown = [ev_id for ev_id in hypothesis.supporting_evidence 
                  if ev_id not in evidence_ids]
        if unknown:
            limitations.append(f"Hypothesis {hypothesis.id} references unknown evidence IDs: {unknown}")
    
    return limitations  # Chỉ append limitations, không block
```

**Problem:** Nếu hypothesis reference evidence IDs không tồn tại, system chỉ append một limitation note. KHÔNG block hay reject hypothesis.

**Impact:** Proposal claim "mọi assessment phải trace về evidence IDs" chỉ được enforce một cách yếu ớt.

**[ISSUE #4] Prompt Injection Markers không đầy đủ**

**Code Evidence** (`orchestrator.py`, lines 365-373):
```python
injection_markers = (
    "ignore previous instructions",
    "system prompt",
    "assistant:",
    "execute ",
    "rm -rf",
    "mark this as benign",
    "suppress this alert",
)
```

**Comparison with OWASP LLM Top 10 2025:**
- OWASP LLM01:2025 defines many more attack patterns
- Thiếu: "[SYSTEM]", "You are now", direct privilege escalation attempts
- Thiếu context-aware attacks

**[ISSUE #5] "Fixed Pipeline" method mâu thuẫn với principles**

**Code Evidence** (`orchestrator.py`, lines 261-342):
```python
def investigate_fixed_pipeline(self, indicator, indicator_type, context):
    """Baseline: triage -> CTI -> Network -> Endpoint."""
    # Step 1: CTI Enrichment (always)
    self._execute_tool_call({"name": "cti_enrichment", ...})
    # Step 2: Network Investigation (for IP/domain)
    if indicator_type in {"ipv4", "domain"}:
        self._execute_tool_call({"name": "network_investigation", ...})
    # Step 3: Endpoint Investigation
    # ...
```

**Problem:** 
- Proposal: "Không dùng pipeline cứng CTI → Network → Endpoint"
- Nhưng code có `investigate_fixed_pipeline()` để làm "baseline comparison"
- Benchmark so sánh "evidence-driven" (heuristic-based) vs "fixed pipeline" (hard-coded)

**Impact:** Architecture có vẻ như self-defeating - define một anti-pattern để so sánh.

### B.3 Missing Implementations

**[ISSUE #6] Integrations là placeholders**

**Code Evidence** (`integrations.py`):
```python
class SecOpsIntegration(ReadOnlySOCIntegration):
    def search(self, query: IntegrationQuery) -> List[Dict[str, Any]]:
        return []  # Always empty
```

**Impact:** MVP scope ghi "No real SIEM integration" nhưng cũng không có mock implementation cho structured integration testing.

**[ISSUE #7] Runbooks defined nhưng không integrated**

**Code Evidence:** `runbooks.py` có `default_soc_runbook()` nhưng không thấy usage trong `orchestrator.py` ngoài việc serialize vào metadata.

### B.4 Positive Implementation Findings

1. ✅ **Evidence Store design tốt**: Append-only, validated, traceable
2. ✅ **Schema validation đầy đủ**: Tất cả 4 schemas được validate
3. ✅ **Security tests toàn diện**: Prompt injection, token bombing, markdown injection
4. ✅ **20 scenarios tốt**: Cover benign, malicious, ambiguous, conflicting signals
5. ✅ **Lifecycle trace concept đúng**: triage→investigate→verify→review
6. ✅ **Confidence calibration logic**: Evidence-based (code lines 696-795)

---

## C. Architecture Validation

### C.1 Alignment with Industry Standards

| Standard | Alignment | Evidence |
|----------|-----------|----------|
| **NIST SP 800-61r3** | ✅ FULL | 4-phase lifecycle, evidence collection |
| **NIST CSF 2.0** | ✅ FULL | RESPOND function mapped |
| **MITRE ATT&CK** | ⚠️ PARTIAL | Techniques used but no explicit coverage matrix |
| **STIX/TAXII** | ⚠️ MENTIONED | Concepts used, no explicit STIX pattern support |
| **CISA IR Playbook** | ✅ FULL | Workflow aligns |
| **OWASP LLM Top 10** | ⚠️ PARTIAL | LLM01 addressed, others not explicitly |
| **OWASP Agentic AI** | ⚠️ MENTIONED | Not implemented |

### C.2 Architecture Issues

**[ARCH-1] LLM Provider Adapter không complete**

**Architecture Claim:** "LLM Provider as Adapter" - switch between OpenAI/Gemini without rewriting skills

**Implementation Status:** 
- `provider.py` có OpenAIProvider và MockProvider
- OpenAIProvider implementation correct
- NHƯNG: Không có Gemini adapter
- NHƯNG: MockProvider không mô phỏng LLM thực

**Impact:** Architecture claim về "provider independence" không thể verify với current test setup.

**[ARCH-2] Evidence-driven orchestration không thể verify**

**Architecture Claim:** "Dynamic Tool Selection" - LLM evaluates evidence and decides next tool

**Problem:** Với MockProvider dùng heuristic, không thể verify:
- LLM có thực sự evaluate evidence?
- LLM có dynamic skip tools khi đủ evidence?
- LLM có đúng context window management?

**[ARCH-3] Skill boundary enforcement có vẻ đúng**

**Architecture Claim:** "Skills are read-only, LLM cannot bypass skill boundaries"

**Code Evidence:**
```python
# agent/orchestrator.py - chỉ 3 tools được định nghĩa
def get_tool_schemas():
    return [
        {"name": "cti_enrichment", ...},
        {"name": "network_investigation", ...},
        {"name": "endpoint_investigation", ...}
    ]
```

**Validation:** ✅ CORRECT - KHÔNG có tools cho containment/blocking trong codebase.

---

## D. Research Findings Summary

(Từ `docs/research_findings.md` - đã verified với industry sources)

### D.1 Problem Validation - FULLY SUPPORTED

| Industry Data | Source | Project Alignment |
|--------------|--------|------------------|
| 90% SOCs overwhelmed | Osterman Research | ✅ Triage-first justified |
| 4,400+ alerts/day | Vectra | ✅ Alert fatigue real |
| 43% time on false positives | Simbian AI | ✅ Advisory-only model justified |
| Agentic AI 15% decisions by 2028 | Gartner | ✅ Market trend aligned |

### D.2 Research Validation - ALIGNED

| Research Finding | Source | Project Alignment |
|-----------------|--------|-------------------|
| LLMs exhibit failure modes autonomously | USENIX SOUPS 2025 | ✅ Advisory-only model |
| Evidence grounding reduces hallucination | USENIX SOUPS 2025 | ✅ Evidence store |
| Over-trust leads to automation bias | ACM TOIT 2026 | ✅ Confidence calibration |
| Trust calibration critical | Stellar Cyber | ✅ Advisory recommendation |

### D.3 Research Gaps Identified

1. **No explicit STIX 2.1 pattern mapping** - Project sử dụng JSON nhưng không reference STIX patterns
2. **MITRE ATT&CK coverage matrix missing** - Techniques used nhưng no formal mapping
3. **Evaluation metrics chưa đầy đủ** - Thiếu false negative rate, cost-benefit analysis

---

## E. Critical Gaps and Contradictions

### E.1 High Severity Issues

| ID | Issue | Evidence | Impact |
|----|-------|----------|--------|
| **GAP-1** | MockProvider không test được dynamic orchestration | `provider.py` _next_tool_call() | Không verify được core claim |
| **GAP-2** | Benchmark comparison không valid | heuristic vs hard-coded | Không prove evidence-driven benefit |
| **GAP-3** | Triage bypass đơn giản | `triage.py` keyword matching | Security boundary yếu |

### E.2 Medium Severity Issues

| ID | Issue | Evidence | Impact |
|----|-------|----------|--------|
| **GAP-4** | Evidence traceability enforcement yếu | `_verify_case_quality()` only adds notes | Proposal claim not enforced |
| **GAP-5** | Prompt injection markers incomplete | 6 markers vs OWASP 2025 | Incomplete security coverage |
| **GAP-6** | Fixed pipeline mâu thuẫn với principles | `investigate_fixed_pipeline()` | Architecture self-defeating |
| **GAP-7** | Không có real LLM integration test | Chỉ có MockProvider | Không verify production behavior |

### E.3 Low Severity Issues

| ID | Issue | Evidence | Impact |
|----|-------|----------|--------|
| **GAP-8** | "Skill contract" không phải industry term | Documentation only | Terminology confusion |
| **GAP-9** | Integrations là placeholders | `integrations.py` returns `[]` | Cannot test integration pattern |
| **GAP-10** | Runbooks defined nhưng not integrated | `runbooks.py` | Dead code |

### E.4 Terminology Issues

| Term | Current Usage | Industry Standard | Status |
|------|-------------|------------------|--------|
| skill contract | Custom term | "API contract" / "interface spec" | ⚠️ Non-standard |
| evidence | Correct | Correct | ✅ |
| pivot | Correct | Correct (threat intel) | ✅ |
| enrichment | Correct | Correct | ✅ |
| triage | Correct | Correct | ✅ |
| orchestration | Correct | Correct | ✅ |

---

## F. Recommended Changes (Ranked by Necessity)

### F.1 CRITICAL - Must Fix Before MVP

**[CHANGE-1] Implement realistic MockProvider hoặc remove benchmark claim**

**Rationale:** Current MockProvider không test được dynamic evidence-driven orchestration. Benchmark comparison vô nghĩa.

**Options:**
1. **Option A:** Rewrite MockProvider để mô phỏng LLM behavior thực (randomized tool selection based on evidence patterns)
2. **Option B:** Remove `investigate_fixed_pipeline()` và benchmark với baseline là "no AI" (manual workflow)
3. **Option C:** Document rõ ràng rằng benchmark chỉ test skill integration, không phải LLM reasoning

**Recommendation:** Option C - Document đây là "integration test" không phải "LLM evaluation". Change benchmark name từ "evidence-driven vs fixed pipeline" sang "tool integration verification".

**[CHANGE-2] Strengthen triage implementation**

**Rationale:** Current keyword matching quá yếu cho production use.

**Recommendation:** 
- Add case-insensitive matching
- Add phrase-based detection (không chỉ single word)
- Consider simple ML model hoặc rule-based engine với negation handling
- Document triage limitations rõ ràng

**[CHANGE-3] Enforce evidence traceability as hard requirement**

**Rationale:** Current chỉ là QA note, không enforce.

**Recommendation:** 
- Nếu hypothesis reference non-existent evidence ID → REJECT hypothesis
- Return error/limitation thay vì accept với note
- Add test case cho this scenario

### F.2 HIGH - Should Fix

**[CHANGE-4] Expand prompt injection markers**

**Recommendation:** Add OWASP LLM01:2025 patterns:
- `[SYSTEM]`, `[INST]`, `[AI]`
- `you are now`, `pretend you are`
- `end of prompt`
- Context-specific patterns

**[CHANGE-5] Remove or justify fixed pipeline method**

**Rationale:** Mâu thuẫn với "no hard pipeline" principle.

**Options:**
1. Remove `investigate_fixed_pipeline()` completely
2. Rename nó thành something clearly artificial (e.g., `investigate_exhaustive()`)
3. Document nó là "pathological worst-case" không phải "baseline"

**[CHANGE-6] Add MITRE ATT&CK coverage documentation**

**Recommendation:** Add explicit matrix showing:
- Which techniques each skill can detect
- Confidence levels per technique
- Limitations per technique

### F.3 MEDIUM - Nice to Have

**[CHANGE-7] Implement real LLM integration tests**

**Recommendation:** Add integration test với actual OpenAI API (scaled-down, mock data) để verify real behavior.

**[CHANGE-8] Clean up dead code**

**Recommendation:** 
- `integrations.py` → Add basic mock implementations hoặc mark as TODO
- `runbooks.py` → Either integrate properly hoặc move to separate module

**[CHANGE-9] Add explicit STIX pattern support**

**Recommendation:** If CTI skill sẽ be used với real feeds, add STIX bundle parsing.

### F.4 LOW - Documentation Only

**[CHANGE-10] Standardize terminology**

**Recommendation:** 
- Change "skill contract" → "skill interface specification"
- Add glossary section
- Document why custom term was chosen

---

## G. Proposal Changes Required

### G.1 Claims to Remove or Rephrase

| Current Claim | Problem | Suggested Change |
|--------------|--------|-----------------|
| "Dynamic evidence-driven orchestration" | MockProvider không test được | "Dynamic tool selection (requires real LLM for full verification)" |
| "LLM as orchestration layer" | Benchmark không prove điều này | "LLM-based orchestration (verified via integration tests)" |
| "No hard pipeline" | Có `investigate_fixed_pipeline()` | Remove or rename method |
| "Benchmark compares evidence-driven vs fixed" | Comparison không valid | "Integration tests verify skill coordination" |

### G.2 Claims to Strengthen

| Current Claim | Evidence Needed | Status |
|--------------|----------------|--------|
| "Evidence traceability" | Code enforcement | ⚠️ Add hard rejection |
| "Security boundaries" | Already solid | ✅ Keep as-is |
| "Triage-first" | Triage implementation | ⚠️ Strengthen |
| "Insufficient evidence is valid" | Already implemented | ✅ Keep as-is |

### G.3 New Claims to Add

| New Claim | Evidence | Priority |
|-----------|----------|----------|
| "Integration-tested skill coordination" | Benchmark results | HIGH |
| "OWASP-aligned security controls" | Expanded markers list | MEDIUM |
| "MITRE ATT&CK technique coverage" | Coverage matrix | MEDIUM |

---

## H. Final Verdict

### H.1 What Should REMAIN UNCHANGED

1. ✅ **Core architecture** - Evidence store, skill separation, read-only enforcement
2. ✅ **3 skills design** - CTI/Network/Endpoint structure is sound
3. ✅ **NIST alignment** - Workflow maps correctly to standards
4. ✅ **Security controls foundation** - Schema validation, untrusted data handling
5. ✅ **Scenario-based evaluation** - 20 cases covering edge cases
6. ✅ **Advisory-only model** - Aligns with CISO concerns and research
7. ✅ **Evidence-grounding concept** - Core innovation worth keeping
8. ✅ **Lifecycle trace concept** - triage→investigate→verify→review

### H.2 What Should Be REDESIGNED

1. ⚠️ **MockProvider** - Không test được dynamic orchestration claim
2. ⚠️ **Benchmark methodology** - So sánh hiện tại không valid
3. ⚠️ **Triage implementation** - Quá simple cho production credibility
4. ⚠️ **Evidence traceability enforcement** - Chỉ là note, không block
5. ⚠️ **Fixed pipeline method** - Mâu thuẫn với principles

### H.3 Summary Assessment

| Aspect | Status | Notes |
|--------|--------|-------|
| **Problem Validation** | ✅ VALID | Alert fatigue well-documented |
| **Architecture** | ⚠️ PARTIAL | Core correct, MockProvider issue |
| **Implementation** | ⚠️ PARTIAL | Skills work, orchestration not testable |
| **Evaluation** | ⚠️ FLAWED | Benchmark doesn't prove claims |
| **Security** | ⚠️ PARTIAL | Foundation good, markers incomplete |
| **Documentation** | ⚠️ PARTIAL | Good sources, some claims unsupported |

### H.4 Overall Verdict

**The project has a SOLID FOUNDATION aligned with industry standards and research.** The core principles (evidence-grounding, advisory-only, read-only) are correct and well-supported by research.

**HOWEVER**, the current implementation has critical gaps that prevent verifying the core claims:
1. MockProvider cannot test dynamic orchestration
2. Benchmark comparison is not valid
3. Triage is too simple
4. Evidence traceability is not enforced

**Recommendation: [REDESIGN BEFORE DEMONSTRATION]**

The project should either:
- **Option A:** Fix the 4 critical issues above before MVP demonstration
- **Option B:** Reposition the project as "integration testing framework" rather than "AI reasoning demonstration" if time/resources are limited

The current state would not survive rigorous technical review because the key differentiator (dynamic evidence-driven orchestration) cannot be verified with the current test setup.

---

## Appendix: Evidence Index

### Code Files Reviewed
- `agent/orchestrator.py` - 863 lines
- `agent/provider.py` - 276 lines
- `agent/triage.py` - 32 lines
- `agent/evidence.py` - 204 lines
- `skills/cti_skill.py` - 238 lines
- `skills/network_skill.py` - 425 lines
- `skills/endpoint_skill.py` - 304 lines
- `skills/base.py` - 180 lines
- `skills/validators.py` - 120 lines
- `cli/main.py` - 385 lines
- `tests/test_security_attack_vectors.py` - 63 lines
- `tests/benchmark_runner.py` - 87 lines

### Documentation Files Reviewed
- `docs/architecture.md`
- `docs/evaluation.md`
- `docs/problem.md`
- `docs/literature_review.md`
- `docs/threat_model.md`
- `docs/ref.bib`

### Scenarios Reviewed
- `case_001.json` - Benign internal DNS
- `case_005.json` - Malicious C2
- `case_010.json` - Lateral movement
- `case_019.json` - Insufficient data
- `case_020.json` - Conflicting signals

---

*Review completed 2026-09-16*
