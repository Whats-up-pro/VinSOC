# VinSOC — phần tiếp tục đã thực hiện, 07/10/2026

Đây là bàn giao implementation và bằng chứng đã chạy, không phải một kế hoạch mới.
Initial remote: `408d75f5e97653d8927497a84599588f1ed73ce8`.
Implementation cuối: `6b724c257dd9e62e5871d36ae64c28f427b6024f`.
[CI implementation](https://github.com/Whats-up-pro/VinSOC/actions/runs/37575048307)
đã SUCCESS; cả `test (3.11)` và `test (3.12)` chạy full suite thành công.
Evidence commit chứa tài liệu này có SHA riêng; khi chạy live phải dùng CI của
chính HEAD đang checkout, không sao chép SHA implementation cũ vào gates.

## Đã làm thật

| Phần | Bằng chứng / trạng thái |
|---|---|
| Snapshot network | Build hai lần từ đúng source CTU S5/S7 đã kiểm SHA; 243.906 flows, distinct source pairs 243.906, S5 129.831 và S7 114.075 |
| Logical identity | Hai build cùng `42c8e0a62441295cc5d95329a65dc22409c37de5b26a1e37dd56fbf0164a758c` |
| Lock E2E | Pin binary `91a13ab149453ca6db6246ada3d7a21708537a12865a01e6475df18dd9a9eac3`; fresh remote clone kiểm `valid=true` |
| Rehearsal | Public orchestrator + NetworkSkill + DuckDB thật; model và reviewer synthetic, không gọi nó là live |
| Preflight thật | `preflight_failed / missing_ledger_or_gates`, 0 request, client=false; safe env check: key source missing |
| Reporting module | Schema linking/grounding TP/FP/FN, coverage, missing stage, witness NA, SQL generation, safety, cost unknown và lỗi từng case |
| Statistics | Denominator planned, micro/macro, difficulty/features n, Wilson diagnostic và deterministic database/family cluster bootstrap; paired E0/E3 không loại case fail |
| Cổng chạy cross-domain | SDK thật, không retry, cap 1.000, canonical consumed ledger, reserve trước call, charge trước parse/scoring, checkpoint partial và revalidate identity trước client |
| Tests | 39 focused passed; full local Python 3.12: 1.110 passed, 1 skipped, 1.888 warnings; rehearsal DB thật đã chạy, không dùng skip thay gate |
| Preservation | 3.269 file benchmark/lock/artifact lịch sử được hash lại, 0 thay đổi; không mở gold/snapshot frozen |

Module mới: `evaluation/r2_cross_domain_v1/{reporting,statistics,release,live}.py`
và `scripts/run_r2_cross_domain.py`. Các source/controller/scorer được benchmark
lock lịch sử pin vẫn giữ nguyên bytes; live adapter riêng dùng lại prompts/tools/
grounding/safety đã pin, không sửa controller synthetic để giả danh live.

Review độc lập tìm được 2 Important và 1 Minor. Một lượt sửa cuối đã khóa đúng
đường dẫn benchmark được tiêu thụ, tách rejected SQL probes khỏi final-SQL safety,
và đếm NO_FINAL_SQL dù lỗi chính là provider. Đồng thời chặn request-contract
failure bằng terminal latch và không cho 0-request case có `usage_valid=true`.
Năm regression tests tái hiện RED rồi GREEN. Reviewer không được dispatch lại.

## Phần live còn thiếu — không được chế kết quả

Không có OpenAI key, account/pricing/reconciliation gates hoặc canonical ledger
của laptop trong runtime này. Attempted/received mới **0/0**, chi phí inference
mới **$0**, không có model score mới, không có human approval. Không copy key từ
chat vào file, không tạo ledger/window khác để bỏ qua lượt đã consumed.

Cross-domain đã có 24 calibration + 96 evaluation (93 families), 8 external
evaluation DB / 7 domains trong inventory. Những DB ignored đó chưa có ở runtime
này: validator thật dừng `SNAPSHOT_CHECKSUM_MISMATCH`. Không tuyên bố đã replay
120 gold mới. Preflight thật: blocked, tối đa 672 requests cho matched E0/E3,
verified full cost ceiling `null`, paid authorization false. Tests của adapter
dùng fake SDK boundary và fixtures; chúng không phải kết quả model/generalization.

## Thao tác tiếp ngay tại laptop có key — network E2E đã được cho phép

1. Dùng checkout sạch đúng `master` mới nhất; `git pull --ff-only origin master`
   chỉ khi có thể fast-forward mà không làm mất working changes. Nếu checkout cũ
   bẩn, giữ nguyên nó và dùng fresh clone; tham chiếu `.env` cũ bằng absolute path.
   Không reset/clean, không stage `.env`, CSV hoặc DuckDB. Kiểm CI SUCCESS của đúng
   `git rev-parse HEAD` trên cả 3.11/3.12 trước khi đi tiếp.

2. Giải nén deliverable `VinSOC_Qualified_Network_Snapshot_20261007.zip` được gửi
   kèm vào thư mục ignored `data/ctu_network_public/`. Dùng file
   `ctu_e2e_20261007.duckdb`. **Không chép đè lock trong repo.** Binary cũ trên
   laptop dù cùng logical rows vẫn không được thay binary đã pin.

3. Trong PowerShell đặt đường dẫn tới file thật; các lệnh này không ghi `.env`:

~~~powershell
$Snapshot = (Resolve-Path 'data/ctu_network_public/ctu_e2e_20261007.duckdb').Path
$EnvFile = 'D:\VINUNI_AI2026\Phase3_VinSOC\.env'
$Window = Join-Path $HOME '.vinsoc/live-windows/network-finalization-20261006'
$Ledger = Join-Path $Window 'ledger.json'
$Gates = Join-Path $Window 'gates.json'
python -c "import sys; from pathlib import Path; from scripts.check_env import check_env,load_env; sys.exit(check_env(dotenv_env=load_env(Path(sys.argv[1]))))" $EnvFile
python -c "import json,sys; from pathlib import Path; from evaluation.finalization.network_contract import validate_lock; r=validate_lock(Path(sys.argv[1]),json.loads(Path('evaluation/finalization/NETWORK_E2E_v1.lock.json').read_text(encoding='utf-8'))); print(json.dumps(r)); sys.exit(0 if r['valid'] else 1)" $Snapshot
$env:VINSOC_LOCAL_SNAPSHOT = $Snapshot
python -m pytest -q tests/test_network_e2e_lifecycle.py -k local_verified_snapshot_two_scenario_rehearsal
~~~

$EnvFile phải trỏ file hiện hữu, không chứa giá trị key trong command. Lệnh
check ở trên đọc đúng file được truyền, chỉ in source/present/missing; không
copy/ghi đè key. Thiếu key hoặc có xung đột thì preflight không được qua. `$Gates` là đường dẫn tới private gates hiện hữu của operator;
nếu tên khác thì đặt đúng path. Thiếu gates thật thì dừng trước API.

4. Private gates phải ghi **HEAD/CI thực tế**, account verified + allocation còn
   lại, pricing official mới kiểm, receipt hashes/chi phí đã phát sinh và
   `unresolved_cost_unknown=false`. Schema/điều kiện nằm ở
   `evaluation/finalization/live_window.py::_validate_gates`. Không dùng fixture
   test, balance cũ hay auto-set cờ verified để thay bằng chứng. Ngân sách network
   tối đa $0.25 và không vượt allocation thực còn lại. Giữ đúng window ở trên;
   không tự xóa claim/ledger hoặc viết ledger rỗng nếu đã consumed.

5. Chạy preflight không gọi model, output namespace mới:

~~~powershell
python -m scripts.demo_ctu_network_public_model_driven --e2e --preflight-only --snapshot $Snapshot --output .vinsoc/network-e2e-resume/preflight-check.json --env-file $EnvFile --ledger $Ledger --gates $Gates --budget-usd 0.25
~~~

Chỉ nếu exit 0 / `preflight_pass=true` mới thực hiện bước 6. Nếu snapshot/key/
account/CI/budget hoặc consumed-window fail, giữ artifact và báo đúng blocker;
không tạo request thử key, không chuyển sang diagnostic hoặc Actions fresh window.

6. **Một invocation live**, hai scenarios botnet/normal, tối đa 4 requests;
   model `gpt-4.1-mini-2025-04-14`, temperature 0, cap 1.000, retry 0. Public
   orchestrator phải nhận model-native arguments, chạy network tool/DB thật,
   model assessment thật; fail thì giữ partial, không retry/fallback:

~~~powershell
python -m scripts.demo_ctu_network_public_model_driven --e2e --snapshot $Snapshot --output .vinsoc/network-e2e-resume/technical-live.json --env-file $EnvFile --ledger $Ledger --gates $Gates --budget-usd 0.25 --review-mode deferred
python -m scripts.render_network_e2e_report --receipt .vinsoc/network-e2e-resume/technical-live.json --output .vinsoc/network-e2e-resume/technical-live.html
~~~

7. Technical pass vẫn là `technical_complete_awaiting_human`. Người thật xem
   evidence/observations/hypotheses/limitations và quyết định; agent không approve
   thay. Nếu technical chưa pass thì không gọi review để đổi thành success.

~~~powershell
python -m scripts.demo_ctu_network_public_model_driven --review-receipt .vinsoc/network-e2e-resume/technical-live.json --output .vinsoc/network-e2e-resume/human-review.json
python -m scripts.render_network_e2e_report --receipt .vinsoc/network-e2e-resume/technical-live.json --review-receipt .vinsoc/network-e2e-resume/human-review.json --output .vinsoc/network-e2e-resume/reviewed.html
~~~

8. Khi có output thực, kiểm attempted/received/valid usage, model/request IDs,
   token/cost/unknown exposure, row evidence, contract/implementation hashes và
   review thật. Commit/push **chỉ JSON/HTML public-safe và receipt** sau sanitize;
   không commit gates, ledger, `.env`, raw SDK response/source bytes/binary DB.
   CI exact evidence SHA phải xanh. Failure/partial là kết quả cần giữ nguyên.

## Cổng cross-domain — hiện chỉ chạy offline

~~~powershell
python -m scripts.run_r2_cross_domain --preflight-only --output .vinsoc/cross-domain-resume/preflight.json
~~~

Exit 1 khi thiếu locked external snapshots/private evidence là đúng, không tạo
client. Muốn mở matched E0/E3 cần data validator pass, account/pricing và token
bound thực, ngân sách riêng đủ **toàn bộ 672 worst-case requests**, paid scope
được cấp riêng. Demo permission không mở quyền này. Không giảm denominator, đổi
model/cap, giả fixture thành external data hoặc lấy chi phí trung bình 8 case làm
cận trên. R1 22/24 và R2 CTU E3 7/8 lịch sử giữ nguyên, chưa có điểm 96-case mới.

Receipt kiểm chứng tại `completion_receipt.json`; trạng thái preflight/data gate
thật tại `offline_status.json`. Frozen/ThreatFox/OTRF official vẫn không được mở.
