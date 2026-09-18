# Evidence V2 + Real CTI Integration

## Goal

This milestone upgrades VinSOC from a flat evidence list and single-source/mock CTI lookup
into a provenance-aware evidence model plus pluggable real CTI enrichment.

No ML training is introduced.

## Evidence model

VinSOC now distinguishes:

- `OBSERVED`: telemetry directly observed in the investigated environment.
- `DERIVED`: deterministic analysis computed from one or more evidence items.
- `EXTERNAL_INTEL`: context supplied by external intelligence/knowledge sources.

This distinction prevents external reputation or analytic output from being silently treated
as equivalent to first-party telemetry.

Each evidence item can now carry:

- concrete source name;
- source/analytic confidence;
- provenance metadata;
- external references;
- source event timestamp;
- parent/related evidence IDs.

## Why CTI is EXTERNAL_INTEL

Threat intelligence tells VinSOC what an external source knows about an IOC. It does not,
by itself, prove compromise inside the investigated environment. The orchestrator therefore
stores CTI tool results as `EXTERNAL_INTEL`.

## CTI providers

### ThreatFox

VinSOC supports exact IOC search against the ThreatFox Community API when
`ABUSECH_AUTH_KEY` is configured.

ThreatFox requires an Auth-Key and documents `search_ioc` for IOC lookup. ThreatFox also
expires IOCs older than six months to reduce false positives caused by infrastructure reuse.

Official documentation:
https://threatfox.abuse.ch/api/

### MalwareBazaar

For hash indicators, VinSOC can query MalwareBazaar using `get_info`.
The Community API currently requires an Auth-Key.

Official documentation:
https://bazaar.abuse.ch/api/

### URLhaus

VinSOC currently uses a local URLhaus JSON/index adapter rather than coupling case replay
to a live API. URLhaus provides regularly regenerated exports, which makes a local snapshot
appropriate for reproducible investigations.

Official documentation:
https://urlhaus.abuse.ch/api/

Configure:

```bash
export URLHAUS_JSON_PATH=/path/to/urlhaus.json
```

### MITRE ATT&CK

ATT&CK is treated as a knowledge/mapping source, not as IOC reputation.
A local ATT&CK STIX 2.1 bundle can map malware/software discovered by upstream CTI into
ATT&CK techniques.

MITRE explicitly publishes ATT&CK in STIX 2.1 for automated ingestion and querying.

Official documentation:
https://attack.mitre.org/resources/working-with-attack/

Configure:

```bash
export ATTACK_STIX_PATH=/path/to/enterprise-attack.json
```

## Runtime configuration

```bash
export ABUSECH_AUTH_KEY=...
export URLHAUS_JSON_PATH=/path/to/urlhaus.json
export ATTACK_STIX_PATH=/path/to/enterprise-attack.json
```

If no CTI source is configured or no source matches an IOC, CTISkill returns
`reputation=unknown`; absence of intelligence is not interpreted as benign.

## Provider fusion rules

Current fusion is deliberately conservative:

1. each provider returns a normalized finding;
2. non-matches are retained in provenance but do not vote for benign;
3. malicious/suspicious matches can enrich the investigation;
4. malware names may be mapped through local ATT&CK STIX;
5. final incident disposition remains evidence-correlation + analyst review, not CTI alone.

## Next milestone

After review of this change:

1. normalize Zeek/Suricata network telemetry;
2. emit `OBSERVED` raw network evidence;
3. emit `DERIVED` deterministic beacon/scan analytics linked back to raw evidence;
4. ingest Sysmon using the same evidence contract;
5. build cross-source correlation and timeline.
