# Network E2E — offline implementation delivered, live BLOCKED

Đã audit và tiếp tục implementation có sẵn theo `docs/superpowers/plans/2026-10-07-network-e2e-agent-a-directive.md`; không dựng lại pipeline hoặc chạy model. Đây là bàn giao checkpoint code và bằng chứng blocked, **không phải demo end-to-end hoàn tất**.

## Trạng thái nghiệm thu

| Mốc | Kết quả thực tế |
|---|---|
| 0 | Bắt đầu remote `58298ac5fa17f5a1d79f06b7274f446dde264422`; checkout cũ, `.env`, untracked và artifact lịch sử giữ nguyên. |
| 1 | Public `investigate()`, policy network-only, guarded SDK/ledger và CLI lên master `d704da16f754fa4c96753e493db3e8b38aca7665`. CI [37561432731](https://github.com/Whats-up-pro/VinSOC/actions/runs/37561432731): 1027 passed, 1 skipped trên Python 3.11/3.12. |
| 2 — code | Lock builder/validator, full evidence/facts, immutable receipts, full human packet và linked offline HTML lên master `8736ab7801bf9fcf15da0003220097e0cbb14d58`; tree `e7607b89806abf403632755b1253175ba252f108`. CI [37569993136](https://github.com/Whats-up-pro/VinSOC/actions/runs/37569993136): 1070 passed, 2 skipped mỗi Python; 3.12 có 1821 warnings. |
| 2 — release | BLOCKED: qualified CTU S5/S7 snapshot chưa có tại môi trường thực hiện. Local rehearsal exit1 `LOCAL_SNAPSHOT_REQUIRED`. Không tạo release lock giả từ hash lịch sử. |
| 3 | BLOCKED: private gates chưa có. Actual preflight exit1 `missing_ledger_or_gates`; client=false, attempted0, response0. Không live/smoke/retry. |
| 4 | Bàn giao [JSON](blocked_handoff.json) và [HTML](blocked_handoff.html) actual blocked cùng runbook. Human review chưa chạy. Renderer/HTML parity kiểm được; mở bằng browser chưa đạt vì `BROWSER_BINARY_UNAVAILABLE`, không claim đã visual QA. |

Hai skip CI gồm đầu vào snapshot local bị ignore; không thay thế snapshot acceptance. Botnet/Normal chưa có arguments/assessment/model/usage thực ở task này, nên không có bảng kết quả model để công bố. Artifact Actions ID/digest: N/A — bằng chứng này commit trong repo, không upload Actions artifact.

## Những gì đã khép ở code

Canonical CLI gọi public lifecycle, native network tool với arguments model và continuation ID giữ nguyên. Policy không đưa mock endpoint pivots/CTU label/seed vào initial prompt. Structured count/IP/port/protocol/time facts, parent links và source pairs/aggregates được kiểm độc lập trước human approval. Payload không bị cắt âm thầm; bounded retrieval và reference sampling có metadata, không tự gọi là full population.

Transport journal ghi attempted/reserve trước SDK, usage/cost trước parse; model/usage/payload/budget lỗi giữ partial/unknown. Một canonical window ngoài checkout, exclusive durable claim xuyên process; mở/preflight read-only, owner mới được gửi request. Trần task không thể tăng bằng sửa gate/CLI lên hơn $0.25. Legacy CLI không bypass claimed/consumed window.

Existing technical/review outputs không bị overwrite khi chạy lại. Assessment transport failure giữ tool trace, native arguments, evidence và lifecycle thực đã thu thập. Human xem full network packet; offline review kiểm cả hai scenario và accounting/identity/facts, không tin truthy flags. Reviewed HTML ghép quyết định bằng hash/run/implementation identity và giữ JSON technical gốc nguyên vẹn.

Review độc lập tìm 7 Important issues ở các boundary trên; một vòng sửa đã xử lý. Regression RED tổng hợp 7 failures; linked-review RED riêng được quan sát. Full human-packet test được viết sau wrapper: chỉ claim GREEN verification, không claim test-first RED cho riêng thay đổi UI đó.

## Kiểm chứng đã chạy

- Focused network guard/policy/lifecycle/contract/runner/renderer: **111 passed, 1 deselected**.
- Full local trước final review: **1061 passed, 1 skipped, 1 failed**, fail duy nhất là thiếu snapshot thật.
- Full offline trên final code, bỏ riêng required-snapshot acceptance: **1070 passed, 1 skipped, 1 deselected**, 1821 warnings trên Python 3.12. Không gọi đây là full local acceptance PASS.
- Required-snapshot test trên `8736ab7`: exit1, `LOCAL_SNAPSHOT_REQUIRED`.
- Changed-file `py_compile`, `git diff --check`, staged allowlist và credential-pattern checks: đạt. CLI/renderer/contract `--help`: đạt.
- Snapshot qualification: exit1, `snapshot_or_contract_qualification_failed`. Preflight-only: exit1, `missing_ledger_or_gates`, 0 calls/client false. Renderer actual preflight/blocked JSON: exit0, PARTIAL, 0 scenario/request.
- Historical R1/R2 results/locks, frozen policies và cross-domain candidates không có diff. Không mở frozen, chạy R1/R2 suites, ThreatFox/OTRF hoặc paid cross-domain.

Files implementation đổi: `agent/network_investigation_policy.py`, `agent/orchestrator.py`, `agent/provider.py`; `evaluation/finalization/live_window.py`, `network_contract.py`; `scripts/demo_ctu_network_public_model_driven.py`, `render_network_e2e_report.py`; `skills/network_skill.py`, `vinsoc_data/network_source.py`; sáu `tests/test_*network_e2e*.py` / `test_finalization_live_window.py`; và `docs/VinSOC_Verified_Demo_Runbook_2026-10-05.md`. Test helper filenames cụ thể có trong git diff; không stage `.env`/DB/source bytes.

## Phạm vi chi phí và dữ liệu

Task mới: attempted0, response0, actual provider/model/usage=null, known new API cost $0, không unresolved request mới. Allocation cũ chưa reconcile, account/project/credit/spend headroom/current pricing chưa xác minh; remaining budget/allocation=null, không suy ra còn tiền hoặc tổng chi phí bằng0. $0.0864 là application reserve **có điều kiện** của request envelope tại giá đã pin, không phải preflight PASS ở đây hoặc invoice/provider hard cap.

Expected snapshot logical hash/counts nằm trong JSON ở trường `expected_snapshot_contract_not_observed`. Actual binary/logical/source count/scenario hash đều chưa đo được; không sao chép expected vào actual. Lock chưa tạo. Snapshot/provenance và account gates phải có thật trước live.

## Tiếp tục đúng gate trên laptop

Dùng commands PowerShell tại mục 8 của [runbook](../../../../docs/VinSOC_Verified_Demo_Runbook_2026-10-05.md): kiểm actual snapshot → required real-snapshot rehearsal → tạo lock một lần → commit/push → CI đúng SHA mới → private account/pricing/reconciliation gates thật → preflight PASS → một live invocation. Không dùng CI của `8736ab7` để chạy một SHA mới chứa lock mà chưa qua CI. Không copy `.env`, không xóa/reset claim, không dùng fixture cho live, không tự approve. Sau live giữ partial/awaiting-human nếu cần, rồi review/render offline; matched R2/cross-domain/frozen vẫn là task riêng.

## Quyết định trong execution (đầy đủ, gồm giới hạn review)

| Quyết định | Lý do và hệ quả nếu sai |
|---|---|
| Dùng milestone ledger thay task-start/task-done | Chỉ thị dùng Mốc; vẫn giữ command/output và atomic commits. Mất chuẩn hóa helper, không mất bằng chứng lệnh. |
| Push bằng connector Git-data, expected-SHA, không force | CLI thiếu credential; tree local/remote đối chiếu trùng. Sai identity có thể tạo remote mismatch, được chặn bằng tree/lease. |
| Local snapshot test fail khi thiếu, chỉ CI skip | Giữ gate thật, không đổi fixture thành acceptance. Full local không xanh khi thiếu input là blocker có chủ đích. |
| Sửa NetworkSkill/network_source sau failing coverage test | Metadata truncation mất ở boundary; không đổi threshold/query/gold. Rủi ro thêm provenance fields cho consumers cũ. |
| Review cả current-tree diff trước commit | HEAD-only bỏ Mốc2 chưa commit. Commit/tree cuối và tests xác nhận đúng source sau review. |
| UI GREEN-only, không bịa RED | Test full packet chạy sau wrapper; bằng chứng TDD yếu hơn cho riêng UI, behavior đã test. |
| Actual snapshot/SDK/pricing/account/live quality chưa phán | Inputs không có; release/live tiếp tục blocked, không suy từ synthetic tests. |
| Không re-audit historical metrics trong task | Preserve result tree; lỗi lịch sử, nếu có, vẫn cần task khác. |
| Giữ legacy Python helpers nhận injected client | Caller kiểm soát transport; canonical CLI được gate. Custom callers cần guard riêng. |
| Không chống owner xóa ledger/đổi home/sửa runtime/gates giả | Ngoài normal application trust; owner có thể cố ý bypass local control. |
| Không claim cryptographic receipt authentication | Structure/facts/accounting/link hashes được kiểm; entire fabricated packet không được xác thực nguồn server. |
| Truncation khai báo, recompute có thể reject bảo thủ | Không broaden analytics/query khi chưa có scenario thật; legitimate bounded group có thể fail an toàn. |
| Sampling không làm mẫu số aggregate | Independent recompute dùng DB; source samples không chứng minh từng record toàn population. |
| Không thẩm định lại khoa học của DERIVED analytics | Giữ production analytics và parent checks; analytic limitations cũ còn nguyên. |
| Prose/causal/verdict do human review | Machine không certify prose; analyst vẫn có thể bỏ sót claim sai. |
| Các malformed/empty/no/multiple/extra-tool paths fail/partial | Tighten schema/deferred statuses; lỗi chưa biết vẫn cần regression mới. |
| BENIGN arbitrary callers không đại diện canonical neutral runner | Không đổi legacy triage; custom context có thể close sớm. |
| Modified kwargs/client/contract thuộc custom caller | Không claim guard code đã bị viết lại; caller có thể bypass transport của chính họ. |
| Raw exception chain bình thường được suppress | Không mở rộng speculative metadata-secret rules; allowlisted official metadata còn là trust assumption. |
| Không thêm SDK-close lifecycle refactor | Chưa có close path gây mất receipt; resource cleanup là maintenance riêng. |
| Không claim Windows/directory-fsync/symlink/storage-failure đã kiểm | Atomic replace/exclusive claim có tests; unusual filesystem failure vẫn là giới hạn. |
| Không thêm convenience aggregate flags | Canonical status/validation/accounting đủ; downstream phải đọc đúng schema. |
| Không broad refactor/import/type/style hay legacy clipping | Tránh mở rộng scope; maintenance debt vẫn còn. |

Deferred minors: renderer của legacy/preflight thiếu `cost_unknown` có thể ghi “No” mặc định (handoff này ghi scope/unknown allocation rõ); error helper guard nhận dict headers thay vì mọi Mapping nên `Retry-After` có thể null. Không suy diễn field thiếu. Không sửa các minor này trong final fix pass.

## Hash artifact

`blocked_handoff.json`: `e10cccfd04c722c5ab1550ed19dc0f984a20fa52597f0b12700bc66ea9d57905`.

`blocked_handoff.html`: `cded7473ea677b8df868359b946874a8f5bd05e48f3f85bdd1c8b89cf3d72c6e`.
