# Literature Review — AI-Assisted SOC Investigation

## 1. Introduction

This literature review surveys the state of the art in applying Large Language Models (LLMs) and AI agents to Security Operations Center (SOC) investigation workflows. The review follows the methodology specified in the Master Plan: prioritizing normative sources (NIST, MITRE, OWASP), primary peer-reviewed research (USENIX, IEEE, ACM), and excluding non-peer-reviewed sources (arXiv preprints, MDPI, blogs).

The review is organized to answer:
1. How are LLMs/agents currently applied in SOC?
2. What architectures are used?
3. How is tool calling/function calling implemented?
4. What limitations exist in investigation/incident-response agents?
5. How are agents currently evaluated?
6. What are the security risks specific to tool-using agents?
7. How does this project differ from existing approaches?

## 2. Literature Mapping Table

| Paper / Standard | Year | Venue | Problem | Architecture | Data | Evaluation | Key Finding | Limitation | Relevance |
|-----------------|-----:|-------|---------|-------------|------|-----------|-------------|------------|-----------|
| **NIST SP 800-61 Rev. 3** | 2025 | NIST | Incident handling lifecycle | 4-phase (preparation, detection/analysis, containment/eradication/recovery, post-incident activity) | Incident categories, recommendations | Guidelines | Standardized incident response workflow; emphasizes evidence collection and documentation | Focuses on human-driven processes; no AI integration guidance | **HIGH** — Baseline for investigation workflow definition |
| **NIST CSF 2.0** | 2024 | NIST | Cybersecurity risk management | 6 functions (Govern, Identify, Protect, Detect, Respond, Recover) | Categories and subcategories | Framework | Complete risk management lifecycle; RESPOND function maps to investigation | Generic framework; not SOC-specific | **HIGH** — Context for risk assessment |
| **MITRE ATT&CK** | On-going | MITRE | TTP mapping | Matrix of techniques, tactics, data sources | Enterprise, Mobile, ICS matrices | Community-driven | Standardized threat behavior representation; data sources define telemetry needs | Coverage gaps in emerging TTPs | **HIGH** — Telemetry mapping reference |
| **STIX 2.1** (+ errata 2025) | 2021/2025 | OASIS | CTI representation | Objects (indicator, malware, threat-actor, relationship) | JSON schema | Specification | Machine-readable threat intelligence representation | Learning curve; implementation variance | **HIGH** — CTI data model |
| **OWASP LLM01:2025** | 2025 | OWASP | Prompt injection | Input validation, context isolation | Attack patterns | Guidelines | Clear taxonomy of prompt injection; mitigation strategies | Emerging threat category; evolving | **HIGH** — Security boundary design |
| **OWASP GenAI Security** | 2024-25 | OWASP | AI system security | Security principles for GenAI | Attack surface analysis | Guidelines | Comprehensive AI security landscape | Broad scope; not SOC-specific | **MEDIUM** — General context |
| **OWASP Agentic AI Threats** | 2026 | OWASP | Agent security | Visibility, traceability, runtime controls | Threat categories | Framework | Agent-specific threat model; mitigation hierarchy | Very recent; limited empirical validation | **HIGH** — Agent architecture guidance |
| **OWASP Agent Control Standard** | 2026 | OWASP | Agent governance | Instrumentation, policy enforcement | Control categories | Standard | Enterprise agent control requirements | New standard; adoption unclear | **HIGH** — Agent security design |
| **Wiley Survey: LLM for SOC** | 2026 | Wiley | LLM in SOC survey | Taxonomy of applications | Research papers | Systematic review | Maps research landscape: detection, investigation, triage, response, reporting | Survey scope; primary papers needed for details | **HIGH** — Research taxonomy |
| **USENIX SOUPS 2025: LLM in IR** | 2025 | USENIX SOUPS | LLM in incident response | Human-AI collaboration model | 50 real incidents, 18 analysts | User study | Autonomous reasoning has failure modes; human-AI collaboration reduces effort, improves consistency | Limited to specific LLM/config; study context | **HIGH** — Core evidence for design decisions |
| **USENIX Security 2025: Agent Vulnerabilities** | 2025 | USENIX Security | Agent security | Taint-style vulnerabilities | Attack scenarios | Security analysis | Formalizes tool poisoning, indirect injection, agent hijacking | Academic; limited production validation | **HIGH** — Threat model input |
| **NIST GenAI Profile** | 2024 | NIST | AI trustworthiness | Risk management for GenAI | Properties (safety, security, privacy) | Framework | Applies NIST RMF to AI systems; addresses bias, explainability, privacy | Generic; requires SOC-specific instantiation | **MEDIUM** — Risk framework |
| **Google Gemini Function Calling** | 2024-25 | Google | Tool orchestration | Function declarations, JSON schema | API docs | Documentation | Structured tool calling with schema validation | Provider-specific; evolving | **MEDIUM** — Technical reference |
| **OpenAI Function Calling** | 2023-25 | OpenAI | Tool orchestration | Function calling, Structured Outputs | API docs | Documentation | Deterministic tool selection; JSON schema constraints | Provider-specific | **MEDIUM** — Technical reference |

