# Benchmark run verification — 14/10/2026

User instructed running the expanded benchmarks. Source inspected:
`c6077a149f08744ce7a8f6bebe4264543dbc7c65`.

R1 real review-gate passed: A 120, B 120, approved, no disagreement. Lock
verification passed 120 cases, distribution 24/54/30/12. CLI preflight failed
with exit 2: only benchmarks/list/run exist. The approved implementation plan
Tasks 6–8 are absent: guarded CLI/run gate, statistics/partial reporting and
the manual one-shot workflow. No provider was created. Local OPENAI_API_KEY,
GH_TOKEN and GITHUB_TOKEN are unavailable; the connected GitHub tools expose
artifact download and contents mutations but no workflow dispatch operation.
Do not use the legacy unguarded run command or change a paid job to push-triggered.

Receipt: `results/evaluation_v1/r1/generalization_v1/run_attempt_20261014/blocked_receipt.json`.
Next implementation is the already approved plan Tasks 6, 7 and 8, then a single
authorized Task 9 dispatch on green CI with verified model/pricing/budget.
User run authorization is already present; this is a technical blocker.

The initially described R2 evaluation run 38532017308 was misidentified before
opening its artifact. Actual control/request/report all specify **calibration**,
24 questions / 48 E0+E3 records, 144 actual model responses, $0.17346330.
It is protocol3 calibration, separate from the preserved protocol2 calibration.
E0 EX 15/24 (62.5%); E3 EX 4/24 (16.67%). E0 syntax/execution 22/24;
E3 syntax/execution 5/24. No new model calls were made by this audit.

[Source workflow](https://github.com/Whats-up-pro/VinSOC/actions/runs/38532017308)
artifact 11879481406, ZIP SHA-256
`f881f318f2166e35ce9259ac0c712056f3869e3c89f117058633d1e9f114709a`.
Archive digest, exact calibration inventory, all 48 binding records, all 144
unique request/response IDs, case-bound cost events and actual cost sum verified.
Public derived receipts and per-case outcomes are in
`results/evaluation_v1/text2sql_integration_v1/calibration_protocol3_audit_20261014/`.
Original ZIP and private journals are not committed. No new SQL replay or
semantic-instance execution was performed; official eligibility is not promoted.

The report's semantic_test_accuracy zero is a missing-field default, not a
measured counterexample failure. The audit projection labels it NOT_MEASURED;
the original artifact remains unchanged.

Evaluation requires 96 distinct questions / 192 paired E0+E3 records. This
artifact contains zero evaluation records. Before an operator starts it, validate
the actual request scope= evaluation, inventory=96, budget reserve, selection
binding and a fresh unused evaluation window. Do not substitute calibration or
reuse its consumed claim. No evaluation accuracy is reported by this receipt.
