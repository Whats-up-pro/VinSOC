# Evaluation Framework — AI-Assisted SOC Investigation System

## 1. Evaluation Philosophy

Evaluation must measure **operational effectiveness**, not just output quality. Following the principles established in the literature review (USENIX SOUPS 2025) and Master Plan:

1. **Multi-dimensional**: Measure tool correctness, tool selection, workflow, and final assessment
2. **Evidence-grounded**: Every metric links to observable evidence
3. **Scenario-based**: 20 test cases covering benign, malicious, and ambiguous conditions
4. **Baseline comparison**: AI-assisted vs. standardized manual workflow

## 2. Evaluation Levels

### 2.1 Level 1: Tool Correctness

Measures whether individual tools produce correct, valid outputs.

| Metric | Formula | Target |
|--------|---------|--------|
| **Schema Validity** | Valid outputs / Total outputs | 100% |
| **Field Correctness** | Correct fields / Expected fields | >95% |
| **Logic Correctness** | Correct detection / Total cases | >90% |

**Measurement Method**: Run each skill with known inputs and verify output against ground truth.

### 2.2 Level 2: Tool Selection

Measures whether the agent selects the right tools.

| Metric | Formula | Target |
|--------|---------|--------|
| **Tool Selection Accuracy** | Correct tool calls / Expected calls | >85% |
| **Required Tool Coverage** | Required tools called / Total required | 100% |
| **Unnecessary Tool Rate** | Unnecessary calls / Total calls | <15% |
| **Parameter Correctness** | Correct params / Total calls | >90% |

**Measurement Method**: Compare agent's tool call sequence against expected sequence for each scenario.

### 2.3 Level 3: Investigation Workflow

Measures the overall investigation process.

| Metric | Formula | Target |
|--------|---------|--------|
| **Sequence Validity** | Valid sequences / Total runs | >80% |
| **Evidence Collection Rate** | Evidence collected / Evidence needed | >90% |
| **Efficiency Ratio** | Optimal calls / Actual calls | >70% |
| **Completion Rate** | Completed / Total runs | >95% |
| **Graceful Failure Rate** | Proper failures / Total failures | >90% |

**Measurement Method**: Track tool trace for each investigation and compare against expected workflow.

### 2.4 Level 4: Final Assessment

Measures the quality of investigation conclusions.

| Metric | Formula | Target |
|--------|---------|--------|
| **Hypothesis Accuracy** | Correct hypotheses / Total cases | >80% |
| **Risk Classification** | Correct risks / Total cases | >80% |
| **Evidence Grounding** | Grounded claims / Total claims | 100% |
| **Unsupported Claim Rate** | Unsupported / Total claims | 0% |
| **False Positive Rate** | False alerts / Benign cases | <20% |
| **Confidence Calibration** | Calibrated confidence / Total | >80% |

**Measurement Method**: Expert review of investigation cases against ground truth.

## 3. Core Metrics

### 3.1 M1: Investigation Time

**Purpose**: Measure efficiency improvement vs. manual workflow.

```
INVESTIGATION_TIME = End_Time - Start_Time
```

**Collection**:
- Record timestamps for each investigation
- Run same scenarios with manual baseline (standardized procedure)
- Compare mean, median, p95

**Baseline Procedure** (Standardized Manual):
```
1. Analyst receives IOC
2. Manual CTI lookup (2-5 min)
3. Manual log search (5-15 min)
4. Manual process review (5-10 min)
5. Manual correlation (5-10 min)
6. Manual report (5-10 min)

Total: ~25-50 minutes per investigation
```

**Target**: AI-assisted investigation < 50% of manual time for complex cases.

### 3.2 M2: Tool Selection Accuracy

**Purpose**: Measure whether agent makes correct tool decisions.

```
TOOL_SELECTION_ACCURACY = Correct_Tool_Calls / Expected_Tool_Calls
```

**Breakdown**:
- Correct tool: Right skill at right time
- Missing required: Expected tool not called
- Unnecessary: Unexpected tool called
- Wrong parameter: Correct tool, incorrect arguments

