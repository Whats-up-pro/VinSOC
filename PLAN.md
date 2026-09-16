# Implementation Plan: VinSOC Critical Issues - Option A

## Context

This plan addresses 5 critical/high priority issues identified in the independent review (`docs/independent_review.md`):

| Issue | Priority | Status |
|-------|----------|--------|
| MockProvider doesn't test dynamic orchestration | CRITICAL | To fix |
| Benchmark comparison invalid | CRITICAL | To fix |
| Triage too simple | HIGH | To fix |
| Evidence traceability weak | HIGH | To fix |
| Prompt injection markers incomplete | MEDIUM | To fix |

### Already Completed
- Fixed `investigate()` / `investigate_fixed_pipeline()` code structure bug
- Fixed lifecycle trace incomplete (verify/review phases)
- Fixed metadata overwrite bug (orchestration_mode)

---

## Phase 1: Strengthen Triage (HIGH Priority)

### Files to Modify
- `agent/triage.py` - Complete rewrite with TriageEngine class
- New: `tests/test_triage.py` - Comprehensive test coverage

### Changes

1. **Add `TriageEngine` class** with:
   - Phrase-based detection using regex (e.g., `\bknown\s+infrastructure\b`)
   - Case-insensitive matching
   - Negation handling ("not malicious", "ruled out", "false positive")
   - Sentence-level analysis for negation context

2. **Benign phrases** (higher priority):
   - `known infrastructure`, `expected traffic`, `allowlist`, `benign`, `known good`, `false positive`, `not a threat`

3. **Suspicious phrases**:
   - `malicious`, `suspicious`, `beacon`, `beaconing`, `exfil`, `exfiltration`, `port scan`, `anomaly`, `c2`, `c&c`, `lateral movement`, `privilege escalation`, `ransomware`, `backdoor`, `cobalt strike`, `apt`

4. **Negation patterns**:
   - `not malicious`, `no evidence of`, `ruled out`, `false positive`, `clear of`, `benign activity`

### Verification
```bash
pytest tests/test_triage.py -v
pytest tests/ -v  # ensure no regressions
```

---

## Phase 2: Expand Prompt Injection Markers (MEDIUM Priority)

### Files to Modify
- `agent/orchestrator.py` - Expand `INJECTION_MARKERS` tuple

### Changes

Add OWASP LLM01:2025 patterns to `INJECTION_MARKERS`:

```python
INJECTION_MARKERS = (
    # Direct override
    "ignore previous instructions", "ignore all previous instructions",
    "disregard previous", "forget all instructions",
    
    # Role attacks
    "you are now", "you are a", "pretend you are", "act as",
    
    # System manipulation
    "[system]", "[inst]", "[ai]", "[skip]", "[abort]", "[stop]",
    
    # Privilege escalation
    "give me admin", "bypass", "disable safety",
    
    # Alert suppression
    "mark as false positive", "close this ticket", "whitelist",
    
    # Code execution
    "run ", "sudo ", "<script", "javascript:",
    
    # Context confusion
    "ignore the above", "do the opposite", "the real prompt is",
    
    # Token smuggling
    "```system", "```assistant", "user:\n",
)
```

### Verification
```bash
pytest tests/test_security_attack_vectors.py -v
```

---

## Phase 3: Enforce Evidence Traceability (HIGH Priority)

### Files to Modify
- `agent/orchestrator.py` - Add `EvidenceTraceabilityViolation` class, modify `_verify_case_quality()`
- `agent/evidence.py` - Add `validate_evidence_references()` helper
- New: `tests/test_traceability.py` - Traceability enforcement tests

### Changes

1. **Add `EvidenceTraceabilityViolation` dataclass** to track violations

2. **Modify `_verify_case_quality()`** to return violations tuple:
   ```python
   def _verify_case_quality(...) -> Tuple[List[str], List[EvidenceTraceabilityViolation]]:
       # Check each hypothesis for non-existent evidence IDs
       # Return limitations AND violations list
   ```

3. **Update `_generate_case()`** to:
   - Include `traceability_violations` in metadata
   - Add `traceability_valid: bool` flag
   - Add security flag when violations found

### Verification
```bash
pytest tests/test_traceability.py -v
pytest tests/ -v  # ensure no regressions
```

---

## Phase 4: MockProvider Documentation & Benchmark Redesign (CRITICAL Priority)

### Files to Modify
- `agent/provider.py` - Add comprehensive docstrings clarifying MockProvider purpose
- `agent/orchestrator.py` - Add deprecation warning to `investigate_fixed_pipeline()`
- `tests/benchmark_runner.py` - Complete redesign of metrics

### Changes

1. **MockProvider class docstring**:
   ```
   WARNING: This provider does NOT simulate LLM reasoning. It provides
   deterministic tool call sequences for the PURPOSE OF TESTING SKILL
   INTEGRATION, not evaluating orchestration logic.
   
   NOT Designed For:
   - Testing "dynamic evidence-driven orchestration"
   - Evaluating LLM reasoning quality
   ```

2. **Deprecate `investigate_fixed_pipeline()`**:
   ```python
   """
   [DEPRECATED] Baseline pipeline for comparison.
   
   WARNING: This does NOT represent "poor AI" - it is a naive
   deterministic baseline. Will be removed in v2.0.
   """
   ```

3. **Redesign benchmark metrics** from "evidence-driven vs fixed" to:
   - `schema_validation_pass_rate`
   - `security_controls_triggered`
   - `evidence_traceability_pass`
   - `avg_tools_executed`
   - `category_coverage`

### Verification
```bash
pytest tests/test_benchmark.py -v
pytest tests/ -v
```

---

## Implementation Sequence

```
Phase 1 (Triage)     ████
Phase 2 (Markers)         ████
Phase 3 (Traceability)       ████
Phase 4 (Mock/Benchmark)           ████
```

---

## Critical Files

| File | Changes |
|------|---------|
| `agent/triage.py` | Complete rewrite with TriageEngine |
| `agent/orchestrator.py` | Traceability enforcement, injection markers, deprecation |
| `agent/provider.py` | MockProvider documentation |
| `agent/evidence.py` | Add validate_evidence_references() |
| `tests/benchmark_runner.py` | Benchmark redesign |

---

## Verification Checklist

After all phases:
- [ ] All new triage tests pass
- [ ] All new OWASP pattern tests pass
- [ ] All new traceability tests pass
- [ ] Existing integration tests pass (no regressions)
- [ ] Existing security tests pass
- [ ] Documentation reflects new MockProvider purpose
- [ ] No regressions in 20 scenario tests

---

## Dependencies and Risks

| Risk | Mitigation |
|------|------------|
| Triage verdicts may change | Run full integration tests after changes |
| False positives on markers | Add specific legitimate input tests |
| Breaking existing tests | Add "graceful degradation" - flag but don't block |
