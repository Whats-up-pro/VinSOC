# VinSOC — authorized execution of the three remaining fixed demos

The user authorized real API calls and implementation on 2026-10-13. This change
adds `selection_mode=remaining3` to the existing guarded GitHub workflow. The
original fixed case and all historical artifacts remain preserved.

The selected original questions are fixed in `demo_selection.json`, in file order:

1. `ctu_cross_66b8e92a76c3359b`: UDP destination IPs present in S5 but absent in S7.
2. `ctu_cross_3f659571f998adb0`: protocol counts where both byte fields are NULL.
3. `ctu_cross_bce6d3679ade4cd6`: protocol average outbound bytes above the S7 average.

Each case has one independent E3 invocation through public `investigate_query`,
with routing, the shared TextToSQLService, the isolated read-only SqlExecutor,
model assessment and evaluator-only scoring. No calibration selection or official
32-case score is asserted by this demo authorization. Human review remains manual.

## Money and scope

Ten authentic prior query demo receipts total $0.06115500. The original allocation
remains $3.00; the reconciled remaining amount before these calls is $2.93884500.
No additional allocation was inferred from full authority.

Official model documents were fetched and parsed on 2026-10-13:

| Model | Context ceiling | Input / cached / output per million tokens |
|---|---:|---|
| gpt-5-mini-2025-08-07 | 400000 | $0.25 / $0.025 / $2.00 |
| gpt-4.1-mini-2025-04-14 | 1047576 | $0.40 / $0.10 / $1.60 |

Sources: https://developers.openai.com/api/docs/models/gpt-5-mini.md and
https://developers.openai.com/api/docs/models/gpt-4.1-mini.md.

Each case reserves the entire documented input context, uncached, with existing
output caps. Caps are routing 1, R2 8, assessment 1: at most 10 requests per case.
The conservative full-case bound is $1.6732608. Three unconditional bounds sum
to $5.0197824, which exceeds the remaining allocation. Therefore execution is
conditional and sequential, not a claim that all worst-case reserves fit $3.

Before EACH case, preflight checks its complete bound against the remaining
allocation AFTER actual usage from all preceding cases has been reconciled.
The shared aggregate cap stays $3. If headroom is insufficient, or cost/transport
is unresolved, later paid cases remain not run and a blocker receipt is saved.
There is no smaller framing estimate, reduced cap, hidden retry or larger budget.

## One-shot and durability

The batch execution ID is `mentor-remaining3-20261013`. An immutable remote batch
claim prevents reopening the execution from another host or workflow rerun.
Remote matching refs also reject any of the three cases already claimed under
another execution. Each case has its own immutable claim and begin/end request
checkpoints. A terminal or unknown-cost case blocks later transmissions.

Raw response and usage are saved before parse by the existing RunJournal. The
workflow preserves canonical journals for artifact upload even after failure or
cancellation. These private journals must never be committed to public Git.

## Verification before live

New boundary tests were observed failing before implementation, then passing.
The existing official-client, source/data mutation, ledger, CPU/memory/timeout,
selection, provenance and human-review gates are preserved. A new exact-SHA CI
and cloud preflight-only receipt are required before live dispatch.

No paid calls were made while preparing this change. Actual workflow IDs, usage,
costs, per-case outputs, CI and viewer are recorded in the subsequent handoff.

## Original archive transport blocker

Cloud preflight `38366545085` on `89409ea` stopped in source restoration before
the guarded runner step. The official Google Drive endpoint returned a quota
page rather than the ZIP, and the existing checksum gate rejected it. No SDK
client, model request or paid claim was created.

The source bytes are now restored from an immutable public mirror revision:
`HAL-9001/spider-databases@4a01bbac6520cd35b216db9e1724e5e1ada60aa4`.
The publisher's LFS object hash matches the original locked archive SHA-256
`00636695dabed6b5f4b8328a16b13e069a2f16591d5efcce57660669c85b121b`.
The original validator checks that full archive and all pinned members before
materialization; a mismatch still fails. The original source manifest, DB
binaries, two delivered ZIPs and gold remain unchanged. This is transport of
the same original archive, not a reconstruction or new source identity.

Mirror provenance: https://huggingface.co/datasets/HAL-9001/spider-databases.
