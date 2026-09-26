# R2 official-dev gate status

Public-dev research is closed. No further prompt, tool, or architecture tuning may use the eight public-dev cases.

## Locked public-dev decision

- Selected architecture: E0 one-shot.
- Public-dev v4 E0: 5/8, or 62.5% Execution Accuracy.
- E2 also reached 5/8 but lost the declared tie-break on API cost and model calls.
- E1 and E3 did not demonstrate an improvement.
- Usage-derived public-dev research cost: v1 `$0.0162844` + v2 `$0.0272104` + v3 `$0.0231008` + v4 `$0.0229036` = **`$0.0894992`**.
- The paid public-dev workflow is manual-only through `workflow_dispatch`.

## Next authorized gate

The next evaluation is exactly one E0 official-dev run over the existing eight cases in `evaluation/text_to_sql_benchmarks/dev/`, after all of the following are verified and frozen:

1. complete ThreatFox full export, CTU-13 Scenario 3, and OTRF APT29 Day 1 source bytes;
2. the official OTRF adapter against the real archive layout;
3. an independently reproducible three-source DuckDB snapshot with binary and logical-content hashes;
4. all existing dev gold SQL against that snapshot;
5. the actual one-shot E0 prompt and provider request contract.

Official-dev must not reuse the public pilot snapshot identity. `evaluation/dualsql_lite/SELECTED_CONFIG.lock` selects E0 but does not lock the future official snapshot or benchmark identity.

R1 remains 22/24 on dev v2. R1 frozen and R2 frozen have not been opened and remain sealed. Work stops for human review after the official-dev E0 result and error analysis.
