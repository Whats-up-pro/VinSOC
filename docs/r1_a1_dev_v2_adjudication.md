# R1 A1 `dev v2` adjudication and version lock

The first real-model baseline is **15/24 case successes** on the original `dev` benchmark at [`1fd3843`](https://github.com/Whats-up-pro/VinSOC/actions/runs/35972408012). Its artifact, prompt, schema, gold and scorer must remain attached to that SHA. This document records a new benchmark version; do not relabel the old run or retroactively claim a different old score.

## Rules approved for v2

- Require `cti_enrichment` for an RFC 1918 source only when the request explicitly asks to **check CTI** for that source. Do not infer CTI from a syntactically valid private IPv4 indicator alone.
- Current flow-only `network_investigation` accepts **IPv4**; it does not look up domain-only traffic. CTI still accepts domains. Do not require network for a domain without a concrete IPv4 pivot. The tool schema and network skill reject unsupported domain input; the fixed pipeline also skips domain network calls.
- Penalize extra predictions even if another required tool matches. In particular, `003`'s network call remains an extra call. `001` now asks about *connection/flow frequency and destination IPs*, which the tool can observe, rather than DNS query counts. `019` explicitly requests evidence-gap explanation without tool calls.

## Case-by-case review

| Case | v1 → v2 | Reason |
|---|---|---|
| `001` | CTI only → network only; reword DNS query volume to connection/flow volume. | Network tool measures flow frequency, not DNS query counts; private IP CTI is not requested. |
| `002` | Unchanged: CTI only. | External-style indicator and vendor reputation are a CTI question. `203.0.113.50` is an illustrative documentation address, not a verified live vendor IOC. |
| `003` | CTI + endpoint → endpoint only; clarify local DLP scope. | Private workstation IP has no CTI purpose or stated network activity; endpoint is relevant. Extra network call remains an FP. |
| `004` | CTI + network(domain) → CTI only; clarify that no resolved IP is supplied. | Flow-only runtime cannot resolve a domain. |
| `005` | Unchanged: CTI + network(IPv4) + endpoint. | Public-style IP, observed connection and host pivot support all three. |
| `006` | CTI + network(domain) → CTI only; clarify email detection versus connection. | Email gateway alert alone does not establish IP flow, and domain-only network lookup is unsupported. |
| `007` | CTI + network(domain) + endpoint → CTI + endpoint; fix request calling a domain an IP. | Domain-only DNS alert has no IPv4 flow pivot; host pivot remains. |
| `008` | Unchanged: CTI + network(IPv4) + endpoint. | Threat intelligence, IP traffic alert and host pivot are specified. |
| `009` | CTI + network → network only. | Internal port scan is visible in IP flows; no private-IP CTI objective. |
| `010` | CTI + network + endpoint → network + endpoint. | Lateral movement supplies IP flow and host pivot, no CTI purpose for private source. |
| `011` | CTI + network → network only. | Outbound transfer is flow evidence; no external destination IOC for CTI. |
| `012` | Unchanged: endpoint only. | Process relationship and hostname pivot. |
| `013` | Unchanged: endpoint only. | Process relationship and hostname pivot. |
| `014` | Unchanged: endpoint only. | Process relationship and hostname pivot. |
| `015` | Unchanged: CTI + network(IPv4) + endpoint. | IP C2 alert and workstation pivot. |
| `016` | Unchanged: CTI(hash) + endpoint. | File hash and host pivot; no IP flow. |
| `017` | CTI + network(domain) + endpoint → CTI + endpoint; clarify lack of resolved IP. | Application domain alert alone is not queryable from flow-only network telemetry. |
| `018` | CTI + network + endpoint → network + endpoint. | Internal actor IP and host pivot support flow/endpoint; external IOC is absent. |
| `019` | CTI only → no-tool; write explicit evidence-gap task and forbid all tools. | No telemetry/asset mapping, private IP alone cannot validate a public IOC. |
| `020` | Unchanged: CTI + network(IPv4). | Explicit CTI-versus-flow comparison for external-style indicator; `203.0.113.25` is illustrative, not a verified live IOC. |
| `021` | Unchanged: no-tool. | Conceptual provenance question. |
| `022` | Unchanged: no-tool. | Capability question; no lookup. Network capability described by the **current v2 schema** is IPv4 flow lookup. |
| `023` | Unchanged: no-tool. | Explicit abstention instruction. |
| `024` | Unchanged: no-tool. | General knowledge question. |

`VERSION.lock` in `evaluation/tool_calling/benchmarks/dev/` names this split `r1_a1_dev_v2`, holds the canonical JSON SHA-256 of the 24 case files and SHA-256 of the scoring files (`arguments.py`, `matching.py`, `metrics.py`, `models.py`). The file is deliberately not named `*.json`: `DecisionRunner.load_cases()` loads every JSON file in the split as a case. The A1 run artifact must additionally record Git commit, prompt/schema/split hashes, exact model and calculated usage-based cost; a v2 run must explicitly carry the version and scorer SHA-256.

**Holdout gate:** no frozen model run, gold edit or result inspection was part of this adjudication. Because the production schema changed, independently check holdout **contract compatibility without using holdout outcomes to edit v2** before the one-time frozen run. Freeze the benchmark and scorer only after reviewing the new `dev` artifact and all case diffs.
