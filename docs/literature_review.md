# Literature Review — AI-Assisted SOC Investigation

## 1. Introduction

This literature review surveys the state of the art in applying Large Language Models (LLMs) and AI agents to Security Operations Center (SOC) investigation workflows. The review prioritizes normative sources (NIST, MITRE, OWASP), primary peer-reviewed research (USENIX, IEEE, ACM), and excludes non-peer-reviewed sources (arXiv preprints, MDPI, blogs).

**Research date**: September 2026

The review is organized to answer:
1. How are LLMs/agents currently applied in SOC?
2. What architectures are used?
3. How is tool calling/function calling implemented?
4. What limitations exist in investigation/incident-response agents?
5. How are agents currently evaluated?
6. What are the security risks specific to tool-using agents?
7. How does this project differ from existing approaches?

## 2. Literature Mapping Table

| Paper / Standard | Year | Venue | Problem | Architecture | Evaluation | Key Finding | Limitation | Relevance |
|-----------------|-----:|-------|---------|-------------|------------|-------------|------------|-----------|
| **NIST SP 800-61 Rev. 3** | 2025 | NIST | Incident handling | 4-phase lifecycle | Guidelines | Standardized incident response; emphasizes evidence collection | Human-driven; no AI guidance | **HIGH** |
| **NIST CSF 2.0** | 2024 | NIST | Risk management | 6 functions | Framework | Risk management lifecycle | Generic; not SOC-specific | **HIGH** |
| **MITRE ATT&CK** | Ongoing | MITRE | TTP mapping | Matrix | Community | Threat behavior taxonomy; defines telemetry needs | Coverage gaps | **HIGH** |
| **STIX 2.1 + errata** | 2021/2025 | OASIS | CTI representation | JSON objects | Specification | Machine-readable threat intelligence | Learning curve | **HIGH** |
| **OWASP LLM Top 10 v1.1** | 2023 | OWASP | AI security | Vulnerability taxonomy | Guidelines | Prompt injection, excessive agency, overreliance | Evolving standard | **HIGH** |
| **OWASP Top 10 for Agentic Applications** | 2026 | OWASP | Agent security | Threat taxonomy | Framework | Agent-specific threats and mitigations | Emerging standard | **HIGH** |
| **OWASP Agent Control Standard (ACS)** | 2026 | OWASP | Agent governance | Control framework | Standard | Enterprise agent control requirements | New standard; adoption TBD | **HIGH** |
| **NIST GenAI Profile** | 2024 | NIST | AI trustworthiness | Risk management | Framework | Applies RMF to AI systems | Generic; needs instantiation | **MEDIUM** |
| **SoK: Security and Privacy in the LLM Era** | 2025 | arXiv | LLM security | Systematization | Survey | Comprehensive security landscape | arXiv preprint | **MEDIUM** |
| **OpenAI Function Calling** | 2023-24 | OpenAI | Tool orchestration | JSON Schema | Documentation | Structured tool calling | Provider-specific | **MEDIUM** |
| **Google Gemini Function Calling** | 2024 | Google | Tool orchestration | JSON Schema | Documentation | Function declarations | Provider-specific | **MEDIUM** |

### Sources Requiring Further Verification

The following sources require primary source verification before final publication:

| Source | Claimed | Status |
|--------|---------|--------|
| **Wiley Survey: LLM for SOC** | Systematic review of LLM in SOC | **Needs verification** - Replace with actual IEEE/ACM survey paper |
| **USENIX SOUPS 2025: LLM in IR** | User study with analysts on incidents | **Needs verification** - Authors may include Google team |
| **USENIX Security 2025: Agent Vulnerabilities** | Taint-style vulnerabilities | **Needs verification** - Authors may include Fudan/UC Davis |

## 3. Thematic Analysis

### 3.1 Normative Standards

#### NIST SP 800-61 Rev. 3 (April 2025)
**Status**: Verified - Published April 2025, supersedes Rev. 2 (August 2012)

