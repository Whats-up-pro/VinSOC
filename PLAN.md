# VinSOC finalization status

Updated 2026-10-05: **DEV_VERIFIED / HOLDOUT_PENDING**.

The earlier COMPLETE / 8-of-8 dev-and-frozen / proof-of-generalization claims in this file are withdrawn because their supporting execution-scored artifacts were absent. Archived predictions and consumption locks are preserved.

- R1 winner: GPT-4.1 mini 22/24, exact-call F1 0.9508, no-tool 5/5. Caveat: 11/24 dev-v2 gold cases adjudicated after the original model output.
- R2 immutable full dev suite: EX 7/8, case006 TOOL_LIMIT, 44 responses, usage-derived $0.02085850, implementation 3f9d72d.
- Post-INTEGER-hint code: no verified full-suite dev score. A separate case006 run cannot replace a failed case in the archived suite.
- S1/S4: consumed=true, protocol_eligible=false; no independent R2 holdout result.

Active instructions and task gates: [2026-10-05 finalization fix](docs/superpowers/plans/2026-10-05-vinsoc-finalization-fix.md). The current delivery is Task 0+1 only, offline scoring/audit and reporting correction, followed by human review. Later dev/model/demo work requires its prescribed gates; frozen requires separate authorization.

Evidence-backed reporting: [corrected evaluation report](docs/evaluation/FINAL_EVALUATION_REPORT.md), [phase-2 original results](docs/evaluation/phase2_results_2026-10-01.md), [consumption lock](evaluation/ctu_network_frozen/CONSUMED.lock).