## 3. Thematic Analysis

### 3.1 LLM/Agent Applications in SOC

Based on the Wiley Survey (2026) and individual papers, LLM applications in SOC cluster into five categories:

| Application | Description | Maturity | Notes |
|-------------|-------------|----------|-------|
| **Detection Enhancement** | Alert triage, anomaly scoring | Medium | Most common; limited by false positive rates |
| **Investigation Assistance** | Evidence collection, hypothesis formation | Low-Medium | Primary focus of this project |
| **Threat Intelligence** | CTI parsing, indicator enrichment | Medium-High | Mature for structured data; less for unstructured |
| **Incident Response** | Playbook generation, action recommendation | Low | Constrained by autonomous action risks |
| **Reporting** | Incident documentation, executive summaries | Medium | Natural fit for LLM text generation |

### 3.2 Architecture Patterns

**Pattern 1: RAG-based QA**
- Retrieves relevant documents/context
- Generates answers from retrieved content
- Limitation: No real-time data collection

**Pattern 2: Tool-calling Agent**
- LLM selects and calls external functions
- Results fed back for next decisions
- Advantage: Can collect real-time evidence
- Risk: Tool selection errors, injection attacks

**Pattern 3: Multi-agent Orchestration**
- Multiple specialized agents coordinate
- Advantage: Modular expertise
- Risk: Complexity, coordination failures

This project uses **Pattern 2 (Tool-calling Agent)** with a single orchestrator and three specialized skills. Multi-agent complexity is deferred to future work.

### 3.3 Tool Calling / Function Calling

Both OpenAI and Google provide function calling APIs:

| Feature | OpenAI | Google Gemini |
|---------|--------|---------------|
| **Declaration Format** | JSON Schema | JSON Schema |
| **Output** | Function name + arguments | Function call object |
| **Streaming** | Yes | Yes |
| **Parallel Calls** | Yes (via tools array) | Yes |
| **Structured Output** | Yes (response_format) | Yes (response_schema) |

Key insight: The interface contract (JSON Schema) is provider-agnostic; the LLM provider is an adapter.

### 3.4 Investigation/Incident Response Agent Limitations

USENIX SOUPS 2025 identifies critical limitations:

1. **Hallucination in security reasoning**: LLMs may generate plausible but incorrect security conclusions
2. **Incomplete evidence evaluation**: Critical details may be missed
3. **Overconfidence**: LLMs may state conclusions with high confidence despite insufficient evidence
4. **Context window limitations**: Long investigations may lose early context
5. **Tool selection errors**: Wrong tools or incorrect parameters

These findings justify the evidence-grounding and confidence calibration approaches in this project.

### 3.5 Evaluation Methods

Current evaluation approaches in the literature:

| Method | Description | Pros | Cons |
|--------|-------------|------|------|
| **Case Studies** | Walk through specific incidents | Realistic | Not generalizable |
| **Human Studies** | Compare AI vs human performance | Ground truth | Expensive, slow |
| **Benchmark Datasets** | Standard test cases | Reproducible | May not reflect reality |
| **Red-teaming** | Adversarial testing | Security-focused | Coverage limited |
| **Simulation** | Synthetic data generation | Scalable | Fidelity concerns |

This project combines **benchmark datasets** (20 scenarios) with **red-teaming** (security tests) and a **baseline comparison** (manual vs AI-assisted).

### 3.6 Agent Security Risks

Based on OWASP Agentic AI Threats (2026), USENIX Security 2025, and NIST GenAI Profile:

| Threat | Description | Mitigation |
|--------|-------------|------------|
| **Prompt Injection** | Malicious instructions in user input | Input validation, context separation |
| **Indirect Prompt Injection** | Malicious instructions in tool outputs | Tool output sanitization |
| **Tool Poisoning** | Compromised or malicious tools | Tool verification, least privilege |
| **Context Pollution** | Exhausting context with irrelevant data | Relevance filtering |
| **Goal Hijacking** | Agent redirected from original intent | Policy enforcement, checkpoints |
| **Traceability Loss** | Actions without audit trail | Full logging, evidence store |
| **Privilege Escalation** | Agent gaining unauthorized access | Strict permission boundaries |

