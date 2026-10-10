# Command log ? single-case VinSOC demo

Secrets and raw provider payloads are redacted. Repeated `gh run view` polling used the same command and is listed once.

| Step | Command(s) | Result / comment |
|---|---|---|
| 1. Verify baseline | `git fetch origin master`; `git merge-base HEAD origin/master`; `python scripts/verify_query_preservation.py` | Local and remote master matched. Base `3573496a?` remained an ancestor; 3,640 protected files and both ZIP hashes were unchanged. |
| 2. TDD for bounded demo | `python -m pytest tests/test_query_pipeline_contract.py::test_single_demo_reserves_one_complete_e3_case_without_selection_gate tests/test_query_cli_viewer.py::test_demo_inventory_is_one_fixed_selection_with_exact_original_question -q` | Red: demo selected 96 cases and lacked a fixed-selection gate. Green after implementation. |
| 3. Targeted offline verification | `python -m pytest tests/test_query_pipeline_contract.py tests/test_query_acceptance_preflight.py tests/test_query_cli_viewer.py tests/test_query_journal_persistence.py tests/test_network_query_lifecycle.py tests/test_provider_routing.py -q` | 47 passed for the first milestone. |
| 4. Local full-suite diagnosis | `$env:VINSOC_LOCAL_SNAPSHOT=<locked CTU DB>; python -m pytest -q -x` | Application tests progressed; Windows alone could not create a symlink (`WinError 1314`) and Unix-only SOC tests require `fcntl`. No gate was weakened. |
| 5. First milestone | `git commit -m "feat: add bounded single-case query demo"`; `git push origin master` | Commit `2f854926?`; CI 38033990632 passed. |
| 6. Clean-host data rehearsal | `git -c core.autocrlf=false clone ...`; `python -m scripts.restore_query_data_bundle ...`; `python -m scripts.validate_original_query_data --restore-sources ...` | Restored 13 exact DB binaries and replayed 120 gold queries, zero model calls. Windows then correctly blocked live SQL because bubblewrap/cgroup isolation is Linux-only. |
| 7. Cloud durability TDD | `python -m pytest tests/test_query_cloud.py tests/test_query_journal_persistence.py ... -q`; `python -m compileall -q ...` | Remote claim-before-client and per-request begin/end checkpoint tests passed. |
| 8. Cloud milestone | `git commit -m "feat: run query demo once on isolated cloud worker"`; `git push origin master` | Commit `5e8e4ff?`; CI 38037320747 passed 5/5 jobs. |
| 9. Budget authorization secret | `gh secret set VINSOC_QUERY_DEMO_AUTH_JSON --repo Whats-up-pro/VinSOC` | Stored fixed case, E3 condition, and exact 3 USD cap. Secret value was not printed. |
| 10. One paid dispatch | `gh workflow run query-demo-once.yml --repo Whats-up-pro/VinSOC --ref master -f ci_run_id=38037320747` | Run 38037640751. One immutable remote window claim; no retry. |
| 11. Observe/checkpoint | `git ls-remote --tags origin "vinsoc-query-demo-*"`; `gh run view 38037640751 ...` | Four requests had paired begin/end tags; workflow and artifact upload succeeded. |
| 12. Download/audit | `gh run download 38037640751 ...`; offline JSON audit | Actual outcome: 4 responses, 4 valid usage records, cost 0.00133865 USD; `TOOL_LIMIT`, no final SQL, technical incomplete. |
