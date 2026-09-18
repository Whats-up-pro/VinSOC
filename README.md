# SOC AI Investigation System

An evidence-grounded, read-only AI-assisted SOC investigation system that orchestrates heterogeneous security skills for faster and more reliable incident analysis.

## Overview

This system demonstrates AI-augmented SOC investigation using:
- **Three Investigation Skills**: CTI Enrichment, Network Investigation, Endpoint Investigation
- **LLM-based Orchestration**: Agent that dynamically selects and coordinates skills
- **Evidence Grounding**: Every hypothesis must cite specific evidence IDs
- **Security Boundaries**: Read-only operations with full audit trails

## Project Structure

```
/Phase3_VinSOC
├── /docs                    # Documentation
│   ├── problem.md           # Problem statement
│   ├── literature_review.md # Literature survey
│   ├── architecture.md      # System architecture
│   ├── threat_model.md      # Security threat model
│   └── evaluation.md        # Evaluation framework
├── /schemas                 # JSON schemas
│   ├── cti_result.json
│   ├── network_result.json
│   ├── endpoint_result.json
│   └── investigation_case.json
├── /skills                   # Investigation skills
│   ├── __init__.py
│   ├── base.py              # Base skill interface
│   ├── cti_skill.py         # CTI enrichment
│   ├── network_skill.py      # Network investigation
│   ├── endpoint_skill.py     # Endpoint investigation
│   └── validators.py         # Schema validators
├── /agent                    # Agent orchestration
│   ├── __init__.py
│   ├── orchestrator.py       # Investigation orchestrator
│   ├── provider.py           # LLM provider adapters
│   ├── tools.py              # Tool definitions
│   ├── evidence.py           # Evidence store
│   ├── hitl.py               # Human review gate contracts and decisions
│   └── integrations.py       # Read-only SOC integration abstraction (SecOps/GTI/SCC)
├── /scenarios                # Test scenarios (20 cases)
│   ├── case_001.json
│   └── ...
├── /tests                    # Test suite
│   ├── __init__.py
│   └── test_skills.py
├── /cli                      # CLI interface
│   └── main.py
├── requirements.txt
└── README.md
```

## Quick Start

### Installation

```bash
pip install -r requirements.txt
```

### Test Skills

```bash
python -m cli.main test
```

### List Available Scenarios

```bash
python -m cli.main list
```

### Run a Scenario

```bash
python -m cli.main scenario case_001
```

### Benchmark Orchestration Modes

```bash
python -m cli.main benchmark --limit 5
```

### Investigate an Indicator Directly

```bash
python -m cli.main investigate 185.220.101.45 --type ipv4 --context "Suspicious connection"
```

## Architecture

### Design Principles

1. **LLM Provider as Adapter**: LLM is the reasoning layer only; skills exist independently
2. **Evidence as First-Class Citizen**: Every conclusion links to observable evidence
3. **Strict Separation**: LLM handles orchestration; skills handle deterministic retrieval
4. **Read-Only Enforcement**: No write capabilities; investigation only
5. **Lifecycle Control**: Triage → Investigate → Verify → Human Review with explicit phase trace
6. **Human-in-the-Loop Decisions**: Analyst can confirm benign closure, request more evidence, approve, reject, or escalate assessments

### Investigation Flow

```
1. INPUT: IOC + Context
2. ORCHESTRATION: LLM selects and coordinates tools
3. SKILL EXECUTION: Evidence-driven selection of CTI, Network, or Endpoint
4. EVIDENCE COLLECTION: All results stored
5. EVALUATION: Agent decides next steps
6. CORRELATION: Evidence combined
7. ASSESSMENT: Risk and confidence assigned
8. REPORT: Evidence-grounded investigation case generated
9. HUMAN REVIEW: Analyst approves, requests more evidence, rejects, or escalates
10. FEEDBACK LOOP: Additional analyst questions can resume read-only investigation
```

## Human-in-the-Loop Workflow

Direct CLI investigations now use two runtime analyst decision gates:

```
Triage
  └─ BENIGN recommendation → analyst CLOSE / CONTINUE

Read-only evidence-driven investigation
  → automatic verification
  → analyst APPROVE / REQUEST_MORE_EVIDENCE / ESCALATE / REJECT
```

`REQUEST_MORE_EVIDENCE` feeds analyst feedback back into the agent and resumes a bounded
read-only investigation pass before verification and review repeat. Tool calls remain
autonomous because VinSOC tools are read-only; operational response authority remains human-controlled.

See `docs/hitl_design.md` for the evidence-backed rationale and source mapping.

## Skills

### CTI Enrichment

Enriches IOCs with threat intelligence:
- Reputation (benign/suspicious/malicious/unknown)
- Related threat actors
- Related malware families
- MITRE ATT&CK techniques

### Network Investigation

Analyzes network telemetry:
- Connection frequency and patterns
- Port patterns and anomalies
- Failed/success ratios
- Detection patterns (port scan, beaconing, exfiltration)

### Endpoint Investigation

Analyzes process relationships:
- Parent-child process chains
- Suspicious spawning patterns
- LOLBin usage detection
- MITRE technique mapping

## Evidence Grounding

Every hypothesis must cite specific evidence IDs:

```
Evidence:
- EV001: CTI shows malicious reputation (HIGH confidence)
- EV002: Network shows beaconing pattern
- EV003: Endpoint shows winword→powershell relationship

Hypothesis:
Multi-stage intrusion (Confidence: HIGH)
Supporting evidence: EV001 + EV002 + EV003
```

## Evaluation Framework

### 20 Scenario Benchmark

| Category | Count |
|----------|------:|
| Benign | 4 |
| Malicious IOC | 4 |
| Network Anomaly | 3 |
| Suspicious Process | 3 |
| Multi-stage | 4 |
| Ambiguous | 2 |

### Metrics

- **Tool Selection Accuracy**: Correct tool calls / Expected calls
- **Evidence Coverage**: Evidence retrieved / Evidence required
- **Assessment Quality**: Hypothesis correctness, risk classification
- **False Positive Rate**: False alerts / Benign cases
- **Investigation Time**: Comparison with manual workflow

## Security

### Threat Model

- **Prompt Injection**: Log data treated as data, not instructions
- **Untrusted Content**: All external data sanitized
- **Privilege Restriction**: Read-only skills only
- **Audit Trail**: Full tool trace and evidence collection

### OWASP Alignment

Follows OWASP Agentic AI Threats and Mitigations:
- Visibility and traceability
- Runtime controls
- Least privilege

## Documentation

See `/docs` for detailed documentation:
- `problem.md` - Problem statement and motivation
- `literature_review.md` - Survey of related work
- `architecture.md` - System architecture
- `threat_model.md` - Security threat analysis
- `evaluation.md` - Evaluation methodology

## License

This is an academic/research project for SOC investigation automation.
