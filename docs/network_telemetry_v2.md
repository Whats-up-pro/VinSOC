# Milestone C — Network Telemetry V2

## Goal

Convert VinSOC network investigation from mock-centric analysis into read-only,
provenance-aware ingestion of real Zeek and Suricata telemetry.

Milestone C intentionally does not train ML models and does not classify a host as
compromised. It produces OBSERVED network evidence and deterministic DERIVED analytics.

## Architecture

```
Zeek conn.log JSON      Suricata EVE JSON
        |                       |
        v                       v
  Zeek adapter           Suricata adapter
        \                       /
         \                     /
          v                   v
          NormalizedNetworkEvent
                    |
                    v
               NetworkQuery
          indicator + time range
                    |
          +---------+---------+
          |                   |
          v                   v
    OBSERVED evidence   deterministic analytics
                              |
                              v
                        DERIVED evidence
```

## Canonical event

The canonical event preserves source semantics instead of forcing vendor-specific fields
into NetworkSkill. Important fields include source/destination IP and port, protocol,
application protocol, timestamps, byte/packet counters, source record identifier and
provenance.

Zeek `uid` and Suricata `flow_id` are retained so later milestones can pivot across
protocol-specific records.

## Supported telemetry

### Zeek

Initial scope is JSON `conn.log` only. The adapter streams line-by-line and ignores
malformed records rather than loading an entire log into memory.

Official reference:
https://docs.zeek.org/en/master/logs/conn.html

### Suricata

Initial EVE scope is:

- `event_type=flow`
- `event_type=alert`

An alert is stored as an observation that a sensor rule fired; it is not treated as proof
of compromise.

Official references:
https://docs.suricata.io/en/latest/output/eve/eve-json-format.html
https://docs.suricata.io/en/latest/appendix/eve-schema.html

## Query semantics

Network queries now support:

- indicator;
- indicator type;
- start/end timestamps;
- direction: any/src/dst/inbound/outbound;
- configurable local CIDRs;
- max event cap.

Inbound/outbound semantics require configured local networks.

Flow-only sources do not resolve domain indicators. DNS/TLS enrichment is deliberately
deferred rather than pretending conn/flow data contains domain attribution.

## Evidence semantics

### OBSERVED

Network flow aggregates and Suricata IDS alerts are stored as `OBSERVED`.

Large result sets are aggregated by source/src/dst/port/protocol before entering
EvidenceStore. Up to 100 source record IDs are retained in provenance, with an explicit
truncation flag.

### DERIVED

Deterministic analytics are stored separately as `DERIVED` and linked back to the
OBSERVED evidence that produced them.

Implemented analytics:

- periodic communication candidate;
- horizontal/vertical scan candidate;
- transfer metrics;
- internal administrative-service fan-out candidate.

## Deliberately removed semantics

Milestone C does not use these shortcuts:

- `>10 MB == exfiltration`;
- `SSH/SMB/RDP port == suspicious`;
- `no analytic fired == normal traffic`;
- `periodic traffic == confirmed C2`;
- `SMB/RDP fan-out == confirmed lateral movement`.

Those are hypotheses requiring correlation with endpoint and CTI evidence.

## Periodicity

The deterministic periodicity analytic exposes:

- sample count;
- mean interval;
- median interval;
- standard deviation;
- median absolute deviation;
- coefficient of variation.

A low-CV flow is labeled `periodic_connection_candidate`, not C2.

## Scan analytics

Scan candidates are separated into:

- horizontal: few ports across many destinations;
- vertical: many ports against few destinations.

Thresholds remain explicit analytic parameters rather than hidden model behavior.

## Transfer metrics

Transfer analytics report:

- outbound bytes;
- inbound bytes;
- out/in ratio;
- connection count;
- network scope.

They intentionally do not emit an exfiltration verdict.

## Internal service fan-out

Administrative-service fan-out currently recognizes ports such as SSH, SMB, RDP and WinRM
only when both source and destination are inside configured local networks. The output is
`internal_service_fanout_candidate`, not lateral movement.

## Security properties

Telemetry is untrusted data. Parsers do not execute content and keep sensor strings inside
structured fields. Malformed JSON lines are skipped. File ingestion is streaming.

## Validation

The CI suite covers:

- Zeek normalization;
- Suricata flow/alert normalization;
- time and direction filtering;
- network scope classification;
- periodicity metrics;
- horizontal/vertical scan candidates;
- transfer semantics;
- service fan-out semantics;
- OBSERVED/DERIVED lineage through EvidenceStore;
- existing HITL, CTI, traceability and integration regressions.

## Next milestone

After Milestone C review:

1. Sysmon ingestion using the same OBSERVED/DERIVED contract;
2. entity normalization across CTI/network/endpoint;
3. cross-source correlation graph;
4. attack timeline;
5. evidence-grounded hypothesis generation.
