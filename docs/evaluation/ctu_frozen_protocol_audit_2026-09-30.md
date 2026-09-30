# CTU frozen protocol audit, 2026-09-30

The frozen attempts committed at `cf46fb4abec295e43a31e9c026e7908e214fe43b`
are **historical exploratory evidence, not protocol-eligible frozen results**.
Keep every existing result JSON unchanged. The S1/S4 holdout has been consumed;
do not rerun it or use its outcomes to tune a new development condition. No
replacement source or model has been selected.

## Checkpoint and interruption

The approved offline checkpoint `92e20d589e00ace33f896b4d24279181c51230a8`
passed local full pytest (614 tests) and [CI Python 3.11/3.12](https://github.com/Whats-up-pro/VinSOC/actions/runs/36667345032).
Its gate resolved seven explicit development source references, recognized case
008 as requiring no source literal, passed two negatives, and replayed 27 v1
lookups without model calls. This checkpoint did not contain a paid v2 runner,
E0′ dev result, selected winner, or frozen-run authorization.

When execution resumed, master and origin/master were both
`cf46fb4abec295e43a31e9c026e7908e214fe43b`. Intermediate commit `d21a030`
replaced the v2 tools API, while leaving `agents.py`, `metrics.py` and
`offline_gate.py` dependent on the removed `V2DatabaseTools` class.
[Full CI at d21a030 failed](https://github.com/Whats-up-pro/VinSOC/actions/runs/36669985928),
and [full CI at cf46fb4 failed during collection](https://github.com/Whats-up-pro/VinSOC/actions/runs/36680054156).
The added v2 tests also required an untracked local snapshot absent on CI.

## Unmet gates

| Required gate | Evidence available |
| --- | --- |
| Pre-run dev comparison, locked winner and v2 SERIES.lock | No v2 SERIES.lock or selected dev configuration exists in the evaluated tree. |
| Full CI on exact implementation SHA before paid calls | The offline SHA's CI does not cover the later tools/scripts. cf46fb4 CI failed. |
| Zero retry and conservative cost preflight | Both scripts construct `OpenAI(...)` without `max_retries=0`; no suite preflight is enforced. |
| Provider response identity and usage before parsing | Neither attempt records response IDs. Baseline case metadata records the actual pinned model; v2 case metadata records no actual response model. |
| Snapshot, question/gold, scorer, prompt/schema and implementation identity | Aggregate reports contain a snapshot path, not the required hashes or implementation SHA. Script scoring does not establish identity with the locked scorer. |
| Complete usage-derived cost | v2 records 66 role turns, but eight case usage entries contain final-return telemetry only; intermediate charged responses are not accumulated. |

The v2 tool implementation used by those scripts also exposes
`dataset_provenance` alongside `network_flows`. It therefore differs from the
approved snapshot tool boundary and the source-metadata adapter at 92e20d5.
Restoring the offline adapter import does not retrospectively repair the
evaluated implementation or make the frozen attempts eligible.

The historical summary lists v2 Syntax Valid as 8/8, while its JSON report lists
3/8. This discrepancy is recorded without changing results or rescoring cases.
The reported Execution Accuracy remains baseline 0/8 and v2 2/8 as descriptive
numbers attached to those attempts, with no generalization or improvement claim
under the approved protocol.

## Cost and immutable evidence

The two aggregate reports state $0.00438375 and $0.01022375, totaling
$0.01460750. Adding the prior recorded $0.050474 gives **$0.06508150 as a
recorded lower bound**, not complete actual spend. v2 intermediate usage and any
SDK retries are unknown. This recovery work made zero model calls and cost $0.

[CONSUMED.lock](../../evaluation/ctu_network_frozen/CONSUMED.lock) records SHA-256
digests for all 18 historical JSON Git blobs at cf46fb4, separate Windows
checkout digests, and the eligibility blockers. The two byte digests differ
because Git normalizes CRLF; no evidence file was changed by this audit. Neither
the artifacts nor existing VERSION.lock, benchmark, gold or scorer were edited.

## Recovery verification

- Preserve the `CTUDatabaseTools` behavior used by the historical attempts.
  Restore the metadata-based offline API in `source_tools.py` and re-export its
  original class name for the existing offline controller and gate.
- Use synthetic DuckDB fixtures for unit tests, leaving source snapshots intact.
- Block both historical frozen scripts before client construction, including
  when a different output directory is supplied. Missing or invalid consumption
  metadata also closes the gate.

Paid continuation is blocked by the consumed holdout and missing pre-run
identity/CI/cost evidence. Do not create retrospective locks to imply those
gates passed, dispatch a replacement frozen run, or silently change its source.

## Đính chính offline sau recovery

[Auditor receipt](../../results/evaluation_v1/ctu_network_frozen/remediation_audit_v1/receipt.json) xác nhận E0 EX 0/8 và E3 EX 2/8; E3 có 3 execution success theo flags cũ, 2 `EXEC_ERROR`, 3 `EMPTY_SQL`. Field `syntax_valid` cũ có semantics thực thi, không chứng minh syntax validity độc lập. Không replay SQL/scorer trong audit.

[Remediation status](r2_remediation_status.md) ghi các checks hiện tại. Hash mới xác nhận bytes hiện tại, không bù pre-run provenance. Cost lịch sử vẫn incomplete; S1/S4 consumed/closed. Phạm vi phiên Tasks 1-7 vẫn zero API calls dù remote thêm plan live tương lai.
