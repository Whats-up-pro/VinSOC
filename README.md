# VinSOC

**AI-Powered SOC Investigation System** · Read-only · Evidence-grounded

VinSOC uses an LLM to select investigation tools and return structured evidence for human analyst review. It does **not** block traffic, modify systems, or make autonomous decisions.

| | |
|---|---|
| **Python** | 3.11+ |
| **Tests** | 197 passed |
| **License** | Research |

---

## Overview

VinSOC transforms raw SOC telemetry into structured, traceable evidence for human analyst review.

```
Analyst Input
     │
     ▼
┌─────────────┐
│  LLM        │
│  Orchestrator│
└──────┬──────┘
       │
       ▼
┌──────────────┬──────────────┬──────────────┐
│  CTI        │  Network     │  Endpoint    │
│  Enrichment │  Investigation│ Investigation│
└──────┬──────┴──────┬───────┴──────┬──────┘
       │              │              │
       ▼              ▼              ▼
┌─────────────────────────────────────────────┐
│              Evidence Store                   │
│  OBSERVED · DERIVED · EXTERNAL_INTEL        │
└──────────────────────┬──────────────────────┘
                       │
                       ▼
               Assessment Report
                       │
                       ▼
              Human Analyst Review
```

---

## Quick Start

```bash
# Install dependencies
pip install -r requirements.txt

# Run all tests
python -m pytest -q

# List available scenarios
python -m cli.main list

# Run investigation
python -m cli.main investigate 185.220.101.45 --type ipv4
```

---

## Evaluation

### Tool Calling (R1) 🔄

Measure LLM tool selection accuracy.

```bash
python -m evaluation.tool_calling benchmarks dev --mode integration
```

**Current Baseline:**

| Metric | Value |
|--------|-------|
| Tool Precision | 80.65% |
| Tool Recall | 59.38% |
| Tool F1 | 68.22% |
| Exact Call F1 | 68.22% |
| Trajectory Success | 0.00% |

### Text-to-SQL (R2) ⏳

Measure SQL generation accuracy against frozen snapshots.

```bash
python -m evaluation.text_to_sql evaluate --snapshot data/snapshots/v1.duckdb
```

---

## Architecture

### Investigation Skills

| Skill | Description | Data Source |
|-------|-------------|-------------|
| `cti_enrichment` | Threat intelligence lookup | ThreatFox |
| `network_investigation` | Network telemetry analysis | CTU-13, CICIDS2017 |
| `endpoint_investigation` | Process relationship analysis | Sysmon |

### Evidence Model (V2)

| Class | Description |
|-------|-------------|
| `OBSERVED` | Raw telemetry from data sources |
| `DERIVED` | Analytics output (beaconing candidates, etc.) |
| `EXTERNAL_INTEL` | CTI enrichment results |

### Data Layer

- **DuckDB** frozen snapshots for network/endpoint data
- Read-only access, no writes permitted
- LLM never sees raw database

---

## Project Structure

```
VinSOC/
├── agent/              # LLM orchestration
│   ├── orchestrator.py
│   ├── evidence.py
│   ├── tools.py
│   └── provider.py
│
├── skills/             # Investigation skills
│   ├── cti_skill.py
│   ├── network_skill.py
│   └── endpoint_skill.py
│
├── evaluation/         # Evaluation framework
│   ├── tool_calling/ # R1 benchmark
│   └── text_to_sql.py
│
├── schemas/          # JSON schemas
├── scenarios/        # Test scenarios
├── tests/            # Unit & integration tests
└── docs/            # Architecture docs
```

---

## Design Principles

| Principle | Description |
|-----------|-------------|
| **Read-only** | No traffic blocking, system modification, or automated response |
| **Evidence-grounded** | Every claim linked to evidence IDs |
| **Fail-closed** | CTI errors fail the investigation |
| **Human review** | Analyst approves/rejects/escalates final assessment |
| **Reproducible** | Pinned models, timestamps, benchmark hashes |

---

## Setup

### Requirements

- Python 3.11+
- DuckDB
- OpenAI API key (optional, for production)

### Installation

```bash
git clone https://github.com/Whats-up-pro/VinSOC.git
cd VinSOC
pip install -r requirements.txt
```

### Environment

```bash
export OPENAI_API_KEY=sk-...
```

---

## Benchmark Cases

**20 development cases** in `evaluation/tool_calling/benchmarks/dev/`

| Category | Description |
|----------|-------------|
| `cti_only` | Single CTI lookup |
| `network_only` | Network analysis only |
| `endpoint_only` | Endpoint investigation only |
| `cti_network` | CTI + Network |
| `cti_network_endpoint` | Full investigation |
| `hostname_led` | Hostname start (no CTI until pivot) |

---

## Documentation

| Document | Description |
|----------|-------------|
| [Architecture](docs/architecture.md) | Full system design |
| [Evaluation](docs/evaluation.md) | Evaluation methodology |
| [Evidence V2](docs/evidence_v2_cti.md) | Evidence model |
| [Network V2](docs/network_telemetry_v2.md) | Network analytics |
| [DuckDB](docs/duckdb_data_layer.md) | Data layer setup |

---

## Roadmap

| Stage | Focus | Status |
|-------|-------|--------|
| R0 | Runtime & semantic integrity | ✅ |
| R1 | Tool Calling Evaluation | 🔄 |
| R2 | Text-to-SQL Benchmark | ⏳ |
| R3 | End-to-End Investigation | ⏳ |

---

## Contributing

Contributions welcome. Please follow existing code patterns and add tests.

---

## License

Research project for SOC investigation evaluation.
