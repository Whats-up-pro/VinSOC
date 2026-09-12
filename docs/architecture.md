# System Architecture — AI-Assisted SOC Investigation System

## 1. Design Principles

### 1.1 LLM Provider as Adapter

The LLM is the **reasoning/orchestration layer only**. All security functionality exists in independent skills. This ensures:

- **Provider independence**: Switch between OpenAI, Gemini, or local models without rewriting skills
- **Testability**: Skills can be tested independently without LLM
- **Reliability**: Skills provide deterministic, validated outputs
- **Security**: LLM cannot bypass skill boundaries

### 1.2 Evidence as First-Class Citizen

All investigation outputs are stored in an Evidence Store:

- Every tool result is evidence
- Evidence is immutable once collected
- Hypotheses must cite specific evidence IDs
- Conclusions are traceable to source

### 1.3 Strict Separation

```
┌─────────────────────────────────────────────────────────────┐
│                     Human Analyst                            │
│                    (oversight + review)                      │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│                  Investigation API / CLI                     │
│                  (input validation, output)                  │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│              Investigation Orchestrator (LLM)               │
│   ┌─────────────────────────────────────────────────────┐   │
│   │  Intent Understanding                                │   │
│   │  Tool Selection & Parameter Generation               │   │
│   │  Evidence Interpretation                             │   │
│   │  Hypothesis Synthesis                                │   │
│   │  Final Report Generation                            │   │
│   └─────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────┘
                              │
              ┌───────────────┼───────────────┐
              ▼               ▼               ▼
     ┌────────────┐   ┌────────────┐   ┌────────────┐
     │ CTI Skill  │   │ Network    │   │ Endpoint   │
     │            │   │ Skill      │   │ Skill      │
     └────────────┘   └────────────┘   └────────────┘
              │               │               │
              ▼               ▼               ▼
     ┌────────────┐   ┌────────────┐   ┌────────────┐
     │ CTI Data  │   │ Network    │   │ Endpoint   │
     │ Sources   │   │ Logs       │   │ Telemetry  │
     └────────────┘   └────────────┘   └────────────┘
```

### 1.4 Read-Only Enforcement

**CRITICAL**: All skills are read-only. The agent cannot:
- Modify firewall rules
- Kill processes
- Delete files
- Execute arbitrary commands
- Perform containment actions

Investigation scope only.

## 2. Component Architecture

### 2.1 Investigation API / CLI

```
┌─────────────────────────────────────────┐
│           Investigation API              │
├─────────────────────────────────────────┤
│  Input Validation                        │
│  - IOC format validation                 │
│  - Schema validation                     │
│  - Security check (prompt injection)      │
├─────────────────────────────────────────┤
│  Output Formatting                       │
│  - Report generation                     │
│  - Trace formatting                     │
│  - Human-readable output                 │
└─────────────────────────────────────────┘
```

### 2.2 Investigation Orchestrator

```
┌─────────────────────────────────────────┐
│         Investigation Orchestrator      │
├─────────────────────────────────────────┤
│  LLM Interface                          │
│  - Provider adapter (OpenAI/Gemini)      │
│  - Tool schema definitions              │
│  - System prompt / policy                │
├─────────────────────────────────────────┤
│  Reasoning Engine                       │
│  - Intent parsing                       │
│  - Evidence evaluation                  │
│  - Decision making                      │
│  - Hypothesis formation                 │
├─────────────────────────────────────────┤
│  State Manager                          │
│  - Investigation case state              │
│  - Evidence collection                  │
│  - Tool trace                           │
└─────────────────────────────────────────┘
```

### 2.3 Investigation Skills

```
┌──────────────────────────────────────────────────────────┐
│                    Skill Interface                        │
├──────────────────────────────────────────────────────────┤
│  Input:  IOC, parameters                                  │
│  Output: JSON (schema-validated)                         │
│  State:  None (stateless, side-effect free)               │
│  Access: Read-only data sources                          │
└──────────────────────────────────────────────────────────┘
```

### 2.4 Evidence Store

