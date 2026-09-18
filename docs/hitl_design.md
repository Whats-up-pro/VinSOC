# VinSOC Human-in-the-Loop Collaborative Assistant Design

## Status

Implemented on `feature/hitl-collaborative-assistant`.

This design changes VinSOC from "autonomous investigation with analyst review mentioned in metadata"
to a bounded-autonomy collaborative workflow with explicit runtime analyst decision gates.

## Evidence-to-design rationale

### 1. SOUPS 2025 — direct incident-response evidence

Kramer et al., *Integrating Large Language Models into Security Incident Response*,
SOUPS 2025 (USENIX), studied 18 security analysts and 50 real-world incidents.
The paper reports that autonomous LLM summaries omitted critical details in 35% of cases
and introduced factual inaccuracies in 42% of cases. Collaborative use reduced analyst
effort while improving readability and consistency.

Design implication for VinSOC:
- Keep evidence collection/tool orchestration automated where actions are read-only.
- Do not let machine-generated assessment become the final operational decision.
- Put a human review gate before final acceptance/escalation.
- Allow analyst feedback to resume evidence collection.

Source:
https://www.usenix.org/conference/soups2025/presentation/kramer

### 2. NIST AI 600-1 — structured human feedback and TEVV

NIST AI 600-1 (Generative AI Profile) recommends structured human feedback exercises,
domain-expert involvement, and evaluation/monitoring across the AI lifecycle.

Design implication for VinSOC:
- Record human decisions as first-class audit data.
- Separate automatic verification from human judgment.
- Preserve analyst rationale/feedback for later evaluation.

Source:
https://doi.org/10.6028/NIST.AI.600-1

### 3. OWASP Agent Control Standard (2026) — runtime control and traceability

The OWASP Agent Control Standard states that agents should be inspectable, traceable,
instrumentable, and controllable at runtime.

Design implication for VinSOC:
- Human review must affect control flow, not exist only as a report field.
- Lifecycle trace must explicitly expose `awaiting_human`, feedback, resume, approval,
  rejection, and escalation states.
- Keep existing read-only tool privilege boundary.

Source:
https://genai.owasp.org/resource/agent-control-standard-acs/

### 4. NIST SP 800-61 Rev. 3 — current incident-response lifecycle guidance

NIST SP 800-61 Rev. 3 (2025) integrates incident response into broader cybersecurity
risk management and emphasizes effective detection, response, recovery, and continuous
improvement.

Design implication for VinSOC:
- Treat analyst decisions and feedback as part of the investigation lifecycle/audit trail.
- Preserve evidence and decision records for post-incident learning and evaluation.

Source:
https://doi.org/10.6028/NIST.SP.800-61r3

## Why not approve every tool call?

VinSOC investigation skills are intentionally read-only. Requiring analyst approval for
every CTI, network, or endpoint lookup would add interaction cost without changing the
system's operational authority boundary.

The implemented policy therefore uses bounded autonomy:

```
IOC + context
    |
    v
Triage
    |
    +-- BENIGN recommendation --> [HUMAN GATE #1]
    |                               CLOSE | CONTINUE
    |
    v
Read-only evidence-driven investigation
    |
    v
Automatic traceability/schema verification
    |
    v
[HUMAN GATE #2]
    |
    +-- APPROVE ----------------------> completed
    +-- REQUEST_MORE_EVIDENCE --------> resume investigation -> verify -> review
    +-- ESCALATE ---------------------> escalated
    +-- REJECT -----------------------> rejected
```

## Runtime states

### Triage gate

When deterministic triage recommends `BENIGN` and a human review gate is configured:

- `triage_review / awaiting_human`
- analyst returns `CLOSE` or `CONTINUE`
- decision is written to `metadata.human_decisions`

A human `CONTINUE` overrides the benign closure recommendation and enters the
investigation loop.

### Final review gate

After automatic verification, the case enters:

- `review / awaiting_human`

Supported decisions:

- `APPROVE`: accept the evidence-grounded assessment.
- `REQUEST_MORE_EVIDENCE`: feed analyst feedback back to the agent and run another
  bounded read-only evidence pass.
- `ESCALATE`: mark the case for higher-level/manual handling.
- `REJECT`: reject the current machine assessment.

Review cycles are bounded by `max_review_cycles` to prevent unbounded loops.

## Implementation map

| Component | Change |
|---|---|
| `agent/hitl.py` | Human decision contract, review-gate protocol, deterministic scripted gate |
| `agent/orchestrator.py` | Triage gate, final review gate, feedback-driven resume, lifecycle/audit metadata |
| `cli/main.py` | Interactive analyst decisions for direct investigations |
| `tests/test_hitl.py` | Tests for close/continue/approve/escalate/feedback-resume behavior |
| `agent/__init__.py` | Public HITL exports |
| `docs/hitl_design.md` | Evidence-backed architecture and implementation rationale |

## Backward compatibility

If no `human_review_gate` is supplied, the orchestrator keeps legacy non-interactive
behavior and records `review_status=not_configured`.

This is intentional for benchmarks and existing programmatic callers. Production or
analyst-facing entry points should supply a review gate.

## Evaluation additions recommended next

The HITL implementation should be evaluated separately from model quality:

- analyst override rate at benign triage;
- review approval / escalation / rejection rates;
- number of additional evidence passes requested;
- assessment change after human feedback;
- time-to-decision and analyst interaction cost;
- unsupported-claim rate before vs. after review;
- inter-analyst agreement on final disposition.

These metrics should be reported alongside the existing tool-selection, evidence-coverage,
assessment-quality, and investigation-time metrics.


## Validation note

The HITL/orchestrator regression suite is run in GitHub Actions on Python 3.11 and 3.12.
The repository-wide baseline currently contains two unrelated `CTISkill` tests that fail
when no CTI data source is configured; this change does not modify that skill behavior.