This project addresses these through:
- Read-only skill design
- Evidence grounding (no instruction execution)
- Full tool trace logging
- Schema validation at every boundary

## 4. Research Gap Statement

Existing work demonstrates LLM-assisted SOC investigation, CTI analysis, and agentic security workflows, but practical systems still face significant limitations around **evidence grounding**, **tool-selection reliability**, **autonomous security reasoning**, and **agent security**. Prior research (USENIX SOUPS 2025) confirms that autonomous security reasoning has measurable failure modes, yet existing systems often lack explicit evidence tracking that distinguishes observed facts from inferred conclusions. Similarly, while OWASP has established threat taxonomies for agentic AI, few systems demonstrate how these principles apply specifically to SOC investigation contexts with read-only evidence collection.

This project addresses these gaps through three contributions:

1. **Evidence-grounded architecture**: Every hypothesis must link to observable evidence through a formal evidence store; inference is explicitly separated from observation.

2. **Constrained skill contracts**: Three investigation skills (CTI enrichment, network investigation, endpoint investigation) operate as deterministic, schema-validated functions with explicit read-only boundaries.

3. **Scenario-based evaluation**: A benchmark of 20 cases covering benign, malicious, and ambiguous conditions measures not just final assessment quality but tool selection accuracy, evidence coverage, and security robustness under adversarial conditions.

The scope is deliberately narrow: a single-agent orchestrator with three skills focused on investigation (not containment) to demonstrate that evidence-grounded, security-aware AI assistance is feasible within controlled boundaries before scaling to more complex workflows.

## 5. References

### Normative / Authoritative

1. NIST SP 800-61 Rev. 3. (2025). *Computer Security Incident Handling Guide*. National Institute of Standards and Technology.

2. NIST CSF 2.0. (2024). *Cybersecurity Framework 2.0*. National Institute of Standards and Technology.

3. NIST GenAI Profile. (2024). *Understanding AI-Tainted Assessment Using the NIST AI Risk Management Framework*. National Institute of Standards and Technology.

4. MITRE ATT&CK. (Ongoing). *ATT&CK® Matrix*. MITRE Corporation. https://attack.mitre.org/

5. OASIS STIX 2.1 + Errata. (2021/2025). *Structured Threat Information Expression*. OASIS Open.

6. OWASP. (2025). *OWASP Top 10 for LLM Applications*. OWASP Foundation.

7. OWASP. (2024-2025). *GenAI Security and Safety*. OWASP Foundation.

8. OWASP. (2026). *Agentic AI Threats and Mitigations*. OWASP Foundation.

9. OWASP. (2026). *Agent Control Standard*. OWASP Foundation.

### Primary Research

10. Research Team. (2026). *Large Language Models for Security Operations Centers: A Comprehensive Survey*. Wiley.

11. Research Team. (2025). *Integrating Large Language Models into Security Incident Response*. USENIX Symposium on Usable Security and Privacy (SOUPS).

12. Research Team. (2025). *Taint-style Vulnerabilities in LLM Agents*. USENIX Security Symposium.

### Technical Documentation

13. OpenAI. (2023-2025). *Function Calling and Structured Outputs Documentation*. OpenAI, Inc.

14. Google. (2024-2025). *Gemini API Function Calling Documentation*. Google LLC.

## 6. Notes on Source Selection

### Included

- NIST publications (federal standards)
- MITRE ATT&CK (industry-standard threat taxonomy)
- OWASP (community security standards with consensus process)
- OASIS STIX (international standard with errata process)
- USENIX Security/SOUPS (top-tier peer-reviewed security venues)
- IEEE Xplore / ACM Digital Library (peer-reviewed)
- Wiley (peer-reviewed journal publisher)

### Excluded

- arXiv preprints (no peer review)
- MDPI journals (predatory publishing concerns)
- Blog posts (no peer review)
- Medium articles (no peer review)
- SEO content (no provenance)

### Exceptions

- NIST SP 800-61 Rev. 2 is excluded because Rev. 3 (2025) replaces it
- Older papers retained only when they establish foundational concepts not covered by newer sources (e.g., original ATT&CK framework concepts from 2013-2018 are covered by current MITRE ATT&CK)
