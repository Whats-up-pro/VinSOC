# B?o c?o Task 6 ? Demo VinSOC full E2E c? API th?t

**Ng?y th?c hi?n:** 2026-10-13 (Asia/Saigon)  
**Repository:** `Whats-up-pro/VinSOC`  
**Nh?nh:** `master`  
**Case c? ??nh:** `ctu_cross_708b66575657429a` / condition `E3`  
**K?t qu? ?i?u h?nh:** **Demo k? thu?t ho?n ch?nh, ?ang ch? ng??i duy?t** (`technical_complete_awaiting_human`)

## 1. T?m t?t cho qu?n l?

M?t l??t demo end-to-end th?t ?? ch?y tr?n chu?i tr?n GitHub Actions, d?ng OpenAI API ? m?i module c?n m? h?nh:

1. Routing g?i `gpt-4.1-mini` v? t?o native tool call `network_query`.
2. R2 schema linker g?i `gpt-5-mini` ba l?n, trong ?? hai l?n g?i c?ng c? tra gi? tr? th?t v? m?t l?n tr? linked schema.
3. R2 SQL generator g?i `gpt-5-mini` hai l?n. Candidate ??u d?ng `UNION ALL` v? b? semantic audit t? ch?i; candidate th? hai d?ng hai m?nh ?? `EXISTS` v? ???c ch?p nh?n.
4. SQL ch?y trong worker c? l?p tr?n DB CTU th?t, tr? m?t h?ng c? gi? tr? `459`.
5. Assessment g?i `gpt-4.1-mini`, tr?ch d?n ??ng hai evidence ID v? n?u k?t lu?n `459`.
6. Independent replay, schema validation, traceability v? execution scoring ??u ??t.
7. Human review v?n l? `awaiting_human`; h? th?ng kh?ng t? nh?p danh t?nh hay t? ph? duy?t.

L??t ho?n ch?nh d?ng **7 API calls**, gi? **$0.00739705**. T?ng chi ph? ?? x?c minh c?a to?n b? chu?i th? demo l? **$0.06115500 / $3.00**, c?n **$2.93884500**. ??y l? m?t fixed-case demo, kh?ng ???c t?nh l? calibration, evaluation 96 case hay pipeline 32 case ch?nh th?c.

## 2. M?c ngu?n v? CI

