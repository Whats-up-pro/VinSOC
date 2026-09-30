# CTU frozen: evidence l?ch s?, kh?ng ?? ?i?u ki?n protocol

Hai l??t S1/S4 ?? ti?u th? holdout. Kh?ng rerun ho?c d?ng k?t qu? n?y ?? ch?nh h? th?ng. Xem [protocol audit](ctu_frozen_protocol_audit_2026-09-30.md) v? [receipt offline](../../results/evaluation_v1/ctu_network_frozen/remediation_audit_v1/receipt.json).

| ?i?u ki?n l?ch s? | Execution Accuracy theo script c? | Execution success theo flags c? | Syntax validity | Chi ph? ???c b?o c?o |
|---|---|---|---|---|
| Baseline E0 | 0/8 | 8/8 | Ch?a x?c minh ??ng ngh?a | $0.00438375 |
| v2 E3 | 2/8 | 3/8 | Ch?a x?c minh ??ng ngh?a | $0.01022375 |

`syntax_valid` trong script c? th?c ch?t ghi query th?c thi ???c; kh?ng ???c di?n gi?i l? ki?m tra c? ph?p ??c l?p. Auditor ch? ??c JSON, kh?ng replay scorer hay ch?y SQL.

## ??nh ch?nh t?ng case E3

| Case | Flags l?ch s? | Di?n gi?i gi?i h?n |
|---|---|---|
| 001, 002 | Kh?p k?t qu? | C? stored-value grounding; ch?a t?ch confound ?? ph?c t?p |
| 003, 008 | EXEC_ERROR | L?i schema; kh?ng ??i th?nh SYNTAX_ERROR |
| 004, 006, 007 | EMPTY_SQL | Kh?ng c? SQL final |
| 005 | RESULT_MISMATCH | SQL th?c thi ???c nh?ng k?t qu? kh?c gold |

Ch?nh l?ch 2 case kh?ng ch?ng minh remediation hay linker c?i thi?n accuracy. Claim causal/validated v? ?? ngh? tuning t? holdout ?? r?t l?i. Snapshot/case l?ch s? gi? nguy?n; kh?ng s?a artifact.

## Cost v? provenance

T?ng hai report l? $0.01460750; c?ng spend ?? ghi nh?n tr??c ?? $0.05047400 th?nh **lower bound $0.06508150**, kh?ng ph?i chi ph? th?c ??y ??. `cost_complete=false`, `cost_unknown=true`: thi?u usage trung gian v? retry policy. Kh?ng suy cost t? s? turn ho?c g?i Billing ?? b? evidence.

Thi?u implementation SHA, exact request bytes, response IDs, pre-run CI/cost lock v? winner lock. Hash receipt l? hash bytes t?i th?i ?i?m audit; kh?ng ch?ng minh provenance g?c. C?c con s? n?y ch? l? historical/exploratory findings, kh?ng ph?i frozen accuracy ???c nghi?m thu.

Artifact g?c: [baseline](../../results/evaluation_v1/ctu_network_frozen/baseline_e0/report.json), [E3](../../results/evaluation_v1/ctu_network_frozen/v2_e3/report.json). B?n b?o c?o tr??c remediation c? th? truy t?i commit `cf46fb4`. S1/S4 v?n closed.
