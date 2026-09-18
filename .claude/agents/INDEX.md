# VinSOC Agent Team

Team members for AI-Assisted SOC Investigation System development.

## Team Structure

| Agent | Role | Status |
|-------|------|--------|
| `soc-architect` | Senior Architect - Agent orchestration & skill contracts | Active |
| `soc-security-reviewer` | Security Specialist - Threat modeling & adversarial testing | Active |
| `soc-skill-dev` | Skills Developer - CTI/Network/Endpoint skill implementation | Active |
| `soc-test-engineer` | Test Engineer - Integration tests & evaluation metrics | Active |

## Quick Start

To assign tasks, mention the agent name in your message:
- **"soc-architect"** - Architecture, orchestration, skill contracts
- **"soc-security-reviewer"** - Security, threat model, adversarial testing
- **"soc-skill-dev"** - Implementation of skills, mock data
- **"soc-test-engineer"** - Testing, scenarios, evaluation

## Current Priorities

1. **HIGH**: Fix bugs in `orchestrator.py` (return statement issue)
2. **HIGH**: Implement missing skill files (`cti_skill.py`, `network_skill.py`, `endpoint_skill.py`)
3. **HIGH**: Create `agent/triage.py` and `agent/runbooks.py`
4. **MEDIUM**: Add unit tests for skills
5. **MEDIUM**: Expand integration test coverage
6. **LOW**: Add adversarial test cases

## Communication

Use `@agent-name` to delegate tasks to specific team members.