```
┌─────────────────────────────────────────┐
│             Evidence Store               │
├─────────────────────────────────────────┤
│  Evidence Registry                       │
│  - Evidence ID                          │
│  - Source skill                         │
│  - Timestamp                            │
│  - Raw data                             │
│  - Processed data                       │
├─────────────────────────────────────────┤
│  Correlation Engine                      │
│  - Evidence linking                     │
│  - Pattern detection                    │
│  - Hypothesis support                   │
└─────────────────────────────────────────┘
```

## 3. Data Flow

### 3.1 Investigation Flow

```
1. INPUT
   Analyst provides: IOC (IP, domain, hash)
                     Context (alert type, initial hypothesis)
                     Constraints (time range, scope)

2. ORCHESTRATION
   LLM parses intent
   LLM selects first skill (CTI usually first)
   LLM generates skill parameters

3. SKILL EXECUTION
   Skill receives parameters
   Skill queries data source
   Skill validates output schema
   Skill returns structured result

4. EVIDENCE COLLECTION
   Skill result stored in Evidence Store
   Evidence ID generated
   Tool trace updated

5. EVALUATION
   LLM evaluates skill result
   LLM decides next action:
     - Call another skill
     - Correlate evidence
     - Generate hypothesis
     - End investigation

6. CORRELATION
   Evidence from multiple skills combined
   Patterns identified
   Hypotheses formed

7. ASSESSMENT
   Risk level assigned
   Confidence level assigned
   Limitations documented

8. REPORT
   Final investigation case generated
   Evidence linked to conclusions
   Audit trail complete
```

### 3.2 Evidence Flow

```
┌─────────┐    ┌─────────┐    ┌─────────┐
│   CTI   │───▶│Evidence │───▶│Correlate│
│ Result  │    │ Store   │    │         │
└─────────┘    └─────────┘    └────┬────┘
                                  │
┌─────────┐    ┌─────────┐        │
│Network  │───▶│Evidence │        │
│ Result  │    │ Store   │        │
└─────────┘    └─────────┘        │
                                  │
┌─────────┐    ┌─────────┐        │
│Endpoint │───▶│Evidence │◀───────┘
│ Result  │    │ Store   │
└─────────┘    └─────────┘
```

## 4. Skill Specifications

### 4.1 CTI Enrichment Skill

```
┌────────────────────────────────────────────────────────┐
│              CTI Enrichment Skill                       │
├────────────────────────────────────────────────────────┤
│  Purpose: Enrich IOC with threat intelligence           │
├────────────────────────────────────────────────────────┤
│  Input IOC Types:                                       │
│    - IPv4 address                                       │
│    - Domain name                                        │
│    - File hash (MD5, SHA1, SHA256)                      │
│    - URL (if implemented)                               │
├────────────────────────────────────────────────────────┤
│  Data Sources:                                         │
│    - External CTI/reputation APIs                       │
│    - Internal threat intel database                     │
│    - STIX bundle data                                   │
├────────────────────────────────────────────────────────┤
│  Output Schema: CTIResult                                │
│    - Reputation (benign/suspicious/malicious/unknown)   │
│    - Confidence (low/medium/high)                       │
│    - Related threat actors                              │
│    - Related malware families                           │
│    - MITRE ATT&CK techniques                           │
│    - Source attribution                                 │
│    - Raw indicators                                     │
└────────────────────────────────────────────────────────┘
```

### 4.2 Network Investigation Skill

```
┌────────────────────────────────────────────────────────┐
│            Network Investigation Skill                  │
├────────────────────────────────────────────────────────┤
│  Purpose: Analyze network telemetry for anomalies       │
├────────────────────────────────────────────────────────┤
│  Input:                                                 │
│    - Indicator (IP, domain)                             │
│    - Time range                                         │
│    - Optional: direction (src/dst)                     │
├────────────────────────────────────────────────────────┤
│  Detection Logic:                                       │
│    - Connection frequency analysis                      │
│    - Unique destination count                           │
│    - Unique port count                                  │
│    - Failed/success connection ratio                     │
│    - Port scan pattern detection                        │
│    - First seen / last seen analysis                    │
├────────────────────────────────────────────────────────┤
│  Output Schema: NetworkResult                           │
│    - Total/successful/failed connections                │
│    - Unique destinations and ports                       │
│    - Detected patterns                                  │
│    - Observed evidence                                  │
└────────────────────────────────────────────────────────┘
```