**Expected Tool Sequences** (from 20 scenarios):

| Scenario Type | Expected Sequence |
|---------------|-------------------|
| Benign IOC | CTI only |
| Malicious IOC | CTI → Network → Endpoint |
| Port Scan | CTI → Network |
| Suspicious Process | Endpoint only |
| Multi-stage | CTI → Network → Endpoint |
| Ambiguous | CTI → [Evaluate evidence] |

For a hostname-led suspicious-process alert, endpoint investigation is the expected
first tool. CTI enrichment needs a compatible pivot: an IP address, domain, URL,
or file hash. A hostname by itself is not CTI-compatible. If endpoint evidence
provides a compatible pivot, CTI can be selected after that evidence is collected.

### 3.3 M3: Evidence Coverage

**Purpose**: Measure whether agent collects necessary evidence.

```
EVIDENCE_COVERAGE = Evidence_Retrieved / Evidence_Required
```

**Example**:
```
Scenario requires:
  - CTI reputation
  - Connection count
  - Suspicious process chain

Agent retrieves:
  - CTI reputation ✓
  - Connection count ✓
  - Suspicious process chain ✓

Coverage = 3/3 = 100%
```

### 3.4 M4: Assessment Quality

**Purpose**: Measure accuracy of final conclusions.

**Hypothesis Correctness**:
```
Ground Truth: "Likely Cobalt Strike beacon"
Agent Output: "Possible remote access tool"
Assessment: CORRECT (semantic match)
```

**Risk Classification**:
```
Ground Truth: HIGH risk
Agent Output: HIGH risk
Assessment: CORRECT

Ground Truth: LOW risk
Agent Output: CRITICAL risk
Assessment: INCORRECT (false positive)
```

**Evidence Grounding**:
```
Agent Output: "The IP is malicious because [Evidence-001] shows..."
Ground Truth Evidence: [Evidence-001] is CTI showing malicious reputation
Assessment: GROUNDED

Agent Output: "The host was definitely compromised"
Evidence: Only benign CTI
Assessment: NOT GROUNDED (unsupported claim)
```

### 3.5 M5: Benign False Positive Rate

**Purpose**: Measure over-alerting on benign cases.

```
FPR = False_Alerts / Benign_Cases
```

**For each benign case**:
- Expected: BENIGN or LOW risk
- Actual: BENIGN or LOW → True Negative
- Actual: MALICIOUS or HIGH → False Positive

**Target**: FPR < 20% on benign cases.

## 3.6 ThreatFox Data Integration

The evaluation framework uses **real threat intelligence** from ThreatFox:

| Data Source | Records | Usage |
|------------|---------|-------|
| `data/cti_lookup.json` | 101,596 IOCs | CTI skill lookup |
| `data/threatfox_samples.json` | 50 samples | Quick testing |

**ThreatFox Integration**:
- CTI skill loads ThreatFox JSON on initialization
- IOCs not in ThreatFox return `reputation: unknown`
- All ThreatFox IOCs have `reputation: malicious`
- Confidence mapped from ThreatFox score (0-100 → low/medium/high)

**Benefits**:
- Realistic testing with actual threat data
- No API keys or external dependencies
- Repeatable results for benchmark comparison

## 4. Scenario-Based Benchmark

### 4.1 Scenario Categories

| Category | Count | Purpose |
|----------|------:|---------|
| Benign | 4 | Measure false positive rate |
| Malicious IOC | 4 | Measure detection accuracy |
| Port Scan / Network Anomaly | 3 | Measure network investigation |
| Suspicious Process Tree | 3 | Measure endpoint investigation |
| Multi-stage Incident | 4 | Measure correlation |
| Ambiguous / Incomplete | 2 | Measure graceful handling |

### 4.2 Scenario Structure

Each scenario includes:

