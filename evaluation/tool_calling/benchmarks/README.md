# R1 Tool Calling Benchmarks

## Structure

```
benchmarks/
├── dev/           # Development cases (20 converted from scenarios)
├── frozen/        # Frozen holdout cases (for official evaluation)
└── README.md
```

## Case Format

Each case is a JSON file with:

```json
{
  "case_id": "case_001",
  "category": "cti_only",
  "difficulty": "basic",
  "request": "...",
  "reference_time": "2026-09-22T00:00:00Z",
  "expected_calls": [
    {
      "call_id": "cti_1",
      "tool": "cti_enrichment",
      "required_arguments": {"indicator": "1.2.3.4"},
      "critical_arguments": ["indicator"],
      "optional": false
    }
  ],
  "forbidden_tools": [],
  "ordering_constraints": [],
  "notes": "..."
}
```

## Categories

| Category | Description |
|----------|-------------|
| `cti_only` | CTI enrichment only |
| `network_only` | Network investigation only |
| `endpoint_only` | Endpoint investigation only |
| `cti_network` | CTI + Network |
| `cti_endpoint` | CTI + Endpoint |
| `network_endpoint` | Network + Endpoint |
| `cti_network_endpoint` | All three tools |
| `hostname_led` | Starts with hostname (no CTI until IOC pivot) |
| `hash_led` | Starts with file hash |
| `url_led` | Starts with URL |

## Difficulty

| Level | Description |
|-------|-------------|
| `basic` | Single tool, obvious choice |
| `intermediate` | Two tools, some context needed |
| `advanced` | Three tools or pivot dependency |

## Usage

```bash
# Run A2 integration benchmark
python -m evaluation.tool_calling benchmarks dev

# Run with specific cases
python -m evaluation.tool_calling benchmarks dev --cases case_001 case_002

# Run frozen (official)
python -m evaluation.tool_calling benchmarks frozen
```
