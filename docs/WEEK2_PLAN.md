# Week 2 Plan: Integrate ThreatFox Data into CTI Skill

## Context

ThreatFox là real threat intelligence feed với 109,262 IOCs. Hiện tại CTI skill dùng mock data. Integration này sẽ:
- Thay thế mock data bằng real CTI data
- Cung cấp realistic testing cho evaluation framework
- Enable validation với actual threat data

## Current State

```
CTISkill
├── __init__(mock_data: Optional[Dict])
├── execute(indicator, indicator_type)
│   ├── If mock_data → return mock result
│   └── Else → error "No CTI data source"
└── _build_result_from_mock() → transforms mock to CTIResult schema
```

**Problem**: No actual CTI data loading mechanism exists.

## Proposed Implementation

### Option A: In-Memory Lookup (Recommended for MVP)

**Approach**: Load ThreatFox CSV → Build in-memory dict → Direct lookup

**Pros**:
- Simple, no external dependencies
- Fast for < 200k IOCs
- Easy to validate

**Cons**:
- Memory footprint (~50-100MB for 100k entries)
- Requires reload on data update

**Implementation**:
```python
class CTISkill:
    def __init__(self, threatfox_path: str = None, mock_data: Dict = None):
        self.threatfox_data = self._load_threatfox(threatfox_path) if threatfox_path else {}

    def _load_threatfox(self, path: str) -> Dict:
        df = pd.read_csv(path)
        return df.set_index('ioc_value').to_dict('index')

    def _lookup_ioc(self, indicator: str) -> Optional[Dict]:
        return self.threatfox_data.get(indicator)
```

### Option B: DuckDB Query (Better for Scale)

**Approach**: Query ThreatFox parquet via DuckDB on-demand

**Pros**:
- Memory efficient
- SQL query capabilities
- Handles larger datasets

**Cons**:
- Requires DuckDB dependency
- Slightly slower per-query

### Option C: SQLite Database

**Approach**: Convert CSV → SQLite → Query

**Pros**:
- Standard SQL
- Persistent storage
- Good for repeated queries

**Cons**:
- Extra conversion step
- File I/O overhead

---

## Recommended Implementation Plan

### Phase 1: Data Pipeline (30 min)

**Files to create:**
1. `scripts/extract_cti_lookup.py` - Convert ThreatFox to JSON lookup table

```python
# Extract CTI lookup from ThreatFox
df = pd.read_csv('data/threatfox_clean.csv')
cti_lookup = {}
for _, row in df.iterrows():
    ioc = row['ioc_value']
    cti_lookup[ioc] = {
        'reputation': 'malicious',  # All ThreatFox IOCs are malicious
        'confidence': _map_confidence(row['confidence_level']),
        'threat_type': row['threat_type'],
        'malware': row['malware_printable'],
        'tags': row['tags'],
        'source': 'ThreatFox',
        'last_seen': row['last_seen_utc']
    }
```

2. Output: `data/cti_lookup.json` (~10MB)

### Phase 2: CTI Skill Enhancement (45 min)

**File to modify:** `skills/cti_skill.py`

**Changes:**
1. Add `threatfox_lookup` parameter to `__init__`
2. Add `_load_threatfox()` method
3. Add `_lookup_ioc()` method
4. Modify `_execute()` to check threatfox data
5. Map ThreatFox fields → CTIResult schema

**Field mapping:**
| ThreatFox Column | CTIResult Field |
|-----------------|-----------------|
| `ioc_value` | `indicator` |
| `ioc_type` | `indicator_type` |
| `threat_type` | `related_malware` (use as category) |
| `malware_printable` | `related_malware` |
| `confidence_level` (0-100) | `confidence` (low/medium/high) |
| `reference` | `sources[].reference` |
| `tags` | `observed_evidence` |

**Confidence mapping:**
```
0-33 → low
34-66 → medium
67-100 → high
```

### Phase 3: Documentation Update (15 min)

**Files to modify:**
1. `docs/architecture.md` - Add ThreatFox as CTI data source
2. `docs/evaluation.md` - Note real CTI data usage

**Update section 4.1 CTI Enrichment Skill:**
```
│  Data Sources:                                         │
│    - External CTI/reputation APIs                       │
│    - Internal threat intel database                     │
│    - STIX bundle data                                   │
│    - ThreatFox IOC feed (109k+ IOCs)                  │  ← ADD
```

### Phase 4: Integration Test (30 min)

**Create:** `tests/test_threatfox_cti.py`

```python
def test_threatfox_cti_lookup():
    skill = CTISkill(threatfox_path='data/threatfox_clean.csv')

    # Test IP lookup
    result = skill.execute(indicator='185.220.101.45')
    assert result.success
    assert result.data['reputation'] == 'malicious'

    # Test unknown IOC
    result = skill.execute(indicator='8.8.8.8')
    assert result.data['reputation'] == 'unknown'
```

---

## Files to Modify/Create

### Create (New Files)
| File | Purpose |
|------|---------|
| `scripts/extract_cti_lookup.py` | Extract JSON lookup from ThreatFox |
| `data/cti_lookup.json` | Pre-processed CTI data (~10MB) |
| `tests/test_threatfox_cti.py` | Integration tests |

### Modify (Existing Files)
| File | Changes |
|------|---------|
| `skills/cti_skill.py` | Add ThreatFox loading + lookup |
| `docs/architecture.md` | Document ThreatFox data source |
| `docs/evaluation.md` | Note real CTI data |
| `README.md` | Add ThreatFox to data sources |

---

## Verification

### Test Commands
```bash
# 1. Extract CTI lookup
python scripts/extract_cti_lookup.py

# 2. Run unit tests
python -m pytest tests/test_skills.py -v

# 3. Run ThreatFox integration test
python -m pytest tests/test_threatfox_cti.py -v

# 4. Test CLI with real IOC
python -m cli.main investigate 185.220.101.45 --type ipv4
```

### Expected Results
- CTI skill returns `reputation: malicious` for ThreatFox IOCs
- CTI skill returns `reputation: unknown` for non-ThreatFox IOCs
- All existing tests still pass (backward compatibility)

---

## Timeline

| Phase | Time | Deliverable |
|-------|------|-------------|
| Phase 1: Data Pipeline | 30 min | `cti_lookup.json` |
| Phase 2: Skill Enhancement | 45 min | Modified `cti_skill.py` |
| Phase 3: Documentation | 15 min | Updated docs |
| Phase 4: Testing | 30 min | `test_threatfox_cti.py` |
| **Total** | **~2 hours** | Working ThreatFox integration |

---

## Alternatives Considered

### Skip Direct Integration
- Keep mock data for testing
- Document ThreatFox as potential future data source
- **Rejected**: Doesn't demonstrate real CTI data handling

### External API Integration
- Connect to VirusTotal, OTX, etc.
- **Rejected**: Requires API keys, rate limits, external dependencies

### RAG with CTI Knowledge Base
- Use vector database for similarity search
- **Rejected**: Overkill for exact IOC matching, adds complexity

---

## Decision

**Proceed with Option A (In-Memory Lookup)** for MVP simplicity. Can migrate to Option B (DuckDB) if scale becomes an issue.
