# Problem Statement — AI-Assisted SOC Investigation System

## 1. Context

Security Operations Centers (SOC) face a fundamental challenge: security analysts must collect and correlate information from multiple heterogeneous sources—including Cyber Threat Intelligence (CTI), network telemetry, and endpoint telemetry—to build coherent incident hypotheses. This process is time-consuming, requires expertise across multiple domains, and is prone to inconsistencies when performed manually.

The 2025 revision of NIST SP 800-61 (Computer Security Incident Handling Guide) emphasizes improving the efficiency and effectiveness of incident detection, response, and recovery across the entire risk management lifecycle. This positions investigation automation as an operational problem, not merely a text-generation problem.

## 2. The Problem

Current SOC investigation workflows suffer from:

1. **Fragmented data sources**: CTI, network logs, endpoint data reside in separate systems requiring manual correlation
2. **Expertise requirements**: Effective investigation requires deep knowledge of threat intelligence, network protocols, and endpoint forensics
3. **Inconsistent analysis**: Manual investigation leads to variability in evidence collection and hypothesis formation
4. **Time constraints**: Thorough investigation of every alert is often impractical under time pressure
5. **Knowledge gaps**: Individual analysts may lack familiarity with emerging TTPs or specific threat actors

## 3. Emerging Opportunity

Modern LLM/Agent systems offer new capabilities:

- **Multi-step tool calling**: Agents can invoke external functions/tools to gather information
- **Structured outputs**: Responses can be constrained to defined JSON schemas
- **Sequential and parallel execution**: Complex workflows can be orchestrated automatically
- **Contextual reasoning**: Agents can interpret and correlate information across sources

OpenAI and Google Gemini provide function calling APIs with structured outputs, enabling reliable tool orchestration with schema-validated parameters.

## 4. Critical Caveats

Research from USENIX SOUPS 2025 ("Integrating Large Language Models into Security Incident Response") demonstrates a crucial insight: **autonomous security reasoning has significant failure modes**. A study with 18 security analysts on 50 real incidents found that:

- LLMs may miss critical details or provide incorrect information when operating autonomously
- Human-AI collaboration reduces analyst effort and improves report consistency
- Full autonomy without evidence grounding leads to unreliable conclusions

This aligns with OWASP Agentic AI Threats (2026), which emphasizes the need for visibility, traceability, and runtime controls in agent-based security systems.

## 5. Problem Definition

> **Design an AI-assisted investigation system capable of automatically selecting and coordinating read-only security investigation skills to collect evidence from multiple telemetry layers, where every conclusion is traceable to observable evidence and every action is under human control.**

### Core Constraints

| Constraint | Rationale |
|------------|-----------|
| **Read-only** | Investigation only; no autonomous containment, blocking, or remediation |
| **Evidence-grounded** | All hypotheses must link to observed evidence |
| **Decoupled architecture** | Skills independent of LLM provider; LLM only for orchestration |
| **Schema-validated** | All tool outputs must conform to defined JSON schemas |
| **Traceable** | Every tool call and evidence must be logged and auditable |
| **Controlled** | Agent security boundaries enforced; no arbitrary command execution |

### Out of Scope

The system is **NOT** designed to:
- Replace SOC analysts
- Perform autonomous containment
- Train or fine-tune models
- Build a complete SIEM or EDR
- Execute arbitrary shell commands

## 6. Research Questions

| ID | Question | Measurement |
|----|----------|-------------|
| **RQ1** | Can an LLM Agent correctly select and coordinate investigation skills to complete a multi-step workflow? | Tool selection accuracy |
| **RQ2** | Can the Agent generate hypotheses based on actual evidence rather than hallucination? | Unsupported claim rate, evidence coverage |
| **RQ3** | Does Agent-assisted investigation reduce time/effort compared to standardized manual workflow? | Investigation time comparison |
| **RQ4** | Does the Agent maintain correct security boundaries when facing prompt injection, malicious log content, tool errors, or insufficient evidence? | Adversarial test success rate |

## 7. System Objectives

### Primary Objective

Build a demonstration system that proves evidence-grounded, read-only AI-assisted SOC investigation is feasible and can outperform naive approaches while maintaining security boundaries.

### Secondary Objectives

1. Establish clear skill contracts (input/output schemas) for three investigation domains
2. Demonstrate dynamic tool selection based on evidence evaluation
3. Create a scenario-based benchmark with 20 test cases covering benign, malicious, and ambiguous conditions
4. Measure investigation efficiency, evidence coverage, assessment quality, and security robustness
5. Document the threat model for agent-based security systems

## 8. Scope Definition

### In-Scope (MVP)

- **3 Investigation Skills**:
  1. CTI Enrichment (IPv4, domain, hash reputation)
  2. Internal Network Investigation (connection patterns, anomaly detection)
  3. Endpoint Investigation (process tree analysis, suspicious relationship detection)

- **Agent Orchestration**:
  - Intent understanding
  - Tool selection and parameter generation
  - Evidence interpretation
  - Hypothesis synthesis
  - Final report generation

- **Evaluation Framework**:
  - 20 scenario-based test cases
  - Tool correctness validation
  - Investigation workflow measurement
  - Assessment quality metrics
  - Security testing

### Out-of-Scope (MVP)

- Automatic containment or remediation
- Full SIEM or EDR implementation
- Model training or fine-tuning
- Multi-agent architectures
- Multimodal (vision) capabilities
- Production deployment infrastructure

## 9. Success Criteria

The MVP is considered complete when:

| Category | Criteria |
|----------|----------|
| **Functional** | 3 skills work independently; Agent calls tools dynamically; Evidence is stored and traced; Final report distinguishes evidence from hypothesis; Risk/confidence have rationale; Read-only enforced |
| **Evaluation** | 20 scenarios run; Benign and ambiguous cases included; Tool-selection, evidence-coverage, assessment-quality, investigation-time metrics available; False-positive measurement computed |
| **Security** | Prompt-injection tested; Untrusted-data separation implemented; Tool privilege restricted; Malformed-result handling tested; Audit logging operational |
| **Documentation** | Architecture diagram; Schema documentation; Literature review; Threat model; Benchmark methodology; Results and limitations |

## 10. Contribution

This project contributes:

1. **A decoupled architecture** for SOC investigation based on tool-calling Agents
2. **Three investigation skills** with clear schemas and read-only security boundaries
3. **An evidence-grounded pipeline** that distinguishes evidence, inference, and hypothesis
4. **A scenario-based benchmark** with 20 cases including malicious/benign/ambiguous conditions
5. **Comprehensive evaluation** of efficiency, reliability, evidence coverage, assessment quality, and security robustness

## 11. Positioning

This project positions itself as:

> **AI augmentation for SOC analysts, not AI replacement.**

This aligns with empirical evidence: LLMs can reduce effort and improve consistency in incident-response work, but autonomous security reasoning still has significant failure modes that require human oversight.
