# VinSOC: giao diện chạy pipeline thật

User requires entering a request in the UI, executing real model calls in the
necessary modules, following the complete pipeline and reviewing the result.
Execution is authorized directly on master, inline, without branches/PRs/agents.
The existing $3 cumulative query allocation remains the financial limit.

## Design

Streamlit controls the existing Linux GitHub Actions runner. The Windows UI
does not instantiate a model SDK or execute model SQL. The worker retains its
network namespace, secret-free environment, read-only DB mount and resource caps.

New page: select scope and case, enter the exact original question, run preflight,
inspect budget/gates, explicitly start a live run, follow actual job steps and
durable request checkpoints, download artifacts, inspect all eight stages and
submit an actual human review. Saved examples remain a separate presentation view.

Catalog covers the four fixed demos, all 32 pipeline cases, 24 calibration cases
and 96 evaluation cases. Protected cases/questions/scorers do not change. Formal
scope execution stays blocked by missing 48 calibration records/selection lock
and insufficient full-run reserve. UI coverage does not imply model completion.

## Cloud release

Each new demo uses a fresh `liveui-<nonce>` execution ID; consumed windows remain
consumed. A workflow request binds scope, case/question, source SHA, CI ID, UTC,
the existing $3 cap and explicit live consent. GitHub workflow_dispatch is the
operator-authorized channel; model keys remain repository secrets.

The runner independently reconciles the ten prior demo receipts and the actual
remaining3 run, then all append-only UI allocation claims/end receipts. An open
claim, failed checkpoint, unpaired transmission or unknown usage blocks further
paid requests. Serialized Actions concurrency prevents concurrent allocation use.

Preflight runs on exact original DBs with current model documents and exact-SHA
CI; attempted=received=0, client_created=false. Live validates again, claims an
immutable remote window, and uses public investigate_query via run_live.
Response/usage precede parsing; private journals and partial artifacts survive.

All pricing bounds and role caps stay in the existing release contract. No lower
reserve, new fake calibration records or altered source/data authorization.

## Progress/results

UI displays real Actions steps and immutable begin/end request events. It never
uses time-based simulated progress. Successful and failed runs retain identities,
SQL, typed result, evidence, raw/accepted assessment, verification and cost IDs.
The output of a new run never silently falls back to an old successful example.
Human approval requires independent technical gates and manually entered identity,
decision, rationale and UTC. No automatic approval.

## Acceptance

Targeted tests, AppTest, compile, preservation and full/required Linux CI must pass
on Python 3.11/3.12. Real acceptance uses the browser UI to preflight and start one
fresh authorized demo, collects actual responses/cost and reopens its real result.
If it fails, preserve that result; do not retry to obtain a prettier outcome.
Formal suites stay NOT_RUN until actual records and gates exist.