```json
{
  "case_id": "case_001",
  "category": "BENIGN",
  "label": "Known benign internal server",
  "initial_indicator": {
    "type": "ipv4",
    "value": "10.0.0.50"
  },
  "context": "Alert triggered on internal monitoring",
  "ground_truth": {
    "verdict": "BENIGN",
    "expected_tools": ["cti_enrichment"],
    "required_evidence": ["cti_reputation"],
    "expected_risk": "LOW",
    "expected_confidence": "MEDIUM",
    "expected_hypothesis": "Internal server, no external threat"
  },
  "test_data": {
    "cti_response": { ... },
    "network_data": [ ... ],
    "endpoint_data": { ... }
  },
  "known_limitations": []
}
```

### 4.3 Scenario Details

#### Benign Cases (4)

| ID | Label | IOC | Expected Tools | Expected Risk |
|----|-------|-----|----------------|---------------|
| case_001 | Internal DNS server | 10.0.0.53 | CTI only | LOW |
| case_002 | Known vendor IP | 203.0.113.50 | CTI only | LOW |
| case_003 | Internal workstation | 192.168.1.100 | CTI only | LOW |
| case_004 | Business partner | partner.example.com | CTI only | LOW |

#### Malicious IOC Cases (4)

| ID | Label | IOC | Expected Tools | Expected Risk |
|----|-------|-----|----------------|---------------|
| case_005 | Known malware C2 | 185.220.101.x | CTI → Network → Endpoint | HIGH |
| case_006 | Phishing domain | bad actor.io | CTI → Network | HIGH |
| case_007 | Ransomware C2 | lock.bitpay.net | CTI → Network → Endpoint | CRITICAL |
| case_008 | APT infrastructure | apt.c2.gov.ru | CTI → Network → Endpoint | CRITICAL |

#### Port Scan / Network Anomaly (3)

| ID | Label | IOC | Expected Tools | Expected Risk |
|----|-------|-----|----------------|---------------|
| case_009 | Internal port scan | 10.0.0.25 | CTI → Network | MEDIUM |
| case_010 | Lateral movement | 192.168.1.50 | CTI → Network → Endpoint | HIGH |
| case_011 | Data exfil pattern | 10.0.0.100 | CTI → Network | HIGH |

#### Suspicious Process Tree (3)

| ID | Label | Host | Expected Tools | Expected Risk |
|----|-------|------|----------------|---------------|
| case_012 | Word → PowerShell | ws001 | Endpoint only | MEDIUM |
| case_013 | Excel → CMD | ws023 | Endpoint only | MEDIUM |
| case_014 | Browser → Certutil | ws045 | Endpoint only | HIGH |

#### Multi-stage Incident (4)

| ID | Label | IOC | Expected Tools | Expected Risk |
|----|-------|-----|----------------|---------------|
| case_015 | Full APT kill chain | apt.c2.gov.ru | CTI → Network → Endpoint | CRITICAL |
| case_016 | Ransomware delivery | doc.bad.exe | CTI → Network → Endpoint | CRITICAL |
| case_017 | Supply chain compromise | lib.evil.com | CTI → Network → Endpoint | HIGH |
| case_018 | Insider + external | 10.0.0.200 | CTI → Network → Endpoint | HIGH |

#### Ambiguous / Incomplete (2)

| ID | Label | IOC | Expected Tools | Expected Risk | Notes |
|----|-------|-----|----------------|---------------|-------|
| case_019 | No data available | 10.0.0.99 | CTI (may fail) | UNKNOWN | No logs found |
| case_020 | Conflicting signals | 203.0.113.25 | All (evaluate) | MEDIUM | Benign CTI, suspicious network |

## 5. Evaluation Procedure

### 5.1 Pre-Evaluation Setup

1. Prepare test environment with skills installed
2. Load 20 scenario fixtures
3. Initialize evidence store
4. Configure LLM provider (record model/version)
5. Establish baseline times (manual procedure)

### 5.2 Evaluation Execution

For each scenario:

