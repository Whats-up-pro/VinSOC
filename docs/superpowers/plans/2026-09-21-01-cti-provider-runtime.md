# PLAN 01 — CTI Provider Runtime Integration

**Save as:** `docs/superpowers/plans/2026-09-21-01-cti-provider-runtime.md`

## Goal

Biến `skills/cti_providers.py` từ adapter code đứng riêng thành **runtime CTI data-source thực sự được `CTISkill` sử dụng**, đồng thời giữ nguyên fail-closed semantics.

## Precondition

```
master >= 4a8261f
CTISkill fail-closed tests currently pass
skills/cti_providers.py exists
```

## Input

Code:
- skills/cti_skill.py
- skills/cti_providers.py
- tests/test_cti_semantics.py
- tests/test_cti_providers.py

Behavior contract:
```
invalid IOC                    → FAIL
hostname                       → FAIL
no applicable CTI source       → FAIL
provider ERROR                 → FAIL
provider successful NO_MATCH   → SUCCESS / UNKNOWN
provider MATCH                 → SUCCESS / RESULT
```

## Output

Runtime architecture:
```
CTISkill
  │
  ├── explicit mock fixture
  ├── explicit local ThreatFox
  └── CTIProvider[]
         ├── ThreatFoxProvider
         ├── MalwareBazaarProvider
         ├── URLhausLocalProvider
         └── AttackSTIXProvider
```

with machine-readable provider outcomes.

---

## Task 1.1 — Formalize provider outcome

### Files
- Modify: skills/cti_providers.py
- Test:   tests/test_cti_providers.py

### Interface

Create:
```python
class CTIProviderStatus(str, Enum):
    MATCH = "match"
    NO_MATCH = "no_match"
    NOT_APPLICABLE = "not_applicable"
    ERROR = "error"

@dataclass
class CTIFinding:
    source: str
    status: CTIProviderStatus
    ...
```

Compatibility property is allowed:
```python
@property
def matched(self):
    return self.status == CTIProviderStatus.MATCH
```
but production aggregation must use `status`.

### RED tests

Add explicit tests:
```python
def test_provider_error_is_not_no_match():
    finding = FakeErrorProvider().lookup("1.2.3.4", "ipv4")
    assert finding.status == CTIProviderStatus.ERROR

def test_malwarebazaar_ipv4_is_not_applicable():
    ...
    assert finding.status == CTIProviderStatus.NOT_APPLICABLE

def test_provider_valid_lookup_without_record_is_no_match():
    ...
    assert finding.status == CTIProviderStatus.NO_MATCH
```

Run: `pytest -q tests/test_cti_providers.py`
Must observe expected failure before implementation.

### GREEN

Convert providers:
```
ThreatFox match              → MATCH
ThreatFox no row             → NO_MATCH
ThreatFox HTTP/error         → ERROR

MalwareBazaar hash match     → MATCH
MalwareBazaar missing hash   → NO_MATCH
MalwareBazaar non-hash      → NOT_APPLICABLE

URLhaus match                → MATCH
URLhaus lookup without row   → NO_MATCH

ATT&CK direct IOC query      → NOT_APPLICABLE
```

---

## Task 1.2 — Inject providers into CTISkill

### File
- Modify: skills/cti_skill.py

### Constructor target:
```python
def __init__(
    self,
    mock_data=None,
    threatfox_path=None,
    threatfox_data=None,
    providers=None,
    auto_load_threatfox=True,
):
```

### Priority
```
explicit mock
→ explicit local ThreatFox
→ explicit providers
→ no source FAIL
```

Do not make unit tests implicitly consume environment credentials.

---

## Task 1.3 — Aggregate provider results

Implement deterministic decision table:
```
Applicable ERROR present
→ FAIL

No provider applicable
→ FAIL

At least one MATCH and no ERROR
→ SUCCESS enriched

Applicable providers execute but all NO_MATCH
→ SUCCESS UNKNOWN
```

`NOT_APPLICABLE` neither counts as error nor successful lookup.

Critical test:
```python
def test_match_plus_provider_error_fails_closed():
    ...
    assert not result.success
```

---

## Task 1.4 — Integrate at application composition point

Inspect where production `CTISkill` is constructed:
- agent/orchestrator.py
- cli/main.py

Composition target:
```python
CTISkill(
    mock_data=...,
    providers=providers_from_environment(),
)
```

only where real/provider execution is intended.

---

## Verification

```bash
pytest -q \
  tests/test_cti_semantics.py \
  tests/test_cti_providers.py \
  tests/test_skills.py
```

Then:
```bash
pytest -q
```

## Acceptance gate

```
[ ] providers actually reachable from CTISkill
[ ] hostname rejected
[ ] no source fails
[ ] provider error fails
[ ] no match is UNKNOWN
[ ] match is enriched result
[ ] no live API dependency in unit tests
```

Commit: `feat(cti): integrate provider runtime with explicit outcomes`