| M?c | SHA | N?i dung | CI |
|---|---|---|---|
| S?a semantic audit v? checkpoint 10 request | `0e85e637bbc5828c221f1f0d2dac0a91090c3c28` | Ch?n SQL `UNION ALL` sai ngh?a, fail-closed, m? checkpoint assessment | [38336323978](https://github.com/Whats-up-pro/VinSOC/actions/runs/38336323978) ? success |
| L?u run 9 v? t?ng R2 l?n 2.000 output token | `7c6e5b907934b8ce76f7f88d4dd9edd80834d9eb` | Kh?c ph?c ba ph?n h?i `finish_reason=length` li?n ti?p | [38337402304](https://github.com/Whats-up-pro/VinSOC/actions/runs/38337402304) ? success |
| ??ng b? commit t?i li?u m?i tr?n master | `42cb274` | G?i rehearsal/recovery ?? c? tr?n remote; ???c gi? nguy?n khi rebase | CI thu?c l?ch s? master |
| Th?m ch? ?? preflight-only tr?n cloud | `0d813371a713839e712bb36c2a2ca6a8fd60ebab` | Cho ph?p ch?ng minh `attempted=0` tr??c live run | [38337917138](https://github.com/Whats-up-pro/VinSOC/actions/runs/38337917138) ? success |

Commit n?n `3573496a165876f36116b2716ca737d17091aaf7` v?n l? t? ti?n. Kh?ng t?o branch, PR hay giao agent. Hai ZIP pin v? protected benchmark/gold/prompt/scorer/history kh?ng b? s?a.

## 3. Nh?t k? t?ng b??c

### B??c 1 ? X?c minh ?i?m ti?p t?c

L?nh ch?nh:

```powershell
git status --short --branch
git rev-parse HEAD
git rev-parse origin/master
git merge-base --is-ancestor 3573496a165876f36116b2716ca737d17091aaf7 HEAD
```

Nh?n x?t:

- `master` ban ??u tr?ng `origin/master` t?i `0e85e637...`.
- Commit n?n l? t? ti?n.
- Workspace c? nhi?u file untracked c?; ch? c?c file c?a Task 6 ???c stage.

K?t lu?n: ?i?m ti?p t?c h?p l?, kh?ng checkout ng??c.

### B??c 2 ? ??ng receipt c?a run 9 v? t?m nguy?n nh?n

C?c l?nh ch?nh:

```powershell
gh run download 38336761761 --repo Whats-up-pro/VinSOC
python <script ki?m case_record, cost_events v? finish_reason>
```

Nh?n x?t:

- Run 9 truy?n/nh?n 6 call th?t: routing 1, R2 5, assessment 0.
- Hai R2 call ??u tra `source_dataset` v? `protocol` th?nh c?ng.
- Ba ph?n h?i linker cu?i ??u r?ng, `finish_reason=length`, ??ng 1.000 output token.
- Kh?ng c? SQL, worker execution hay assessment; tr?ng th?i ???c gi? l? `technical_incomplete`.
- Chi ph? run 9: `$0.00810660`; l?y k? l?c ?? `$0.05375795`.

K?t lu?n: l?i n?m ? completion ceiling c?a linker, kh?ng n?m ? DB, API transport hay tool grounding.

Receipt: `results/evaluation_v1/text2sql_integration_v1/single_demo_full_e2e_9_20261013/`.

### B??c 3 ? TDD cho gi?i h?n R2 v? reconciliation run 10

Test ??:

```powershell
.\.venv\Scripts\python.exe -m pytest `
  tests/test_query_pipeline_contract.py::test_r2_completion_budget_allows_live_linker_to_finish_after_tool_calls `
  tests/test_query_pipeline_contract.py::test_budget_package_includes_single_demo_e3_ceiling `
  tests/test_query_cloud.py::test_tenth_demo_authorization_reconciles_nine_transmitted_attempts -q
```

K?t qu? ?? h?p l?: 3 failed v? contract v?n l? 1.000 token, c?n ti?n c? `$1.6572608`, v? `full-e2e-10` ch?a ???c ph?p.

Thay ??i:

- R2 `max_completion_tokens`: 1.000 ? 2.000.
- C?n demo E3: `$1.6572608` ? `$1.6732608`.
- Th?m canonical prior audit cho run 9 v? profile `full-e2e-10`.

Test xanh:

```text
3 passed in 0.35s
46 passed in 3.93s
```

K?t lu?n: t?ng token ri?ng cho R2, kh?ng s?a prompt, model, protected history hay s? call t?i ?a.

### B??c 4 ? Compile, preservation, commit v? CI m?c token

L?nh ch?nh:

```powershell
.\.venv\Scripts\python.exe -m compileall -q evaluation/finalization scripts/run_query_demo_cloud.py
.\.venv\Scripts\python.exe scripts/verify_query_preservation.py
git diff --check
git commit -m "fix: preserve linker completion budget"
git push origin master
gh run watch 38337402304 --repo Whats-up-pro/VinSOC --exit-status
```

Nh?n x?t CI `38337402304`:

- Python 3.11: 1.344 passed, 7 skipped; required offline 49 passed, 0 skipped; real-data 13 passed, 0 skipped.
- Python 3.12: c?ng s? l??ng.
- 13 DB g?c v? 120 gold queries ???c ki?m l?i.

K?t lu?n: m?c token ??t CI ??ng SHA `7c6e5b9...`.

### B??c 5 ? Preflight local fail-closed

L?nh ch?nh:

```powershell
.\.venv\Scripts\python.exe -m scripts.run_query_demo_cloud `
  --mode preflight --output-dir .tmp-query-demo-preflight-10
```

K?t qu?:

```json
{
  "status": "blocked",
  "client_created": false,
  "attempted": 0,
  "received": 0,
  "new_cost_ceiling_usd": 1.6732608
}
```

L? do: Windows local kh?ng c? runtime snapshot v?a restore v? kh?ng c? Linux `bubblewrap`, n?n gate tr? `FULL_LOCKED_INVENTORY_UNVERIFIED` v? `RUNTIME_CODE_CI_OR_ISOLATION_UNVERIFIED`.

K?t lu?n: gate fail-closed ??ng; kh?ng ph?t sinh API call hay chi ph?. C?n preflight-only tr?n ch?nh cloud runner.

### B??c 6 ? Th?m preflight-only cho workflow

TDD:

```powershell
.\.venv\Scripts\python.exe -m pytest `
  tests/test_query_cloud.py::test_demo_workflow_can_stop_after_cloud_preflight_without_api_calls -q
```

Test ??u ti?n ?? v? workflow ch?a c? `run_mode`. Sau khi th?m choice `preflight|live`, test ??t. Nh?m x?c minh:

```text
27 passed in 0.44s
protected_changed: []
external_model_calls: 0
```

Push ??u ti?n b? t? ch?i v? remote `master` c? commit m?i `42cb274`. C?c l?nh x? l?:

```powershell
git fetch origin master
git rebase origin/master
.\.venv\Scripts\python.exe -m pytest tests/test_query_cloud.py tests/test_query_pipeline_contract.py -q
.\.venv\Scripts\python.exe scripts/verify_query_preservation.py
git push origin master
```

K?t lu?n: gi? commit m?i h?n tr?n master, rebase s?ch v? push SHA `0d813371...`.

### B??c 7 ? CI release gate ??ng SHA cu?i

L?nh:

```powershell
gh run watch 38337917138 --repo Whats-up-pro/VinSOC --exit-status
```

K?t qu? tr?n c? Python 3.11 v? 3.12:

- Full suite: **1.345 passed, 7 skipped** m?i phi?n b?n.
- Required offline: **49 passed, 0 skipped** m?i phi?n b?n.
- Required real-data/isolation: **13 passed, 0 skipped** m?i phi?n b?n.
- 13 DB g?c x?c minh ??ng; 120/120 gold queries replay th?nh c?ng.

B?y skip ch? thu?c full suite chung; c?c job b?t bu?c c? 0 skip.

### B??c 8 ? Preflight-only tr?n cloud

L?nh ?i?u h?nh ?? d?ng; payload authorization ???c redacted kh?i b?o c?o:

```powershell
<authorization-json-redacted> | gh secret set VINSOC_QUERY_DEMO_AUTH_JSON --repo Whats-up-pro/VinSOC
gh workflow run query-demo-once.yml --repo Whats-up-pro/VinSOC `
  --ref master -f ci_run_id=38337917138 -f run_mode=preflight
gh run watch 38338323675 --repo Whats-up-pro/VinSOC --exit-status
```

K?t qu? run [38338323675](https://github.com/Whats-up-pro/VinSOC/actions/runs/38338323675):

- `authorized=true`, `status=preflight_pass`, `reasons=[]`.
- `attempted=0`, `received=0`, `client_created=false`.
- Role caps: routing 1, R2 8, assessment 1; t?i ?a 10 request.
- C?n ti?n m?i: `$1.6732608`.
- Chi ph?: `$0`.
- Artifact `11786265638`, digest `sha256:602cb765a5ee73a27e724c0d2f4b582a1e90028450b1ec48f29beab21e03264b`.

K?t lu?n: m?i gate ??t tr??c request tr? ph? ??u ti?n.

### B??c 9 ? Live full E2E c? API th?t

L?nh:

```powershell
gh workflow run query-demo-once.yml --repo Whats-up-pro/VinSOC `
  --ref master -f ci_run_id=38337917138 -f run_mode=live
gh run watch 38338493466 --repo Whats-up-pro/VinSOC --exit-status
gh secret delete VINSOC_QUERY_DEMO_AUTH_JSON --repo Whats-up-pro/VinSOC
gh run download 38338493466 --repo Whats-up-pro/VinSOC
```

Run: [38338493466](https://github.com/Whats-up-pro/VinSOC/actions/runs/38338493466)  
Artifact: `11785766818`  
Digest: `sha256:ed290e86e1342bc0c9bb5d45d1319094c90d477597015d75480fa92f97c52540`

K?t qu? module:

| # | Module/role | Model | H?nh vi | K?t qu? |
|---:|---|---|---|---|
| 1 | Routing | `gpt-4.1-mini-2025-04-14` | Native tool call `network_query` v?i nguy?n v?n c?u h?i | ??t |
| 2 | R2 linker | `gpt-5-mini-2025-08-07` | `value_search(source_dataset contains 5)` | T?m `ctu13_s5`, ??ng th?i c? witness `ctu13_s7` |
| 3 | R2 linker | `gpt-5-mini-2025-08-07` | `value_search(protocol exact TCP)` | T?m ??ng `TCP` |
| 4 | R2 linker | `gpt-5-mini-2025-08-07` | Tr? linked schema/constraints | ??t, 1 table v? 4 columns |
| 5 | R2 generator | `gpt-5-mini-2025-08-07` | Sinh hai count b?ng `UNION ALL` | B? semantic audit t? ch?i |
| 6 | R2 generator | `gpt-5-mini-2025-08-07` | Sinh m?t count v?i hai correlated `EXISTS` | ???c ch?p nh?n |
| 7 | Assessment | `gpt-4.1-mini-2025-04-14` | ??c typed result/evidence, t?o assessment | H?p l?, tr?ch d?n ?? evidence |

T?t c? 7 request ??u c? GitHub begin/end checkpoint, provider request ID, response ID, usage, latency v? cost.

### B??c 10 ? SQL, typed result v? ki?m ch?ng

SQL cu?i:

```sql
SELECT COUNT(DISTINCT dst_ip) AS distinct_dst_ips
FROM network_flows f
WHERE f.dst_ip IS NOT NULL
  AND EXISTS (
    SELECT 1 FROM network_flows s5
    WHERE s5.dst_ip = f.dst_ip
      AND s5.source_dataset = 'ctu13_s5'
      AND s5.protocol = 'TCP'
      AND s5.event_time > TIMESTAMP '2011-08-15 17:00:00'
  )
  AND EXISTS (
    SELECT 1 FROM network_flows s7
    WHERE s7.dst_ip = f.dst_ip
      AND s7.source_dataset = 'ctu13_s7'
      AND s7.protocol = 'TCP'
      AND s7.event_time > TIMESTAMP '2011-08-16 14:00:00'
  );
```

Typed result:

```json
{
  "columns": [{"name": "distinct_dst_ips", "type": "BIGINT"}],
  "rows": [[459]],
  "row_count": 1,
  "truncated": false
}
```

Ki?m ch?ng:

- `execution_success=true`.
- `execution_accurate=true`.
- `scoring_error_category=OK`.
- `independent_query_replay=true`.
- `schema_valid=true`, `traceability_valid=true`.
- Assessment `validation_passed=true`, kh?ng c? validation error.
- Hai evidence IDs: `ev_bf7ff9fc_2` cho execution/provenance v? `ev_03d85032_3` cho typed result.

K?t lu?n: c?u tr? l?i k? thu?t l? **459 distinct destination IPs xu?t hi?n trong c? hai t?p ?i?u ki?n S5 v? S7**.

## 4. Isolation worker

Kh?ng d?ng ri?ng tr??ng `isolation` do executor t? ghi ?? k?t lu?n. B?ng ch?ng ??c l?p ?? kh?a t?i:

`results/evaluation_v1/text2sql_integration_v1/offline_release_20261010/r2_independent_kernel_observation.json`

Quan s?t ngo?i worker qua `/proc` v? cgroup filesystem x?c nh?n:

- network namespace kh?c;
- environment ch? c? allowlist, kh?ng c? secret;
- ch? snapshot c?n thi?t ???c mount read-only;
- `memory.max=536870912`, `swap.max=0` cho to?n process group;
- `cpu.max=100000 100000`, affinity 1 CPU;
- timeout v? group kill ???c test trong required real-data suite.

CI `38337917138` ch?y l?i required real-data/isolation tr?n Python 3.11 v? 3.12: 13 passed, 0 skipped m?i phi?n b?n. Receipt executor c?a ch?nh demo c?ng kh?p backend `bubblewrap`, network unshared, DB read-only, 512 MiB, 1 CPU, timeout 10 gi?y.

## 5. Chi ph? v? usage

### L??t run 10

| Ch? s? | Gi? tr? |
|---|---:|
| Calls th?t | 7 |
| Input tokens | 12.067 |
| Output tokens | 2.689 |
| Cached tokens | 5.376 |
| Chi ph? l??t | `$0.00739705` |
| C?n preflight | `$1.67326080` |

### To?n b? l?ch s? demo trong allocation $3

| Ch? s? | Gi? tr? |
|---|---:|
| Provider calls ?? truy?n | 57 |
| Chi ph? ?? x?c minh | `$0.06115500` |
| S? d? | `$2.93884500` |
| Unknown exposure | `$0.00000000` |

Preflight-only kh?ng t?o SDK client v? c? chi ph? `$0`.

## 6. Gate ?? ??ng v? gate c?n m?

?? ??ng:

- R2 independent worker boundaries v? required real-data CI.
- Preflight selection/source/data/account/pricing/budget cho fixed demo run 10.
- Remote one-shot claim v? 7 begin/end checkpoints.
- Routing, linker, generator, semantic repair, isolated SQL execution, evidence, assessment.
- Execution accuracy v? independent replay cho fixed case.
- Authorization secret ?? x?a sau run.

C?n m?:

- Human review: `awaiting_human`, `human_decisions=[]`. Ng??i duy?t ph?i t? nh?p identity, decision, rationale v? UTC.
- `semantic_correctness_verified=false` cho prose policy; m?y kh?ng t? ch?ng nh?n di?n gi?i cu?i.
- Module diagnostic `value_grounding.predicates` b?o 0/6/5 d? witness precision l? 3/3 v? unsupported literal rate l? 0. ??y l? ch?nh l?ch bi?u di?n metric c?n xem ri?ng, kh?ng l?m thay ??i execution result 459.
- Calibration 24, evaluation 96 v? pipeline 32 ch?a c? artifacts th?t trong l??t n?y, n?n kh?ng ghi COMPLETE v? kh?ng c?ng b? score ch?nh th?c.

## 7. Nh?n ??nh chung

Task 6 ?? ??t m?c ti?u demo k? thu?t end-to-end c? API th?t. ?i?m m?nh nh?t c?a run l? semantic audit ?? ch?ng minh t?c d?ng th?c t?: candidate SQL ??u ti?n c? th? ch?y nh?ng tr? sai ngh?a; pipeline kh?ng ch?p nh?n, y?u c?u model s?a v? ch? th?c thi candidate ??ng. K?t qu? 459 ???c t?o t? DB th?t trong worker c? l?p, ?i qua typed evidence, independent replay v? assessment th?t.

R?i ro c?n l?i thu?c l?p qu?n tr? v? reporting metric, kh?ng thu?c ???ng ch?y k? thu?t c?a fixed demo: c?n ng??i th?t duy?t assessment, v? c?n ?i?u tra ch?nh l?ch metric value-grounding tr??c khi d?ng module score ?? b?o c?o ch?t l??ng m? h?nh. Kh?ng n?n suy r?ng k?t qu? m?t case n?y th?nh accuracy c?a calibration/evaluation/pipeline.