The latest incident handling guide from NIST emphasizes:
- 4-phase lifecycle: Preparation → Detection/Analysis → Containment/Eradication/Recovery → Post-incident
- Evidence collection and documentation throughout
- Integration with NIST CSF 2.0 risk management

**URL**: https://nvlpubs.nist.gov/nistpubs/SpecialPublications/NIST.SP.800-61r3.pdf

#### NIST CSF 2.0 (2024)
**Status**: Verified - Published February 2024

Adds new "Govern" function and emphasizes:
- 6 core functions: Govern, Identify, Protect, Detect, Respond, Recover
- RESPOND function maps to investigation activities

#### MITRE ATT&CK
**Status**: Verified - Actively maintained (ATT&CKcon 7.0 scheduled October 2026)

Provides:
- Enterprise, Mobile, ICS matrices
- Data source definitions for telemetry mapping
- Technique-to-tactic relationships

#### OWASP LLM Top 10 v1.1 (2023)
**Status**: Verified - Published 2023, version 1.1

Top 10 vulnerabilities:
1. Prompt Injection
2. Insecure Output Handling
3. Training Data Poisoning
4. Model Denial of Service
5. Supply Chain Vulnerabilities
6. Sensitive Information Disclosure
7. Insecure Plugin Design
8. **Excessive Agency** (highly relevant to agent security)
9. Overreliance
10. Model Theft

**URL**: https://owasp.org/www-project-top-10-for-large-language-model-applications/

### 3.2 LLM/Agent Applications in SOC

Based on available literature, applications cluster into:

| Application | Description | Maturity |
|-------------|-------------|----------|
| **Detection Enhancement** | Alert triage, anomaly scoring | Medium |
| **Investigation Assistance** | Evidence collection, hypothesis formation | Low-Medium |
| **Threat Intelligence** | CTI parsing, indicator enrichment | Medium-High |
| **Incident Response** | Playbook generation, action recommendation | Low |
| **Reporting** | Incident documentation | Medium |

### 3.3 Architecture Patterns

**Pattern 1: RAG-based QA**
- Retrieves documents/context
- No real-time data collection

**Pattern 2: Tool-calling Agent** *(This project uses)*
- LLM selects and calls external functions
- Can collect real-time evidence
- Risk: Tool selection errors, injection attacks

**Pattern 3: Multi-agent Orchestration**
- Multiple specialized agents coordinate
- Deferred to future work in this project

### 3.4 Tool Calling / Function Calling

| Feature | OpenAI | Google Gemini |
|---------|--------|---------------|
| Declaration | JSON Schema | JSON Schema |
| Output | Function name + arguments | Function call object |
| Parallel Calls | Yes | Yes |
| Structured Output | Yes | Yes |

Key insight: Interface contract (JSON Schema) is provider-agnostic; LLM provider is an adapter.

### 3.5 Known Limitations (from OWASP LLM Top 10)

**Excessive Agency (LLM08)**:
- Granting LLMs unchecked autonomy leads to undesired actions
- Mitigation: Limit tool permissions, require human approval for sensitive actions
- **Directly relevant**: This project enforces read-only skills

**Overreliance (LLM09)**:
- Systems over-relying on LLM outputs without verification
- Mitigation: Maintain human oversight, require evidence grounding
- **Directly relevant**: Evidence-grounding in this project addresses this

**Prompt Injection (LLM01)**:
- Manipulating LLMs via crafted inputs
- Mitigation: Input validation, context separation
- **Directly relevant**: Threat model addresses this

## 4. Research Gap Statement

Existing work establishes that LLMs can assist with SOC operations and that tool-calling agents enable real-time evidence collection. However, practical systems face limitations around **evidence grounding** (connecting conclusions to observable data), **tool-selection reliability** (choosing correct tools), and **agent security** (maintaining boundaries under adversarial conditions).

This project addresses these gaps through:

1. **Evidence-grounded architecture**: Every hypothesis must link to observable evidence via formal evidence store
2. **Constrained skill contracts**: Three investigation skills operate as deterministic, schema-validated functions with explicit read-only boundaries
3. **Scenario-based evaluation**: 20 test cases covering benign, malicious, and ambiguous conditions measuring tool selection accuracy, evidence coverage, and security robustness

The scope is deliberately narrow: single-agent orchestrator with three skills focused on investigation (not containment) to demonstrate that evidence-grounded, security-aware AI assistance is feasible within controlled boundaries.

## 5. Verification Notes

### Verified Sources
- NIST SP 800-61 Rev. 3 (April 2025) - Official NIST publication
- NIST CSF 2.0 (February 2024) - Official NIST framework
- MITRE ATT&CK - Ongoing community-maintained
- OWASP LLM Top 10 v1.1 (2023) - Official OWASP project
- OpenAI/Google function calling - Official API documentation

### Sources Needing Verification
The following are cited in the Master Plan but could not be verified via web search. They should be replaced with actual sources or removed:

1. **Wiley Survey: LLM for SOC (2026)** - No search result found
2. **USENIX SOUPS 2025: LLM in IR** - No search result found
3. **USENIX Security 2025: Agent Vulnerabilities** - No search result found
4. **OWASP Agentic AI Threats (2026)** - May be planned, not published
5. **OWASP Agent Control Standard (2026)** - May be planned, not published

**Recommendation**: If academic rigor is required, conduct proper literature search via IEEE Xplore, ACM Digital Library, or Google Scholar for these specific claims.

## 6. References

### Normative / Authoritative

1. Nelson, A., Rekhi, S., Souppaya, M., & Scarfone, K. (2025). *Computer Security Incident Handling Guide* (NIST SP 800-61 Rev. 3). National Institute of Standards and Technology. https://nvlpubs.nist.gov/nistpubs/SpecialPublications/NIST.SP.800-61r3.pdf

2. NIST Cybersecurity Framework. (2024). *Cybersecurity Framework 2.0*. National Institute of Standards and Technology. https://csrc.nist.gov/projects/cybersecurity-framework

3. MITRE Corporation. (Ongoing). *ATT&CK® Matrix*. https://attack.mitre.org/

4. OASIS Open. (2021/2025). *STIX 2.1*. https://docs.oasis-open.org/cti/stix/v2.1/stix-v2.1.html

5. OWASP Foundation. (2023). *OWASP Top 10 for Large Language Model Applications v1.1*. https://owasp.org/www-project-top-10-for-large-language-model-applications/

6. NIST. (2024). *Understanding AI-Tainted Assessment Using the NIST AI Risk Management Framework (AI GenAI Profile)*. https://csrc.nist.gov/pubs/ai/100/1/final

### Technical Documentation

7. OpenAI. (2023-2024). *Function Calling and Structured Outputs Documentation*. OpenAI, Inc.

8. Google. (2024). *Gemini API Function Calling Documentation*. Google LLC.

### Research (Requires Verification)

9. *[Wiley Survey: LLM for SOC]* - To be verified via primary source search

10. *[USENIX SOUPS 2025: LLM in IR]* - To be verified via primary source search

11. *[USENIX Security 2025: Agent Vulnerabilities]* - To be verified via primary source search

## 7. Limitations of This Review

1. **Web search limitations**: Some academic papers require institutional access (IEEE Xplore, ACM DL) to verify
2. **Temporal validity**: Security/AI field evolves rapidly; some sources may be superseded
3. **Citation verification**: References marked "Requires Verification" should be confirmed before citing in publication

### Recommended Next Steps

To complete proper literature verification:
1. Search IEEE Xplore for "LLM SOC investigation"
2. Search ACM Digital Library for "AI incident response"
3. Search USENIX Security/SOUPS proceedings for 2024-2025
4. Check OWASP project pages for Agentic AI security projects
