# R2 remediation metric contract

Identity m?i: `dualsql_lite_ctu_gpt5_v2_remediation_v1`; kh?ng ph?i lock c?a m?t paid run. Scorer duy nh?t: `evaluation.text_to_sql.evaluate_sql_case`, portable SHA-256 ?? kh?a trong `evaluation/ctu_network_public/VERSION.lock` l? `bd3d9da9e78bbcab560cefabae93a8c5592757a53375bdd31b7ee613d0c66fdf`. Verifier ghi implementation SHA th?c t?; kh?ng g?n SHA t??ng lai.

Execution Accuracy = s? final SQL kh?p gold / to?n b? case kh?a, k? c? failure. Syntax Validity d?ng DuckDB parser v? y?u c?u ??ng m?t statement; unknown column c? th? syntax valid nh?ng execution fail. Multi-statement ???c parser gate lo?i tr??c execution. Safety, execution success, EX l? c?c flags ri?ng t? evaluator.

Comparator hi?n t?i gi? th? t? select-list values, b? kh?c bi?t alias. `ordered_rows`, `scalar`, `boolean` gi? row order; `unordered_rows` v? `multiset_rows` b? order nh?ng gi? duplicate multiplicity. Float canonicalization l?m tr?n 9 ch? s?; kh?ng th?m tolerance hay t? sort ordered rows.

Final SQL v? probe d?ng c?ng snapshot-only read-only boundary, c?m writes, external readers v? internal/provenance tables. Gold ch? d?ng sau inference, kh?ng truy?n sang linker/generator.

Diagnostic literal grounding v? column precision kh?ng thay EX, kh?ng v?o selection lock hay input inference. Catalog c? cap; kh?ng t?m th?y trong catalog ch?a ?? ch?ng minh kh?ng t?n t?i trong snapshot. Kh?ng d?ng metric n?y ?? tuning t? frozen.

Report fixture c? raw counts/rates v? lu?n `official_eligible=false`; kh?ng bi?n fixture th?nh accuracy c?a model th?t. Frozen l?ch s? E3 EX2/8, execution3/8 theo flags c?; syntax validity ??ng ngh?a ch?a x?c minh. Cost/provenance l?ch s? incomplete.