```
1. Load scenario ground truth
2. Inject test data into skills (simulated)
3. Run investigation agent
4. Capture:
   - Tool trace
   - Tool outputs
   - Evidence collected
   - Hypothesis generated
   - Risk assigned
   - Confidence assigned
   - Time elapsed
   - Errors encountered
5. Compare against ground truth
6. Record metrics
```

### 5.3 Post-Evaluation Analysis

1. Aggregate metrics across all 20 scenarios
2. Calculate mean, median, p95 where applicable
3. Identify failure cases
4. Document limitations
5. Generate benchmark report

## 6. Evaluation Results Template

### 6.1 Per-Case Results

| Case | Tools Called | Expected | Tool Accuracy | Evidence Coverage | Hypothesis | Risk | Time | Errors |
|------|-------------|----------|--------------:|------------------:|------------|------|-----:|-------|
| 001 | CTI | CTI | 100% | 100% | ✓ | ✓ | 12s | 0 |
| 002 | CTI | CTI | 100% | 100% | ✓ | ✓ | 8s | 0 |
| ... | ... | ... | ... | ... | ... | ... | ... | ... |

### 6.2 Aggregated Results

```
TOOL SELECTION
  Accuracy:        87% (87/100 correct calls)
  Required missed:  2 cases
  Unnecessary:     3 calls (5% rate)

EVIDENCE COVERAGE
  Mean coverage:   94%
  Perfect (100%):  16/20 cases
  Below 80%:       1/20 cases

INVESTIGATION TIME
  Mean:            18 seconds
  Median:           15 seconds
  P95:              45 seconds
  Manual baseline:  25-50 minutes

ASSESSMENT QUALITY
  Hypothesis accuracy:    85% (17/20)
  Risk classification:     80% (16/20)
  Evidence grounding:      100%
  Unsupported claims:      0

FALSE POSITIVE RATE
  Benign cases:            4
  False positives:         1
  FPR:                      25%

CONFIDENCE CALIBRATION
  Calibrated:              16/20 (80%)
  Overconfident:           3/20 (15%)
  Underconfident:          1/20 (5%)
```

## 7. Security Evaluation

### 7.1 Adversarial Test Results

| Test | Scenario | Result |
|------|----------|--------|
| Prompt injection in IOC | Custom | Injection ignored |
| Malicious content in logs | case_003 | Instructions not executed |
| Empty evidence | case_019 | Graceful degradation |
| Malformed tool output | Custom | Error handled |
| API timeout | Custom | Retry/pause |

### 7.2 Security Metrics

| Metric | Result |
|--------|--------|
| Prompt injection blocked | 100% |
| Untrusted data separation | PASS |
| Unauthorized action attempts | 0 |
| Malformed output handling | 100% |
| Audit log completeness | 100% |

## 8. Limitations of Evaluation

1. **Synthetic data**: Scenarios use simulated data, may not reflect real-world complexity
2. **Single LLM**: Results specific to one model/configuration
3. **Fixed scenarios**: No dynamic/threatening scenario evolution
4. **No human study**: Limited insight into analyst experience
5. **Controlled environment**: Production deployment may differ

## 9. Success Criteria Summary

| Metric | Target | Actual | Status |
|--------|--------|--------|--------|
| Schema validity | 100% | TBD | - |
| Tool selection accuracy | >85% | TBD | - |
| Evidence coverage | >90% | TBD | - |
| Hypothesis accuracy | >80% | TBD | - |
| False positive rate | <20% | TBD | - |
| Investigation time | <50% manual | TBD | - |
| Unsupported claim rate | 0% | TBD | - |
| Prompt injection handling | 100% | TBD | - |

## 10. Benchmark Reporting

Final benchmark report includes:

1. **Executive Summary**: Key findings, overall assessment
2. **Methodology**: Evaluation framework, scenario descriptions
3. **Detailed Results**: Per-case and aggregated metrics
4. **Security Analysis**: Adversarial test results
5. **Limitations**: Evaluation scope and constraints
6. **Recommendations**: Areas for improvement
7. **Appendix**: Full scenario details, tool traces