### 4.3 Endpoint Investigation Skill

```
┌────────────────────────────────────────────────────────┐
│            Endpoint Investigation Skill                 │
├────────────────────────────────────────────────────────┤
│  Purpose: Analyze process relationships for anomalies   │
├────────────────────────────────────────────────────────┤
│  Input:                                                 │
│    - Host identifier                                    │
│    - Time range                                         │
│    - Optional: process relationship context             │
├────────────────────────────────────────────────────────┤
│  Detection Logic:                                       │
│    - Parent-child process relationships                 │
│    - Suspicious chain detection                          │
│    - LOLBin usage patterns                              │
│    - Unusual process spawning                           │
├────────────────────────────────────────────────────────┤
│  Suspicious Patterns (MVP):                             │
│    - winword.exe → powershell.exe                       │
│    - excel.exe → cmd.exe                               │
│    - browser.exe → powershell.exe                       │
│    - powershell.exe → certutil.exe                      │
│    - powershell.exe → cmd.exe                           │
├────────────────────────────────────────────────────────┤
│  Output Schema: EndpointResult                          │
│    - Process tree                                       │
│    - Suspicious relationships                           │
│    - MITRE techniques                                   │
│    - Observed evidence                                  │
└────────────────────────────────────────────────────────┘
```

## 5. Investigation Policy

### 5.1 Default Investigation Workflow

```
INVESTIGATION_WORKFLOW:
  1. Parse incident/indicator input
  2. Validate IOC format and security
  3. Call CTI Enrichment (always first)
  4. Evaluate CTI result:
     - If malicious → proceed to network investigation
     - If benign → assess if further investigation needed
     - If suspicious → proceed with caution
     - If unknown → proceed based on context
  5. Evaluate network evidence:
     - If anomalies detected → consider endpoint investigation
     - If no anomalies → may stop or document benign finding
  6. Correlate all evidence
  7. Generate hypothesis
  8. Assign risk and confidence
  9. Document limitations
  10. Generate final report
```

### 5.2 Dynamic Tool Selection

The agent may **skip tools** based on evidence:

```
Example 1 - Benign IOC:
  CTI: benign reputation
  Network: normal traffic patterns
  Decision: Endpoint investigation unnecessary
  Reason: Evidence indicates benign activity

Example 2 - Clear Malicious:
  CTI: malicious, high confidence
  Decision: All three skills recommended
  Reason: Full scope needed for complete assessment

Example 3 - Insufficient Data:
  CTI: unknown reputation
  Network: no logs found
  Decision: Cannot complete investigation
  Reason: Evidence gaps are blocking
  Output: Risk UNKNOWN, confidence LOW
```

### 5.3 Evidence Correlation Rules

| Evidence Combination | Likely Interpretation |
|----------------------|----------------------|
| Malicious CTI + Port Scan Pattern | External reconnaissance |
| Malicious CTI + Suspicious Process Tree | Possible intrusion |
| Malicious CTI + Normal Network + Normal Endpoint | Stale IOC or third-party compromise |
| Benign CTI + Suspicious Network | Insider threat or policy violation |
| Benign CTI + Suspicious Process Tree | Potentially unwanted software |
| Unknown CTI + Normal Everything | May need additional context |

## 6. Schema Definitions

### 6.1 CTIResult Schema

```json
{
  "indicator": "string (required)",
  "indicator_type": "ipv4 | domain | hash | url",
  "reputation": "benign | suspicious | malicious | unknown",
  "confidence": "low | medium | high",
  "related_actors": ["string"],
  "related_malware": ["string"],
  "mitre_techniques": [{"technique_id": "string", "technique_name": "string", "tactics": ["string"]}],
  "sources": [{"name": "string", "last_updated": "ISO8601", "reference": "string"}],
  "observed_evidence": [{"type": "string", "value": "string", "context": "string"}],
  "raw_enrichment": "object (optional, provider-specific)"
}
```

