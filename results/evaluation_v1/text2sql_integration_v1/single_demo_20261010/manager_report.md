# VinSOC single-case E3 demo - management report

## Executive result

The guarded workflow executed one fixed real-data demo on the public `investigate_query` path. Infrastructure, isolation, accounting, and provenance gates passed. The model run is **technical incomplete**: it executed three valid read-only SQL probes, then hit `TOOL_LIMIT` before producing final SQL. Assessment and human review therefore remained blocked. No result was fabricated and the paid window was not retried.

- Case: `ctu_cross_708b66575657429a`
- Budget cap: **$3.00**; conservative preflight ceiling: **$1.4532608**
- Actual cost: **$0.00133865**; remaining cap: **$2.99866135**
- Calls: **4** (`routing=1`, `r2=3`, `assessment=0`)
- Tokens: input **4407**, cached input **2304**, output **367**
- Final SQL: **missing**; execution score: **0/1** for this non-official demo record
- Human review: **blocked_invalid_technical**; no analyst identity, decision, rationale, or UTC was invented

## What worked

1. Preflight passed with `attempted=0`, `received=0`, `client_created=false`.
2. GitHub Ubuntu 22.04 enforced bubblewrap network namespace, read-only DB mount, empty worker environment, 512 MiB process-group memory, one CPU, PID and timeout limits.
3. The fixed question routed through `investigate_query` and the native `network_query` tool.
4. All four responses had usage, model identity, request/response IDs, cost, latency, and remote begin/end checkpoints.
5. Three SQL probes executed in the isolated worker. Observed values were scenario names `ctu13_s5`, `ctu13_s7`, then counts **1529** and **1210** for the two strict time filters.

## What failed

The E3 worker spent its three executed R2 calls on scenario discovery and two separate counts. It reached the tool limit without returning a combined final SQL statement. That caused `NO_FINAL_SQL`, empty evidence and assessment, failed independent replay, and a blocked technical review. The original runner labeled the record `technical_complete_awaiting_human`; the offline audit corrects that label to `technical_incomplete` while retaining the original artifact unchanged.

## Evidence

- Implementation: `5e8e4ff03a58d7746861152f583d639fc24c2f91`
- CI: https://github.com/Whats-up-pro/VinSOC/actions/runs/38037320747
- Paid workflow: https://github.com/Whats-up-pro/VinSOC/actions/runs/38037640751
- Artifact: ID `11664103562`, SHA-256 `37ac6fe695f57de0d44ae780d288f8223cbe4cbd0ed6fb70e1117eaee2b23ac9`, retained until 2027-01-08
- CI counts: Python 3.11 and 3.12 each 1,314 passed / 7 skipped; required offline each 43/43 with 0 skip; required real-data each 13/13 with 0 skip; 13 DB and 120 gold replayed

## Management assessment

The platform controls behaved correctly and cheaply. The demo exposed a product-quality issue in the query loop rather than an infrastructure or budget problem: the model needs a guaranteed finalization step or a more efficient probe policy before this case can be presented as a successful end-to-end answer. Because the immutable paid window is consumed, another model run requires a new explicit scope and budget decision.