### 6.2 NetworkResult Schema

```json
{
  "indicator": "string (required)",
  "indicator_type": "ipv4 | domain",
  "query_time_range": {"start": "ISO8601", "end": "ISO8601"},
  "total_connections": "integer",
  "unique_destinations": "integer",
  "unique_ports": "integer",
  "failed_connections": "integer",
  "successful_connections": "integer",
  "patterns_detected": [
    {"pattern": "string", "confidence": "low | medium | high", "evidence": ["string"]}
  ],
  "connection_summary": [
    {"dst": "string", "port": "integer", "count": "integer", "first_seen": "ISO8601", "last_seen": "ISO8601"}
  ],
  "observed_evidence": [{"type": "string", "value": "any", "context": "string"}]
}
```

### 6.3 EndpointResult Schema

```json
{
  "host": "string (required)",
  "query_time_range": {"start": "ISO8601", "end": "ISO8601"},
  "process_tree": [
    {
      "parent": "string",
      "parent_pid": "integer",
      "child": "string",
      "child_pid": "integer",
      "relationship": "string (optional)"
    }
  ],
  "suspicious_relationships": [
    {
      "parent": "string",
      "child": "string",
      "suspicious": "boolean",
      "suspicious_reasons": ["string"],
      "mitre_technique": "string (optional)"
    }
  ],
  "observed_evidence": [{"type": "string", "value": "any", "context": "string"}]
}
```

### 6.4 InvestigationCase Schema

```json
{
  "case_id": "string (UUID)",
  "created_at": "ISO8601",
  "initial_indicator": {"type": "string", "value": "string", "context": "string (optional)"},
  "tool_trace": [
    {
      "tool": "cti_enrichment | network_investigation | endpoint_investigation",
      "arguments": "object",
      "result_summary": "string",
      "timestamp": "ISO8601",
      "evidence_ids": ["string"]
    }
  ],
  "evidence": [
    {
      "evidence_id": "string",
      "source_tool": "string",
      "type": "string",
      "data": "object",
      "collected_at": "ISO8601"
    }
  ],
  "hypotheses": [
    {
      "id": "string",
      "description": "string",
      "supporting_evidence": ["evidence_id"],
      "confidence": "low | medium | high"
    }
  ],
  "risk_level": "LOW | MEDIUM | HIGH | CRITICAL | UNKNOWN",
  "confidence": "LOW | MEDIUM | HIGH",
  "limitations": ["string"],
  "final_assessment": "string",
  "supporting_evidence": ["evidence_id"],
  "contradicting_evidence": ["evidence_id (optional)"]
}
```

## 7. Security Boundaries

### 7.1 Trust Zones

```
┌─────────────────────────────────────────────────────────┐
│                     TRUSTED ZONE                         │
│  ┌─────────────────────────────────────────────────┐   │
│  │  Investigation Orchestrator                      │   │
│  │  - LLM reasoning                                  │   │
│  │  - Decision making                                │   │
│  │  - Report generation                              │   │
│  └─────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────┘
                          │
                    LLM API Call
                    (minimum context)
                          │
┌─────────────────────────────────────────────────────────┐
│                    UNTRUSTED ZONE                        │
│  ┌─────────────────────────────────────────────────┐   │
│  │  External CTI APIs                               │   │
│  │  - Untrusted content from CTI                    │   │
│  │  - Sanitized before use                          │   │
│  └─────────────────────────────────────────────────┘   │
│  ┌─────────────────────────────────────────────────┐   │
│  │  Log Data                                        │   │
│  │  - May contain malicious content                │   │
│  │  - Never treated as instructions                │   │
│  └─────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────┘
```

### 7.2 Data Isolation

| Data Type | Treatment |
|-----------|-----------|
| User Input (IOC) | Validated, sanitized |
| CTI Response | Parsed for structure, content treated as data |
| Network Logs | Never executed, only parsed for patterns |
| Process Data | Only structured fields extracted |
| LLM Output | All validated against schemas |

### 7.3 Privilege Model

```
┌────────────────────────────────────────┐
│         Skill Privilege Model           │
├────────────────────────────────────────┤
│  READ operations:                      │
│    ✓ Query CTI database/API            │
│    ✓ Read network logs                  │
│    ✓ Read endpoint telemetry            │
│    ✓ Store evidence                     │
├────────────────────────────────────────┤
│  WRITE operations:                     │
│    ✗ None (read-only system)           │
├────────────────────────────────────────┤
│  EXECUTE operations:                    │
│    ✗ No shell commands                  │
│    ✗ No containment actions             │
│    ✗ No process termination             │
│    ✗ No file modification               │
└────────────────────────────────────────┘
```

## 8. Technology Stack

### 8.1 Core Dependencies

| Component | Technology | Rationale |
|-----------|------------|-----------|
| Language | Python 3.11+ | Skill ecosystem, LLM SDKs |
| Schema Validation | Pydantic v2 | Type safety, JSON schema export |
| LLM SDK | OpenAI SDK / Google GenAI | Provider adapters |
| CLI Output | Rich | Terminal formatting |
| Testing | pytest | Unit/integration testing |
| Data | JSON | Interoperability, schema export |

### 8.2 Project Structure

```
/soc_investigation
├── /docs                    # Documentation
│   ├── problem.md
│   ├── literature_review.md
│   ├── architecture.md
│   ├── threat_model.md
│   └── evaluation.md
├── /schemas                 # JSON schemas
│   ├── cti_result.json
│   ├── network_result.json
│   ├── endpoint_result.json
│   └── investigation_case.json
├── /skills                  # Investigation skills
│   ├── __init__.py
│   ├── base.py             # Base skill interface
│   ├── cti_skill.py        # CTI enrichment
│   ├── network_skill.py    # Network investigation
│   ├── endpoint_skill.py   # Endpoint investigation
│   └── validators.py       # Schema validators
├── /agent                   # Agent orchestration
│   ├── __init__.py
│   ├── orchestrator.py     # Main orchestrator
│   ├── provider.py          # LLM provider adapter
│   ├── tools.py            # Tool definitions
│   └── evidence.py         # Evidence store
├── /scenarios               # Test scenarios
│   ├── case_001.json
│   ├── ...
│   └── case_020.json
├── /tests                   # Test suite
│   ├── test_skills.py
│   ├── test_agent.py
│   └── test_integration.py
└── /cli                    # CLI interface
    └── main.py
```

## 9. Scalability Considerations

### 9.1 MVP Scope (Week 1-5)

- Single agent, single investigation
- 3 skills, synchronous execution
- In-memory evidence store
- CLI interface

### 9.2 Future Extensions

| Feature | Priority | Rationale |
|---------|----------|-----------|
| RAG with ATT&CK | SG2 | Enhance technique correlation |
| Multi-model comparison | SG3 | Evaluate provider differences |
| Better observability | SG4 | Trace graph visualization |
| MCP adapter | SG5 | Standard protocol integration |
| Concurrent investigations | Post-MVP | Scale investigation throughput |
| Persistent evidence store | Post-MVP | Long-term evidence retention |

## 10. Compliance Alignment

### 10.1 NIST SP 800-61 Rev. 3 Alignment

| Phase | System Support |
|-------|----------------|
| Preparation | Schema definitions, scenario training |
| Detection & Analysis | CTI enrichment, evidence collection |
| Documentation | Automated case generation, evidence tracing |
| Incident Score | Risk assessment with evidence support |
| Post-Incident | Complete audit trail |

### 10.2 MITRE ATT&CK Alignment

| Skill | ATT&CK Data Sources |
|-------|---------------------|
| CTI Enrichment | External threat intelligence feeds |
| Network Investigation | Network traffic, Firewall logs |
| Endpoint Investigation | Process tracking, Command execution |

### 10.3 STIX 2.1 Alignment

The system uses STIX 2.1 concepts for:
- Indicator representation (IP, domain, hash)
- Observable patterns
- Threat actor relationships
- Tool/skill output in STIX-inspired JSON format
